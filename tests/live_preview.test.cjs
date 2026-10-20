const {test} = require('node:test');
const assert = require('node:assert/strict');
const preview = require('../m7_editor/static/m7_editor/js/live_preview.js');

const cv = {
  meta: {target_role: 'Backend Developer'},
  personal: {full_name: 'Ali', email: 'ali@example.com'}, summary: 'Builds APIs',
  skills: ['Python', {name: 'Django'}],
  experience: [{job_title: 'Developer', company: 'Acme', start_date: '2022-01',
    is_current: true, highlights: ['Built APIs']}],
  projects: [{name: 'Tracker', description: 'Tracks tasks', technologies: 'Django, PostgreSQL',
    highlights: ['Task search'], url: 'https://example.com'}],
  education: [{degree: 'BS', institution: 'University', grade: '3.2'}],
  certifications: [{name: 'Certificate', issuer: 'Institute', issue_date: '2024-01'}],
  achievements: [{title: 'Award', description: 'Team award'}],
  languages: [{language: 'English', level: 'Fluent'}]
};

test('draft presentation matches renderer section ordering, labels, dates and bullets', () => {
  const before = JSON.stringify(cv);
  const data = preview.context(cv);
  assert.equal(data.name, 'Ali');
  assert.deepEqual(data.skills, ['Python', 'Django']);
  assert.deepEqual(data.sections.map(x => x.label), ['Professional Experience', 'Projects',
    'Education', 'Certifications', 'Achievements', 'Languages']);
  assert.equal(data.sections[0].items[0].subtitle, 'Acme | 2022-01 - Present');
  assert.deepEqual(data.sections[1].items[0].bullets, ['Task search', 'https://example.com']);
  assert.equal(data.sections[1].items[0].subtitle, 'Technologies: Django, PostgreSQL');
  assert.equal(data.sections[2].items[0].description, 'Grade: 3.2');
  assert.equal(JSON.stringify(cv), before);
});

test('empty, legacy and partially typed entries follow renderer fallbacks', () => {
  const data = preview.context({personal: {}, summary: {unknown: 'ignore'},
    experience: [{role: 'Intern', responsibilities: ['Built APIs']}, {}],
    projects: ['Legacy project'], skills: [false, null, ' Git ']});
  assert.equal(data.name, 'Curriculum Vitae');
  assert.equal(data.summary, '');
  assert.deepEqual(data.skills, ['Git']);
  assert.deepEqual(data.sections[0].items[0].bullets, ['Built APIs']);
  assert.equal(data.sections[0].items.length, 1);
  assert.equal(data.sections[1].items[0].title, 'Legacy project');
});

// Small DOM double: innerHTML writes are forbidden so user content must stay text.
class Node {
  constructor(tag) { this.tag = tag; this.children = []; this.style = {}; }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(node) { this.children = node.children; }
  set innerHTML(_) { throw new Error('Unsafe HTML interpolation'); }
}
function documentDouble() {
  const main = new Node('main');
  return {main, createDocumentFragment: () => new Node('fragment'),
    createElement: tag => new Node(tag), querySelector: () => main,
    createTextNode: text => Object.assign(new Node('#text'), {textContent: text}),
    documentElement: {scrollHeight: 1123}, body: {scrollHeight: 1123}};
}

test('user markup is literal text, and cleared sections disappear from the draft', () => {
  const document = documentDouble();
  const name = '<img src=x onerror=alert(1)>';
  preview.render(document, {...cv, personal: {full_name: name}});
  assert.equal(document.main.children[0].children[0].textContent, name);
  assert.equal(document.main.children[0].children[0].tag, 'h1');
  preview.render(document, {personal: {full_name: name}});
  assert.equal(document.main.children.length, 1);
});

test('typing updates locally, fits A4, and grows and shrinks long drafts', () => {
  const document = documentDouble();
  const listeners = {};
  const frame = {contentDocument: document, style: {},
    addEventListener: (event, handler) => { listeners[event] = handler; },
    removeEventListener: event => { delete listeners[event]; }, removeAttribute() {}};
  const stage = {style: {}};
  let draft = structuredClone(cv);
  let requests = 0;
  const controller = preview.create({frame, stage, viewport: {clientWidth: 400},
    request: () => { requests++; }, getCV: () => draft, onReady() {},
    onError: error => { throw error; }});
  listeners.load();
  const scale = 400 / (210 * 96 / 25.4);
  assert.equal(frame.style.transform, `scale(${scale})`);
  assert.equal(stage.style.height, `${1123 * scale}px`);
  draft.summary = 'Unsaved new summary';
  document.documentElement.scrollHeight = 2000;
  controller.update();
  assert.equal(document.main.children[1].children[1].textContent, 'Unsaved new summary');
  assert.equal(frame.style.height, '2000px');
  document.documentElement.scrollHeight = 1123;
  controller.update();
  assert.equal(frame.style.height, '1123px');
  controller.setZoom(1);
  assert.equal(frame.style.transform, 'scale(1)');
  assert.equal(stage.style.width, `${210 * 96 / 25.4}px`);
  controller.setZoom(1.25);
  assert.equal(frame.style.transform, 'scale(1.25)');
  assert.equal(stage.style.height, `${1123 * 1.25}px`);
  controller.setZoom('fit');
  assert.equal(frame.style.transform, `scale(${scale})`);
  controller.setZoom(999);
  assert.equal(frame.style.transform, `scale(${scale})`);
  assert.equal(requests, 0);
  controller.destroy();
  assert.equal(listeners.load, undefined);
});

test('preview errors are reported and disposed requests cannot update the iframe', async () => {
  let rejectRequest;
  const errors = [];
  const frame = {style: {}, addEventListener() {}, removeEventListener() {}, removeAttribute() {}};
  const controller = preview.create({frame, stage: {style: {}}, viewport: {}, getCV: () => cv,
    request: () => new Promise((_, reject) => { rejectRequest = reject; }),
    onReady() {}, onError: error => errors.push(error)});
  const loading = controller.load();
  rejectRequest(Object.assign(new Error('Sign in again'), {status: 401}));
  await loading;
  assert.equal(errors[0].status, 401);
  const second = controller.load();
  controller.destroy();
  rejectRequest(new Error('Late request'));
  await second;
  assert.equal(errors.length, 1);
  assert.equal(frame.srcdoc, undefined);
});

test('section selection scrolls the preview up or down at its current zoom only when hidden', () => {
  const document = documentDouble();
  let headingTop = 1200;
  const heading = {getBoundingClientRect: () => ({top: headingTop, bottom: headingTop + 30})};
  document.getElementById = id => id === 'm7-preview-projects'
    ? {querySelector: () => heading} : null;
  const listeners = {};
  const frame = {contentDocument: document, style: {},
    addEventListener: (event, handler) => { listeners[event] = handler; },
    removeEventListener() {}, removeAttribute() {},
    getBoundingClientRect: () => ({top: 100})};
  const calls = [];
  const panel = {scrollHeight: 1200, clientHeight: 400, scrollTop: 0,
    getBoundingClientRect: () => ({top: 100, bottom: 500}),
    scrollTo: options => calls.push(options)};
  const viewport = {clientWidth: 400};
  const controller = preview.create({frame, panel, viewport, stage: {style: {}},
    toolbar: {offsetHeight: 60}, request() {}, getCV: () => cv, onReady() {},
    onError: error => { throw error; }});
  // Selection made before the template finishes loading is retained.
  controller.scrollToSection('projects');
  listeners.load();
  const scale = 400 / (210 * 96 / 25.4);
  assert.equal(calls[0].top, 100 + 1200 * scale - 172);
  assert.equal(calls[0].behavior, 'smooth');
  headingTop = 200;
  controller.scrollToSection('projects');
  assert.equal(calls.length, 1); // The heading is already visible.
  headingTop = 0;
  panel.scrollTop = 400;
  controller.scrollToSection('projects');
  assert.equal(calls[1].top, 328); // Scroll upwards to reveal the heading.
  headingTop = 500;
  panel.scrollTop = 0;
  controller.setZoom(1.25);
  controller.scrollToSection('projects');
  assert.equal(calls[2].top, 553);
  controller.scrollToSection('unknown');
  assert.equal(calls.length, 3);
  controller.destroy();
});

test('empty sections wait for content, narrow previews scroll internally and respect reduced motion', () => {
  const previousMatchMedia = global.matchMedia;
  global.matchMedia = () => ({matches: true});
  try {
    const document = documentDouble();
    let target = null;
    document.getElementById = () => target;
    const listeners = {};
    const frame = {contentDocument: document, style: {},
      addEventListener: (event, handler) => { listeners[event] = handler; },
      removeEventListener() {}, removeAttribute() {},
      getBoundingClientRect: () => ({top: 100})};
    const calls = [];
    const viewport = {clientWidth: 400, scrollTop: 0,
      getBoundingClientRect: () => ({top: 100, bottom: 400}),
      scrollTo: options => calls.push(options)};
    const controller = preview.create({frame, viewport, stage: {style: {}},
      panel: {scrollHeight: 400, clientHeight: 400}, initialZoom: 1,
      request() {}, getCV: () => cv, onReady() {}, onError: error => { throw error; }});
    listeners.load();
    controller.scrollToSection('certifications');
    assert.equal(calls.length, 0);
    target = {querySelector: () => null,
      getBoundingClientRect: () => ({top: 1000, bottom: 1040})};
    controller.update();
    assert.equal(calls[0].top, 988);
    assert.equal(calls[0].behavior, 'instant');
    controller.update();
    assert.equal(calls.length, 1); // Typing does not repeatedly pull the scroll position.
    controller.destroy();
  } finally { global.matchMedia = previousMatchMedia; }
});

test('designed live preview preserves columns, section order and skill elements', () => {
  const document = documentDouble();
  document.body.dataset = {sideKeys: 'skills,education', sectionOrder: 'summary,projects,experience,skills,education,certifications,achievements,languages'};
  preview.render(document, cv);
  const layout = document.main.children[1];
  assert.equal(layout.className, 'layout');
  const main = layout.children[0], side = layout.children[1];
  assert.equal(main.className, 'main-column'); assert.equal(side.className, 'side-column');
  assert.deepEqual(main.children.slice(0, 3).map(node => node.id), ['m7-preview-summary', 'm7-preview-projects', 'm7-preview-experience']);
  assert.deepEqual(side.children.map(node => node.id), ['m7-preview-skills', 'm7-preview-education']);
  assert.equal(side.children[0].children[1].children[0].className, 'skill');
});

const skillGroupFixtures = require('./fixtures/skill_groups.json');
test('skill group fixtures match server presentation and do not rewrite saved data', () => {
  for (const fixture of skillGroupFixtures) {
    const input = {skills: fixture.skills};
    const before = JSON.stringify(input);
    const data = preview.context(input);
    assert.deepEqual(data.skillGroups, fixture.groups, fixture.name);
    assert.deepEqual(data.skills, fixture.skills);
    assert.equal(JSON.stringify(input), before);
  }
});

test('grouped draft skills use bold labels, separate rows and literal user text in every layout', () => {
  for (const designed of [false, true]) {
    const document = documentDouble();
    if (designed) document.body.dataset = {sideKeys: 'skills', sectionOrder: 'skills'};
    const skills = ['Programming: Python, <img src=x onerror=alert(1)>', 'Tools: Git'];
    preview.render(document, {skills});
    const section = designed ? document.main.children[1].children[1].children[0] : document.main.children[1];
    const rows = section.children[1];
    assert.equal(rows.className, 'skill-groups');
    assert.equal(rows.children.length, 2);
    assert.equal(rows.children[0].children[0].tag, 'strong');
    assert.equal(rows.children[0].children[0].textContent, 'Programming:');
    assert.equal(rows.children[0].children[2].textContent, 'Python, <img src=x onerror=alert(1)>');
    assert.equal(rows.children[1].children[0].textContent, 'Tools:');
  }
});
