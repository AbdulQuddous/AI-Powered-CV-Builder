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
};

const $ = (id) => document.getElementById(id);


// ======================================================
// 1. UTILITIES
// ======================================================

function getToken() {
    return sessionStorage.getItem(TOKEN_KEY);
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
}


function closeModal(id) {
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
}


function clearSession() {
    sessionStorage.removeItem(TOKEN_KEY);

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


async function handleLogin(event) {
    event.preventDefault();

    const email = $("loginEmail").value.trim();
    const password = $("loginPassword").value;

    const button = $("loginSubmit");

    clearFormError("loginError");

    setButtonBusy(button, true, "Signing in...");

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
                payload.detail ||
                payload.message ||
                "Invalid email or password."
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

        sessionStorage.setItem(TOKEN_KEY, token);

        $("loginPassword").value = "";

        closeModal("loginModal");

        updateAuthUI();

        showToast("Successfully signed in.");

        await loadCVs();

    } catch (error) {
        showFormError(
            "loginError",
            error.message || "Unable to sign in."
        );

    } finally {
        setButtonBusy(button, false);
    }
}


function logout() {
    clearSession();

    closeModal("createModal");
    closeModal("previewModal");

    showToast("You have signed out.");

    openModal("loginModal");
}


// ======================================================
// 4. SHARED API CLIENT
// ======================================================

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

    const response = await fetch(path, {
        ...options,
        headers,
        credentials: "same-origin",
    });

    if (response.status === 401) {
        clearSession();
        openModal("loginModal");

        throw new Error(
            "Your session has expired. Please sign in again."
        );
    }

    if (!response.ok) {
        let payload = {};

        try {
            payload = await response.json();
        } catch (_) {
            // The server may return a non-JSON error.
        }

        let message =
            payload.detail ||
            payload.message ||
            payload.error;

        if (typeof message !== "string") {
            message = `Request failed (${response.status}).`;
        }

        throw new Error(message);
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

        // Each CV ID must be a valid integer.
        state.cvs = allCVs.filter((cv) => {
            return (
                cv &&
                Number.isSafeInteger(Number(cv.id)) &&
                Number(cv.id) > 0
            );
        });

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
    setButtonBusy(button, true, "Copying...");

    try {
        await apiFetch(
            `/api/cvs/${id}/duplicate/`,
            {
                method: "POST",
                body: JSON.stringify({}),
            }
        );

        showToast("CV duplicated successfully.");

        await loadCVs();

    } catch (error) {
        showToast(
            error.message || "Could not duplicate CV."
        );

    } finally {
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

async function openCreateCV() {
    if (!requireLogin()) {
        return;
    }

    $("createForm").reset();

    clearFormError("createError");

    openModal("createModal");

    await loadCreateTemplates();
}


async function handleCreateCV(event) {
    event.preventDefault();

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

    try {
        const response = await apiFetch(
            "/api/cvs/",
            {
                method: "POST",
                body: JSON.stringify(payload),
            }
        );

        const result = await response.json();

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

    if (action === "edit") {
        editCV(id);

    } else if (action === "view") {
        await viewCV(id);

    } else if (action === "duplicate") {
        await duplicateCV(id, button);
    }
}


// ======================================================
// 17. REGISTER EVENTS
// ======================================================

function registerEvents() {
    $("loginForm").addEventListener(
        "submit",
        handleLogin
    );

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
            if (event.key !== "Escape") {
                return;
            }

            [
                "createModal",
                "previewModal",
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
    } else {
        openModal("loginModal");
    }
}


document.addEventListener(
    "DOMContentLoaded",
    initializeDashboard
);