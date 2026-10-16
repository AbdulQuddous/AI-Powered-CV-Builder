"use strict";

/*
 * M9 — CV Dashboard
 *
 * Uses existing APIs only.
 * No database access.
 * No CV schema modifications.
 * No rendering or AI business logic.
 */

const TOKEN_KEY = "cv_access";

const state = {
    cvs: [],
    loading: false,
    toastTimer: null,
    creating: false,
    duplicating: new Set(),
    listGeneration: 0,
    eventsRegistered: false,
    registering: false,
    signingIn: false,
    signingOut: false,
    createMode: 'manual',
};

const profile = {generation: 0, loaded: null, loading: false, saving: false, saved: false};
const sessionList = {generation: 0, busy: false, next: null};

const $ = (id) => document.getElementById(id);


// ======================================================
// 1. UTILITIES
// ======================================================

function getToken() {
    return window.M1Session ? window.M1Session.accessToken() : sessionStorage.getItem(TOKEN_KEY);
}

function getAuthIdentity() {
    return window.M1Session ? window.M1Session.identity() : getToken();
}


function escapeHTML(value) {
    const element = document.createElement("span");

    element.textContent = String(value ?? "");

    return element.innerHTML;
}


function formatDate(value) {
    if (!value) {
        return "Not available";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Not available";
    }

    return new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    }).format(date);
}


function dateValue(value) {
    const timestamp = new Date(value || 0).getTime();

    return Number.isFinite(timestamp) ? timestamp : 0;
}


function getTemplateId(cv) {
    return String(
        cv.data?.meta?.template_id ||
        cv.template_id ||
        "modern"
    );
}


function getTargetRole(cv) {
    return String(
        cv.data?.meta?.target_role ||
        cv.target_role ||
        "General Resume"
    );
}

function getCareerLevel(cv) {
    const level = cv.data?.meta?.career_level || cv.career_level || "";
    return ({fresher: "Fresher", experienced: "Experienced", other: "Other"})[level] || "Not specified";
}


function getTemplateLabel(templateId) {
    const label = String(templateId)
        .replace(/[_-]/g, " ")
        .replace(/\b\w/g, (character) => {
            return character.toUpperCase();
        });

    return `${label} Template`;
}


function showToast(message) {
    const toast = $("toast");

    toast.textContent = message;
    toast.classList.remove("hidden");

    clearTimeout(state.toastTimer);

    state.toastTimer = setTimeout(() => {
        toast.classList.add("hidden");
    }, 3500);
}


function showFeedback(message) {
    const element = $("feedback");

    element.textContent = message;
    element.classList.remove("hidden");
}


function clearFeedback() {
    $("feedback").classList.add("hidden");
    $("feedback").textContent = "";
}


function showFormError(id, message) {
    const element = $(id);

    element.textContent = message;
    element.classList.remove("hidden");
}


function clearFormError(id) {
    const element = $(id);

    element.textContent = "";
    element.classList.add("hidden");
}


function setButtonBusy(button, busy, busyText) {
    if (busy) {
        button.dataset.originalText = button.textContent;
        button.textContent = busyText;
        button.disabled = true;
    } else {
        button.textContent =
            button.dataset.originalText || button.textContent;

        button.disabled = false;
    }
}


// ======================================================
// 2. MODAL MANAGEMENT
// ======================================================

function openModal(id) {
    $(id).classList.remove("hidden");

    document.body.style.overflow = "hidden";
    if (id === 'loginModal') $('loginEmail').focus();
    if (id === 'registerModal') $('registerName').focus();
}


function closeModal(id) {
    if (id === 'chatSessionsModal') { sessionList.generation++; sessionList.busy = false; }
    $(id).classList.add("hidden");

    if (id === "previewModal") {
        $("previewFrame").removeAttribute("srcdoc");
    }

    const anotherModal = document.querySelector(
        ".dashboard-modal:not(.hidden)"
    );

    if (!anotherModal) {
        document.body.style.overflow = "";
    }
}


// ======================================================
// 3. AUTHENTICATION
// ======================================================

function updateAuthUI() {
    const signedIn = Boolean(getToken());

    $("authStatus").textContent = signedIn
        ? "Signed in"
        : "Not signed in";

    $("logoutBtn").classList.toggle(
        "hidden",
        !signedIn
    );
    $('profileBtn').classList.toggle('hidden', !signedIn);
}


function clearSession(preserveResume = false) {
    const resumeURL = preserveResume ? new URL(window.location.href) : null;
    state.listGeneration++;
    resetProfile();
    window.M9Crud?.reset();
    window.M6Review?.reset();
    closeModal("aiModal");
    window.M4Import?.reset();
    closeModal("importModal");
    resetChat();
    closeModal('chatSessionsModal');
    $('chatSessionsRows').replaceChildren();
    if (resumeURL) window.history.replaceState(null, '', resumeURL);
    sessionStorage.removeItem("m9_chat_sessions");
    if (window.M1Session) window.M1Session.clear();
    else sessionStorage.removeItem(TOKEN_KEY);

    state.cvs = [];

    updateAuthUI();
    updateStatistics();
    populateTemplateFilter();
    renderCVs();
}


function requireLogin() {
    if (!getToken()) {
        openModal("loginModal");
        return false;
    }

    return true;
}

function authErrorMessage(payload, fallback) {
    const details = payload?.error?.details || payload?.detail || payload?.message;
    function messages(value, field = '') {
        if (typeof value === 'string') return [field ? `${field}: ${value}` : value];
        if (Array.isArray(value)) return value.flatMap(item => messages(item, field));
        if (!value || typeof value !== 'object') return [];
        return Object.entries(value).flatMap(([key, item]) => messages(item, key.replaceAll('_', ' ')));
    }
    return messages(details).join(' · ') || fallback;
}

function profileControls() {
    const changed = profile.loaded && $('profileName').value.trim() !== profile.loaded.full_name;
    if (profile.saved && changed && !profile.saving) {
        profile.saved = false;
        $('profileStatus').textContent = 'Unsaved changes.';
    }
    $('profileFields').disabled = profile.loading || profile.saving || !profile.loaded;
    $('profileSubmit').disabled = profile.loading || profile.saving || !profile.loaded || !changed;
    $('profileSubmit').textContent = profile.saving ? 'Saving...' : profile.saved ? 'Saved ✓' : 'Save profile';
    $('profileCancel').disabled = profile.saving;
    $('profileCancel').textContent = profile.saved ? 'Done' : 'Close';
    $('profileCancel').classList.toggle('profile-done', profile.saved);
    $('profileStatus').classList.toggle('profile-status-success', profile.saved);
    $('profileRetry').disabled = profile.loading || profile.saving;
    $('profileModal').setAttribute('aria-busy', String(profile.loading || profile.saving));
    if (profile.saving) $('profileModal').focus();
}

function resetProfile() {
    profile.generation++;
    profile.loaded = null;
    profile.loading = profile.saving = false;
    profile.saved = false;
    $('profileName').value = $('profileEmail').value = '';
    $('profileStatus').textContent = '';
    clearFormError('profileError');
    $('profileRetry').classList.add('hidden');
    profileControls();
    closeModal('profileModal');
}

function closeProfile() {
    if (profile.saving) return;
    resetProfile();
    if (getToken()) $('profileBtn').focus();
}

function adoptProfile(data) {
    if (!Number.isSafeInteger(data?.user_id) || typeof data.email !== 'string' || typeof data.full_name !== 'string') {
        throw new Error('The account service returned an invalid profile. Please retry.');
    }
    profile.loaded = data;
    $('profileEmail').value = data.email;
    $('profileName').value = data.full_name;
}

async function openProfile() {
    if (!requireLogin() || profile.loading || profile.saving) return;
    resetProfile();
    const generation = profile.generation, access = getAuthIdentity();
    profile.loading = true;
    $('profileStatus').textContent = 'Loading your profile...';
    profileControls();
    openModal('profileModal');
    $('profileCancel').focus();
    try {
        const response = await apiFetch('/api/auth/me/');
        const data = await response.json();
        if (generation !== profile.generation || access !== getAuthIdentity()) return;
        adoptProfile(data);
        $('profileStatus').textContent = 'Change your full name to enable Save profile.';
    } catch (error) {
        if (generation !== profile.generation || access !== getAuthIdentity()) return;
        showFormError('profileError', authErrorMessage(error.details,
            error.status ? error.message : 'Could not load your profile. Check your connection and retry.'));
        $('profileStatus').textContent = '';
        $('profileRetry').classList.remove('hidden');
    } finally {
        if (generation === profile.generation && access === getAuthIdentity()) {
            profile.loading = false;
            profileControls();
            if (profile.loaded) $('profileName').focus();
        }
    }
}

async function saveProfile(event) {
    event.preventDefault();
    if (profile.loading || profile.saving || !profile.loaded || !requireLogin()) return;
    const fullName = $('profileName').value.trim();
    if (fullName === profile.loaded.full_name) return;
    if (fullName.length > 150) {
        showFormError('profileError', 'Full name must be 150 characters or fewer.');
        return;
    }
    const generation = profile.generation, access = getAuthIdentity();
    profile.saving = true;
    profile.saved = false;
    clearFormError('profileError');
    $('profileStatus').textContent = 'Saving your profile...';
    profileControls();
    try {
        const response = await apiFetch('/api/auth/me/', {
            method: 'PATCH', body: JSON.stringify({full_name: fullName})
        });
        const data = await response.json();
        if (generation !== profile.generation || access !== getAuthIdentity()) return;
        adoptProfile(data);
        profile.saved = true;
        $('profileStatus').textContent = '✓ Profile updated successfully. Click Done to return to your dashboard.';
        showToast('Profile updated successfully.');
    } catch (error) {
        if (generation !== profile.generation || access !== getAuthIdentity()) return;
        showFormError('profileError', authErrorMessage(error.details,
            error.status ? error.message : 'Could not save your profile. Check your connection and retry.'));
        $('profileStatus').textContent = '';
    } finally {
        if (generation === profile.generation && access === getAuthIdentity()) {
            profile.saving = false;
            profileControls();
            if (profile.saved) $('profileCancel').focus();
        }
    }
}

function showAuthForm(mode) {
    if (state.registering || state.signingIn) return;
    const registering = mode === 'register';
    clearFormError('loginError');
    clearFormError('registerError');
    $('loginPassword').value = '';
    $('registerPassword').value = '';
    $('registerConfirm').value = '';
    if (registering && !$('registerEmail').value) $('registerEmail').value = $('loginEmail').value;
    closeModal(registering ? 'loginModal' : 'registerModal');
    openModal(registering ? 'registerModal' : 'loginModal');
    $(registering ? 'registerName' : 'loginEmail').focus();
}

async function handleRegister(event) {
    event.preventDefault();
    if (state.registering) return;
    clearFormError('registerError');
    const password = $('registerPassword').value;
    if (password !== $('registerConfirm').value) {
        showFormError('registerError', 'Passwords do not match.');
        $('registerConfirm').focus();
        return;
    }
    const email = $('registerEmail').value.trim();
    state.registering = true;
    setButtonBusy($('registerSubmit'), true, 'Creating account...');
    $('backToLogin').disabled = true;
    try {
        const response = await fetch('/api/auth/register/', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, full_name: $('registerName').value.trim(), password}),
        }).catch(() => { throw new Error('Could not connect. Check your connection and try again.'); });
        let payload = {};
        try { payload = await response.json(); } catch (_) { /* Use a readable fallback below. */ }
        if (!response.ok) throw new Error(authErrorMessage(payload,
            response.status === 429 ? 'Too many attempts. Please wait and try again.' : 'Unable to create your account. Please try again.'));
        $('loginEmail').value = payload.email || email;
        $('registerForm').reset();
        state.registering = false;
        showAuthForm('login');
        showToast('Account created. Sign in to start building your CV.');
    } catch (error) {
        showFormError('registerError', error.message || 'Unable to create your account. Please try again.');
    } finally {
        state.registering = false;
        setButtonBusy($('registerSubmit'), false);
        $('backToLogin').disabled = false;
    }
}


async function handleLogin(event) {
    event.preventDefault();
    if (state.signingIn) return;
    state.signingIn = true;

    const email = $("loginEmail").value.trim();
    const password = $("loginPassword").value;

    const button = $("loginSubmit");

    clearFormError("loginError");

    setButtonBusy(button, true, "Signing in...");
    $('openRegister').disabled = true;

    try {
        const response = await fetch("/api/auth/login/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            credentials: "same-origin",
            body: JSON.stringify({
                email,
                password,
            }),
        });

        const payload = await response.json();

        if (!response.ok) {
            throw new Error(
                authErrorMessage(payload, "Invalid email or password.")
            );
        }

        const token =
            payload.access ||
            payload.data?.access;

        if (!token) {
            throw new Error(
                "Login succeeded but no access token was returned."
            );
        }

        if (window.M1Session) window.M1Session.storeTokens({access: token, refresh: payload.refresh || payload.data?.refresh});
        else sessionStorage.setItem(TOKEN_KEY, token);

        $("loginPassword").value = "";

        closeModal("loginModal");

        updateAuthUI();

        showToast("Successfully signed in.");

        await loadCVs();
        await resumeDashboardAction();

    } catch (error) {
        showFormError(
            "loginError",
            error.message || "Unable to sign in."
        );

    } finally {
        state.signingIn = false;
        $('openRegister').disabled = false;
        setButtonBusy(button, false);
    }
}


async function logout() {
    if (state.signingOut) return;
    state.signingOut = true;
    $('logoutBtn').disabled = true;
    const owner = getAuthIdentity();
    let revoked = true;
    try {
        if (window.M1Session) revoked = await window.M1Session.logout();
        if (getToken() && getAuthIdentity() !== owner) return;
    clearSession();

    closeModal("createModal");
    closeModal("previewModal");

    showToast(revoked ? 'You have signed out.' : 'Signed out on this device. Server session revocation could not be confirmed.');

    openModal("loginModal");
    } finally {
        state.signingOut = false;
        $('logoutBtn').disabled = false;
    }
}


// ======================================================
// 4. SHARED API CLIENT
// ======================================================

function apiErrorMessage(payload, status) {
    const labels = {name: 'CV name', target_role: 'Target role', career_level: 'Career level',
        template_id: 'Template', data: 'CV data', non_field_errors: ''};
    function messages(value, path = '') {
        if (typeof value === 'string') return [path ? `${path}: ${value}` : value];
        if (Array.isArray(value)) return value.flatMap(item => messages(item, path));
        if (value && typeof value === 'object') {
            // Canonical document errors carry a path and a human-readable message.
            if (typeof value.message === 'string') return messages(value.message, value.path || path);
            return Object.entries(value).flatMap(([key, item]) =>
                messages(item, labels[key] ?? key.replace(/_/g, ' ')));
        }
        return [];
    }
    for (const value of [payload?.detail, payload?.message, payload?.error]) {
        if (typeof value === 'string' && value) return value;
    }
    const details = payload?.error?.details ?? payload;
    const errors = messages(details).filter(Boolean);
    return errors.length ? errors.slice(0, 5).join(' ') : `Request failed (${status}).`;
}

async function apiFetch(path, options = {}) {
    const token = getToken();

    if (!token) {
        throw new Error(
            "Please sign in to access your CVs."
        );
    }

    const headers = new Headers(
        options.headers || {}
    );

    headers.set(
        "Authorization",
        `Bearer ${token}`
    );

    if (
        options.body !== undefined &&
        !(options.body instanceof FormData)
    ) {
        headers.set(
            "Content-Type",
            "application/json"
        );
    }

    let response;
    try {
        const transport = window.M1Session ? window.M1Session.request : fetch;
        response = await transport(path, {...options, headers, credentials: 'same-origin'});
    } catch (error) {
        if (error.status === 401) { clearSession(true); openModal('loginModal'); }
        throw error;
    }

    if (response.status === 401) {
        clearSession(true);
        openModal("loginModal");

        throw Object.assign(new Error(
            "Your session has expired. Please sign in again."
        ), { status: 401 });
    }

    if (!response.ok) {
        let payload = {};

        try {
            payload = await response.json();
        } catch (_) {
            // The server may return a non-JSON error.
        }

        const message = apiErrorMessage(payload, response.status);

        throw Object.assign(new Error(message), { status: response.status, details: payload });
    }

    return response;
}


// ======================================================
// 5. LIST RESPONSE NORMALIZATION
// ======================================================

function normalizeListResponse(payload) {
    if (Array.isArray(payload)) {
        return {
            items: payload,
            next: null,
        };
    }

    const data = payload.data ?? payload;

    if (Array.isArray(data)) {
        return {
            items: data,
            next: payload.next || null,
        };
    }

    if (Array.isArray(data.results)) {
        return {
            items: data.results,
            next: data.next || null,
        };
    }

    if (Array.isArray(data.cvs)) {
        return {
            items: data.cvs,
            next: data.next || null,
        };
    }

    throw new Error(
        "Unexpected CV list response from the server."
    );
}


// ======================================================
// 6. FETCH USER CVS
// ======================================================

async function loadCVs() {
    if (!requireLogin()) {
        return;
    }

    if (state.loading) {
        return;
    }

    state.loading = true;
    const generation = state.listGeneration;
    const access = getAuthIdentity();

    clearFeedback();

    $("loadingState").classList.remove("hidden");
    $("cardsGrid").classList.add("hidden");
    $("emptyState").classList.add("hidden");

    try {
        let nextURL = "/api/cvs/";

        const allCVs = [];
        const visited = new Set();

        /*
         * Supports DRF pagination:
         *
         * {
         *   count,
         *   next,
         *   previous,
         *   results: [...]
         * }
         */

        while (nextURL) {
            const url = new URL(
                nextURL,
                window.location.origin
            );

            // Never send a JWT to an external origin.
            if (
                url.origin !== window.location.origin ||
                !url.pathname.startsWith("/api/cvs/")
            ) {
                throw new Error(
                    "Invalid CV pagination URL."
                );
            }

            const requestURL =
                url.pathname + url.search;

            if (visited.has(requestURL)) {
                throw new Error(
                    "Repeated CV pagination URL."
                );
            }

            visited.add(requestURL);

            const response = await apiFetch(
                requestURL
            );

            const payload = await response.json();

            const page = normalizeListResponse(
                payload
            );

            allCVs.push(...page.items);

            nextURL = page.next;
        }

        if (generation !== state.listGeneration || access !== getAuthIdentity()) return;
        // Each CV ID must be a valid integer.
        state.cvs = allCVs.filter((cv) => {
            return (
                cv &&
                Number.isSafeInteger(Number(cv.id)) &&
                Number(cv.id) > 0
            );
        });
        window.M6Review?.observe(state.cvs);

        updateStatistics();
        populateTemplateFilter();
        renderCVs();

    } catch (error) {
        showFeedback(
            error.message || "Unable to load CVs."
        );

        showToast("Could not load your CVs.");

    } finally {
        state.loading = false;

        $("loadingState").classList.add("hidden");
        $("cardsGrid").classList.remove("hidden");
    }
}


// ======================================================
// 7. DASHBOARD STATISTICS
// ======================================================

function updateStatistics() {
    const cvs = state.cvs;

    $("summaryTotal").textContent = cvs.length;

    const templates = new Set(
        cvs.map((cv) => getTemplateId(cv))
    );

    $("summaryTemplates").textContent =
        templates.size;

    if (cvs.length === 0) {
        $("summaryUpdated").textContent = "—";
        return;
    }

    const latestCV = [...cvs].sort((a, b) => {
        return (
            dateValue(b.updated_at) -
            dateValue(a.updated_at)
        );
    })[0];

    $("summaryUpdated").textContent = formatDate(
        latestCV.updated_at
    );
}


// ======================================================
// 8. TEMPLATE FILTER
// ======================================================

function populateTemplateFilter() {
    const select = $("templateFilter");

    const oldValue = select.value;

    select.replaceChildren();

    select.add(
        new Option("All Templates", "")
    );

    const templates = [
        ...new Set(
            state.cvs.map((cv) => getTemplateId(cv))
        ),
    ].sort();

    templates.forEach((templateId) => {
        select.add(
            new Option(
                getTemplateLabel(templateId),
                templateId
            )
        );
    });

    if (templates.includes(oldValue)) {
        select.value = oldValue;
    }
}


// ======================================================
// 9. SEARCH AND SORT
// ======================================================

function getFilteredCVs() {
    const search = $("searchInput")
        .value.trim().toLowerCase();

    const template = $("templateFilter").value;

    const sort = $("sortSelect").value;

    const filtered = state.cvs.filter((cv) => {
        const name = String(
            cv.name || ""
        ).toLowerCase();

        const role = getTargetRole(
            cv
        ).toLowerCase();

        const matchesSearch =
            name.includes(search) ||
            role.includes(search);

        const matchesTemplate =
            !template ||
            getTemplateId(cv) === template;

        return matchesSearch && matchesTemplate;
    });

    if (sort === "oldest") {
        filtered.sort((a, b) => {
            return (
                dateValue(a.updated_at) -
                dateValue(b.updated_at)
            );
        });

    } else if (sort === "name") {
        filtered.sort((a, b) => {
            return String(a.name || "").localeCompare(
                String(b.name || "")
            );
        });

    } else {
        filtered.sort((a, b) => {
            return (
                dateValue(b.updated_at) -
                dateValue(a.updated_at)
            );
        });
    }

    return filtered;
}


// ======================================================
// 10. RENDER CV CARDS
// ======================================================

function renderCVs() {
    const grid = $("cardsGrid");

    grid.replaceChildren();

    const cvs = getFilteredCVs();

    $("resultsCount").textContent =
        `Showing ${cvs.length} of ${state.cvs.length} CVs`;

    if (cvs.length === 0) {
        $("emptyState").classList.remove("hidden");

        const hasCVs = state.cvs.length > 0;

        $("emptyTitle").textContent = hasCVs
            ? "No matching CVs"
            : "No CVs yet";

        $("emptyDescription").textContent = hasCVs
            ? "Try changing your search or filters."
            : "Create your first CV to get started.";

        $("emptyCreate").classList.toggle(
            "hidden",
            hasCVs
        );

        return;
    }

    $("emptyState").classList.add("hidden");

    cvs.forEach((cv) => {
        const id = Number(cv.id);

        const name = escapeHTML(
            cv.name || `CV #${id}`
        );

        const role = escapeHTML(
            getTargetRole(cv)
        );
        const career = escapeHTML(getCareerLevel(cv));

        const template = escapeHTML(
            getTemplateLabel(getTemplateId(cv))
        );

        const updated = escapeHTML(
            formatDate(cv.updated_at)
        );

        const card = document.createElement("article");

        card.className = "cv-card";

        card.innerHTML = `
            <div class="flex items-start justify-between gap-3">

                <div
                    class="flex h-14 w-14 items-center
                           justify-center rounded-2xl
                           bg-indigo-50 text-3xl"
                >
                    📄
                </div>

                <span
                    class="rounded-full bg-emerald-50
                           px-3 py-1 text-xs
                           font-semibold text-emerald-700"
                >
                    Saved
                </span>

            </div>

            <div class="mt-6 flex-1">

                <h3
                    class="text-lg font-bold
                           leading-snug text-slate-900"
                >
                    ${name}
                </h3>

                <p class="mt-2 text-sm text-slate-500">
                    ${role}
                </p>
                <p class="mt-2 text-sm text-slate-500">Career level: ${career}</p>

                <div class="mt-4 flex flex-wrap gap-2">

                    <span
                        class="rounded-lg bg-indigo-50
                               px-3 py-1.5 text-xs
                               font-medium text-indigo-700"
                    >
                        ${template}
                    </span>

                </div>

                <p class="mt-5 text-xs text-slate-400">
                    Updated ${updated}
                </p>

            </div>

            <div
                class="mt-6 grid grid-cols-3 gap-2
                       border-t border-slate-100 pt-5"
            >

                <button
                    type="button"
                    data-action="edit"
                    data-id="${id}"
                    class="rounded-lg bg-indigo-600
                           px-2 py-2.5 text-sm
                           font-semibold text-white
                           hover:bg-indigo-700"
                >
                    Edit
                </button>

                <button
                    type="button"
                    data-action="view"
                    data-id="${id}"
                    class="rounded-lg border
                           border-slate-200
                           px-2 py-2.5 text-sm
                           font-medium
                           hover:bg-slate-50"
                >
                    View
                </button>

                <button
                    type="button"
                    data-action="duplicate"
                    data-id="${id}"
                    class="rounded-lg border
                           border-slate-200
                           px-2 py-2.5 text-sm
                           font-medium
                           hover:bg-slate-50"
                >
                    Duplicate
                </button>

            </div>
        `;

        const operations = document.createElement("div");
        operations.className = "mt-3 grid grid-cols-2 gap-2";
        for (const [action, label] of [["versions", "Version history"], ["delete", "Delete"]]) {
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.action = action;
            button.dataset.id = id;
            button.className = action === "delete" ? "danger-outline-button" : "secondary-button";
            button.textContent = label;
            button.setAttribute("aria-label", `${label} for ${cv.name || `CV #${id}`}`);
            operations.appendChild(button);
        }
        card.appendChild(operations);

        const aiButton = document.createElement("button");
        aiButton.type = "button";
        aiButton.className = "secondary-button mt-3";
        aiButton.dataset.action = "ai";
        aiButton.dataset.id = id;
        aiButton.textContent = "Continue with AI";
        card.appendChild(aiButton);
        const reviewAI = document.createElement("button");
        reviewAI.type = "button";
        reviewAI.className = "secondary-button mt-3";
        reviewAI.dataset.action = "intelligence";
        reviewAI.dataset.id = id;
        reviewAI.textContent = "AI Review";
        card.appendChild(reviewAI);
        const remembered = rememberedChats()[String(id)];
        if (remembered) {
            const reviewButton = document.createElement("button");
            reviewButton.type = "button";
            reviewButton.className = "secondary-button mt-3";
            reviewButton.textContent = "Review AI chat";
            reviewButton.addEventListener("click", () => openAIChat(id, remembered));
            card.appendChild(reviewButton);
        }
        grid.appendChild(card);
    });
}


// ======================================================
// 11. EDIT EXISTING CV — M7
// ======================================================

function editCV(id) {
    window.location.href = `/cvs/${id}/edit/`;
}


// ======================================================
// 12. VIEW CV — M8
// ======================================================

async function viewCV(id) {
    try {
        /*
         * M8 preview requires JWT.
         * A normal iframe URL cannot send our Bearer token.
         *
         * Therefore:
         * 1. Fetch HTML using Authorization header.
         * 2. Display the returned HTML in a sandboxed iframe.
         */

        const response = await apiFetch(
            `/api/cvs/${id}/preview/`
        );

        const html = await response.text();

        const baseTag =
            `<base href="${window.location.origin}/">`;

        let previewHTML = html;

        if (/<head[^>]*>/i.test(html)) {
            previewHTML = html.replace(
                /<head[^>]*>/i,
                (match) => match + baseTag
            );
        } else {
            previewHTML = baseTag + html;
        }

        $("previewFrame").srcdoc = previewHTML;

        openModal("previewModal");

    } catch (error) {
        showToast(
            error.message || "Could not preview CV."
        );
    }
}


// ======================================================
// 13. DUPLICATE CV — M2
// ======================================================

async function duplicateCV(id, button) {
    if (state.duplicating.has(id) || !requireLogin()) return;
    state.duplicating.add(id);
    const access = getAuthIdentity();
    setButtonBusy(button, true, "Copying...");

    try {
        const response = await apiFetch(
            `/api/cvs/${id}/duplicate/`,
            {
                method: "POST",
                body: JSON.stringify({}),
            }
        );

        const duplicate = await response.json();
        if (access !== getAuthIdentity()) return;
        if (!Number.isSafeInteger(duplicate.id) || duplicate.id <= 0) {
            throw new Error("The copy may have been created. Refresh the dashboard to find it.");
        }
        state.listGeneration++;
        state.cvs.push(duplicate);
        updateStatistics();
        populateTemplateFilter();
        renderCVs();

        await loadCVs();
        if (access === getAuthIdentity()) {
            showToast(`Created “${duplicate.name}” (CV #${duplicate.id}).`);
        }

    } catch (error) {
        showToast(
            error.message || "Could not duplicate CV."
        );

    } finally {
        state.duplicating.delete(id);
        setButtonBusy(button, false);
    }
}


// ======================================================
// 14. LOAD AVAILABLE TEMPLATES — M3
// ======================================================

async function loadCreateTemplates() {
    const select = $("templateId");

    try {
        const response = await apiFetch(
            "/api/templates/"
        );

        const payload = await response.json();

        const templates =
            Array.isArray(payload)
                ? payload
                : Array.isArray(payload.results)
                    ? payload.results
                    : Array.isArray(payload.data)
                        ? payload.data
                        : Array.isArray(payload.data?.results)
                            ? payload.data.results
                            : [];

        if (!templates.length) {
            return;
        }

        select.replaceChildren();

        templates.forEach((template) => {
            const id = String(
                template.id || template.slug || ""
            );

            if (!id) {
                return;
            }

            select.add(
                new Option(
                    template.name || id,
                    id
                )
            );
        });

        const modernOption = [...select.options].find(
            (option) => option.value === "modern"
        );

        if (modernOption) {
            select.value = "modern";
        }

    } catch (error) {
        /*
         * Template discovery is optional.
         * Keep the default Modern option.
         */
        console.warn(
            "Template list unavailable:",
            error.message
        );
    }
}


// ======================================================
// 15. CREATE NEW CV — M2
// ======================================================

async function openCreateCV(mode = 'manual') {
    if (!requireLogin()) {
        return;
    }

    $("createForm").reset();
    state.createMode = mode;
    $('createTitle').textContent = mode === 'ai' ? 'Create CV with AI' : 'Create new CV';
    $('createSubmit').textContent = mode === 'ai' ? 'Start AI interview' : 'Create CV';

    clearFormError("createError");

    openModal("createModal");

    await loadCreateTemplates();
}


async function handleCreateCV(event) {
    event.preventDefault();
    if (state.creating || !requireLogin()) return;

    const button = $("createSubmit");

    clearFormError("createError");

    const payload = {
        name: $("cvName").value.trim(),

        target_role: $("targetRole").value.trim(),

        career_level: $("careerLevel").value,

        template_id: $("templateId").value,

        data: {},
    };

    if (!payload.name || !payload.target_role) {
        showFormError(
            "createError",
            "Please enter a CV name and target role."
        );

        return;
    }

    setButtonBusy(button, true, "Creating...");
    state.creating = true;
    const access = getAuthIdentity();

    try {
        if (state.createMode === 'ai') {
            await openAIChat(null, null, {cv_name: payload.name, target_role: payload.target_role,
                career_level: payload.career_level, template_id: payload.template_id});
            if (access === getAuthIdentity() && chat.session) closeModal('createModal');
            return;
        }
        const response = await apiFetch(
            "/api/cvs/",
            {
                method: "POST",
                body: JSON.stringify(payload),
            }
        );

        const result = await response.json();
        if (access !== getAuthIdentity()) return;

        const createdCV =
            result.data?.id
                ? result.data
                : result.cv?.id
                    ? result.cv
                    : result;

        const createdId = Number(createdCV.id);

        if (!Number.isSafeInteger(createdId) || createdId <= 0) {
            throw new Error(
                "CV created, but the API did not return a valid ID. " +
                "Refresh the dashboard to find your new CV."
            );
        }

        closeModal("createModal");

        showToast("CV created successfully.");

        // Open your existing M7 editor.
        editCV(createdId);

    } catch (error) {
        showFormError(
            "createError",
            error.message || "Could not create CV."
        );

    } finally {
        state.creating = false;
        setButtonBusy(button, false);
    }
}


// ======================================================
// 16. CARD ACTION HANDLER
// ======================================================

async function handleCardClick(event) {
    const button = event.target.closest(
        "button[data-action]"
    );

    if (!button) {
        return;
    }

    const id = Number(button.dataset.id);

    if (!Number.isSafeInteger(id) || id <= 0) {
        return;
    }

    const action = button.dataset.action;

    if (action === "delete" || action === "versions") {
        const cv = state.cvs.find(item => Number(item.id) === id);
        if (!cv) return;
        if (action === "delete") window.M9Crud.openDelete(cv, button);
        else await window.M9Crud.openHistory(cv, button);
    } else if (action === "intelligence") {
        await window.M6Review.open(id);
    } else if (action === "ai") {
        await openAIChat(id);

    } else if (action === "edit") {
        editCV(id);

    } else if (action === "view") {
        await viewCV(id);

    } else if (action === "duplicate") {
        await duplicateCV(id, button);
    }
}

function onCVDeleted(id) {
    state.listGeneration++;
    state.cvs = state.cvs.filter(cv => Number(cv.id) !== id);
    rememberChat(id, null);
    if (Number(chat.cvId) === id) resetChat();
    window.M6Review?.observe(state.cvs);
    updateStatistics();
    populateTemplateFilter();
    renderCVs();
}

function onCVRestored(cv) {
    state.listGeneration++;
    state.cvs = state.cvs.map(item => Number(item.id) === Number(cv.id) ? cv : item);
    window.M6Review?.observe(state.cvs);
    updateStatistics(); populateTemplateFilter(); renderCVs();
}


// M9 only renders M5 responses; it never interprets cv_updates.
const chat = { session: null, cvId: null, busy: false, generation: 0, pending: null, openRequest: null, draft: null, review: null };

function rememberedChats() {
    try { return JSON.parse(sessionStorage.getItem("m9_chat_sessions") || "{}") || {}; }
    catch (_) { return {}; }
}

function rememberChat(cvId, id) {
    const sessions = rememberedChats();
    if (id) sessions[String(cvId)] = id;
    else delete sessions[String(cvId)];
    sessionStorage.setItem("m9_chat_sessions", JSON.stringify(sessions));
}

function resetChat() {
    chat.generation++;
    chat.session = null;
    chat.pending = null;
    chat.openRequest = null;
    clearChatReview();
    chat.busy = false;
    $("chatHistory").replaceChildren();
    $("chatInput").value = "";
    closeModal("chatModal");
    const url = new URL(window.location.href);
    url.searchParams.delete("chat");
    window.history.replaceState(null, "", url);
}

function chatBusy(busy) {
    chat.busy = busy;
    const inactive = !chat.session || chat.session.status !== "active";
    $("chatInput").disabled = busy || inactive;
    $("chatSend").disabled = busy || inactive;
    $("chatRetry").disabled = busy;
    $("chatSave").disabled = busy;
    $("chatThinking").classList.toggle("hidden", !busy);
    for (const id of ['chatSkip', 'chatBack', 'chatProgress']) $(id).disabled = busy || inactive;
    for (const id of ['chatDraft', 'chatFinalReview', 'chatApplyReview', 'chatDiscardReview', 'chatExternalApproval', 'chatReopen', 'chatLatest']) $(id).disabled = busy;
}

function appendChatMessage(role, content) {
    if (!["user", "assistant"].includes(role)) return;
    const bubble = document.createElement("div");
    bubble.className = `chat-message chat-message-${role}`;
    const label = document.createElement("strong");
    label.textContent = role === "user" ? "You" : "Assistant";
    bubble.append(label, document.createTextNode(String(content || "")));
    $("chatHistory").appendChild(bubble);
    $("chatHistory").scrollTop = $("chatHistory").scrollHeight;
}

function renderChatSession(session) {
    chat.session = session;
    chat.cvId = session.cv_id;
    $("chatHistory").replaceChildren();
    (session.messages || []).forEach(message => appendChatMessage(message.role, message.content));
    const cv = state.cvs.find(item => Number(item.id) === Number(session.cv_id));
    $("chatCVName").textContent = cv?.name || (session.cv_id ? `CV #${session.cv_id}` : "New AI conversation");
    const completed = session.status === "completed";
    $("chatStatus").textContent = completed ? "Collection complete" : session.status === "archived" ? "Conversation archived" : session.current_section === "review" ? "Review — you can send corrections" : `Current section: ${session.current_section}`;
    $("chatComplete").classList.toggle("hidden", !completed);
    $("chatSave").classList.toggle("hidden", !completed);
    $("chatDraft").classList.toggle("hidden", !completed);
    $('chatReopen').classList.toggle('hidden', !completed || Boolean(session.conversation_state?.chat_saved_cv_id || session.conversation_state?.edit_saved_cv_id));
    $("chatEditor").classList.toggle("hidden", !completed || !session.cv_id);
    if (session.cv_id) $("chatEditor").href = `/cvs/${session.cv_id}/edit/`;
    chatBusy(chat.busy);
}

function chatError(error) {
    const messages = {
        401: "Your session has expired. Please sign in again.",
        404: "This conversation is unavailable or does not belong to your account.",
        409: "This conversation changed or is no longer active. Reopen it to load the latest messages.",
        429: "Too many requests. Please wait before retrying.",
        502: "The assistant is temporarily unavailable. Please retry shortly.",
        500: "Something went wrong. Please try again later."
    };
    $("chatError").textContent = error.status === 400
        ? error.message || 'Please correct the supplied details before continuing.'
        : messages[error.status] || (chat.session
            ? "Unable to reach the conversation service. Your message is preserved; please retry."
            : "Unable to open the conversation. Your selections are preserved; please retry.");
    $("chatError").classList.remove("hidden");
    $("chatRetry").classList.toggle("hidden", [400, 401, 404, 409].includes(error.status));
}

async function getChatSession(id) {
    const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(id)}/`);
    return response.json();
}

async function openSavedChats() {
    if (!requireLogin() || sessionList.busy) return;
    sessionList.generation++;
    sessionList.next = '/api/chat/sessions/';
    $('chatSessionsRows').replaceChildren();
    openModal('chatSessionsModal');
    $('chatSessionsClose').focus();
    await loadSavedChatPage();
}

async function loadSavedChatPage() {
    if (sessionList.busy || !sessionList.next || !requireLogin()) return;
    const generation = sessionList.generation;
    sessionList.busy = true;
    $('chatSessionsMore').disabled = true;
    $('chatSessionsStatus').textContent = 'Loading your conversations...';
    clearFormError('chatSessionsError');
    try {
        const url = new URL(sessionList.next, window.location.origin);
        if (url.origin !== window.location.origin || url.pathname !== '/api/chat/sessions/') throw new Error('Invalid conversation page.');
        const response = await apiFetch(url.pathname + url.search);
        const page = normalizeListResponse(await response.json());
        if (generation !== sessionList.generation) return;
        for (const session of page.items) {
            if (!/^[0-9a-f-]{36}$/i.test(session.id)) continue;
            const button = document.createElement('button');
            button.type = 'button'; button.className = 'secondary-button w-full mt-3 text-left';
            const cv = state.cvs.find(item => Number(item.id) === Number(session.cv_id));
            button.textContent = `${cv?.name || session.cv_name || 'CV interview'} · ${session.status} · ${formatDate(session.updated_at)}`;
            button.addEventListener('click', () => {
                closeModal('chatSessionsModal');
                openAIChat(session.cv_id, session.id);
            });
            $('chatSessionsRows').appendChild(button);
        }
        sessionList.next = page.next;
        $('chatSessionsStatus').textContent = $('chatSessionsRows').children.length ? 'Choose a conversation to continue or review.' : 'No saved conversations yet.';
        $('chatSessionsMore').classList.toggle('hidden', !page.next);
        $('chatSessionsMore').textContent = 'Load more conversations';
    } catch (error) {
        if (generation !== sessionList.generation) return;
        showFormError('chatSessionsError', 'Could not load your conversations. Please retry.');
        $('chatSessionsStatus').textContent = '';
        $('chatSessionsMore').textContent = 'Retry loading';
        $('chatSessionsMore').classList.remove('hidden');
    } finally {
        if (generation === sessionList.generation) {
            sessionList.busy = false;
            $('chatSessionsMore').disabled = false;
        }
    }
}

async function resumeDashboardAction() {
    const query = new URLSearchParams(window.location.search);
    const sessionId = query.get('chat'), reviewId = query.get('review');
    if (query.has('import')) await window.M4Import?.resume();
    else if (sessionId && /^[0-9a-f-]{36}$/i.test(sessionId)) await openAIChat(null, sessionId);
    else if (reviewId && /^\d+$/.test(reviewId) && Number.isSafeInteger(Number(reviewId)) && Number(reviewId) > 0) await window.M6Review.open(Number(reviewId));
}

async function openAIChat(cvId, explicitId = null, initialValues = null) {
    if (!requireLogin() || chat.busy) return;
    const generation = ++chat.generation;
    chat.openRequest = {cvId, explicitId, initialValues: initialValues ? {...initialValues} : null};
    chat.session = null;
    chat.cvId = cvId;
    chat.pending = null;
    clearChatReview();
    $("chatInput").value = "";
    $("chatHistory").replaceChildren();
    $("chatStatus").textContent = "Opening conversation…";
    $("chatError").classList.add("hidden");
    $("chatRetry").classList.add("hidden");
    $("chatComplete").classList.add("hidden");
    $("chatEditor").classList.add("hidden");
    $("chatSave").classList.add("hidden");
    $("chatReopen").classList.add("hidden");
    $("chatLatest").classList.add("hidden");
    $("chatSaveStatus").classList.add("hidden");
    openModal("chatModal");
    chatBusy(true);
    try {
        let session;
        const remembered = initialValues ? null : explicitId || rememberedChats()[String(cvId)];
        if (remembered) {
            try { session = await getChatSession(remembered); }
            catch (error) {
                if (error.status !== 404 || explicitId) throw error;
                rememberChat(cvId, null);
            }
            if (!explicitId && session?.status !== "active") session = null;
        }
        if (generation !== chat.generation) return;
        if (!session) {
            const response = await apiFetch("/api/chat/sessions/", {
                method: "POST", body: JSON.stringify({ cv_id: cvId, ...(initialValues || {}) })
            });
            const created = await response.json();
            if (generation !== chat.generation) return;
            rememberChat(cvId, created.id);
            session = { ...created, messages: [{ role: "assistant", content: created.assistant_message }] };
        }
        if (generation !== chat.generation) return;
        renderChatSession(session);
        chat.openRequest = null;
        if (initialValues?.cv_name !== undefined) closeModal('createModal');
        const url = new URL(window.location.href);
        url.searchParams.set("chat", session.id);
        window.history.replaceState(null, "", url);
    } catch (error) {
        if (generation === chat.generation) {
            $('chatStatus').textContent = 'Conversation could not be opened.';
            if (error.status === 400 && initialValues?.cv_name !== undefined) {
                chat.openRequest = null;
                closeModal('chatModal');
                openModal('createModal');
                showFormError('createError', error.message || 'Please check your CV details.');
            } else {
                chatError(error);
            }
        }
    } finally {
        if (generation === chat.generation) {
            chatBusy(false);
            if (chat.session?.status === 'active') $('chatInput').focus();
        }
    }
}

async function sendChatMessage(event) {
    event?.preventDefault();
    if (chat.busy || !chat.session || chat.session.status !== "active") return;
    const text = $("chatInput").value.trim();
    if (!text) return;
    const requestId = chat.pending?.text === text ? chat.pending.requestId : window.crypto?.randomUUID?.();
    const generation = chat.generation;
    $("chatError").classList.add("hidden");
    $("chatRetry").classList.add("hidden");
    chatBusy(true);
    try {
        // Reconcile a failed/ambiguous POST before retrying to avoid duplicate messages.
        if (chat.pending) {
            const latest = await getChatSession(chat.session.id);
            if (generation !== chat.generation) return;
            const received = latest.messages.some(message => message.role === "user" && message.content === chat.pending.text && !chat.pending.ids.includes(message.id));
            renderChatSession(latest);
            if (received) {
                if (text === chat.pending.text) $("chatInput").value = "";
                chat.pending = null;
                return;
            }
            chat.pending = null;
            if (latest.status !== "active") return;
        }
        chat.pending = { text, ids: (chat.session.messages || []).map(message => message.id), requestId };
        appendChatMessage("user", text);
        const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(chat.session.id)}/messages/`, {
            method: "POST", body: JSON.stringify({ message: text, request_id: chat.pending.requestId, expected_updated_at: chat.session.updated_at })
        });
        const result = await response.json();
        if (generation !== chat.generation) return;
        // Store successful response locally before loading authoritative history.
        chat.session.messages.push({ role: "user", content: text }, {
            role: "assistant", content: result.assistant_message,
            next_action: result.next_action
        });
        chat.session.current_section = result.section;
        if (result.next_action === "complete") chat.session.status = "completed";
        if (result.next_action === "review") chat.session.current_section = "review";
        chat.pending = null;
        $("chatInput").value = "";
        renderChatSession(chat.session);
        clearChatReview();
        try {
            const latest = await getChatSession(chat.session.id);
            if (generation === chat.generation) renderChatSession(latest);
        } catch (_) { /* The successful response remains visible; refresh reloads history. */ }
    } catch (error) {
        if (generation === chat.generation) {
            renderChatSession(chat.session);
            if (error.status === 400) chat.pending = null;
            chatError(error);
        }
    } finally {
        if (generation === chat.generation) {
            chatBusy(false);
            if (!$("chatInput").disabled) $("chatInput").focus();
        }
    }
}

// ======================================================
// 17. REGISTER EVENTS
// ======================================================

function clearChatReview() {
    chat.draft = null; chat.review = null;
    $('chatDraftPanel').classList.add('hidden');
    $('chatExternalApproval').checked = false;
    $('chatDraftDetails').replaceChildren();
    $('chatReviewSuggestions').replaceChildren();
    $('chatReviewStatus').textContent = '';
    $('chatApplyReview').classList.add('hidden');
    $('chatDiscardReview').classList.add('hidden');
}

async function reopenCollectedChat() {
    if (chat.busy || chat.session?.status !== 'completed') return;
    const generation = chat.generation;
    chatBusy(true);
    try {
        const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(chat.session.id)}/reopen/`, {method: 'POST'});
        const session = await response.json();
        if (generation !== chat.generation) return;
        clearChatReview(); renderChatSession(session);
    } catch (error) { if (generation === chat.generation) chatError(error); }
    finally { if (generation === chat.generation) chatBusy(false); }
}

async function reviewChatDraft() {
    if (chat.busy || chat.session?.status !== 'completed') return;
    const generation = chat.generation;
    chatBusy(true);
    try {
        const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(chat.session.id)}/draft/`);
        const result = await response.json();
        if (generation !== chat.generation) return;
        clearChatReview(); chat.draft = result;
        for (const [section, value] of Object.entries(result.draft)) {
            if (section === 'schema_version') continue;
            const heading = document.createElement('h3'); heading.textContent = section.replaceAll('_', ' ');
            const content = document.createElement('p'); content.style.whiteSpace = 'pre-wrap';
            const describe = item => typeof item === 'object' && item !== null
                ? Object.entries(item).filter(([, v]) => v !== '' && v !== false && (!Array.isArray(v) || v.length))
                    .map(([k, v]) => `${k.replaceAll('_', ' ')}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' · ')
                : String(item || '');
            content.textContent = Array.isArray(value) ? value.map(describe).join('\n') : describe(value);
            $('chatDraftDetails').appendChild(heading); $('chatDraftDetails').appendChild(content);
        }
        $('chatDraftPanel').classList.remove('hidden');
    } catch (error) { if (generation === chat.generation) chatError(error); }
    finally { if (generation === chat.generation) chatBusy(false); }
}

async function requestChatFinalReview() {
    if (chat.busy || !chat.draft || chat.session?.status !== 'completed') return;
    if (!$('chatExternalApproval').checked) {
        $('chatReviewStatus').textContent = 'Please approve external processing first, or save without Gemini review.'; return;
    }
    const generation = chat.generation;
    chatBusy(true); $('chatReviewStatus').textContent = 'Reviewing your draft…';
    try {
        const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(chat.session.id)}/final-review/`, {
            method: 'POST', body: JSON.stringify({ approved_external_processing: true, fingerprint: chat.draft.fingerprint })
        });
        const result = await response.json();
        if (generation !== chat.generation) return;
        chat.review = result; $('chatReviewSuggestions').replaceChildren();
        const feedback = document.createElement('p'); feedback.textContent = result.result.overall_feedback;
        $('chatReviewSuggestions').appendChild(feedback);
        for (const text of [...result.result.suggestions, ...result.result.missing_information, ...result.result.warnings]) {
            const item = document.createElement('p'); item.textContent = text; $('chatReviewSuggestions').appendChild(item);
        }
        result.result.proposed_changes.forEach((change, index) => {
            const label = document.createElement('label');
            const check = document.createElement('input'); check.type = 'checkbox'; check.dataset.reviewIndex = String(index);
            label.appendChild(check); label.appendChild(document.createTextNode(` ${change.original} → ${change.replacement}. ${change.reason}`));
            $('chatReviewSuggestions').appendChild(label);
        });
        $('chatApplyReview').classList.toggle('hidden', !result.result.proposed_changes.length);
        $('chatDiscardReview').classList.remove('hidden');
        $('chatReviewStatus').textContent = result.cached ? 'Saved review reused. Choose any wording changes you approve.' : 'Review ready. Choose any wording changes you approve.';
    } catch (_) {
        if (generation === chat.generation) $('chatReviewStatus').textContent = 'Review unavailable. You can retry or save your CV without suggestions.';
    } finally { if (generation === chat.generation) chatBusy(false); }
}

async function decideChatReview(rejectAll) {
    if (chat.busy || !chat.review) return;
    const generation = chat.generation;
    const indexes = rejectAll ? [] : [...$('chatReviewSuggestions').querySelectorAll('input[data-review-index]')]
        .filter(node => node.checked).map(node => Number(node.dataset.reviewIndex));
    chatBusy(true);
    try {
        const response = await apiFetch(`/api/chat/sessions/${encodeURIComponent(chat.session.id)}/final-review/decisions/`, {
            method: 'POST', body: JSON.stringify({fingerprint: chat.review.fingerprint, accepted_indexes: indexes})
        });
        await response.json();
        if (generation === chat.generation) $('chatReviewStatus').textContent = indexes.length
            ? 'Selected changes approved. Save your CV to apply them.' : 'All wording changes rejected. Your collected wording is preserved.';
    } catch (_) {
        if (generation === chat.generation) $('chatReviewStatus').textContent = 'Could not record this decision. Review the latest draft before trying again.';
    } finally { if (generation === chat.generation) chatBusy(false); }
}

async function saveChatCV() {
    if (chat.busy || chat.session?.status !== "completed") return;
    const generation = chat.generation;
    chatBusy(true);
    $("chatThinking").classList.add("hidden");
    $("chatError").classList.add("hidden");
    $("chatRetry").classList.add("hidden");
    $("chatSaveStatus").classList.remove("hidden");
    $("chatSaveStatus").textContent = "Saving collected details…";
    try {
        const payload = { session_id: chat.session.id };
        if (chat.session.cv_id) {
            const response = await apiFetch(`/api/cvs/${chat.session.cv_id}/`);
            const cv = await response.json();
            if (generation !== chat.generation) return;
            payload.expected_version = chat.session.conversation_state?.existing_cv_version || cv.version;
        }
        const response = await apiFetch("/api/cvs/from-chat/", {
            method: "POST", body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (generation !== chat.generation) return;
        chat.session.cv_id = result.cv.id;
        chat.session.conversation_state = {...chat.session.conversation_state, chat_saved_cv_id: result.cv.id};
        rememberChat(result.cv.id, chat.session.id);
        rememberChat(null, null);
        renderChatSession(chat.session);
        $("chatSaveStatus").textContent = "Details saved. You can now view or edit your CV." +
            (result.warnings?.length ? " " + result.warnings.join(" ") : "");
        await loadCVs();
    } catch (error) {
        if (generation === chat.generation) {
            $('chatLatest').classList.toggle('hidden', error.status !== 409 || !chat.session.cv_id);
            $("chatSaveStatus").textContent = error.status === 409
                ? "The saved CV changed. Your proposed changes are retained. Use Open latest CV in a new chat to continue. Your earlier proposals remain in Resume AI chat."
                : error.status === 400
                    ? "Some collected details need clarification before they can be saved. " + error.message
                    : "Could not save the details. Please sign in if needed and try Save again.";
        }
    } finally {
        if (generation === chat.generation) chatBusy(false);
    }
}

function registerEvents() {
    if (state.eventsRegistered) return;
    state.eventsRegistered = true;
    window.M9Crud.init({fetch: apiFetch, requireLogin, openModal, closeModal,
        normalizeList: normalizeListResponse, onDeleted: onCVDeleted, onRestored: onCVRestored, notify: showToast});
    const ai = window.M6Api.create(apiFetch);
    window.M6Review.init({fetch: apiFetch, ai, requireLogin, openModal, refresh: loadCVs});
    window.M4Import.init({ fetch: apiFetch, ai, requireLogin, openModal, refresh: loadCVs });
    $("chatSave").addEventListener("click", saveChatCV);
    $('chatDraft').addEventListener('click', reviewChatDraft);
    $('chatReopen').addEventListener('click', reopenCollectedChat);
    $('chatLatest').addEventListener('click', () => {
        if (!chat.busy && chat.session?.cv_id) return openAIChat(chat.session.cv_id, null, {});
    });
    $('chatFinalReview').addEventListener('click', requestChatFinalReview);
    $('chatApplyReview').addEventListener('click', () => decideChatReview(false));
    $('chatDiscardReview').addEventListener('click', () => decideChatReview(true));
    for (const [id, command] of [['chatSkip', 'skip this question'], ['chatBack', 'undo'], ['chatProgress', 'show collected information']]) {
        $(id).addEventListener('click', () => {
            if (chat.busy || chat.session?.status !== 'active') return;
            $('chatInput').value = command; return sendChatMessage();
        });
    }
    $("createAI").addEventListener("click", () => openCreateCV('ai'));
    $('resumeChat').addEventListener('click', openSavedChats);
    $('chatSessionsMore').addEventListener('click', loadSavedChatPage);
    $("chatForm").addEventListener("submit", sendChatMessage);
    $("chatRetry").addEventListener("click", () => {
        if (chat.session) return sendChatMessage();
        const request = chat.openRequest;
        return openAIChat(request?.cvId ?? chat.cvId, request?.explicitId ?? null, request?.initialValues ?? null);
    });
    $("loginForm").addEventListener(
        "submit",
        handleLogin
    );
    $('openRegister').addEventListener('click', () => showAuthForm('register'));
    $('backToLogin').addEventListener('click', () => showAuthForm('login'));
    $('registerForm').addEventListener('submit', handleRegister);
    $('profileBtn').addEventListener('click', openProfile);
    $('profileForm').addEventListener('submit', saveProfile);
    $('profileName').addEventListener('input', profileControls);
    $('profileCancel').addEventListener('click', closeProfile);
    $('profileRetry').addEventListener('click', openProfile);

    $("createForm").addEventListener(
        "submit",
        handleCreateCV
    );

    $("logoutBtn").addEventListener(
        "click",
        logout
    );

    $("cardsGrid").addEventListener(
        "click",
        handleCardClick
    );

    $("searchInput").addEventListener(
        "input",
        renderCVs
    );

    $("templateFilter").addEventListener(
        "change",
        renderCVs
    );

    $("sortSelect").addEventListener(
        "change",
        renderCVs
    );

    $("refreshBtn").addEventListener(
        "click",
        loadCVs
    );

    [
        "heroCreate",
        "sidebarCreate",
        "emptyCreate",
    ].forEach((id) => {
        $(id).addEventListener(
            "click",
            openCreateCV
        );
    });

    document.querySelectorAll(
        "[data-close]"
    ).forEach((button) => {
        button.addEventListener("click", () => {
            closeModal(
                button.dataset.close
            );
        });
    });

    document.addEventListener(
        "keydown",
        (event) => {
            if (!$('profileModal').classList.contains('hidden') && event.key === 'Escape') {
                event.preventDefault();
                closeProfile();
                return;
            }
            const authModal = ['loginModal', 'registerModal', 'profileModal', 'chatSessionsModal',
                'chatModal', 'importModal', 'createModal', 'previewModal'].map($)
                .find(modal => !modal.classList.contains('hidden'));
            if (authModal && event.key === 'Tab') {
                const controls = [...authModal.querySelectorAll('input, button, textarea, select, a[href]')]
                    .filter(control => !control.disabled && !control.closest('fieldset:disabled') && !control.closest('.hidden') &&
                        (!control.getClientRects || control.getClientRects().length));
                const first = controls[0], last = controls[controls.length - 1];
                if (!first) {
                    event.preventDefault();
                    authModal.focus();
                    return;
                }
                if (first && ((!event.shiftKey && document.activeElement === last) ||
                    (event.shiftKey && document.activeElement === first))) {
                    event.preventDefault();
                    (event.shiftKey ? last : first).focus();
                }
                return;
            }
            if (event.key !== "Escape") {
                return;
            }

            [
                "createModal",
                "previewModal",
                "chatModal",
                "importModal",
                "aiModal",
                "chatSessionsModal",
            ].forEach((id) => {
                if (!$(id).classList.contains("hidden")) {
                    closeModal(id);
                }
            });
        }
    );
}


// ======================================================
// 18. INITIALIZE DASHBOARD
// ======================================================

async function initializeDashboard() {
    registerEvents();

    updateAuthUI();
    updateStatistics();
    renderCVs();

    if (getToken()) {
        await loadCVs();
        await resumeDashboardAction();
    } else {
        openModal("loginModal");
    }
}


document.addEventListener(
    "DOMContentLoaded",
    initializeDashboard
);
