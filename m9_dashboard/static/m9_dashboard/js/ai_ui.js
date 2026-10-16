/* Safe presentation of API data, shared by review and import. */
(function (global) {
    'use strict';
    const $ = id => document.getElementById(id);
    const label = value => String(value).replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());
    function node(tag, text, parent, className = '') {
        const element = document.createElement(tag);
        element.textContent = String(text ?? '');
        element.className = className;
        if (parent) parent.appendChild(element);
        return element;
    }
    function messages(container, entries, empty) {
        container.replaceChildren();
        if (!entries?.length) { node('p', empty, container); return; }
        const list = node('ul', '', container);
        entries.forEach(item => node('li', typeof item === 'string' ? item : item.message || item.code || '', list));
    }
    function health(result) {
        $('aiHealth').classList.toggle('hidden', !result);
        if (!result) return;
        $('aiStructure').textContent = `Structure: ${result.valid ? 'Valid' : 'Needs correction'} · Issues found: ${result.warnings.length}`;
        messages($('aiWarnings'), result.warnings, 'No warnings returned.');
    }
    function analysis(result, cvId) {
        $('aiAnalysis').classList.toggle('hidden', !result);
        $('aiSuggestions').replaceChildren();
        if (!result) return;
        $('aiScore').textContent = Number.isFinite(result.match_score) ? `Role Alignment Score: ${result.match_score}/100` : 'No role alignment score provided.';
        $('aiEstimate').classList.toggle('hidden', !Number.isFinite(result.match_score));
        messages($('aiStrengths'), result.strengths, 'No strengths returned.');
        messages($('aiGaps'), result.gaps, 'No gaps returned.');
        const groups = new Map();
        (result.suggestions || []).forEach(item => {
            const section = item.section || 'general';
            if (!groups.has(section)) {
                const group = node('section', '', $('aiSuggestions'), 'ai-suggestion-group');
                node('h4', label(section), group);
                groups.set(section, group);
            }
            const card = node('article', '', groups.get(section), 'ai-suggestion');
            node('span', `${label(item.priority || 'medium')} priority · ${item.source || 'AI'}`, card, 'ai-priority');
            node('p', item.message, card);
            node('p', item.recommended_action, card);
            const link = node('a', 'Open in Editor', card, 'secondary-button');
            const supported = ['personal','summary','skills','education','experience','projects','certifications','achievements','languages'];
            link.href = `/cvs/${cvId}/edit/${supported.includes(section) ? '#'+section : ''}`;
        });
        if (!groups.size) node('p', 'No suggestions returned.', $('aiSuggestions'));
    }
    function comparison(pending) {
        $('aiComparison').classList.toggle('hidden', !pending);
        $('aiOriginal').value = pending?.original || '';
        $('aiRewritten').value = pending?.rewritten || '';
        messages($('aiChanges'), pending?.changes || [], 'No change notes returned.');
    }
    function preview(container, cv, {editable = false} = {}) {
        container.replaceChildren();
        let schema = {};
        const schemaText = $('m9-cv-schema')?.textContent;
        if (schemaText) { try { schema = JSON.parse(schemaText); } catch (_) { /* M2 still validates on save. */ } }
        function assign(path, value) {
            let target = cv;
            path.slice(0, -1).forEach(key => { target = target[key]; });
            target[path.at(-1)] = value;
        }
        function blank(contract) {
            if (contract.type === 'object') return Object.fromEntries(Object.entries(contract.properties).map(([key, child]) => [key, blank(child)]));
            return contract.type === 'array' ? [] : contract.type === 'boolean' ? false : '';
        }
        function render(value, parent, path, contract = {}) {
            if (Array.isArray(value)) {
                if (editable && contract.items?.type === 'string') {
                    const input = node('textarea', '', parent, 'form-input');
                    input.rows = 3; input.value = value.join('\n');
                    input.id = 'importField-' + path.join('_');
                    input.setAttribute('aria-label', label(path.at(-1)) + ' (one item per line)');
                    input.addEventListener('input', () => assign(path, input.value.split(/\r?\n/).map(item => item.trim()).filter(Boolean)));
                    return;
                }
                if (editable && contract.items?.type === 'object') {
                    value.forEach((item, index) => {
                        const block = node('div', '', parent, 'ai-panel');
                        render(item, block, [...path, index], contract.items);
                        const remove = node('button', 'Remove entry', block, 'secondary-button');
                        remove.type = 'button';
                        remove.addEventListener('click', () => { value.splice(index, 1); preview(container, cv, {editable}); });
                    });
                    const add = node('button', 'Add ' + label(path.at(-1)) + ' entry', parent, 'secondary-button');
                    add.type = 'button'; add.disabled = value.length >= (contract.maxItems ?? Infinity);
                    add.addEventListener('click', () => { value.push(blank(contract.items)); preview(container, cv, {editable}); });
                    return;
                }
                if (!value.length) return;
                const list = node('ul', '', parent);
                value.forEach((item, index) => render(item, node('li', '', list), [...path, index], contract.items));
            } else if (value && typeof value === 'object') {
                Object.entries(value).forEach(([key, item]) => {
                    if (editable && path[0] === 'meta' && key === 'template_id') return;
                    if (!editable && (item === '' || item === null || (Array.isArray(item) && !item.length))) return;
                    const row = node('div', '', parent);
                    node('strong', label(key) + ': ', row);
                    render(item, row, [...path, key], contract.properties?.[key]);
                });
            } else if (editable) {
                const choices = contract.enum || [];
                const input = node(choices.length ? 'select' : contract.maxLength > 255 ? 'textarea' : 'input', '', parent, 'form-input');
                input.id = 'importField-' + path.join('_');
                input.setAttribute('aria-label', path.map(label).join(' '));
                if (choices.length) choices.forEach(choice => {
                    const option = node('option', choice || 'Not specified', input);
                    option.value = choice; option.selected = choice === value;
                });
                if (typeof value === 'boolean') { input.type = 'checkbox'; input.checked = value; }
                else {
                    if (['date', 'start_date', 'end_date'].includes(path.at(-1))) input.type = 'month';
                    else if (path.at(-1) === 'email') input.type = 'email';
                    input.value = value ?? '';
                    if (contract.maxLength) input.maxLength = contract.maxLength;
                }
                input.addEventListener('input', () => assign(path, typeof value === 'boolean' ? input.checked : input.value));
            } else { node('span', value, parent); }
        }
        Object.entries(cv).filter(([key]) => key !== 'schema_version').forEach(([key, value]) => {
            const section = node('section', '', container, 'ai-suggestion-group');
            node('h4', key === 'meta' ? 'CV details' : label(key), section);
            render(value, section, [key], schema.properties?.[key]);
        });
    }
    function error(error) {
        return ({400: 'Please check the supplied CV information and supported text length.',
            401: 'Your session expired. Please sign in again.', 403: 'You cannot access this CV.',
            404: 'This CV is unavailable or does not belong to your account.',
            409: 'The CV changed elsewhere. Reload it and generate a new suggestion before applying.',
            429: 'You have reached the current AI request limit. Please try again later.',
            502: 'AI could not produce a valid response. Your CV has not been changed.',
            503: 'AI assistance is temporarily unavailable. You can continue editing manually.'})[error.status] ||
            (error.name === 'AbortError' ? 'The request timed out. Please retry.' : 'The request failed. Check your connection and refresh the saved CV before retrying.');
    }
    global.M6UI = {node, health, analysis, comparison, preview, error};
})(window);
