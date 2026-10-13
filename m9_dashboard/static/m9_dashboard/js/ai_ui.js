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
    function preview(container, cv) {
        container.replaceChildren();
        function render(value, parent) {
            if (Array.isArray(value)) {
                if (!value.length) return;
                const list = node('ul', '', parent);
                value.forEach(item => render(item, node('li', '', list)));
            } else if (value && typeof value === 'object') {
                Object.entries(value).forEach(([key, item]) => {
                    if (item === '' || item === null || (Array.isArray(item) && !item.length)) return;
                    const row = node('div', '', parent);
                    node('strong', label(key) + ': ', row);
                    render(item, row);
                });
            } else { node('span', value, parent); }
        }
        Object.entries(cv).filter(([key]) => key !== 'schema_version').forEach(([key, value]) => {
            const section = node('section', '', container, 'ai-suggestion-group');
            node('h4', key === 'meta' ? 'CV details' : label(key), section);
            render(value, section);
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
