/* State, form behavior and live preview.
   M7 Editor + M8 Rendering & Export Integration.
   No backend models, migrations, or AI calls.
*/

(function (global) {
  'use strict';

  const copy = value =>
    JSON.parse(JSON.stringify(value));

  const SECTIONS = [
    ['personal', 'Personal'],
    ['summary', 'Summary'],
    ['experience', 'Experience'],
    ['education', 'Education'],
    ['projects', 'Projects'],
    ['skills', 'Skills'],
    ['certifications', 'Certifications'],
    ['achievements', 'Achievements'],
    ['languages', 'Languages']
  ];

  const PERSONAL_KEYS = [
    'full_name',
    'email',
    'phone',
    'location',
    'linkedin',
    'github',
    'portfolio'
  ];

  const DEFAULT_ROW = {
    experience: {
      company: '',
      job_title: '',
      location: '',
      start_date: '',
      end_date: '',
      is_current: false,
      highlights: []
    },

    education: {
      degree: '',
      institution: '',
      field_of_study: '',
      start_date: '',
      end_date: '',
      grade: ''
    },

    projects: {
      name: '',
      description: '',
      technologies: [],
      url: '',
      highlights: []
    },
    certifications: {name: '', issuer: '', date: '', url: ''},
    languages: {name: '', proficiency: ''}
  };

  // --------------------------------
  // HELPER FUNCTIONS
  // --------------------------------

  function emptyLike(v) {
    if (Array.isArray(v)) {
      return [];
    }

    if (v && typeof v === 'object') {
      return Object.fromEntries(
        Object.entries(v).map(
          ([k, val]) => [k, emptyLike(val)]
        )
      );
    }

    if (v === null) {
      return null;
    }

    if (typeof v === 'boolean') {
      return false;
    }

    if (typeof v === 'number') {
      return 0;
    }

    return '';
  }

  function fieldValue(value) {
    if (Array.isArray(value)) {
      return value
        .map(x => x ?? '')
        .join('\n');
    }

    if (
      value === null ||
      value === undefined
    ) {
      return '';
    }

    if (typeof value === 'object') {
      return JSON.stringify(value);
    }

    return String(value);
  }

  function setScalar(original, typed) {
    if (Array.isArray(original)) {
      return typed
        .split(/\r?\n/)
        .map(x => x.trim())
        .filter(Boolean);
    }

    if (typeof original === 'number') {
      const n = Number(typed);

      return (
        typed.trim() === '' ||
        !Number.isFinite(n)
      )
        ? original
        : n;
    }

    if (typeof original === 'boolean') {
      return typed === 'true';
    }

    return typed;
  }

  function snapshot(v) {
    return JSON.stringify(v);
  }

  // --------------------------------
  // ALPINE EDITOR COMPONENT
  // --------------------------------

  function cvEditor() {
    return {

      id: '',
      cv: {},
      cvSchema: null,
      loaded: null,
      initial: '',

      active: 'personal',
      sections: SECTIONS,

      authRequired: false,
      loading: true,
      saving: false,

      // M8 states
      m8Busy: false,
      m8PreviewOpen: false,
      m8PreviewUrl: null,
      livePreviewLoading: false,
      livePreviewError: '',
      livePreviewZoom: 'fit',
      _livePreview: null,

      notice: '',
      error: '',

      username: '',
      password: '',

      conflict: false,

      // --------------------------------
      // CHECK UNSAVED CHANGES
      // --------------------------------

      get dirty() {
        return (
          !!this.loaded &&
          snapshot(this.cv) !== this.initial
        );
      },

      get activeLabel() {
        return (
          SECTIONS.find(
            ([key]) => key === this.active
          )?.[1] || ''
        );
      },

      // --------------------------------
      // INITIALIZE EDITOR
      // --------------------------------

      init() {
        const schemaNode = global.document.getElementById('m7-cv-schema');
        if (schemaNode) {
          const schema = JSON.parse(schemaNode.textContent);
          if (schema && typeof schema === 'object') this.cvSchema = schema;
        }
        const requestedSection = (global.location?.hash || '').slice(1);
        if (SECTIONS.some(([key]) => key === requestedSection)) {
          this.active = requestedSection;
        }
        this.id = JSON.parse(
          global.document
            .getElementById('m7-config')
            .textContent
        );

        global.addEventListener(
          'beforeunload',
          event => {
            if (this.dirty) {
              event.preventDefault();
              event.returnValue = '';
            }
          }
        );

        this.$watch?.('cv', () => this._livePreview?.update());
        this.reload();
      },

      startLivePreview() {
        if (!this.$refs || !global.M7LivePreview) return;
        this._livePreview?.destroy();
        this.livePreviewLoading = true;
        this.livePreviewError = '';
        this._livePreview = global.M7LivePreview.create({
          frame: this.$refs.liveFrame,
          viewport: this.$refs.liveViewport,
          stage: this.$refs.liveStage,
          panel: this.$refs.livePanel,
          toolbar: this.$refs.liveToolbar,
          initialZoom: this.livePreviewZoom,
          getCV: () => this.cv,
          request: () => this.m8Request('preview/'),
          onReady: () => {
            this.livePreviewLoading = false;
            this._livePreview?.scrollToSection(this.active);
          },
          onError: error => {
            this.livePreviewLoading = false;
            this.livePreviewError = error.message || 'Could not load the CV template.';
            if (error.status === 401) this.authRequired = true;
          }
        });
        this._livePreview.load();
      },

      setLivePreviewZoom(zoom) {
        if (!['fit', 1, 1.25].includes(zoom)) return;
        this.livePreviewZoom = zoom;
        this._livePreview?.setZoom(zoom);
      },

      selectSection(section) {
        if (!SECTIONS.some(([key]) => key === section)) return;
        this.active = section;
        this._livePreview?.scrollToSection(section);
      },

      destroy() {
        this._livePreview?.destroy();
        this.closeM8Preview();
      },

      // --------------------------------
      // LOAD CV FROM M2
      // --------------------------------

      async reload(force = false) {
        if (
          !force &&
          this.dirty &&
          !global.confirm(
            'Discard your unsaved edits and reload from server?'
          )
        ) {
          return;
        }

        this.loading = true;
        this.error = '';
        this.notice = '';
        this.conflict = false;

        try {
          const loaded = await global.M7Api.load(
            this.id
          );

          this.loaded = loaded;

          // Preserve unknown JSON fields
          this.cv = copy(loaded.document);

          this.initial = snapshot(this.cv);

          this.authRequired = false;
          this.$nextTick?.(() => this.startLivePreview());

        } catch (e) {
          this.authRequired = e.status === 401;
          this.error = e.message;
          if ([401, 403, 404].includes(e.status)) {
            this.loaded = null;
            this.cv = {};
            this.initial = '';
            this._livePreview?.destroy();
            this.closeM8Preview();
          }

        } finally {
          this.loading = false;
        }
      },

      // --------------------------------
      // LOGIN USING M1
      // --------------------------------

      async signIn() {
        this.error = '';
        this.loading = true;

        try {
          await global.M7Api.login(
            this.username,
            this.password
          );

          this.password = '';

          await this.reload(true);

        } catch (e) {
          this.error = e.message;
          this.loading = false;
        }
      },

      // --------------------------------
      // SAVE CV TO M2
      // --------------------------------

      async save() {
        if (
          !this.dirty ||
          this.saving ||
          this.conflict
        ) {
          return;
        }

        this.saving = true;
        this.error = '';
        this.notice = '';

        try {
          const result = await global.M7Api.save(
            this.id,
            this.loaded,
            copy(this.cv)
          );

          this.loaded = result;
          this.cv = copy(result.document);
          this.initial = snapshot(this.cv);

          this.notice = 'CV saved successfully.';

        } catch (e) {
          this.conflict =
            e.status === 409 ||
            e.code === 'version_conflict';

          this.authRequired = e.status === 401;

          this.error = this.conflict
            ? (
              'Another edit was saved first. ' +
              'Download your draft, then reload ' +
              'the latest version.'
            )
            : e.message;

        } finally {
          this.saving = false;
        }
      },

      // =================================================
      // M8 — CV RENDERING AND EXPORT
      // =================================================

      // --------------------------------
      // CHECK WHETHER M8 IS READY
      // --------------------------------

      ensureM8Ready() {
        this.error = '';

        if (
          this.authRequired ||
          !this.loaded
        ) {
          this.error =
            'Sign in and load your CV first.';

          return false;
        }

        if (
          this.saving ||
          this.loading ||
          this.m8Busy
        ) {
          return false;
        }

        if (this.conflict) {
          this.error =
            'Resolve the version conflict before previewing or exporting.';

          return false;
        }

        if (this.dirty) {
          this.error =
            'Save your changes before previewing or exporting. M8 uses the saved CV.';

          return false;
        }

        return true;
      },

      // --------------------------------
      // M8 AUTHENTICATED API REQUEST
      // --------------------------------

      async m8Request(action, method = 'GET') {

        // Use JWT stored by existing M7 API
        const token =
          global.sessionStorage.getItem('cv_access') ||
          global.sessionStorage.getItem('access') ||
          global.sessionStorage.getItem('access_token');

        if (!token) {
          const error = new Error(
            'Please sign in again to access M8.'
          );

          error.status = 401;

          throw error;
        }

        const url =
          `/api/cvs/${encodeURIComponent(this.id)}/${action}`;

        const transport = global.M1Session ? global.M1Session.request : global.fetch;
        const response = await transport(
          url,
          {
            method,

            headers: {
              Authorization: `Bearer ${token}`
            },

            credentials: 'same-origin',

            cache: 'no-store'
          }
        );

        if (!response.ok) {

          let message =
            `M8 request failed (HTTP ${response.status}).`;

          try {
            const body = await response.json();

            const detail =
              body.detail ||
              body.message ||
              body.error;

            if (typeof detail === 'string') {
              message = detail;

            } else if (
              detail &&
              typeof detail === 'object'
            ) {
              message = JSON.stringify(detail);
            }

          } catch (_) {
            // Keep original HTTP error
          }

          const error = new Error(message);

          error.status = response.status;

          throw error;
        }

        return response;
      },

      // --------------------------------
      // M8 HTML PREVIEW
      // --------------------------------

      async previewM8() {

        if (!this.ensureM8Ready()) {
          return;
        }

        this.m8Busy = true;
        this.notice = '';

        try {

          const response = await this.m8Request(
            'preview/',
            'GET'
          );

          const markup = await response.text();

          const url = URL.createObjectURL(
            new Blob(
              [markup],
              {
                type: 'text/html;charset=utf-8'
              }
            )
          );

          // Close previous preview
          this.closeM8Preview();

          this.m8PreviewUrl = url;

          this.m8PreviewOpen = true;

          this.notice =
            'Rendered preview loaded from M8.';

        } catch (error) {

          if (error.status === 401) {
            this.authRequired = true;
          }

          this.error = error.message;

        } finally {
          this.m8Busy = false;
        }
      },

      // --------------------------------
      // CLOSE M8 PREVIEW
      // --------------------------------

      closeM8Preview() {

        this.m8PreviewOpen = false;

        if (this.m8PreviewUrl) {

          URL.revokeObjectURL(
            this.m8PreviewUrl
          );

          this.m8PreviewUrl = null;
        }
      },

      // --------------------------------
      // M8 PDF / DOCX DOWNLOAD
      // --------------------------------

      async downloadM8(format) {

        if (!['pdf', 'docx'].includes(format)) {
          return;
        }

        if (!this.ensureM8Ready()) {
          return;
        }

        this.m8Busy = true;
        this.notice = '';

        try {

          const response = await this.m8Request(
            `export/${format}/`,
            'POST'
          );

          const contents = await response.blob();

          const url = URL.createObjectURL(
            contents
          );

          const anchor =
            global.document.createElement('a');

          anchor.href = url;

          anchor.download =
            `cv-${this.id}.${format}`;

          global.document.body.appendChild(
            anchor
          );

          anchor.click();

          anchor.remove();

          global.setTimeout(
            () => URL.revokeObjectURL(url),
            60000
          );

          this.notice =
            `${format.toUpperCase()} exported successfully via M8.`;

        } catch (error) {

          if (error.status === 401) {
            this.authRequired = true;
          }

          this.error = error.message;

        } finally {
          this.m8Busy = false;
        }
      },

      // =================================================
      // M7 — PERSONAL INFORMATION
      // =================================================

      personalKeys() {

        const val = this.cv.personal;

        return [
          ...new Set([
            ...PERSONAL_KEYS,

            ...Object.keys(
              val &&
              typeof val === 'object'
                ? val
                : {}
            )
          ])
        ];
      },

      personalValue(key) {
        return fieldValue(
          this.cv.personal?.[key]
        );
      },

      setPersonal(key, value) {

        if (
          !this.cv.personal ||
          typeof this.cv.personal !== 'object' ||
          Array.isArray(this.cv.personal)
        ) {
          this.cv.personal = {};
        }

        for (const required of PERSONAL_KEYS) {

          if (
            !Object.prototype.hasOwnProperty.call(
              this.cv.personal,
              required
            )
          ) {
            this.cv.personal[required] = null;
          }
        }

        this.cv.personal[key] = setScalar(
          this.cv.personal[key],
          value
        );
      },

      // =================================================
      // M7 — PROFESSIONAL SUMMARY
      // =================================================

      setSummary(value) {

        this.cv.summary = setScalar(
          this.cv.summary,
          value
        );
      },

      // =================================================
      // M7 — DYNAMIC CV SECTIONS
      // =================================================

      list(section) {

        return Array.isArray(this.cv[section])
          ? this.cv[section]
          : [];
      },

      isList(section) {

        return (
          this.cv[section] == null ||
          Array.isArray(this.cv[section])
        );
      },

      isMap(section) {

        const x = this.cv[section];

        return (
          x &&
          typeof x === 'object' &&
          !Array.isArray(x)
        );
      },

      rowFields(row) {

        return (
          row &&
          typeof row === 'object' &&
          !Array.isArray(row)
        )
          ? Object.keys(row)
          : [];
      },

      isRow(row) {

        return (
          row !== null &&
          typeof row === 'object' &&
          !Array.isArray(row)
        );
      },

      isEditableValue(v) {

        return (
          v === null ||
          typeof v !== 'object' ||
          Array.isArray(v)
        );
      },

      value: fieldValue,

      isMultiline(key, v) {

        return (
          Array.isArray(v) ||
          /description|responsibilities|summary|details|achievement|bullet/i.test(
            key
          )
        );
      },

      isDateField(key) {
        return ['date', 'start_date', 'end_date'].includes(key);
      },

      rowChoices(section, field) {
        return this.cvSchema?.properties?.[section]?.items?.properties?.[field]?.enum || [];
      },

      listLimit(section) {
        return this.cvSchema?.properties?.[section]?.maxItems ?? Infinity;
      },

      // --------------------------------
      // ADD SECTION ENTRY
      // --------------------------------

      add(section) {
        if (this.list(section).length >= this.listLimit(section)) return;

        if (this.cv[section] == null) {
          this.cv[section] = [];
        }

        if (!Array.isArray(this.cv[section])) {
          return;
        }

        const sample = this.cv[section].find(
          x => x !== null && x !== undefined
        );

        this.cv[section].push(
          sample !== undefined
            ? emptyLike(sample)
            : DEFAULT_ROW[section]
              ? copy(DEFAULT_ROW[section])
              : ''
        );
      },

      // --------------------------------
      // REMOVE SECTION ENTRY
      // --------------------------------

      remove(section, index) {

        this.cv[section].splice(
          index,
          1
        );
      },

      // --------------------------------
      // MOVE SECTION ENTRY
      // --------------------------------

      move(section, index, delta) {

        const list = this.cv[section];

        const next = index + delta;

        if (
          !Array.isArray(list) ||
          next < 0 ||
          next >= list.length
        ) {
          return;
        }

        [
          list[index],
          list[next]
        ] = [
          list[next],
          list[index]
        ];
      },

      // --------------------------------
      // UPDATE SECTION ENTRY
      // --------------------------------

      setRow(section, index, key, value) {

        const row = this.cv[section][index];

        if (key === null) {

          this.cv[section][index] = setScalar(
            row,
            value
          );

        } else {

          row[key] = setScalar(
            row[key],
            value
          );
        }
      },

      // --------------------------------
      // UPDATE DICTIONARY SECTION
      // --------------------------------

      setMapValue(section, key, value) {

        this.cv[section][key] = setScalar(
          this.cv[section][key],
          value
        );
      },

      // --------------------------------
      // UPDATE PLAIN TEXT SECTION
      // --------------------------------

      setPlain(section, value) {

        this.cv[section] = setScalar(
          this.cv[section],
          value
        );
      },

      // =================================================
      // M7 — LIVE CONTENT PREVIEW
      // =================================================

      short(value) {

        if (value == null) {
          return '';
        }

        if (Array.isArray(value)) {

          return value
            .map(v => this.short(v))
            .filter(Boolean)
            .join(' • ');
        }

        if (typeof value === 'object') {

          return Object.values(value)
            .map(v => this.short(v))
            .filter(Boolean)
            .join(' • ');
        }

        return String(value);
      },

      previewRows(section) {

        const val = this.cv[section];

        if (val == null) {
          return [];
        }

        if (Array.isArray(val)) {

          return val
            .map(x => this.short(x))
            .filter(Boolean);
        }

        if (typeof val === 'object') {

          return Object.entries(val).map(
            ([k, v]) => `${k}: ${this.short(v)}`
          );
        }

        return val
          ? [String(val)]
          : [];
      },

      // =================================================
      // M7 — EXPORT UNSAVED JSON DRAFT
      // =================================================

      exportDraft() {

        const blob = new Blob(
          [
            JSON.stringify(
              this.cv,
              null,
              2
            )
          ],
          {
            type: 'application/json'
          }
        );

        const href = URL.createObjectURL(
          blob
        );

        const link =
          global.document.createElement('a');

        link.href = href;

        link.download =
          `cv-${this.id}-unsaved.json`;

        link.click();

        setTimeout(
          () => URL.revokeObjectURL(href),
          1000
        );
      }
    };
  }

  // --------------------------------
  // EXPOSE EDITOR GLOBALLY
  // --------------------------------

  global.M7Editor = {
    cvEditor,
    fieldValue,
    emptyLike,
    setScalar
  };

  // --------------------------------
  // SUPPORT JAVASCRIPT UNIT TESTING
  // --------------------------------

  if (
    typeof module !== 'undefined' &&
    module.exports
  ) {
    module.exports = global.M7Editor;
  }

  // --------------------------------
  // REGISTER WITH ALPINE.JS
  // --------------------------------

  if (global.document) {

    global.document.addEventListener(
      'alpine:init',
      () => {

        global.Alpine.data(
          'cvEditor',
          cvEditor
        );
      }
    );
  }

})(
  typeof window !== 'undefined'
    ? window
    : globalThis
);
