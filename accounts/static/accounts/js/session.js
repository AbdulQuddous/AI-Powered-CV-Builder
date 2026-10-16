/* Shared M1 JWT transport for the existing dashboard and editor. */
(function (global) {
    'use strict';
    const ACCESS = 'cv_access', REFRESH = 'cv_refresh', ID = 'cv_auth_session';
    let refreshing = null;
    const storage = () => global.sessionStorage;
    const accessToken = () => storage().getItem(ACCESS) || storage().getItem('access') || storage().getItem('access_token');
    const refreshToken = () => storage().getItem(REFRESH);
    const identity = () => accessToken() ? storage().getItem(ID) || 'legacy-session' : null;
    const expired = () => Object.assign(new Error('Your session expired. Please sign in again.'), {status: 401});
    const changed = () => Object.assign(new Error('The signed-in account changed. Please retry.'), {status: 409, code: 'session_changed'});
    function clear() {
        [ACCESS, REFRESH, ID, 'access', 'access_token'].forEach(key => storage().removeItem(key));
    }
    function storeTokens(tokens, renewal = false) {
        if (typeof tokens?.access !== 'string' || !tokens.access) throw expired();
        if (!renewal) {
            clear();
            storage().setItem(ID, global.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`);
        }
        storage().setItem(ACCESS, tokens.access);
        if (typeof tokens.refresh === 'string' && tokens.refresh) storage().setItem(REFRESH, tokens.refresh);
    }
    function privatePath(path) {
        const url = new URL(path, global.location.origin);
        if (url.origin !== global.location.origin || !url.pathname.startsWith('/api/')) {
            throw new Error('Refusing to send credentials outside the application API.');
        }
        return url.pathname + url.search;
    }
    async function refreshAccess() {
        if (refreshing) return refreshing;
        const owner = identity(), original = refreshToken();
        if (!owner || !original) throw expired();
        refreshing = (async () => {
            const response = await global.fetch('/api/auth/refresh/', {
                method: 'POST', credentials: 'same-origin', cache: 'no-store',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify({refresh: original})
            });
            let payload = {};
            try { payload = await response.json(); } catch (_) { /* Treat an invalid renewal as expired. */ }
            if (identity() !== owner || refreshToken() !== original) throw changed();
            if (!response.ok || typeof payload.access !== 'string' || typeof payload.refresh !== 'string') {
                if (response.status >= 500 || response.status === 429) {
                    throw Object.assign(new Error('Session renewal is temporarily unavailable. Please retry.'), {status: response.status});
                }
                clear();
                throw expired();
            }
            storeTokens(payload, true);
        })().finally(() => { refreshing = null; });
        return refreshing;
    }
    async function request(path, options = {}, bodyFactory = null) {
        path = privatePath(path);
        const owner = identity();
        if (!owner) throw expired();
        const send = () => {
            const headers = new Headers(options.headers || {});
            headers.set('Authorization', `Bearer ${accessToken()}`);
            return global.fetch(path, {...options, headers, credentials: 'same-origin', cache: 'no-store',
                ...(bodyFactory ? {body: bodyFactory()} : {})});
        };
        const before = accessToken();
        let response = await send();
        if (response.status === 401 && refreshToken()) {
            // Another simultaneous request may already have renewed this token.
            if (before === accessToken()) await refreshAccess();
            if (owner !== identity()) throw changed();
            response = await send();
        }
        if (owner !== identity()) throw changed();
        if (response.status === 401) clear();
        return response;
    }
    async function logout() {
        const owner = identity();
        let revoked = true;
        try {
            if (owner && refreshToken()) {
                const response = await request('/api/auth/logout/', {
                    method: 'POST', headers: {'Content-Type': 'application/json'}
                }, () => JSON.stringify({refresh: refreshToken()}));
                revoked = response.status === 204;
            }
        } catch (_) { revoked = false; }
        finally { if (owner === identity()) clear(); }
        return revoked;
    }
    global.M1Session = {accessToken, identity, storeTokens, clear, request, logout};
    if (typeof module !== 'undefined' && module.exports) module.exports = global.M1Session;
})(typeof window !== 'undefined' ? window : globalThis);
