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
                const result = await response.json();
                if (!result?.data || typeof result.data !== 'object') throw new Error('Invalid AI response');
                return result.data;
            } finally { clearTimeout(timer); }
        }
        return {
            validate: (cv, role = '') => post('validate', {cv, target_role: role, use_ai: false}),
            optimize: (cv, role, job = '') => post('optimize', {cv, target_role: role, job_description: job, use_ai: true}),
            suggestions: (cv, role, job = '') => post('suggestions', {cv, target_role: role, job_description: job, use_ai: true}),
            rewrite: (text, section, role) => post('rewrite', {text, section, target_role: role}),
            improve: (text, section, role) => post('improve', {text, section, target_role: role}),
            extract: raw_text => post('extract', {raw_text})
        };
    }
    global.M6Api = {create};
})(window);
