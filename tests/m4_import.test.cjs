const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const { File } = require('node:buffer');

function harness(fetchHandler, search = '') {
    const elements = new Map();
    function element() {
        const classes = new Set(['hidden']);
        return {
            value: '', disabled: false, dataset: {}, textContent: '', children: [], listeners: {},
            classList: { add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x), toggle(x, hide) { if (hide) classes.add(x); else classes.delete(x); } },
            addEventListener(name, handler) { this.listeners[name] = handler; },
            setAttribute() {}, replaceChildren() {}, add() {}, appendChild() {},
        };
    }
    const get = id => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
    const storage = new Map([['cv_access', 'test-jwt']]);
    const calls = [];
    const location = { origin: 'http://localhost', href: 'http://localhost/dashboard/' + search, search };
    const window = { location, history: { replaceState(_a, _b, url) { location.href = String(url); location.search = new URL(url).search; } } };
    const context = vm.createContext({ window, console, URL, URLSearchParams, Headers, FormData, setTimeout, clearTimeout,
        Option: function () {},
        document: { getElementById: get, createElement: element, querySelector: () => null, addEventListener() {}, body: { style: {} } },
        sessionStorage: { getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
        fetch: async (url, options) => {
            assert.equal(options.headers.get('Authorization'), 'Bearer test-jwt');
            assert.equal(options.credentials, 'same-origin');
            calls.push({ url, options });
            return fetchHandler(url, options);
        }
    });
    vm.runInContext(fs.readFileSync('m9_dashboard/static/m9_dashboard/js/dashboard.js', 'utf8'), context);
    vm.runInContext(fs.readFileSync('m9_dashboard/static/m9_dashboard/js/import_cv.js', 'utf8'), context);
    vm.runInContext('window.M4Import.init({fetch: apiFetch, requireLogin, openModal})', context);
    return { get, calls, context, click: id => get(id).listeners.click(), select: file => get('importFile').listeners.change({ target: { files: [file] } }) };
}
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const imported = (status = 'uploaded', text = '') => ({ import_id: 7, file_name: 'CV.docx', file_type: 'docx', file_size: 1024, status, text, error_message: '' });
const cvFile = () => new File(['CV text'], 'CV.docx');

test('validation prevents unsupported, oversized and empty files from uploading', async () => {
    const h = harness(() => { throw new Error('No request should be made'); });
    for (const file of [{name:'CV.txt',size:100}, {name:'CV.pdf',size:5*1024*1024+1}, {name:'CV.docx',size:0}]) {
        h.select(file);
        assert.equal(h.get('importModal').dataset.state, 'upload_error');
        await h.click('importUpload');
    }
    assert.equal(h.calls.length, 0);
});

test('upload uses FormData and extraction returns plain text without CV or AI requests', async () => {
    const h = harness((url, options) => {
        if (url.endsWith('/upload/')) {
            assert.equal(options.method, 'POST');
            assert.ok(options.body instanceof FormData);
            assert.equal(options.body.get('file').name, 'CV.docx');
            assert.equal(options.headers.has('Content-Type'), false);
            return response(imported(), 201);
        }
        if (url.endsWith('/extract/')) {
            assert.equal(options.body, undefined);
            return response(imported('extracted', 'Ali Khan\nPython\n<script>literal text</script>'));
        }
        return response(imported());
    });
    h.select(cvFile());
    assert.equal(h.get('importModal').dataset.state, 'file_selected');
    assert.equal(h.calls.length, 0);
    await h.click('importUpload');
    assert.equal(h.get('importModal').dataset.state, 'uploaded');
    await h.click('importExtract');
    assert.equal(h.get('importModal').dataset.state, 'extracted');
    assert.match(h.get('importText').value, /<script>literal text<\/script>/);
    assert.equal(h.calls.length, 3);
    assert.ok(h.calls.every(call => call.url.startsWith('/api/cv-import/')));
});

test('duplicate clicks are disabled while upload is running', async () => {
    let complete;
    const h = harness(() => new Promise(resolve => { complete = resolve; }));
    h.select(cvFile());
    const request = h.click('importUpload');
    assert.equal(h.get('importModal').dataset.state, 'uploading');
    assert.equal(h.get('importUpload').disabled, true);
    await h.click('importUpload');
    assert.equal(h.calls.length, 1);
    complete(response(imported(), 201));
    await request;
    assert.equal(h.get('importExtract').disabled, false);
});

test('backend upload validation is visible and file remains recoverable', async () => {
    const h = harness(() => response({error:{details:{file:['File size exceeds backend limit.']}}},400));
    h.select(cvFile());
    await h.click('importUpload');
    assert.equal(h.get('importModal').dataset.state, 'upload_error');
    assert.equal(h.get('importError').textContent, 'File size exceeds backend limit.');
    assert.equal(h.get('importSelected').classList.contains('hidden'), false);
    assert.equal(h.get('importUpload').disabled, false);
});

test('extraction failure exposes backend explanation and supports retry', async () => {
    let attempts = 0;
    const h = harness((url) => {
        if(url.endsWith('/upload/')) return response(imported(),201);
        if(url.endsWith('/extract/')) {
            attempts++;
            return attempts === 1 ? response({detail:'PDF contains no extractable text.'},422) : response(imported('extracted','Recovered text'));
        }
        return response(imported(attempts ? 'failed' : 'uploaded'));
    });
    h.select(cvFile()); await h.click('importUpload'); await h.click('importExtract');
    assert.equal(h.get('importModal').dataset.state,'extraction_error');
    assert.equal(h.get('importError').textContent,'PDF contains no extractable text.');
    assert.equal(h.get('importExtract').textContent,'Retry extraction');
    await h.click('importExtract');
    assert.equal(h.get('importText').value,'Recovered text');
});

test('URL resume loads history; a finished extraction is never resent', async () => {
    const h = harness(() => response(imported('extracted','Already extracted')), '?import=7');
    await vm.runInContext('window.M4Import.resume()',h.context);
    assert.equal(h.get('importText').value,'Already extracted');
    await h.click('importExtract');
    assert.ok(h.calls.every(call => call.options.method !== 'POST'));
});

test('lost extraction response reconciles through GET before retry', async () => {
    let finished = false, attempts = 0;
    const h = harness(url => {
        if(url.endsWith('/upload/'))return response(imported(),201);
        if(url.endsWith('/extract/')){finished=true;attempts++;throw new Error('Lost response');}
        return response(imported(finished?'extracted':'uploaded',finished?'Completed text':''));
    });
    h.select(cvFile());await h.click('importUpload');await h.click('importExtract');
    assert.equal(h.get('importModal').dataset.state,'extraction_error');
    await h.click('importExtract');
    assert.equal(h.get('importText').value,'Completed text');
    assert.equal(attempts,1);
});

test('authentication expiry clears imported text and prevents stale responses', async () => {
    const h = harness(() => response({detail:'Token expired'},401),'?import=7');
    await vm.runInContext('window.M4Import.resume()',h.context);
    assert.equal(h.get('importText').value,'');
    assert.equal(h.get('loginModal').classList.contains('hidden'),false);
    assert.equal(h.get('importModal').classList.contains('hidden'),true);
    assert.equal(h.get('importModal').dataset.state,'idle');
});

test('drag/drop uses the same explicit upload and validation flow', () => {
    const h = harness(() => {throw Error('Selection must not upload');});
    const drop=h.get('importDrop');
    drop.listeners.dragenter({preventDefault(){}});
    assert.equal(drop.classList.contains('dragging'),true);
    drop.listeners.drop({preventDefault(){},dataTransfer:{files:[cvFile()]}});
    assert.equal(drop.classList.contains('dragging'),false);
    assert.equal(h.get('importModal').dataset.state,'file_selected');
    assert.equal(h.calls.length,0);
});

test('in-progress extraction waits for status refresh instead of resending', async () => {
    let done = false;
    const h = harness(() => response(imported(done ? 'extracted' : 'extracting', done ? 'Ready text' : '')), '?import=7');
    await vm.runInContext('window.M4Import.resume()', h.context);
    assert.equal(h.get('importModal').dataset.state, 'extracting');
    assert.equal(h.get('importExtract').classList.contains('hidden'), true);
    await h.click('importExtract');
    assert.ok(h.calls.every(call => call.options.method !== 'POST'));
    done = true;
    await h.click('importRefresh');
    assert.equal(h.get('importText').value, 'Ready text');
});

test('reset discards a late upload response', async () => {
    let complete;
    const h = harness(() => new Promise(resolve => { complete = resolve; }));
    h.select(cvFile());
    const request = h.click('importUpload');
    vm.runInContext('window.M4Import.reset()', h.context);
    complete(response(imported(), 201));
    await request;
    assert.equal(h.get('importModal').dataset.state, 'idle');
    assert.equal(h.get('importDetails').classList.contains('hidden'), true);
});
