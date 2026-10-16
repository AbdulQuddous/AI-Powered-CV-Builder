/* M6's public API; authentication stays in the existing M9 helper. */
(function (global) {
    'use strict';
    function create(fetchApi) {
        async function post(operation, payload) {
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 60000);
            try {
                const response = await fetchApi(`/api/ai/${operation}/`, {
                    method: 'POST', signal: controller.signal, body: JSON.stringify(payload)
                });
                let result;
                try { result = await response.json(); }
                catch (_) { throw Object.assign(new Error('Unreadable AI response'), {status: 502}); }
                if (!result?.data || typeof result.data !== 'object') throw Object.assign(new Error('Invalid AI response'), {status: 502});
                return result.data;
            } finally { clearTimeout(timer); }
        }
        return {
            validate: (cv, role = '') => post('validate', {cv, target_role: role, use_ai: false}),
            optimize: (cv, role, job = '') => post('optimize', {cv, target_role: role, job_description: job, use_ai: true}),
            suggestions: (cv, role, job = '') => post('suggestions', {cv, target_role: role, job_description: job, use_ai: true}),
            tailor: (cvId, version, role, job = '') => post('tailor', {cv_id: cvId, expected_version: version, target_role: role, job_description: job}),
            rewrite: (text, section, role, job = '') => post('rewrite', {text, section, target_role: role, job_description: job}),
            improve: (text, section, role, job = '') => post('improve', {text, section, target_role: role, job_description: job}),
            extract: raw_text => post('extract', {raw_text})
        };
    }
    global.M6Api = {create};
})(window);
