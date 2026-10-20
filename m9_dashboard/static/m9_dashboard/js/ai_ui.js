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
        $('aiSingleComparison').classList.toggle('hidden', !pending);
        $('aiOriginal').value = pending?.original || '';
        $('aiRewritten').value = pending?.rewritten || '';
        messages($('aiChanges'), pending?.changes || [], 'No change notes returned.');
    }
    function tailoring(proposal, selectionChanged) {
        $('aiWholeComparison').classList.toggle('hidden', !proposal);
        $('aiTailorChanges').replaceChildren();
        $('aiTailorSuggestions').replaceChildren();
        $('aiTailorWarnings').replaceChildren();
        $('aiJobAlignment').replaceChildren();
        $('aiJobAlignment').classList.toggle('hidden', !(proposal?.job_alignment?.length || proposal?.job_alignment_warning));
        $('aiTailorSummary').textContent = proposal ? proposal.changes.length ? proposal.summary : 'No wording changes were proposed. Your saved CV is unchanged.' : '';
        if (!proposal) return;
        if (proposal.job_alignment_warning) node('p', proposal.job_alignment_warning, $('aiJobAlignment'), 'ai-muted');
        if (proposal.job_alignment?.length) {
            node('h4', 'How your CV relates to this job', $('aiJobAlignment'));
            node('p', 'Based on your saved CV. Review the evidence; missing requirements stay as advice.', $('aiJobAlignment'), 'ai-muted');
            const list = node('ul', '', $('aiJobAlignment'), 'ai-requirements');
            const statuses = {supported: 'CV evidence found', partial: 'Related evidence — check fit', missing: 'Not evidenced in your CV'};
            for (const item of proposal.job_alignment) {
                const row = node('li', '', list, 'ai-requirement');
                node('span', statuses[item.status], row, `ai-requirement-status ai-requirement-${item.status}`);
                node('p', item.requirement, row, 'ai-requirement-text');
                for (const evidence of item.evidence) {
                    const section = evidence.path.split('/')[1] || 'CV';
                    node('p', `${label(section)}: “${evidence.quote}”`, row, 'ai-requirement-evidence');
                }
            }
        }
        const warnings = proposal.warnings || [];
        if (warnings.length) node('p', warnings[0], $('aiTailorWarnings'));
        if (warnings.length > 1) {
            const details = node('details', '', $('aiTailorWarnings'));
            node('summary', `Why ${warnings.length - 1} ${warnings.length === 2 ? 'suggestion was' : 'suggestions were'} left out`, details);
            const list = node('ul', '', details);
            warnings.slice(1).forEach(warning => node('li', warning, list));
        }
        proposal.changes.forEach((change, index) => {
            const card = node('article', '', $('aiTailorChanges'), 'ai-change-card');
            const label = node('label', '', card, 'ai-change-label');
            const check = node('input', '', label, 'ai-change-check');
            check.type = 'checkbox'; check.checked = change.accepted;
            check.id = `aiChange-${index}`;
            node('span', change.label, label);
            check.addEventListener('change', () => {
                change.accepted = check.checked;
                selectionChanged();
            });
            const columns = node('div', '', card, 'ai-columns');
            for (const [heading, text, className] of [
                ['Current wording', change.original, 'ai-change-text'],
                ['Suggested wording', change.rewritten, 'ai-change-text ai-suggested']
            ]) {
                const column = node('div', '', columns, className);
                node('h4', heading, column);
                node('p', text, column);
            }
            node('p', change.reason, card, 'ai-change-reason');
        });
        if (proposal.suggestions?.length) {
            node('h4', 'Other ways to strengthen your CV', $('aiTailorSuggestions'));
            const list = node('ul', '', $('aiTailorSuggestions'));
            proposal.suggestions.forEach(text => node('li', text, list));
        }
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
        if (error.status === 503) {
            const reasons = {
                invalid_request: 'Gemini could not accept the review request. Refresh the page and try again. If it continues, ask the site administrator to check the AI request configuration.',
                configuration_error: 'The AI service is not configured correctly. Ask the site administrator to check the Gemini configuration.',
                authentication_failed: 'Gemini rejected the service credentials. Ask the site administrator to check the API key.',
                permission_denied: 'The AI service does not have permission to use Gemini. Ask the site administrator to check access.',
                quota_exceeded: 'The Gemini request quota has been reached. Try again later, or ask the site administrator to check the AI quota.',
                model_not_found: 'The configured Gemini model is unavailable. Ask the site administrator to check the model setting.',
                timeout: 'Gemini took too long to respond. Try again; your job details are still here.',
                connection_failed: 'The server could not connect to Gemini. Try again shortly; your job details are still here.',
            };
            const message = reasons[error.details?.error?.reason];
            if (message) return message;
        }
        if (error.status === 400) {
            const message = error.userMessage || error.details?.error?.message || error.message;
            if (typeof message === 'string' && message && message !== 'Request failed (400).') return message;
        }
        if (error.status === 502) {
            const reasons = {
                factual_validation: 'AI suggested changes that could not be verified against your CV. Your saved CV is unchanged. Try again for a fresh review.',
                source_mismatch: 'AI could not match its changes to your saved wording. Try again to request a fresh review.',
                response_truncated: 'The AI response was cut short. Try again to request a complete review.',
                response_blocked: 'AI could not generate a review for this request. Adjust the job description or choose a part to rewrite.',
                response_invalid_json: 'AI returned an incomplete review. Try again to request a fresh review.',
                schema_invalid: 'AI returned an incomplete review. Try again to request a fresh review.',
            };
            const message = reasons[error.details?.error?.reason];
            if (message) return message;
        }
        return ({400: 'Check the target role, job description and selected text, then try again.',
            401: 'Your session expired. Please sign in again.', 403: 'You cannot access this CV.',
            404: 'This CV is unavailable or does not belong to your account.',
            409: 'The CV changed elsewhere. Reload it and generate a new suggestion before applying.',
            429: 'You have reached the current AI request limit. Please try again later.',
            500: 'The service could not complete this request. Try again shortly or edit your CV manually.',
            502: 'AI could not produce a usable suggestion. Try again, or choose a smaller part to rewrite.',
            503: 'AI assistance is temporarily unavailable. Try again shortly, or edit your CV manually.'})[error.status] ||
            (error.name === 'AbortError' ? 'AI took too long to respond. Try again; your job details are still here.'
                : 'Could not connect to the service. Check your connection and try again; your job details are still here.');
    }
    global.M6UI = {node, health, analysis, comparison, tailoring, preview, error};
})(window);
