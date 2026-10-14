/* M7 browser adapter: the ONLY place that knows M1 and M2 HTTP contracts. */

(function (global) {
  'use strict';

  const DOCUMENT_FIELDS = [
    'cv_data',
    'content',
    'cv_json',
    'structured_data',
    'document',
    'data'
  ];

  const SECTIONS = [
    'personal',
    'summary',
    'skills',
    'education',
    'experience',
    'projects',
    'certifications',
    'achievements',
    'languages'
  ];

  function hasSectionKeys(obj) {
    return !!(
      obj &&
      typeof obj === 'object' &&
      !Array.isArray(obj) &&
      SECTIONS.some(k =>
        Object.prototype.hasOwnProperty.call(obj, k)
      )
    );
  }

  function isObject(x) {
    return !!x && typeof x === 'object' && !Array.isArray(x);
  }

  function normalizeResponse(payload) {
    if (!isObject(payload)) {
      throw new Error('M2 returned an invalid CV response.');
    }

    // Supported:
    // {data:{id, cv_data, version}}
    // {cv:{...}}
    // {id, content,...}

    let resource =
      isObject(payload.data) && !hasSectionKeys(payload.data)
        ? payload.data
        : payload;

    if (isObject(resource.cv) && !hasSectionKeys(resource)) {
      resource = resource.cv;
    }

    if (!isObject(resource)) {
      throw new Error('Cannot locate CV resource in response.');
    }

    let field = DOCUMENT_FIELDS.find(k =>
      hasSectionKeys(resource[k])
    );

    const document = field
      ? resource[field]
      : hasSectionKeys(resource)
        ? resource
        : null;

    if (!document) {
      throw new Error(
        'Cannot locate CV JSON. Check M2 adapter in api.js.'
      );
    }

    if (!field) {
      field = null;
    }

    const version =
      resource.version ??
      resource.current_version ??
      resource.version_number ??
      resource.revision ??
      payload.version ??
      payload.current_version ??
      payload.version_number ??
      payload.revision ??
      null;

    return {
      document,
      field,
      version,
      id: resource.id ?? payload.id ?? null
    };
  }

  function buildPatchBody(loaded, document) {
    // M2 keeps the source-of-truth.
    // Adjust these two field names here if its
    // existing PATCH serializer uses a different contract.

    const documentField = loaded.field || 'cv_data';

    if (
      loaded.version === null ||
      loaded.version === undefined
    ) {
      throw new Error(
        'CV version was not returned by M2. ' +
        'Set the correct version field in api.js.'
      );
    }

    return {
      [documentField]: document,
      expected_version: loaded.version
    };
  }

  function getCookie(name) {
    if (typeof document === 'undefined') {
      return '';
    }

    return document.cookie
      .split(';')
      .map(p => p.trim())
      .find(p => p.startsWith(name + '='))
      ?.slice(name.length + 1) || '';
  }

  function token() {
    if (typeof sessionStorage === 'undefined') {
      return null;
    }

    return (
      sessionStorage.getItem('cv_access') ||
      sessionStorage.getItem('access') ||
      sessionStorage.getItem('access_token')
    );
  }

  function validationMessages(details, path = '') {
    if (typeof details === 'string') return [path ? `${path}: ${details}` : details];
    if (Array.isArray(details)) return details.flatMap(item => validationMessages(item, path));
    if (!isObject(details)) return [];
    if (typeof details.path === 'string' && typeof details.message === 'string') {
      return [`${details.path.replaceAll('/', ' → ')}: ${details.message}`];
    }
    return Object.entries(details).flatMap(([key, value]) =>
      validationMessages(value, [path, key].filter(Boolean).join(' → ')));
  }

  async function request(url, method = 'GET', payload) {
    const access = token();

    const headers = {
      Accept: 'application/json'
    };

    if (payload !== undefined) {
      headers['Content-Type'] = 'application/json';
    }

    if (access) {
      headers.Authorization = `Bearer ${access}`;
    }

    const csrf = getCookie('csrftoken');

    if (csrf && method !== 'GET') {
      headers['X-CSRFToken'] = decodeURIComponent(csrf);
    }

    let response;

    try {
      response = await fetch(url, {
        method,
        credentials: 'same-origin',
        headers,
        ...(
          payload === undefined
            ? {}
            : { body: JSON.stringify(payload) }
        )
      });
    } catch (_) {
      throw Object.assign(
        new Error('Network error. Check your connection.'),
        { status: 0 }
      );
    }

    const contentType =
      response.headers.get('content-type') || '';

    const body = contentType.includes('json')
      ? await response.json()
      : null;

    if (!response.ok) {
      const code =
        body?.error?.code ||
        body?.code ||
        '';

      const details =
        body?.error?.details ||
        body?.details ||
        body;

      const text =
        body?.error?.message ||
        body?.message ||
        body?.detail ||
        (
          response.status === 409
            ? 'CV changed elsewhere.'
            : `Request failed (${response.status}).`
        );

      const messages = response.status === 400 ? validationMessages(details).slice(0, 5) : [];
      const error = new Error(messages.length ? messages.join(' · ') : String(text));

      Object.assign(error, {
        status: response.status,
        code,
        details
      });

      throw error;
    }

    return body;
  }

  const api = {
    load: async id => {
      return normalizeResponse(
        await request(
          `/api/cvs/${encodeURIComponent(id)}/`
        )
      );
    },

    save: async (id, loaded, cv) => {
      await request(
        `/api/cvs/${encodeURIComponent(id)}/`,
        'PATCH',
        buildPatchBody(loaded, cv)
      );

      // Reload to get the latest version and canonical JSON.
      return api.load(id);
    },

    login: async (email, password) => {

    const response = await request(
        '/api/auth/login/',
        'POST',
        {
            email: email.trim(),
            password: password
        }
    );

    const access =
        response?.access ??
        response?.data?.access ??
        response?.tokens?.access;

    if (!access) {
        throw new Error(
            'Login successful, but access token was not returned.'
        );
    }

    sessionStorage.setItem(
        'cv_access',
        access
    );

    return access;
    },

    logout: () => {
      sessionStorage.removeItem('cv_access');
    }
  };

  global.M7Api = {
    ...api,
    normalizeResponse,
    buildPatchBody,
    validationMessages
  };

  if (
    typeof module !== 'undefined' &&
    module.exports
  ) {
    module.exports = global.M7Api;
  }

})(
  typeof window !== 'undefined'
    ? window
    : globalThis
);
