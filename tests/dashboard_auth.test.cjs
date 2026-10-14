const test = require('node:test'), assert = require('node:assert/strict');
const vm = require('node:vm'), fs = require('node:fs');

function harness(fetcher) {
    const elements = new Map(), storage = new Map(), calls = [], listeners = new Map();
    let document;
    const get = id => {
        if (!elements.has(id)) {
            const classes = new Set(['hidden']);
            elements.set(id, {id, value: '', textContent: '', disabled: false, dataset: {}, children: [], events: {},
                classList: {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x),
                    toggle: (x, on) => on ? classes.add(x) : classes.delete(x)},
                addEventListener(event, fn) { (this.events[event] ||= []).push(fn); },
                focus() { document.activeElement = this; },
                reset() { for (const key of ['registerName', 'registerEmail', 'registerPassword', 'registerConfirm']) get(key).value = ''; },
                replaceChildren() { this.children = []; }, appendChild(node) { this.children.push(node); },
                add() {}, removeAttribute() {}, setAttribute() {},
                closest(selector) {
                    if (selector === 'fieldset:disabled' && ['profileEmail','profileName'].includes(this.id) && get('profileFields').disabled) return get('profileFields');
                    if (selector === '.hidden' && this.id === 'profileRetry' && this.classList.contains('hidden')) return this;
                    return null;
                },
                querySelectorAll() { return (this.id === 'profileModal'
                    ? ['profileRetry', 'profileEmail', 'profileName', 'profileCancel', 'profileSubmit'] : this.id === 'registerModal'
                    ? ['registerName', 'registerEmail', 'registerPassword', 'registerConfirm', 'registerSubmit', 'backToLogin']
                    : ['loginEmail', 'loginPassword', 'loginSubmit', 'openRegister']).map(get); }
            });
        }
        return elements.get(id);
    };
    document = {getElementById: get, body: {style: {}}, activeElement: null,
        createElement: () => ({textContent: '', innerHTML: ''}), querySelectorAll: () => [],
        querySelector: () => ['loginModal', 'registerModal', 'profileModal'].map(get).find(el => !el.classList.contains('hidden')),
        addEventListener(event, fn) { (listeners.get(event) || listeners.set(event, []).get(event)).push(fn); }};
    const window = {location: {search: '', origin: 'http://localhost', href: 'http://localhost/dashboard/'}, history: {replaceState() {}},
        M9Crud: {init() {}, reset() {}}, M6Api: {create() {}},
        M6Review: {init() {}, observe() {}, reset() {}}, M4Import: {init() {}, reset() {}, async resume() {}}};
    const context = vm.createContext({document, window, console, Headers, FormData, URL, URLSearchParams,
        setTimeout: () => 0, clearTimeout() {}, Option: function () {},
        sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
        fetch: async (url, options) => { calls.push({url, options}); return fetcher(url, options); }});
    vm.runInContext(fs.readFileSync('m9_dashboard/static/m9_dashboard/js/dashboard.js', 'utf8'), context);
    get('registerName').value = 'Ali Khan'; get('registerEmail').value = ' ali@example.com ';
    get('registerPassword').value = get('registerConfirm').value = 'Strong-password-735!';
    return {get, calls, storage, document, listeners,
        run: code => vm.runInContext(code, context),
        submit: () => vm.runInContext('handleRegister({preventDefault(){}})', context)};
}
const response = (status, data) => ({ok: status >= 200 && status < 300, status, json: async () => data});

test('register link switches forms, preserves email, clears passwords and moves focus', () => {
    const h = harness();
    h.get('loginEmail').value = 'new@example.com'; h.get('registerEmail').value = '';
    h.run("openModal('loginModal'); showAuthForm('register')");
    assert.equal(h.get('loginModal').classList.contains('hidden'), true);
    assert.equal(h.get('registerModal').classList.contains('hidden'), false);
    assert.equal(h.get('registerEmail').value, 'new@example.com');
    assert.equal(h.document.activeElement.id, 'registerName');
    h.run("showAuthForm('login')");
    assert.equal(h.get('registerModal').classList.contains('hidden'), true);
    assert.equal(h.document.activeElement.id, 'loginEmail');
    assert.equal(h.get('registerPassword').value, '');
    assert.equal(h.calls.length, 0);
});

test('registration uses M1 fields and returns to sign-in without inventing tokens', async () => {
    const h = harness(async () => response(201, {user_id: 4, email: 'ali@example.com', full_name: 'Ali Khan'}));
    await h.submit();
    assert.equal(h.calls[0].url, '/api/auth/register/');
    assert.equal(h.calls[0].options.method, 'POST');
    assert.deepEqual(JSON.parse(h.calls[0].options.body), {
        email: 'ali@example.com', full_name: 'Ali Khan', password: 'Strong-password-735!'});
    assert.equal(h.get('loginEmail').value, 'ali@example.com');
    assert.equal(h.get('loginModal').classList.contains('hidden'), false);
    assert.equal(h.get('registerPassword').value, '');
    assert.equal(h.get('registerConfirm').value, '');
    assert.equal(h.storage.size, 0);
    assert.match(h.get('toast').textContent, /Account created/);
});

test('mismatched confirmation does not create an account', async () => {
    const h = harness(); h.get('registerConfirm').value = 'different';
    await h.submit();
    assert.equal(h.calls.length, 0);
    assert.match(h.get('registerError').textContent, /do not match/);
    assert.equal(h.document.activeElement.id, 'registerConfirm');
});

test('duplicate-email and password rules from M1 are shown and allow retry', async () => {
    const h = harness(async () => response(400, {error: {code: 'validation_error', details: {
        email: ['An account with this email already exists.'], password: ['This password is too common.']}}}));
    await h.submit();
    assert.match(h.get('registerError').textContent, /email: An account/);
    assert.match(h.get('registerError').textContent, /password: This password is too common/);
    assert.equal(h.get('registerSubmit').disabled, false);
    assert.equal(h.get('backToLogin').disabled, false);
    assert.equal(h.get('registerEmail').value, ' ali@example.com ');
});

test('duplicate submissions and form switching are blocked while creating an account', async () => {
    let finish;
    const h = harness(() => new Promise(resolve => { finish = resolve; }));
    h.run("openModal('registerModal')");
    const pending = h.submit();
    await h.submit();
    h.run("showAuthForm('login')");
    assert.equal(h.calls.length, 1);
    assert.equal(h.get('registerModal').classList.contains('hidden'), false);
    assert.equal(h.get('registerSubmit').disabled, true);
    finish(response(201, {email: 'ali@example.com'})); await pending;
    assert.equal(h.get('registerSubmit').disabled, false);
});

test('network and non-JSON rate-limit errors leave registration available', async () => {
    for (const [fetcher, expected] of [
        [async () => { throw new TypeError('Failed to fetch'); }, /Check your connection/],
        [async () => ({ok: false, status: 429, json: async () => { throw Error('Not JSON'); }}), /Too many attempts/]
    ]) {
        const h = harness(fetcher); await h.submit();
        assert.match(h.get('registerError').textContent, expected);
        assert.equal(h.get('registerSubmit').disabled, false);
    }
});

test('new accounts sign in through the existing M1 login and load their dashboard', async () => {
    const h = harness(async url => {
        if (url === '/api/auth/register/') return response(201, {email: 'ali@example.com'});
        if (url === '/api/auth/login/') return response(200, {access: 'jwt', refresh: 'refresh'});
        if (url === '/api/cvs/') return response(200, {results: [], next: null});
        throw Error('Unexpected request ' + url);
    });
    await h.submit(); h.get('loginPassword').value = 'Strong-password-735!';
    await h.run('handleLogin({preventDefault(){}})');
    assert.equal(h.storage.get('cv_access'), 'jwt');
    assert.equal(h.get('loginModal').classList.contains('hidden'), true);
    assert.equal(h.calls[2].options.headers.get('Authorization'), 'Bearer jwt');
    assert.equal(h.get('loginPassword').value, '');
});

test('auth listeners register once and Tab stays within the active dialog', () => {
    const h = harness(); h.run("registerEvents(); registerEvents(); openModal('registerModal')");
    assert.equal(h.get('registerForm').events.submit.length, 1);
    assert.equal(h.get('openRegister').events.click.length, 1);
    let prevented = false;
    h.get('backToLogin').focus();
    const keydown = h.listeners.get('keydown')[0];
    keydown({key: 'Tab', shiftKey: false, preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.equal(h.document.activeElement.id, 'registerName');
    keydown({key: 'Tab', shiftKey: true, preventDefault() {}});
    assert.equal(h.document.activeElement.id, 'backToLogin');
});

const account = {user_id: 4, email: 'ali@example.com', full_name: 'Ali Khan'};
function signedInProfile(fetcher) {
    const h = harness(fetcher);
    h.storage.set('cv_access', 'jwt');
    return h;
}

test('profile reads M1 only and PATCH sends only the editable full name', async () => {
    let saved = {...account};
    const h = signedInProfile(async (url, options) => {
        assert.equal(url, '/api/auth/me/');
        assert.equal(options.headers.get('Authorization'), 'Bearer jwt');
        if (options.method === 'PATCH') {
            assert.deepEqual(JSON.parse(options.body), {full_name: 'Ali Updated'});
            saved.full_name = 'Ali Updated';
        }
        return response(200, {...saved});
    });
    await h.run('openProfile()');
    assert.equal(h.get('profileEmail').value, 'ali@example.com');
    assert.equal(h.get('profileName').value, 'Ali Khan');
    assert.equal(h.get('profileSubmit').disabled, true);
    h.get('profileName').value = 'Ali Updated';
    await h.run('saveProfile({preventDefault(){}})');
    assert.equal(h.get('profileName').value, 'Ali Updated');
    assert.match(h.get('profileStatus').textContent, /Profile updated successfully.*Click Done/);
    assert.equal(h.get('profileStatus').classList.contains('profile-status-success'), true);
    assert.equal(h.get('profileSubmit').textContent, 'Saved ✓');
    assert.equal(h.get('profileSubmit').disabled, true);
    assert.equal(h.get('profileCancel').textContent, 'Done');
    assert.equal(h.document.activeElement.id, 'profileCancel');
    h.get('profileName').value = 'Another change';
    h.run('profileControls()');
    assert.equal(h.get('profileSubmit').disabled, false);
    assert.equal(h.get('profileSubmit').textContent, 'Save profile');
    assert.equal(h.get('profileCancel').textContent, 'Close');
    assert.equal(h.get('profileStatus').classList.contains('profile-status-success'), false);
    assert.equal(h.get('profileStatus').textContent, 'Unsaved changes.');
    await h.run('openProfile()');
    assert.equal(h.get('profileName').value, 'Ali Updated');
    assert.equal(h.calls.length, 3);
    assert.equal(h.calls.filter(call => call.url.startsWith('/api/cvs/')).length, 0);
});

test('profile cancel makes no writes and anonymous opening requires sign-in', async () => {
    const h = signedInProfile(async () => response(200, account));
    await h.run('openProfile()');
    h.get('profileName').value = 'Unsaved edit';
    h.run('closeProfile()');
    assert.equal(h.calls.length, 1);
    assert.equal(h.get('profileName').value, '');
    assert.equal(h.get('profileModal').classList.contains('hidden'), true);
    assert.equal(h.document.activeElement.id, 'profileBtn');
    h.storage.clear();
    await h.run('openProfile()');
    assert.equal(h.get('loginModal').classList.contains('hidden'), false);
    assert.equal(h.calls.length, 1);
});

test('profile validation failures preserve edits and save can be retried', async () => {
    const h = signedInProfile(async (_url, options) => options.method === 'PATCH'
        ? response(400, {error: {details: {full_name: ['Invalid full name.']}}}) : response(200, account));
    await h.run('openProfile()'); h.get('profileName').value = 'Typed name';
    await h.run('saveProfile({preventDefault(){}})');
    assert.match(h.get('profileError').textContent, /full name: Invalid full name/);
    assert.equal(h.get('profileName').value, 'Typed name');
    assert.equal(h.get('profileSubmit').disabled, false);
});

test('profile blocks duplicate saves and ignores load responses after closing', async () => {
    let finish;
    const h = signedInProfile((_url, options) => options.method === 'PATCH'
        ? new Promise(resolve => { finish = resolve; }) : Promise.resolve(response(200, account)));
    await h.run('openProfile()'); h.get('profileName').value = 'New name';
    h.run('registerEvents()');
    const pending = h.run('saveProfile({preventDefault(){}})');
    await h.run('saveProfile({preventDefault(){}})'); h.run('closeProfile()');
    assert.equal(h.get('profileModal').classList.contains('hidden'), false);
    assert.equal(h.calls.length, 2);
    let prevented = false;
    h.listeners.get('keydown')[0]({key: 'Tab', preventDefault() { prevented = true; }});
    assert.equal(prevented, true);
    assert.equal(h.document.activeElement.id, 'profileModal');
    finish(response(200, {...account, full_name: 'New name'})); await pending;
    const slow = signedInProfile(() => new Promise(resolve => { finish = resolve; }));
    const loading = slow.run('openProfile()'); slow.run('closeProfile()');
    finish(response(200, account)); await loading;
    assert.equal(slow.get('profileEmail').value, '');
    assert.equal(slow.get('profileName').value, '');
});

test('expired profile authentication clears private data and opens login', async () => {
    const h = signedInProfile(async () => response(401, {error: {details: {detail: 'Token expired'}}}));
    await h.run('openProfile()');
    assert.equal(h.storage.get('cv_access'), undefined);
    assert.equal(h.get('profileModal').classList.contains('hidden'), true);
    assert.equal(h.get('profileEmail').value, '');
    assert.equal(h.get('loginModal').classList.contains('hidden'), false);
});

test('profile load errors offer retry and keyboard Escape cancels editing', async () => {
    let fail = true;
    const h = signedInProfile(async () => { if (fail) throw new Error('Offline'); return response(200, account); });
    await h.run('openProfile()');
    assert.equal(h.get('profileRetry').classList.contains('hidden'), false);
    assert.equal(h.get('profileSubmit').disabled, true);
    fail = false; await h.run('openProfile()');
    assert.equal(h.get('profileName').value, 'Ali Khan');
    h.run('registerEvents(); registerEvents()');
    assert.equal(h.get('profileForm').events.submit.length, 1);
    const keydown = h.listeners.get('keydown')[0];
    h.get('profileName').value = 'Unsaved edit';
    keydown({key: 'Escape', preventDefault() {}});
    assert.equal(h.get('profileModal').classList.contains('hidden'), true);
    assert.equal(h.calls.filter(call => call.options.method === 'PATCH').length, 0);
});
