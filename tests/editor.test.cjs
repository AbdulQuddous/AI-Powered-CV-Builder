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
