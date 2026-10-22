/* Review AI proposals, then save approved wording through the existing CV API. */
(function (global) {
    'use strict';
    const $ = id => document.getElementById(id);
    const copy = value => JSON.parse(JSON.stringify(value));
    const at = (data, path) => path.reduce((value, key) => value?.[key], data);
    const ui = () => global.M6UI;
    const role = () => $('aiRole').value.trim();
    const job = () => $('aiJob').value.trim();
    const invalid = message => Object.assign(new Error(message), {status: 400, userMessage: message});
    const conflict = () => Object.assign(new Error('Saved CV changed'), {status: 409});
    const badResponse = () => Object.assign(new Error('Invalid AI response'), {status: 502});
    let api, selected = null, generation = 0, busy = false, mode = 'whole', loadingId = null;
    let validation = null, analysis = null, fingerprint = null, pending = null, tailored = null, fields = [], retry = null;
    const FOCUS_RECHECK_MS = 60000;
    let lastCheckedAt = 0;
    const active = () => mode === 'whole' ? tailored : pending;
    const approved = () => mode === 'whole' ? (tailored?.changes || []).filter(change => change.accepted) : pending ? [pending] : [];
    const key = () => JSON.stringify([selected.id, selected.version, selected.data, role(), job()]);
    function reviewContext(source) {
        const reviewRole = role() || (job() ? 'Pasted job description' : 'Wording review');
        const sourceRole = source.data.meta?.target_role || '';
        return `Review focus: ${reviewRole}${job() && role() ? ' · Job description included' : ''}` +
            (sourceRole && sourceRole.toLowerCase() !== reviewRole.toLowerCase() ? ` · Saved CV target: ${sourceRole}` : '');
    }
    function proposalStatus() {
        if (mode === 'part') return pending ? 'Your rewrite is ready to review.' : 'Your saved CV is up to date.';
        if (!tailored) return 'Your saved CV is up to date.';
        const count = tailored.changes.length;
        if (!count) return 'CV review complete. Advice is ready below; there are no wording changes to save.';
        return `${count} wording ${count === 1 ? 'change is' : 'changes are'} ready to review.` +
            (tailored.warnings?.length ? ' Other suggestions were left out; see the explanation below.' : ' Save only the changes you want.');
    }

    function status(message) {
        $('aiStatus').textContent = message;
        $('aiStatus').classList.toggle('hidden', !message);
    }
    function clearError() {
        retry = null;
        $('aiError').textContent = '';
        $('aiError').classList.add('hidden');
        $('aiRetry').classList.add('hidden');
        for (const id of ['aiRole', 'aiJob']) $(id).removeAttribute('aria-invalid');
    }
    function setBusy(value, message) {
        busy = value;
        if (message) status(message);
        $('aiModal').setAttribute('aria-busy', String(value));
        for (const id of ['aiValidate','aiOptimize','aiTailor','aiRewrite','aiImprove','aiDiscard','aiReload','aiField','aiRole','aiJob','aiPDF','aiModeWhole','aiModePart','aiPolishPart']) {
            $(id).disabled = value || !selected;
        }
        $('aiRetry').disabled = value;
        $('aiApply').disabled = value || !approved().length;
        $('aiDiscard').disabled = value || !active();
        $('aiRewrite').disabled = value || !selected || !fields.length;
        $('aiImprove').disabled = $('aiRewrite').disabled;
        const count = approved().length;
        const hasChanges = mode === 'part' ? Boolean(pending) : Boolean(tailored?.changes.length);
        $('aiApply').classList.toggle('hidden', !hasChanges);
        $('aiApply').textContent = mode === 'part' ? 'Save this change' : count ? `Save ${count} ${count === 1 ? 'change' : 'changes'}` : 'Select changes to save';
        for (const check of $('aiTailorChanges').querySelectorAll('input[type="checkbox"]')) check.disabled = value;
    }
    function renderProposal() {
        const proposal = active();
        const adviceOnly = mode === 'whole' && tailored && !tailored.changes.length;
        ui().comparison(mode === 'part' ? pending : null);
        ui().tailoring(mode === 'whole' ? tailored : null, () => setBusy(busy));
        $('aiComparison').classList.toggle('hidden', !proposal);
        $('aiComparisonTitle').textContent = adviceOnly ? 'Advice for your CV' : mode === 'whole' ? 'Review the whole-CV improvements' : 'Review the rewrite';
        $('aiReviewState').textContent = adviceOnly ? 'No changes to save' : 'Not saved yet';
        $('aiReviewState').classList.toggle('ai-review-badge-neutral', Boolean(adviceOnly));
        $('aiReviewIntro').textContent = adviceOnly ? 'For a focused wording review, choose Polish one part.' : 'Check the wording and facts. Only the changes you approve will be saved.';
        $('aiPolishPart').classList.toggle('hidden', !adviceOnly);
        $('aiDiscard').textContent = adviceOnly ? 'Close review' : 'Discard suggestions';
        const context = proposal?.reviewContext || '';
        $('aiReviewContext').textContent = context || '';
        $('aiReviewContext').classList.toggle('hidden', !context);
        $('aiReviewCache').classList.toggle('hidden', !(mode === 'whole' && tailored?.cached));
        setBusy(busy);
    }
    function invalidate(message = '') {
        validation = analysis = fingerprint = pending = tailored = null;
        ui().health(null); ui().analysis(null);
        renderProposal();
        if (message) status(message);
    }
    function switchMode(next, focus = false) {
        if (busy) return;
        mode = next;
        const whole = mode === 'whole';
        for (const [id, chosen] of [['aiModeWhole', whole], ['aiModePart', !whole]]) {
            $(id).setAttribute('aria-selected', String(chosen));
            $(id).tabIndex = chosen ? 0 : -1;
        }
        $('aiWholeMode').classList.toggle('hidden', !whole);
        $('aiPartMode').classList.toggle('hidden', whole);
        $('aiJobHelp').textContent = whole
            ? 'Enter your target role and paste the job description. Gemini will tailor the wording to this job using your existing CV.'
            : 'Add your target role and job description to tailor this part with Gemini. Leave them blank for a general wording review.';
        for (const id of ['aiRole', 'aiJob']) $(id).setAttribute('aria-required', String(whole));
        $('aiRoleRequirement').textContent = whole ? '(required)' : '(optional)';
        $('aiJobRequirement').textContent = whole ? '(required)' : '(optional)';
        clearError();
        renderProposal();
        if (selected) status(active() ? proposalStatus() : whole
            ? 'Enter a target role and job description, then tailor your whole CV.'
            : 'Choose a part of your CV, then request a rewrite.');
        if (focus) $(whole ? 'aiModeWhole' : 'aiModePart').focus();
    }
    function fieldChanged() {
        if (busy) return;
        pending = null;
        const field = fields[Number($('aiField').value)];
        $('aiSource').value = field && selected ? at(selected.data, field.path) : '';
        describeField(field);
        renderProposal();
    }
    function describeField(field) {
        $('aiFieldHelp').textContent = field?.section === 'summary'
            ? 'Gemini can draw on facts throughout your saved CV to focus your summary on this job. Review every suggested claim before saving.'
            : ['experience', 'projects'].includes(field?.section)
                ? 'Gemini uses facts from this selected entry to focus the wording on this job. Other jobs and projects cannot supply new claims for it.'
                : 'Gemini preserves the facts in the selected text. To add or correct factual details, use the CV editor.';
    }
    function populateFields() {
        fields = [];
        function add(section, path, label) {
            const value = at(selected.data, path);
            if (typeof value === 'string' && value.trim()) fields.push({section, path, pointer: '/' + path.join('/'), label});
        }
        add('summary', ['summary'], 'Professional summary');
        for (const section of ['experience', 'projects']) {
            (selected.data[section] || []).forEach((item, index) => {
                const name = item.name || item.company || `${section === 'experience' ? 'Work experience' : 'Project'} ${index + 1}`;
                if (section === 'projects') add(section, [section,index,'description'], `${name} — description`);
                (item.highlights || []).forEach((_, bullet) => add(section, [section,index,'highlights',bullet], `${name} — bullet ${bullet + 1}`));
            });
        }
        (selected.data.achievements || []).forEach((_, index) => add('achievements', ['achievements',index], `Achievement ${index + 1}`));
        $('aiField').replaceChildren();
        fields.forEach((field, index) => $('aiField').add(new Option(field.label, String(index))));
        if (!fields.length) $('aiField').add(new Option('Add a summary, work bullet or project description in the editor first.', ''));
        const first = fields[0];
        $('aiSource').value = first ? at(selected.data, first.path) : '';
        describeField(first);
    }
    function adopt(cv) {
        if (!cv?.data || !Number.isSafeInteger(cv.id) || !Number.isInteger(cv.version)) throw badResponse();
        const changed = !selected || selected.id !== cv.id || selected.version !== cv.version || JSON.stringify(selected.data) !== JSON.stringify(cv.data);
        selected = cv;
        lastCheckedAt = Date.now();
        if (changed) {
            invalidate();
            populateFields();
        }
        $('aiCVName').textContent = cv.name;
        $('aiEditor').href = `/cvs/${cv.id}/edit/`;
        $('aiEditor').removeAttribute('aria-disabled');
    }
    async function fresh(run) {
        lastCheckedAt = Date.now();
        const response = await api.fetch(`/api/cvs/${selected.id}/`);
        const cv = await response.json();
        if (run !== generation) return false;
        adopt(cv);
        return true;
    }
    function reset() {
        generation++;
        selected = loadingId = null; fields = [];
        busy = false;
        lastCheckedAt = 0;
        clearError();
        invalidate();
        $('aiSource').value = '';
        $('aiCVName').textContent = '';
        $('aiEditor').removeAttribute('href');
        $('aiEditor').setAttribute('aria-disabled', 'true');
        $('aiMoreTools').open = false;
        switchMode('whole');
        status('Select a saved CV to begin.');
    }
    function showError(error, action) {
        $('aiError').textContent = ui().error(error);
        $('aiError').classList.remove('hidden');
        status('');
        retry = [400, 401, 403, 404, 409].includes(error.status) ? null : action;
        $('aiRetry').classList.toggle('hidden', !retry);
    }
    async function open(id) {
        if (!api.requireLogin()) return;
        reset();
        loadingId = id;
        const run = generation;
        $('aiRole').value = ''; $('aiJob').value = '';
        api.openModal('aiModal');
        setBusy(true, 'Loading your saved CV…');
        try {
            const response = await api.fetch(`/api/cvs/${id}/`);
            const cv = await response.json();
            if (run !== generation) return;
            adopt(cv);
            $('aiRole').value = cv.data.meta?.target_role || '';
            status('Enter a target role and job description, then tailor your whole CV.');
        } catch (error) { if (run === generation) showError(error, () => open(id)); }
        finally {
            if (run === generation) {
                setBusy(false);
                if (selected) $('aiRole').focus();
            }
        }
    }
    async function operation(message, action, retryAction) {
        if (busy || !selected || !api.requireLogin()) return;
        const run = generation;
        clearError();
        setBusy(true, message);
        let focusField = null;
        try { await action(run); }
        catch (error) {
            if (run === generation) {
                showError(error, retryAction);
                focusField = error.fieldId;
            }
        }
        finally {
            if (run === generation) {
                setBusy(false);
                if (focusField) $(focusField).focus();
            }
        }
    }
    function health() {
        return operation('Checking for missing CV details…', async run => {
            if (!await fresh(run)) return;
            if (!validation) {
                const result = await api.ai.validate(selected.data, role());
                if (run !== generation) return;
                validation = result;
            }
            ui().health(validation);
            status('Check complete. Review any missing details below.');
        }, health);
    }
    function analyze() {
        return operation('Reviewing how your CV matches the job…', async run => {
            if (!role() && !job()) throw invalid('Enter a target role or paste a job description first.');
            if (!await fresh(run)) return;
            const signature = key();
            if (!analysis || fingerprint !== signature) {
                const result = role()
                    ? await api.ai.optimize(selected.data, role(), job())
                    : await api.ai.suggestions(selected.data, role(), job());
                if (run !== generation) return;
                analysis = result; fingerprint = signature;
            }
            validation = analysis;
            ui().health(validation); ui().analysis(analysis, selected.id);
            status('Job-fit advice is ready below. Use Improve whole CV to request wording changes.');
        }, analyze);
    }
    function tailor() {
        return operation('Gemini is matching the job requirements and tailoring your CV…', async run => {
            for (const [id, value, message] of [
                ['aiRole', role(), 'Enter the target role you are applying for.'],
                ['aiJob', job(), 'Paste the job description so Gemini can tailor your whole CV to its requirements.']
            ]) {
                if (!value) {
                    $(id).setAttribute('aria-invalid', 'true');
                    throw Object.assign(invalid(message), {fieldId: id});
                }
            }
            if (!await fresh(run)) return;
            if (!fields.length) throw invalid('Add a summary, work bullet or project description in the CV editor first.');
            const source = copy(selected);
            const signature = key();
            const result = await api.ai.tailor(source.id, source.version, role(), job());
            if (run !== generation || signature !== key()) return;
            if (result.cv_id !== source.id || result.version !== source.version || typeof result.summary !== 'string' || !Array.isArray(result.changes) || !Array.isArray(result.suggestions) || (result.warnings !== undefined && (!Array.isArray(result.warnings) || !result.warnings.every(item => typeof item === 'string')))) throw badResponse();
            if (result.job_alignment !== undefined && (!Array.isArray(result.job_alignment) || result.job_alignment.length > 6 || !result.job_alignment.every(item =>
                item && typeof item.requirement === 'string' && ['supported', 'partial', 'missing'].includes(item.status) && Array.isArray(item.evidence) && item.evidence.every(evidence =>
                    evidence && typeof evidence.path === 'string' && typeof evidence.quote === 'string')))) throw badResponse();
            if (result.job_alignment_warning !== undefined && typeof result.job_alignment_warning !== 'string') throw badResponse();
            const seen = new Set();
            const changes = result.changes.map(change => {
                const field = fields.find(item => item.pointer === change.path);
                if (!field || seen.has(change.path) || change.original !== at(source.data, field.path) || typeof change.rewritten !== 'string' || !change.rewritten.trim() || change.rewritten.length > 5000 || typeof change.reason !== 'string') throw badResponse();
                seen.add(change.path);
                return {...change, label: field.label, path: field.path.slice(), accepted: true};
            });
            tailored = {...result, changes, reviewContext: reviewContext(source), cvId: source.id, version: source.version, document: source.data};
            renderProposal();
            status(proposalStatus());
            $('aiComparison').scrollIntoView?.({behavior: 'smooth', block: 'nearest'});
        }, tailor);
    }
    function write(action = 'rewrite') {
        return operation(action === 'improve' ? 'Polishing your selected text…' : 'Rewriting your selected text…', async run => {
            const requested = fields[Number($('aiField').value)];
            if (!requested) throw invalid('Choose some saved CV text first.');
            const path = requested.path.slice();
            const original = at(selected.data, path);
            const version = selected.version;
            const document = JSON.stringify(selected.data);
            if (!await fresh(run)) return;
            if (selected.version !== version || JSON.stringify(selected.data) !== document || at(selected.data,path) !== original) throw conflict();
            if (!original.trim() || original.length > 5000) throw invalid('Choose text with between 1 and 5,000 characters.');
            pending = null;
            renderProposal();
            const source = copy(selected), signature = key();
            const context = {cv_id: source.id, expected_version: source.version, field_path: requested.pointer};
            const focus = reviewContext(source);
            const result = await api.ai[action](original, requested.section, role(), job(), context);
            if (run !== generation || signature !== key()) return;
            if ((result.original !== undefined && result.original !== original) || typeof result.rewritten !== 'string' || !result.rewritten.trim() || result.rewritten.length > 5000) throw badResponse();
            pending = {...result, original, path, reviewContext: focus, cvId: source.id, version: source.version, document: source.data};
            renderProposal();
            status('Compare the wording below. Save it if you like it, or discard it.');
            $('aiComparison').scrollIntoView?.({behavior: 'smooth', block: 'nearest'});
        }, () => write(action));
    }
    function apply() {
        return operation('Saving your approved changes…', async run => {
            const proposal = active();
            const changes = approved();
            if (!proposal || !changes.length) return;
            if (proposal.cvId !== selected.id || proposal.version !== selected.version || JSON.stringify(proposal.document) !== JSON.stringify(selected.data)) {
                invalidate();
                throw conflict();
            }
            const document = copy(proposal.document);
            for (const change of changes) {
                const parent = at(document, change.path.slice(0, -1));
                if (parent[change.path.at(-1)] !== change.original) throw conflict();
                parent[change.path.at(-1)] = change.rewritten;
            }
            try {
                const response = await api.fetch(`/api/cvs/${proposal.cvId}/`, {method: 'PATCH', body: JSON.stringify({data: document, expected_version: proposal.version})});
                const saved = await response.json();
                if (run !== generation) return;
                adopt(saved);
                status(mode === 'whole' ? `Saved ${changes.length} ${changes.length === 1 ? 'change' : 'changes'} to your CV. You can download the updated PDF below.` : 'Saved this change to your CV. You can download the updated PDF below.');
                // Saving succeeded even if refreshing the dashboard list is unavailable.
                try { await api.refresh(); } catch (_) { /* The approved CV is already saved. */ }
            } catch (error) {
                if (error.status === 409 && run === generation) { invalidate(); await fresh(run); }
                throw error;
            }
        }, apply);
    }
    function observe(cvs) {
        if (!selected) return;
        const latest = cvs.find(cv => cv.id === selected.id);
        if (!latest || latest.version !== selected.version || JSON.stringify(latest.data) !== JSON.stringify(selected.data)) {
            generation++;
            busy = false;
            invalidate('Saved CV changed. Refresh the CV before requesting new improvements.');
            clearError();
            setBusy(false);
        }
    }
    function roleChanged() {
        if (busy) return;
        invalidate();
        clearError();
        status('Job details updated. Request new suggestions for this job.');
    }
    function discard() {
        if (busy) return;
        const adviceOnly = mode === 'whole' && tailored && !tailored.changes.length;
        if (mode === 'whole') tailored = null;
        else pending = null;
        clearError();
        renderProposal();
        status(adviceOnly ? 'Review closed. Your saved CV is unchanged.' : 'Suggestions discarded. Your saved CV is unchanged.');
    }
    function reload() {
        if (!selected) return loadingId ? open(loadingId) : null;
        return operation('Refreshing your saved CV…', async run => {
            if (await fresh(run)) status('Your saved CV is up to date.');
        }, reload);
    }
    function downloadPDF() {
        return operation('Preparing your saved CV as a PDF…', async run => {
            const response = await api.fetch(`/api/cvs/${selected.id}/export/pdf/`, {method: 'POST'});
            const blob = await response.blob();
            if (run !== generation) return;
            const url = URL.createObjectURL(blob);
            const link = ui().node('a', ''); link.href = url; link.download = `cv-${selected.id}.pdf`; link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
            status('Your saved CV has been downloaded.');
        }, downloadPDF);
    }
    function init(dependencies) {
        api = dependencies;
        $('aiModal').addEventListener('keydown', event => {
            if (event.key !== 'Tab') return;
            const controls = [...$('aiModal').querySelectorAll('button, input, textarea, select, a[href], summary')]
                .filter(element => !element.disabled && element.getClientRects().length);
            const first = controls[0], last = controls.at(-1);
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        });
        for (const [id, next] of [['aiModeWhole', 'whole'], ['aiModePart', 'part']]) {
            $(id).addEventListener('click', () => switchMode(next));
            $(id).addEventListener('keydown', event => {
                if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
                    event.preventDefault();
                    switchMode(event.key === 'Home' ? 'whole' : event.key === 'End' ? 'part' : mode === 'whole' ? 'part' : 'whole', true);
                }
            });
        }
        $('aiTailor').addEventListener('click', tailor);
        $('aiPolishPart').addEventListener('click', () => switchMode('part', true));
        $('aiValidate').addEventListener('click', health);
        $('aiOptimize').addEventListener('click', analyze);
        $('aiRewrite').addEventListener('click', () => write());
        $('aiImprove').addEventListener('click', () => write('improve'));
        $('aiApply').addEventListener('click', apply);
        $('aiDiscard').addEventListener('click', discard);
        $('aiPDF').addEventListener('click', downloadPDF);
        $('aiRetry').addEventListener('click', () => retry?.());
        $('aiField').addEventListener('change', fieldChanged);
        for (const id of ['aiRole','aiJob']) $(id).addEventListener('input', roleChanged);
        $('aiReload').addEventListener('click', reload);
        global.addEventListener?.('focus', () => {
            if (!selected || busy || $('aiModal').classList.contains('hidden') || Date.now() - lastCheckedAt < FOCUS_RECHECK_MS) return;
            return operation('Checking your saved CV…', async run => {
                const previousVersion = selected.version;
                const previousData = JSON.stringify(selected.data);
                if (await fresh(run)) status(selected.version !== previousVersion || JSON.stringify(selected.data) !== previousData
                    ? 'Your saved CV changed. Previous suggestions were cleared; request a new review.'
                    : proposalStatus());
            });
        });
        switchMode('whole');
        setBusy(false);
    }
    global.M6Review = {init, open, reset, observe};
})(window);
