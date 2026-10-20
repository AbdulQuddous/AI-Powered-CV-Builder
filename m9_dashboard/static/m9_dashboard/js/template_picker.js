/* Visual creation choices use M3 metadata; M2/M5 still receive template_id. */
(function (global) {
    'use strict';
    const filterTemplates = (rows, search = '', category = '') => {
        const term = search.trim().toLowerCase();
        return rows.filter(row => (!category || row.gallery_category === category) &&
            (!term || [row.name, row.description, row.category_label, row.id].join(' ').toLowerCase().includes(term)));
    };
    if (typeof module !== 'undefined' && module.exports) module.exports = {filterTemplates};
    if (!global.document) return;
    const $ = id => global.document.getElementById(id);
    let rows = [], preview = null, initialized = false, previewTrigger = null;
    const selected = () => $('templateId').value;
    function add(parent, tag, className, text) {
        const node = global.document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        parent.appendChild(node);
        return node;
    }
    function imageURL(value) {
        try {
            const url = new URL(value, global.location.origin);
            return url.origin === global.location.origin && url.pathname.startsWith('/static/') ? url.href : '';
        } catch (_) { return ''; }
    }
    function sync() {
        const row = rows.find(item => item.id === selected());
        $('createSelectedTemplate').textContent = row?.name || selected() || 'Choose a design';
        for (const card of $('createTemplateGrid').children) {
            const checked = card.dataset.templateId === selected();
            card.classList.toggle('is-selected', checked);
            card.querySelector('input').checked = checked;
        }
    }
    function choose(id) {
        if (!rows.some(row => row.id === id)) return;
        $('templateId').value = id;
        sync();
    }
    function closePreview(focus = false) {
        preview = null;
        $('createTemplateDetail').classList.add('hidden');
        $('createTemplateBrowse').classList.remove('hidden');
        $('createTemplatePreviewImage').removeAttribute('src');
        if (focus && previewTrigger?.isConnected) previewTrigger.focus();
    }
    function openPreview(row, trigger) {
        preview = row; previewTrigger = trigger;
        $('createTemplatePreviewName').textContent = row.name;
        $('createTemplatePreviewDescription').textContent = row.description || 'A preview with fictional sample content.';
        const image = $('createTemplatePreviewImage');
        image.alt = `${row.name} template with fictional sample content`;
        const url = imageURL(row.preview_url);
        image.hidden = !url;
        if (url) image.src = url;
        $('createTemplateUse').textContent = `Use ${row.name}`;
        $('createTemplateBrowse').classList.add('hidden');
        $('createTemplateDetail').classList.remove('hidden');
        $('createTemplateDetail').scrollTop = 0;
        $('createTemplateBack').focus();
    }
    function render() {
        const visible = filterTemplates(rows, $('createTemplateSearch').value, $('createTemplateCategory').value);
        const grid = $('createTemplateGrid');
        grid.replaceChildren(); grid.scrollTop = 0;
        $('createTemplateCount').textContent = `${visible.length} of ${rows.length} designs · Select a preview to choose`;
        $('createTemplateEmpty').classList.toggle('hidden', visible.length > 0);
        for (const row of visible) {
            const card = add(grid, 'article', 'create-template-option');
            card.dataset.templateId = row.id;
            const label = add(card, 'label', 'create-template-choice');
            const input = add(label, 'input');
            input.type = 'radio'; input.name = 'createTemplateChoice'; input.value = row.id;
            input.setAttribute('aria-label', `Select ${row.name}`);
            input.addEventListener('change', () => { if (input.checked) choose(row.id); });
            const thumb = add(label, 'span', 'create-template-thumb');
            const url = imageURL(row.preview_url);
            if (url) {
                const img = add(thumb, 'img');
                img.src = url; img.alt = `${row.name} template preview`; img.width = 594; img.height = 840;
                img.loading = 'lazy'; img.decoding = 'async';
                img.addEventListener('error', () => { img.hidden = true; add(thumb, 'span', 'create-template-style', 'Preview unavailable'); }, {once: true});
            } else add(thumb, 'span', 'create-template-style', 'Preview unavailable');
            const check = add(thumb, 'span', 'create-template-check', '✓'); check.setAttribute('aria-hidden', 'true');
            const meta = add(label, 'span', 'create-template-meta');
            add(meta, 'span', 'create-template-name', row.name);
            add(meta, 'span', 'create-template-style', row.category_label || 'CV template');
            const expand = add(card, 'button', 'create-template-preview-button', 'Larger preview ↗');
            expand.type = 'button'; expand.setAttribute('aria-label', `Preview ${row.name}`);
            expand.addEventListener('click', () => openPreview(row, expand));
        }
        sync();
    }
    function setTemplates(items) {
        rows = items.filter(row => row && /^[a-zA-Z0-9_-]+$/.test(row.id) && typeof row.name === 'string');
        if (!rows.length) throw new Error('No template designs were returned.');
        const starters = [selected(), 'modern', 'ats_standard', 'professional_meridian', 'simple_direct', 'modern_horizon', 'creative_studio'];
        const rank = row => { const index = starters.indexOf(row.id); return index < 0 ? starters.length : index; };
        rows.sort((a, b) => rank(a) - rank(b));
        $('createTemplateSearch').value = ''; $('createTemplateCategory').value = '';
        closePreview(); render();
        $('createTemplateGrid').setAttribute('aria-busy', 'false');
    }
    function loading() {
        closePreview();
        $('createTemplatePicker').disabled = true;
        $('createTemplateGrid').replaceChildren();
        $('createTemplateGrid').setAttribute('aria-busy', 'true');
        $('createTemplateCount').textContent = 'Loading designs…';
        $('createSelectedTemplate').textContent = 'Loading…';
        $('createTemplateEmpty').classList.add('hidden');
        $('createTemplateError').classList.add('hidden');
    }
    function error() {
        $('createTemplateErrorText').textContent = 'Could not load the collection. Showing the default Modern design. Retry to see all designs.';
        $('createTemplateError').classList.remove('hidden');
        setTemplates([{id: 'modern', name: 'Modern', gallery_category: 'modern', category_label: 'Modern',
            preview_url: $('createTemplatePicker').dataset.fallbackPreview}]);
    }
    function init() {
        if (initialized) return;
        initialized = true;
        $('createTemplateSearch').addEventListener('input', render);
        $('createTemplateSearch').addEventListener('keydown', event => {
            if (event.key === 'Enter') event.preventDefault();
        });
        $('createTemplateCategory').addEventListener('change', render);
        $('templateId').addEventListener('change', sync);
        $('createTemplateBack').addEventListener('click', () => closePreview(true));
        $('createTemplateUse').addEventListener('click', () => {
            if (!preview) return;
            choose(preview.id); closePreview(true);
        });
        $('createTemplatePreviewImage').addEventListener('error', () => {
            $('createTemplatePreviewImage').hidden = true;
            $('createTemplatePreviewDescription').textContent = 'This image could not be loaded. You can still choose the design or return to all designs.';
        });
    }
    global.M9TemplatePicker = {init, setTemplates, loading, error, sync, closePreview,
        setDisabled: value => { $('createTemplatePicker').disabled = value; }};
})(typeof window !== 'undefined' ? window : globalThis);
