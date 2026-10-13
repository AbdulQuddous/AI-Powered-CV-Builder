/* Coordinates M2 reads/saves and M6 proposals. No conversation or AI logic. */
(function (global) {
    'use strict';
    const $ = id => document.getElementById(id);
    const copy = value => JSON.parse(JSON.stringify(value));
    let api, selected = null, generation = 0, busy = false;
    let validation = null, analysis = null, fingerprint = null, pending = null, fields = [];
    const ui = () => global.M6UI;
    const at = (data, path) => path.reduce((value, key) => value?.[key], data);
    const role = () => $('aiRole').value.trim();
    const job = () => $('aiJob').value.trim();
    const key = () => JSON.stringify([selected.id, selected.version, selected.data, role(), job()]);

    function setBusy(value, status) {
        busy = value;
        if (status) $('aiStatus').textContent = status;
        $('aiModal').setAttribute('aria-busy', String(value));
        ['aiValidate','aiOptimize','aiViewSuggestions','aiRewrite','aiImprove','aiApply','aiDiscard','aiReload','aiField','aiRole','aiJob','aiPDF'].forEach(id => { $(id).disabled = value || !selected; });
        $('aiApply').disabled = value || !pending;
        $('aiRewrite').disabled = $('aiImprove').disabled = value || !fields.length;
    }
    function invalidate(message = '') {
        validation = analysis = fingerprint = pending = null;
        ui().health(null); ui().analysis(null); ui().comparison(null);
        if (message) $('aiStatus').textContent = message;
    }
    function fieldChanged() {
        pending = null; ui().comparison(null);
        const field = fields[Number($('aiField').value)];
        $('aiSource').value = field && selected ? at(selected.data, field.path) : '';
        setBusy(busy);
    }
    function populateFields() {
        fields = [];
        function add(section, path, label) {
            const value = at(selected.data, path);
            if (typeof value === 'string' && value.trim()) fields.push({section, path, label});
        }
        add('summary', ['summary'], 'Professional summary');
        ['experience','projects'].forEach(section => {
            (selected.data[section] || []).forEach((item, index) => {
                const name = item.name || item.company || `${section} ${index+1}`;
                if (section === 'projects') add(section, [section,index,'description'], `${name} — description`);
                (item.highlights || []).forEach((_, bullet) => add(section, [section,index,'highlights',bullet], `${name} — bullet ${bullet+1}`));
            });
        });
        (selected.data.achievements || []).forEach((_, index) => add('achievements',['achievements',index],`Achievement ${index+1}`));
        $('aiField').replaceChildren();
        fields.forEach((field,index) => $('aiField').add(new Option(field.label,String(index))));
        if (!fields.length) $('aiField').add(new Option('No saved prose to improve. Add it in the editor.', ''));
        fieldChanged();
    }
    function adopt(cv) {
        if (!cv?.data || !Number.isSafeInteger(cv.id) || !Number.isInteger(cv.version)) throw new Error('Invalid saved CV response');
        if (!selected || selected.id !== cv.id || selected.version !== cv.version || JSON.stringify(selected.data) !== JSON.stringify(cv.data)) {
            invalidate('Saved CV changed. Run a new review.');
            selected = cv;
            populateFields();
        } else selected = cv;
        $('aiCVName').textContent = cv.name;
        $('aiEditor').href = `/cvs/${cv.id}/edit/`;
    }
    async function fresh(run) {
        const response = await api.fetch(`/api/cvs/${selected.id}/`);
        const cv = await response.json();
        if (run !== generation) return false;
        adopt(cv);
        return true;
    }
    function reset() {
        generation++;
        selected = null; fields = [];
        invalidate();
        $('aiSource').value = '';
        $('aiCVName').textContent = '';
        $('aiError').classList.add('hidden');
        setBusy(false);
    }
    async function open(id) {
        if (!api.requireLogin()) return;
        reset();
        const run = generation;
        $('aiRole').value = ''; $('aiJob').value = '';
        api.openModal('aiModal');
        setBusy(true, 'Loading selected CV…');
        try {
            const response = await api.fetch(`/api/cvs/${id}/`);
            const cv = await response.json();
            if (run !== generation) return;
            adopt(cv);
            $('aiRole').value = cv.data.meta?.target_role || '';
            $('aiStatus').textContent = 'Run a health check or request AI analysis.';
        } catch(error) { if (run === generation) showError(error); }
        finally {
            if (run === generation) {
                setBusy(false);
                if (selected) $('aiRole').focus();
            }
        }
    }
    function showError(error) {
        $('aiError').textContent = ui().error(error);
        $('aiError').classList.remove('hidden');
        $('aiStatus').textContent = 'The operation did not complete. You can retry.';
    }
    async function operation(message, action) {
        if (busy || !selected || !api.requireLogin()) return;
        const run = generation;
        $('aiError').classList.add('hidden');
        setBusy(true, message);
        try { await action(run); }
        catch(error) { if (run === generation) showError(error); }
        finally { if (run === generation) setBusy(false); }
    }
    function health() {
        return operation('Checking CV structure and completeness…', async run => {
            if (!await fresh(run)) return;
            if (!validation) {
                const result = await api.ai.validate(selected.data, role());
                if (run !== generation) return;
                validation = result;
            }
            ui().health(validation);
            $('aiStatus').textContent = 'Health check complete. No AI request was used.';
        });
    }
    function analyze(mode = 'optimize') {
        return operation('Analyzing your CV…', async run => {
            if (!await fresh(run)) return;
            if (mode === 'optimize' && !role()) { throw Object.assign(new Error('Target role required'), {status:400}); }
            const signature = key();
            if (!analysis || fingerprint !== signature) {
                const result = await api.ai[mode](selected.data, role(), job());
                if (run !== generation) return;
                analysis = result; fingerprint = signature;
            }
            validation = analysis;
            ui().health(validation); ui().analysis(analysis,selected.id);
            $('aiStatus').textContent = 'Analysis ready. All insights and suggestions use this result.';
        });
    }
    function write(mode) {
        return operation(mode === 'improve' ? 'Improving selected text…' : 'Rewriting selected text…', async run => {
            const requested = fields[Number($('aiField').value)];
            if (!requested) return;
            const path = requested.path.slice();
            const original = at(selected.data,path);
            const version = selected.version;
            const document = JSON.stringify(selected.data);
            if (!await fresh(run)) return;
            if (selected.version !== version || JSON.stringify(selected.data) !== document || at(selected.data,path) !== original) {
                throw Object.assign(new Error('Field changed'),{status:409});
            }
            if (!original.trim() || original.length > 3000) { throw Object.assign(new Error('Unsupported text length'),{status:400}); }
            pending = null; ui().comparison(null);
            const result = await api.ai[mode](original,requested.section,role());
            if (run !== generation) return;
            if (typeof result.rewritten !== 'string' || !result.rewritten.trim()) throw new Error('Invalid rewritten text');
            pending = {...result, original, path, cvId:selected.id, version:selected.version, document:copy(selected.data)};
            ui().comparison(pending);
            $('aiStatus').textContent = 'Compare the wording. Apply saves only this field; Discard leaves the CV unchanged.';
        });
    }
    function apply() {
        return operation('Saving approved wording…', async run => {
            if (!pending || pending.cvId !== selected.id || pending.version !== selected.version) return;
            const proposal = pending;
            const document = copy(proposal.document);
            const parent = at(document,proposal.path.slice(0,-1));
            parent[proposal.path.at(-1)] = proposal.rewritten;
            try {
                const response = await api.fetch(`/api/cvs/${proposal.cvId}/`, {method:'PATCH', body:JSON.stringify({data:document, expected_version:proposal.version})});
                const saved = await response.json();
                if (run !== generation) return;
                adopt(saved);
                $('aiStatus').textContent = 'Approved wording saved. Previous analysis is stale; run a new review.';
                await api.refresh();
            } catch(error) {
                if (error.status === 409 && run === generation) { invalidate(); await fresh(run); }
                throw error;
            }
        });
    }
    function observe(cvs) {
        if (!selected) return;
        const latest = cvs.find(cv => cv.id === selected.id);
        if (!latest || latest.version !== selected.version || JSON.stringify(latest.data) !== JSON.stringify(selected.data)) {
            generation++;
            invalidate('Saved CV changed. Reload the CV before reviewing it again.');
            setBusy(false);
        }
    }
    function roleChanged() {
        analysis = fingerprint = pending = null;
        ui().analysis(null); ui().comparison(null);
        $('aiStatus').textContent = 'Analysis cleared because the target role or job description changed.';
        setBusy(busy);
    }
    async function downloadPDF() {
        return operation('Generating PDF from the saved CV…', async run => {
            const response = await api.fetch(`/api/cvs/${selected.id}/export/pdf/`, {method:'POST'});
            const blob = await response.blob();
            if (run !== generation) return;
            const url = URL.createObjectURL(blob);
            const link = ui().node('a',''); link.href=url; link.download=`cv-${selected.id}.pdf`; link.click();
            setTimeout(() => URL.revokeObjectURL(url),1000);
            $('aiStatus').textContent = 'PDF downloaded from the saved CV.';
        });
    }
    function init(dependencies) {
        api = dependencies;
        $('aiModal').addEventListener('keydown', event => {
            if (event.key !== 'Tab') return;
            const controls = [...$('aiModal').querySelectorAll('button, input, textarea, select, a[href]')]
                .filter(element => !element.disabled && element.getClientRects().length);
            const first = controls[0], last = controls.at(-1);
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        });
        $('aiValidate').addEventListener('click',health);
        $('aiOptimize').addEventListener('click',() => analyze());
        $('aiViewSuggestions').addEventListener('click',() => analyze('suggestions'));
        $('aiRewrite').addEventListener('click',() => write('rewrite'));
        $('aiImprove').addEventListener('click',() => write('improve'));
        $('aiApply').addEventListener('click',apply);
        $('aiPDF').addEventListener('click',downloadPDF);
        $('aiDiscard').addEventListener('click',() => { pending=null; ui().comparison(null); setBusy(false); $('aiStatus').textContent='Suggestion discarded. Your CV is unchanged.'; });
        $('aiField').addEventListener('change',fieldChanged);
        ['aiRole','aiJob'].forEach(id => $(id).addEventListener('input',roleChanged));
        $('aiReload').addEventListener('click',() => selected ? open(selected.id) : null);
        global.addEventListener?.('focus', () => {
            if (!selected || busy || $('aiModal').classList.contains('hidden')) return;
            operation('Checking current saved CV…', async run => {
                const previousVersion = selected.version;
                if (await fresh(run) && selected.version === previousVersion) {
                    $('aiStatus').textContent = 'Saved CV is current.';
                }
            });
        });
        setBusy(false);
    }
    global.M6Review = {init,open,reset,observe};
})(window);
