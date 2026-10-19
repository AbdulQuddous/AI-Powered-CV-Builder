const { test } = require('node:test');
const assert = require('node:assert/strict');
const api = require('../m7_editor/static/m7_editor/js/api.js');
const edit = require('../m7_editor/static/m7_editor/js/editor.js');
const cv = {
  schema_version: '1.0', meta: { target_role: 'Backend Developer' },
  personal: { full_name: 'A', email: null }, summary: 'Engineer',
  experience: [{ company: 'Acme', role: 'Intern', responsibilities: ['Built APIs'] }],
  projects: [], skills: ['Python'], education: [], certifications: [],
  achievements: [], languages: [], unexpected_legacy_field: { retain: true },
};

test('nested M2 envelope is read without restructuring CV JSON', () => {
  const got = api.normalizeResponse({ data: { id: 9, cv_data: cv, version: 6 } });
  assert.equal(got.version, 6);
  assert.equal(got.field, 'cv_data');
  assert.deepEqual(got.document, cv);
  assert.deepEqual(api.buildPatchBody(got, cv), {cv_data: cv, expected_version: 6});
});

test('different document field is honored without updating M2', () => {
  const got = api.normalizeResponse({ id: 9, content: cv, current_version: 5 });
  assert.equal(got.field, 'content');
  assert.deepEqual(api.buildPatchBody(got, cv), {content: cv, expected_version: 5});
});

test('version omitted by backend blocks blind write', () => {
  const got = api.normalizeResponse({ id: 9, cv_json: cv });
  assert.throws(() => api.buildPatchBody(got, cv), /version/);
});

test('editor public login bypasses authenticated transport and retains M1 refresh token', async () => {
  const previous = {fetch: global.fetch, session: global.M1Session};
  let stored;
  global.M1Session = {request: () => { throw new Error('Login must remain public'); }, storeTokens: tokens => { stored = tokens; }};
  global.fetch = async () => ({ok: true, headers: {get: () => 'application/json'}, json: async () => ({access: 'access', refresh: 'refresh'})});
  try {
    await api.login('user@example.com', 'Strong-passphrase');
    assert.deepEqual(stored, {access: 'access', refresh: 'refresh'});
  } finally {global.fetch = previous.fetch; global.M1Session = previous.session;}
});

test('editor uses M10 collection limits and enum choices without deleting entries', () => {
  const component = edit.cvEditor();
  component.cvSchema = require('../shared/schemas/cv_schema.json');
  component.cv = {experience: []};
  for (let index=0; index<6; index++) component.add('experience');
  assert.equal(component.cv.experience.length, 5);
  assert.deepEqual(component.rowChoices('languages', 'proficiency'), ['', 'basic', 'conversational', 'professional', 'fluent', 'native']);
});

test('editor changes only requested fields and preserves unknown sections', () => {
  const component = edit.cvEditor();
  component.cv = structuredClone(cv);
  component.loaded = {version: 6};
  component.initial = JSON.stringify(component.cv);
  component.setPersonal('email', 'a@example.com');
  component.add('experience');
  component.setRow('experience', 1, 'company', 'Beta');
  component.move('experience', 1, -1);
  assert.equal(component.cv.experience[0].company, 'Beta');
  assert.equal(component.cv.experience[1].company, 'Acme');
  assert.equal(component.cv.personal.email, 'a@example.com');
  assert.deepEqual(component.cv.unexpected_legacy_field, {retain: true});
  assert.equal(component.dirty, true);
});

test('multiline arrays remain arrays rather than string', () => {
  assert.deepEqual(edit.setScalar(['A'], 'A\nB\n'), ['A', 'B']);
  assert.equal(edit.setScalar(null, 'Text'), 'Text');
  assert.deepEqual(edit.emptyLike({url: null, lines: ['a']}), {url:null, lines:[]});
});

test('save uses existing PATCH endpoint and re-fetches the canonical version', async () => {
  const previousFetch = global.fetch;
  let version = 4;
  let saved = structuredClone(cv);
  const calls = [];
  global.fetch = async (url, options = {}) => {
    calls.push([url, options.method || 'GET']);
    if (options.method === 'PATCH') {
      const patch = JSON.parse(options.body);
      assert.equal(patch.expected_version, 4);
      assert.equal(patch.cv_data.summary, 'Updated');
      saved = patch.cv_data;
      version = 5;
    }
    return {ok: true, status: 200, headers: {get: () => 'application/json'},
      json: async () => ({data: {id: 7, cv_data: saved, version}})};
  };
  try {
    const loaded = await api.load(7);
    const next = await api.save(7, loaded, {...cv, summary:'Updated'});
    assert.deepEqual(calls.map(c=>c[1]), ['GET','PATCH','GET']);
    assert.equal(next.version, 5);
    assert.equal(next.document.summary, 'Updated');
  } finally { global.fetch = previousFetch; }
});

test('server conflict is propagated without overwrite', async () => {
  const previousFetch = global.fetch;
  let calls = 0;
  global.fetch = async (url, opts) => {
    calls++;
    return {ok: false, status: 409, headers: {get: () => 'application/json'},
      json: async () => ({error: {code:'version_conflict', message:'Stale version'}})};
  };
  try {
    await assert.rejects(api.save(7,{field:'cv_data',version:4},cv),
      err => err.status === 409 && err.code === 'version_conflict');
    assert.equal(calls, 1);
  } finally { global.fetch = previousFetch; }
});

test('editor accepts only known section names from navigation links', () => {
  const previous = {document: global.document, location: global.location, addEventListener: global.addEventListener};
  try {
    global.document = {getElementById: () => ({textContent: '12'})};
    global.addEventListener = () => {};
    for (const [hash, expected] of [['#projects', 'projects'], ['#unsupported-section', 'personal']]) {
      global.location = {hash};
      const component = edit.cvEditor();
      component.reload = () => {};
      component.init();
      assert.equal(component.active, expected);
    }
  } finally {
    global.document = previous.document;
    global.location = previous.location;
    global.addEventListener = previous.addEventListener;
  }
});

test('new entries use M10 field names and types even when sections are empty', () => {
  const schema = require('../shared/schemas/cv_schema.json');
  const component = edit.cvEditor();
  component.cv = {experience: [], education: [], projects: [], certifications: [], languages: []};
  for (const section of Object.keys(component.cv)) {
    component.add(section);
    const row = component.cv[section][0];
    const contract = schema.properties[section].items;
    assert.deepEqual(Object.keys(row).sort(), [...contract.required].sort());
    for (const [key, value] of Object.entries(row)) {
      assert.equal(Array.isArray(value) ? 'array' : typeof value,
        contract.properties[key].type || 'string');
    }
  }
  component.setRow('certifications', 0, 'name', 'Advance AI Bootcamp');
  component.setRow('certifications', 0, 'date', '2026-10');
  assert.equal(component.cv.certifications[0].name, 'Advance AI Bootcamp');
  assert.equal(component.cv.certifications[0].date, '2026-10');
  assert.equal(component.isDateField('date'), true);
});

test('section buttons reveal the selected preview section including repeated selections', () => {
  const component = edit.cvEditor();
  const calls = [];
  component._livePreview = {scrollToSection: section => calls.push(section)};
  component.selectSection('projects');
  assert.equal(component.active, 'projects');
  component.selectSection('projects');
  component.selectSection('unsupported');
  assert.deepEqual(calls, ['projects', 'projects']);
});

test('M2 certificate validation error is visible and failed saves preserve the draft', async () => {
  const previous = {fetch: global.fetch, api: global.M7Api};
  let calls = 0;
  global.fetch = async () => {
    calls++;
    return {ok: false, status: 400, headers: {get: () => 'application/json'},
      json: async () => ({error: {code: 'validation_error', details: {data: [
        {path: 'certifications/0/date', message: 'Use a year and month.'}
      ]}}})};
  };
  global.M7Api = api;
  try {
    const component = edit.cvEditor();
    component.id = 11;
    component.cv = structuredClone(cv);
    component.loaded = {field: 'data', version: 3};
    component.initial = JSON.stringify(component.cv);
    component.cv.certifications = [{name: 'Advance AI Bootcamp', issuer: '', date: '2026', url: ''}];
    await component.save();
    assert.match(component.error, /certifications → 0 → date: Use a year and month/);
    assert.equal(component.cv.certifications[0].name, 'Advance AI Bootcamp');
    assert.equal(component.dirty, true);
    assert.equal(component.saving, false);
    assert.equal(component.loaded.version, 3);
    assert.equal(calls, 1);
  } finally { global.fetch = previous.fetch; global.M7Api = previous.api; }
});

test('saved preview requests actual PDF pages and displays their page count', async () => {
  const component = edit.cvEditor(); component.id = 18; component.loading = false;
  component.cv = structuredClone(cv); component.initial = JSON.stringify(component.cv); component.loaded = {version: 11};
  const calls = [];
  component.m8Request = async (action, method) => {
    calls.push([action, method]);
    return {text: async () => '<html><body>2 A4 pages</body></html>', headers: {get: name => name === 'X-CV-Page-Count' ? '2' : null}};
  };
  await component.previewM8();
  assert.deepEqual(calls, [['preview/document/', 'GET']]);
  assert.equal(component.m8PreviewPages, 2); assert.equal(component.m8PreviewOpen, true);
  assert.match(component.notice, /Exact PDF preview/);
  component.closeM8Preview(); assert.equal(component.m8PreviewPages, 0);
});

test('M8 preview and export requests pin the version loaded by the editor', async () => {
  const previous = {session: global.M1Session, storage: global.sessionStorage};
  const paths = [];
  global.sessionStorage = {getItem: () => 'test-access'};
  global.M1Session = {request: async path => { paths.push(path); return {ok: true}; }};
  try {
    const component = edit.cvEditor(); component.id = 18; component.loaded = {version: 11};
    await component.m8Request('preview/document/');
    await component.m8Request('export/docx/?layout=fixed', 'POST');
    assert.deepEqual(paths, ['/api/cvs/18/preview/document/?expected_version=11', '/api/cvs/18/export/docx/?layout=fixed&expected_version=11']);
  } finally { global.M1Session = previous.session; global.sessionStorage = previous.storage; }
});

test('Word download defaults to matching pages and retains an explicit editable option', async () => {
  const previous = {document: global.document, timer: global.setTimeout}; const names = [], paths = [];
  global.document = {body: {appendChild() {}}, createElement: () => ({click() { names.push(this.download); }, remove() {}})};
  global.setTimeout = fn => { fn(); return 0; };
  try {
    const component = edit.cvEditor(); component.id = 18; component.loading = false;
    component.cv = structuredClone(cv); component.initial = JSON.stringify(component.cv); component.loaded = {version: 11};
    component.m8Request = async path => { paths.push(path); return {blob: async () => new Blob(['Word'])}; };
    await component.downloadM8('docx'); await component.downloadM8('docx', 'editable');
    assert.deepEqual(paths, ['export/docx/?layout=fixed', 'export/docx/?layout=editable']);
    assert.deepEqual(names, ['cv-18.docx', 'cv-18-editable.docx']);
  } finally { global.document = previous.document; global.setTimeout = previous.timer; }
});
