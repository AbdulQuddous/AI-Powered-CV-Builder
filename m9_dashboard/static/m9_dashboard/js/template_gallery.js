/* M9 presentation. Public metadata uses M3; all private writes use versioned M2. */
(function (global) {
  'use strict';
  const pageURL = (state, page = 1) => {
    const query = new URLSearchParams({page: String(page), page_size: '12'});
    for (const key of ['category', 'search', 'career_level', 'role']) if (state[key]) query.set(key, state[key]);
    return '/api/templates/?' + query;
  };
  function switchPayload(cv, template) {
    if (!Number.isSafeInteger(cv.version) || cv.version < 1) throw new Error('Reload this CV before switching templates.');
    return {template_id: template.id, expected_version: cv.version};
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {pageURL, switchPayload};
  if (!global.document) return;
  const $ = id => global.document.getElementById(id);
  const state = {category: '', search: '', career_level: '', role: '', page: 0, next: null,
    generation: 0, busy: false, selected: null, cv: null, previewGeneration: 0, useGeneration: 0};
  const query = new URLSearchParams(global.location.search);
  const privateCV = query.get('cv_id');
  let searchTimer, previewController;
  let authIdentity = global.M1Session?.identity();
  const personal = () => $('previewData').value;
  const signedIn = () => Boolean(global.M1Session?.accessToken());
  async function request(url, options = {}, isPrivate = false) {
    const response = await (isPrivate ? global.M1Session.request(url, options) : global.fetch(url, options));
    if (!response.ok) {
      let body = {}; try { body = await response.json(); } catch (_) { /* HTTP status is enough. */ }
      const message = response.status === 409 ? 'This CV changed elsewhere. Reload the page to review its latest version before switching.'
        : response.status === 401 ? 'Sign in to your workspace to continue.'
        : response.status === 404 ? 'This CV or template is unavailable.'
        : body.detail || body.error?.message || 'Could not complete the request. Please retry.';
      throw Object.assign(new Error(message), {status: response.status});
    }
    return response;
  }
  function add(parent, tag, className, text) {
    const node = document.createElement(tag); node.className = className || '';
    if (text !== undefined) node.textContent = text;
    parent.appendChild(node); return node;
  }
  function card(template) {
    const article = add($('templateGrid'), 'article', 'template-card');
    article.dataset.templateId = template.id;
    const shell = add(article, 'div', 'thumbnail-shell');
    const preview = add(shell, 'button', 'thumbnail-button');
    preview.type = 'button'; preview.setAttribute('aria-label', `Preview ${template.name}`);
    const img = add(preview, 'img'); img.src = template.preview_url || ''; img.alt = `${template.name} CV, populated with fictional comparison content`;
    img.loading = 'lazy'; img.decoding = 'async'; img.width = 594; img.height = 840;
    img.addEventListener('error', () => { img.hidden = true; add(preview, 'span', '', 'Image unavailable. Open the full preview.'); }, {once: true});
    preview.addEventListener('click', () => openPreview(template));
    const info = add(article, 'div', 'card-info'), heading = add(info, 'div', 'card-heading');
    add(heading, 'h2', '', template.name);
    if (template.ats_compatible) add(heading, 'span', 'ats-badge', 'ATS-oriented');
    add(info, 'p', 'card-category', template.category_label + ' · ' + template.layout_family.replaceAll('_', ' '));
    const actions = add(info, 'div', 'card-actions');
    const expand = add(actions, 'button', 'outline-button', 'Preview'); expand.type = 'button';
    expand.addEventListener('click', () => openPreview(template));
    const use = add(actions, 'button', 'primary-button', 'Use template'); use.type = 'button';
    use.addEventListener('click', () => choose(template));
  }
  async function load(reset = false) {
    if (!reset && state.busy) return;
    if (reset) { state.generation++; state.page = 0; $('templateGrid').replaceChildren(); }
    const generation = state.generation, page = state.page + 1;
    state.busy = true; $('galleryError').hidden = true; $('galleryStatus').textContent = 'Loading templates…';
    $('templateGrid').setAttribute('aria-busy', 'true'); $('loadMoreTemplates').disabled = true;
    try {
      const response = await request(pageURL(state, page)); const result = await response.json();
      if (generation !== state.generation) return;
      result.results.forEach(card); state.page = page; state.next = result.next;
      $('templateCount').textContent = `${result.count} ${result.count === 1 ? 'design' : 'designs'}`;
      $('galleryStatus').textContent = result.count ? '' : 'No designs match these filters. Try another search or reset the filters.';
      $('loadMoreTemplates').hidden = !state.next;
    } catch (error) {
      if (generation !== state.generation) return;
      $('galleryErrorText').textContent = error.message; $('galleryError').hidden = false;
      $('galleryStatus').textContent = ''; $('loadMoreTemplates').hidden = true;
    } finally {
      if (generation === state.generation) { state.busy = false; $('templateGrid').setAttribute('aria-busy', 'false'); $('loadMoreTemplates').disabled = false; }
    }
  }
  function sizePreview() {
    if (!$('templatePreview').open) return;
    const frame = $('templateFrame'), view = $('previewViewport'), choice = $('previewZoom').value;
    const doc = frame.contentDocument;
    if (doc?.head && !doc.getElementById('gallery-embed-style')) {
      const style = doc.createElement('style'); style.id = 'gallery-embed-style';
      style.textContent = 'html{overflow:hidden;background:white!important}body{padding:0!important;background:white!important}.document{margin:0!important;box-shadow:none!important}';
      doc.head.appendChild(style);
    }
    frame.style.height = '1123px';
    const width = 794, scale = choice === 'fit' ? Math.min(1, (view.clientWidth - 40) / width) : Number(choice);
    const height = Math.max(1123, frame.contentDocument?.documentElement.scrollHeight || 0);
    frame.style.height = `${height}px`; frame.style.transform = `scale(${scale})`;
    $('previewStage').style.width = `${width * scale}px`; $('previewStage').style.height = `${height * scale}px`;
  }
  async function openPreview(template) {
    state.selected = template; previewController?.abort(); previewController = new AbortController();
    const generation = ++state.previewGeneration;
    $('previewTitle').textContent = template.name; $('previewCategory').textContent = template.category_label;
    $('previewStatus').textContent = personal() ? 'Loading your private CV preview…' : 'Loading fictional sample…';
    $('templateFrame').removeAttribute('srcdoc');
    if (!$('templatePreview').open) $('templatePreview').showModal();
    try {
      const suffix = personal() ? '?cv_id=' + encodeURIComponent(personal()) : '';
      const response = await request(template.preview_html_url + suffix, {signal: previewController.signal}, Boolean(personal()));
      const html = await response.text();
      if (generation !== state.previewGeneration || !$('templatePreview').open) return;
      $('templateFrame').srcdoc = html;
      $('previewStatus').textContent = personal() ? 'Private preview · Your saved CV content' : 'Fictional comparison profile · Alex Morgan';
    } catch (error) { if (generation === state.previewGeneration && error.name !== 'AbortError') $('previewStatus').textContent = error.message; }
  }
  function closePreview() {
    state.previewGeneration++; previewController?.abort(); $('templateFrame').removeAttribute('srcdoc');
    if ($('templatePreview').open) $('templatePreview').close();
  }
  async function loadCVs() {
    $('personalStatus').textContent = 'Loading your saved CVs…';
    if (!signedIn()) { $('personalStatus').textContent = 'Sign in through My workspace to preview your own CVs.'; return; }
    try {
      const response = await request('/api/cvs/?page_size=100', {}, true), data = await response.json();
      $('previewData').replaceChildren(new Option('Fictional comparison profile', ''));
      data.results.forEach(cv => $('previewData').add(new Option(cv.name, cv.id)));
      if (privateCV && data.results.some(cv => String(cv.id) === privateCV)) $('previewData').value = privateCV;
      // A direct editor link may identify a CV beyond the first list page.
      if (privateCV && !$('previewData').value) {
        const r = await request(`/api/cvs/${encodeURIComponent(privateCV)}/`, {}, true); const cv = await r.json();
        $('previewData').add(new Option(cv.name, cv.id)); $('previewData').value = cv.id;
      }
      $('personalStatus').textContent = data.results.length ? 'Your CV content is fetched only when you open a private preview.' : 'No saved CVs yet. Try the fictional sample or create your first CV.';
    } catch (error) { $('personalStatus').textContent = error.message; }
  }
  async function choose(template) {
    const generation = ++state.useGeneration;
    state.selected = template; state.cv = null; closePreview();
    $('useTemplateTitle').textContent = `Use ${template.name}`; $('useStatus').textContent = '';
    $('gallerySignIn').hidden = signedIn(); $('creationFields').hidden = Boolean(personal());
    $('confirmUseTemplate').disabled = Boolean(personal());
    $('confirmUseTemplate').textContent = personal() ? 'Apply to this CV' : 'Create CV';
    $('useTemplateDescription').textContent = personal() ? 'Change the design of this saved CV. All content is preserved in the next version.' : template.description;
    $('galleryTargetRole').value = state.role || '';
    if (state.career_level) $('galleryCareerLevel').value = state.career_level;
    else $('galleryCareerLevel').value = template.supported_levels[0] || 'fresher';
    for (const option of $('galleryCareerLevel').options) option.disabled = template.supported_levels.length > 0 && !template.supported_levels.includes(option.value);
    if ($('galleryCareerLevel').selectedOptions[0]?.disabled) $('galleryCareerLevel').value = template.supported_levels[0];
    for (const input of $('creationFields').querySelectorAll('input')) input.required = !personal();
    $('useTemplateDialog').showModal();
    if (personal()) {
      try { const response = await request(`/api/cvs/${encodeURIComponent(personal())}/`, {}, true); const cv = await response.json();
        if (generation !== state.useGeneration || !$('useTemplateDialog').open) return;
        state.cv = cv;
        $('useTemplateDescription').textContent = `Apply ${template.name} to “${state.cv.name}” (version ${state.cv.version}). Your CV content and career details will be preserved.`;
      } catch (error) { if (generation !== state.useGeneration) return; $('useStatus').textContent = error.message; }
    }
    if (generation !== state.useGeneration) return;
    $('confirmUseTemplate').disabled = !signedIn() || (Boolean(personal()) && !state.cv);
  }
  async function submit(event) {
    event.preventDefault();
    if (!state.selected || $('confirmUseTemplate').disabled) return;
    $('confirmUseTemplate').disabled = true; $('useStatus').textContent = 'Saving your selection…';
    try {
      if (state.cv) {
        const response = await request(`/api/cvs/${state.cv.id}/`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(switchPayload(state.cv, state.selected))}, true);
        const saved = await response.json(); global.location.href = `/cvs/${saved.id}/edit/`;
      } else {
        const values = {name: $('galleryCVName').value.trim(), target_role: $('galleryTargetRole').value.trim(), career_level: $('galleryCareerLevel').value, template_id: state.selected.id};
        if ($('galleryCreationMode').value === 'ai') {
          const q = new URLSearchParams({create: 'ai', template: values.template_id, role: values.target_role, level: values.career_level, name: values.name});
          global.location.href = '/dashboard/?' + q; return;
        }
        const response = await request('/api/cvs/', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({...values, data: {}})}, true);
        const saved = await response.json(); global.location.href = `/cvs/${saved.id}/edit/`;
      }
    } catch (error) { $('useStatus').textContent = error.message; }
    finally { $('confirmUseTemplate').disabled = false; }
  }
  document.querySelectorAll('[data-category]').forEach(button => button.addEventListener('click', () => {
    state.category = button.dataset.category;
    document.querySelectorAll('[data-category]').forEach(node => { const selected = node === button; node.classList.toggle('selected', selected); node.setAttribute('aria-pressed', String(selected)); });
    load(true);
  }));
  document.querySelectorAll('[data-role]').forEach(button => button.addEventListener('click', () => {
    state.role = button.dataset.role;
    document.querySelectorAll('[data-role]').forEach(node => node.classList.toggle('selected', node === button)); load(true);
  }));
  $('templateSearch').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { state.search = $('templateSearch').value.trim(); load(true); }, 220); });
  $('galleryLevel').addEventListener('change', () => { state.career_level = $('galleryLevel').value; load(true); });
  $('resetFilters').addEventListener('click', () => {
    clearTimeout(searchTimer); state.category = ''; state.search = ''; state.career_level = ''; state.role = '';
    $('templateSearch').value = ''; $('galleryLevel').value = '';
    document.querySelectorAll('[data-category]').forEach(node => { const selected = !node.dataset.category; node.classList.toggle('selected', selected); node.setAttribute('aria-pressed', String(selected)); });
    document.querySelectorAll('[data-role]').forEach(node => node.classList.remove('selected')); load(true);
  });
  $('loadMoreTemplates').addEventListener('click', () => load()); $('retryGallery').addEventListener('click', () => load(true));
  $('loadPersonalCVs').addEventListener('click', loadCVs); $('closePreview').addEventListener('click', closePreview);
  $('templatePreview').addEventListener('cancel', event => { event.preventDefault(); closePreview(); });
  $('templateFrame').addEventListener('load', sizePreview); $('previewZoom').addEventListener('change', sizePreview);
  global.addEventListener('resize', sizePreview);
  $('previewUse').addEventListener('click', () => choose(state.selected));
  $('closeUse').addEventListener('click', () => { state.useGeneration++; $('useTemplateDialog').close(); });
  $('useTemplateDialog').addEventListener('cancel', () => { state.useGeneration++; }); $('useTemplateForm').addEventListener('submit', submit);
  $('gallerySignIn').addEventListener('click', () => {
    if (!state.selected) return;
    const params = new URLSearchParams({create: $('galleryCreationMode').value, template: state.selected.id,
      role: $('galleryTargetRole').value.trim(), level: $('galleryCareerLevel').value, name: $('galleryCVName').value.trim()});
    $('gallerySignIn').href = '/dashboard/?' + params;
  });
  $('previewData').addEventListener('change', () => { if ($('templatePreview').open) openPreview(state.selected); });
  function checkAccount() {
    const current = global.M1Session?.identity();
    if (current === authIdentity) return;
    authIdentity = current; closePreview();
    if ($('useTemplateDialog').open) $('useTemplateDialog').close();
    state.cv = null; $('previewData').replaceChildren(new Option('Fictional comparison profile', ''));
  }
  global.addEventListener('focus', checkAccount); global.addEventListener('pageshow', checkAccount);
  document.addEventListener('visibilitychange', checkAccount);
  global.addEventListener('pagehide', closePreview);
  load(true); if (privateCV) loadCVs();
})(typeof window !== 'undefined' ? window : globalThis);
