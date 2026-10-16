/* M4 text import, then optional M6 proposals and explicitly confirmed M2 creation. */
(function (global) {
    "use strict";
    const MAX_SIZE = 5 * 1024 * 1024;
    const $ = id => document.getElementById(id);
    let api, file = null, record = null, busy = false, generation = 0, resumeId = null;
    let proposal = null, parsed = null, parsedText = null, createdId = null;
    let templatesReady = false;

    function queryId() {
        const value = new URLSearchParams(global.location.search).get("import");
        return value && /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;
    }

    function remember(id) {
        resumeId = id;
        const url = new URL(global.location.href);
        if (id) url.searchParams.set("import", id);
        else url.searchParams.delete("import");
        global.history.replaceState(null, "", url);
    }

    function errorMessage(error, stage) {
        if (error.status === 401) return "Your session expired. Please sign in again.";
        if (error.status === 404) return "This import is unavailable or does not belong to your account.";
        if (error.status === 429) return "Too many requests. Wait a moment, then try again.";
        const detail = error.details?.error?.details || error.details;
        if ([400, 422].includes(error.status)) {
            if (Array.isArray(detail?.data)) return detail.data.map(item => typeof item === 'string' ? item : `${item.path}: ${item.message}`).join(' · ');
            const message = detail?.detail || detail?.file;
            if (typeof message === "string") return message;
            if (Array.isArray(message)) return message.filter(item => typeof item === "string").join(" ");
        }
        return stage === "upload"
            ? "Upload failed. Your file is still selected. Please retry. If the response was lost, the server may already have received the file."
            : "Unable to extract or load text. Refresh the import status or retry when available.";
    }

    function showError(message) {
        $("importError").textContent = message;
        $("importError").classList.remove("hidden");
    }

    function view(state, message) {
        $('importEditFields').disabled = busy || Boolean(createdId);
        $("importModal").dataset.state = state;
        $("importStatus").textContent = message;
        $("importModal").setAttribute("aria-busy", String(busy));
        $("importSelected").classList.toggle("hidden", !file || Boolean(record));
        $("importDrop").classList.toggle("hidden", Boolean(record));
        $("importDetails").classList.toggle("hidden", !record);
        $("importResult").classList.toggle("hidden", record?.status !== "extracted");
        ["importFile", "importRemove", "importUpload", "importExtract", "importRefresh", "importNew", "importReload", "importParse", "importConfirm", "importDiscard", "importCVTitle", "importTemplate"].forEach(id => { $(id).disabled = busy; });
        $("importParse").disabled = busy || record?.status !== "extracted";
        $("importConfirm").disabled = busy || !proposal || !templatesReady || Boolean(createdId);
        $("importDiscard").disabled = busy || Boolean(createdId);
        $("importUpload").disabled = busy || !file;
        $("importExtract").classList.toggle("hidden", !record || ["extracting", "extracted"].includes(record.status));
        $("importExtract").textContent = record?.status === "failed" || state === "extraction_error" ? "Retry extraction" : "Extract Text";
    }

    function renderRecord(data) {
        if (!data || !Number.isSafeInteger(data.import_id) || data.import_id <= 0) throw new Error("Invalid import response");
        if (record && record.text !== data.text) clearProposal();
        record = data;
        file = null;
        remember(data.import_id);
        $("importRecordName").textContent = data.file_name;
        $("importRecordMeta").textContent = `${String(data.file_type).toUpperCase()} · ${(data.file_size / 1024).toFixed(1)} KB · ${data.status}`;
        $("importText").value = data.text || "";
        const labels = {
            uploaded: "Upload complete. Click Extract Text to continue.",
            extracting: "Extraction is in progress. Refresh status to check the result.",
            extracted: "Text extracted. Review it below.",
            failed: "Text extraction failed. You can retry or choose another file."
        };
        view(data.status === "failed" ? "extraction_error" : data.status, labels[data.status] || "Import loaded.");
        if (data.status === "failed") showError(data.error_message || "Text extraction failed.");
    }

    function reset() {
        generation++;
        busy = false;
        file = null;
        record = null;
        clearProposal();
        remember(null);
        $("importFile").value = "";
        $("importText").value = "";
        $("importError").classList.add("hidden");
        $("importReload").classList.add("hidden");
        view("idle", "Choose a file to begin.");
    }

    function clearProposal() {
        proposal = parsed = parsedText = createdId = null;
        templatesReady = false;
        $("importCVPreview").replaceChildren();
        $("importAIWarnings").textContent = "";
        $("importStructured").classList.add("hidden");
        $("importEditor").classList.add("hidden");
    }

    async function parseWithAI() {
        if (busy || !record || record.status !== "extracted" || !api.requireLogin()) return;
        if (createdId) {
            $("importStructured").classList.remove("hidden");
            return;
        }
        const raw = record.text.trim();
        if (raw.length < 20 || raw.length > 20000) {
            showError("AI extraction supports 20–20,000 characters. This import is outside that range.");
            return;
        }
        const run = generation;
        busy = true;
        templatesReady = false;
        $("importError").classList.add("hidden");
        view("parsing", "Extracting CV information with AI…");
        try {
            if (!parsed || parsedText !== raw) {
                const result = await api.ai.extract(raw);
                if (run !== generation) return;
                if (!result.cv || typeof result.cv !== "object") throw new Error("Invalid CV proposal");
                parsed = result; parsedText = raw;
            }
            proposal = JSON.parse(JSON.stringify(parsed.cv));
            global.M6UI.preview($("importCVPreview"), proposal, {editable: true});
            $("importAIWarnings").textContent = (parsed.warnings || []).map(item => typeof item === "string" ? item : item.message).join(" ");
            $("importCVTitle").value = `${proposal.personal?.full_name || proposal.meta?.target_role || 'Imported'} CV`;
            $("importStructured").classList.remove("hidden");
            const response = await api.fetch("/api/templates/");
            const body = await response.json();
            if (run !== generation) return;
            const templates = Array.isArray(body) ? body : body.results || body.data?.results || body.data || [];
            $("importTemplate").replaceChildren();
            templates.forEach(item => $("importTemplate").add(new Option(item.name, item.id)));
            if (templates.some(item => item.id === proposal.meta.template_id)) $("importTemplate").value = proposal.meta.template_id;
            templatesReady = templates.length > 0;
            busy = false;
            view("review", "Review the information and confirm to create a new CV. Existing CVs will stay unchanged.");
        } catch (error) {
            if (run !== generation) return;
            busy = false;
            view("parsing_error", "Could not complete AI extraction. You can retry.");
            showError(error.status === 400 ? errorMessage(error, 'create') : global.M6UI.error(error));
        }
    }

    async function confirmProposal() {
        if (busy || !proposal || !templatesReady || createdId || !api.requireLogin()) return;
        const name = $("importCVTitle").value.trim();
        const template = $("importTemplate").value;
        if (!name || !template) { showError("Choose a CV name and available template before confirming."); return; }
        const run = generation;
        busy = true;
        $("importError").classList.add("hidden");
        view("saving", "Creating the CV you approved…");
        try {
            const data = JSON.parse(JSON.stringify(proposal));
            data.meta.template_id = template;
            const response = await api.fetch("/api/cvs/", {method:"POST", body:JSON.stringify({name,data})});
            const cv = await response.json();
            if (run !== generation) return;
            createdId = cv.id;
            if (!Number.isSafeInteger(createdId) || createdId <= 0) throw new Error("Invalid created CV ID");
            $("importEditor").href = `/cvs/${createdId}/edit/`;
            $("importEditor").classList.remove("hidden");
            busy = false;
            view("saved", "Approved CV created. Open it in the editor or find it on the dashboard.");
            await api.refresh();
        } catch (error) {
            if (run !== generation) return;
            busy = false;
            view("save_error", "Could not confirm the save. Refresh the dashboard to check for the CV before retrying.");
            showError(error.status === 400 ? errorMessage(error, 'create') : global.M6UI.error(error));
        }
    }

    function selectFile(files) {
        if (busy || record) return;
        $("importError").classList.add("hidden");
        if (files.length !== 1) { showError("Please select one PDF or DOCX file."); return; }
        const selected = files[0];
        const extension = selected.name.split(".").pop().toLowerCase();
        if (!["pdf", "docx"].includes(extension) || !selected.size || selected.size > MAX_SIZE) {
            file = null;
            $("importFile").value = "";
            view("upload_error", "Choose a supported file to continue.");
            showError(!["pdf", "docx"].includes(extension) ? "Only PDF and DOCX files are supported." : !selected.size ? "The file is empty." : "File size exceeds the maximum of 5 MB.");
            return;
        }
        file = selected;
        $("importFileName").textContent = selected.name;
        $("importFileMeta").textContent = `${extension.toUpperCase()} · ${(selected.size / 1024).toFixed(1)} KB`;
        view("file_selected", "File selected. Click Upload CV when ready.");
    }

    async function upload() {
        if (busy || !file || !api.requireLogin()) return;
        const run = generation;
        busy = true;
        $("importError").classList.add("hidden");
        view("uploading", "Uploading your CV…");
        try {
            const body = new FormData();
            body.append("file", file);
            const response = await api.fetch("/api/cv-import/upload/", { method: "POST", body });
            const data = await response.json();
            if (run !== generation) return;
            busy = false;
            renderRecord(data);
        } catch (error) {
            if (run !== generation) return;
            busy = false;
            view("upload_error", "Upload failed. You can retry with the selected file.");
            showError(errorMessage(error, "upload"));
        }
    }

    async function load(id = record?.import_id || resumeId) {
        if (busy || !id || !api.requireLogin()) return;
        const run = generation;
        busy = true;
        $("importError").classList.add("hidden");
        $("importReload").classList.add("hidden");
        view("loading", "Loading import status…");
        try {
            const response = await api.fetch(`/api/cv-import/${id}/`);
            const data = await response.json();
            if (run !== generation) return;
            busy = false;
            renderRecord(data);
        } catch (error) {
            if (run !== generation) return;
            busy = false;
            view("extraction_error", "Could not load import status.");
            $("importReload").classList.remove("hidden");
            showError(errorMessage(error, "load"));
        }
    }

    async function extract() {
        if (busy || !record || !api.requireLogin()) return;
        const run = generation;
        busy = true;
        $("importError").classList.add("hidden");
        view("extracting", "Extracting text…");
        try {
            // Check a potentially lost response before attempting another extraction.
            const latestResponse = await api.fetch(`/api/cv-import/${record.import_id}/`);
            const latest = await latestResponse.json();
            if (run !== generation) return;
            if (["extracted", "extracting"].includes(latest.status)) {
                busy = false;
                renderRecord(latest);
                return;
            }
            const response = await api.fetch(`/api/cv-import/${record.import_id}/extract/`, { method: "POST" });
            const data = await response.json();
            if (run !== generation) return;
            busy = false;
            renderRecord(data);
        } catch (error) {
            if (run !== generation) return;
            busy = false;
            if (error.status === 422) record.status = "failed";
            view("extraction_error", "Extraction failed. Refresh status or retry extraction.");
            showError(errorMessage(error, "extract"));
        }
    }

    function init(dependencies) {
        api = dependencies;
        resumeId = queryId();
        $("importCV").addEventListener("click", () => {
            if (!api.requireLogin()) return;
            api.openModal("importModal");
        });
        $("importFile").addEventListener("change", event => selectFile(event.target.files));
        $("importUpload").addEventListener("click", upload);
        $("importExtract").addEventListener("click", extract);
        $("importRefresh").addEventListener("click", () => load());
        $("importReload").addEventListener("click", () => load());
        $("importParse").addEventListener("click", parseWithAI);
        $("importConfirm").addEventListener("click", confirmProposal);
        $("importDiscard").addEventListener("click", () => {
            proposal = null;
            $("importStructured").classList.add("hidden");
            view("extracted", "Proposal discarded. No CV was created.");
        });
        ["importRemove", "importNew"].forEach(id => $(id).addEventListener("click", reset));
        const drop = $("importDrop");
        ["dragenter", "dragover"].forEach(name => drop.addEventListener(name, event => {
            event.preventDefault();
            if (!busy) drop.classList.add("dragging");
        }));
        drop.addEventListener("dragleave", () => drop.classList.remove("dragging"));
        drop.addEventListener("drop", event => {
            event.preventDefault();
            drop.classList.remove("dragging");
            selectFile(event.dataTransfer.files);
        });
        view("idle", "Choose a file to begin.");
    }

    async function resume() {
        if (resumeId && api.requireLogin()) {
            api.openModal("importModal");
            await load(resumeId);
        }
    }

    global.M4Import = { init, resume, reset };
})(window);
