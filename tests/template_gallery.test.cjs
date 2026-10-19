const {test} = require('node:test');
const assert = require('node:assert/strict');
const gallery = require('../m9_dashboard/static/m9_dashboard/js/template_gallery.js');
const editor = require('../m7_editor/static/m7_editor/js/editor.js');

test('gallery filters are encoded and paging keeps every filter', () => {
  const path = gallery.pageURL({category: 'ats', search: 'R&D <design>', career_level: 'fresher', role: 'Developer'}, 3);
  const url = new URL(path, 'http://localhost');
  assert.equal(url.pathname, '/api/templates/');
  assert.equal(url.searchParams.get('page'), '3');
  assert.equal(url.searchParams.get('page_size'), '12');
  assert.equal(url.searchParams.get('search'), 'R&D <design>');
  assert.equal(url.searchParams.get('career_level'), 'fresher');
});

test('switch sends only design and expected version, preserving all CV content in M2', () => {
  const cv = {id: 12, version: 4, data: {summary: 'Keep this', meta: {target_role: 'Engineer'}}};
  const before = JSON.stringify(cv);
  assert.deepEqual(gallery.switchPayload(cv, {id: 'professional_blue'}), {template_id: 'professional_blue', expected_version: 4});
  assert.equal(JSON.stringify(cv), before);
  assert.throws(() => gallery.switchPayload({...cv, version: null}, {id: 'modern'}), /Reload/);
});

test('unsaved editor content stays in the editor when changing templates', () => {
  const component = editor.cvEditor(); component.loaded = {version: 1}; component.id = 12;
  component.cv = {summary: 'Unsaved draft'}; component.initial = JSON.stringify({summary: 'Saved'});
  const previous = global.location; global.location = {href: '/cvs/12/edit/'};
  try {
    component.openTemplateGallery();
    assert.equal(global.location.href, '/cvs/12/edit/');
    assert.match(component.notice, /Save your changes/);
    assert.equal(component.cv.summary, 'Unsaved draft');
    component.initial = JSON.stringify(component.cv); component.openTemplateGallery();
    assert.equal(global.location.href, '/templates/?cv_id=12');
  } finally { global.location = previous; }
});
