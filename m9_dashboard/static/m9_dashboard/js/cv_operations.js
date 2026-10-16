/* M9 deletion, history and explicitly confirmed restoration through M2. */
(function (global) {
    'use strict';
    const $ = id => document.getElementById(id);
    let api, generation = 0, deleteCV = null, deleting = false, deleteTrigger = null;
    let historyCV = null, historyBusy = false, historyTrigger = null, nextURL = null, seen = new Set();
    let restoreVersion = null, restoring = false;
    const title = cv => cv.name || `CV #${cv.id}`;
    const visible = id => !$(id).classList.contains('hidden');
    function message(error, operation) {
        return ({401:'Your session expired. Please sign in again.',403:'You do not have permission to access this CV.',
            404:'This CV is unavailable or does not belong to your account.',429:'Too many requests. Please wait before retrying.'})[error.status] ||
            (operation === 'delete' ? 'Could not confirm deletion. Your CV stays listed. Retry or refresh the dashboard to check its current status.' : 'Could not load version history. Please retry.');
    }
    function focusBack(trigger) {
        if (trigger?.isConnected) trigger.focus();
        else $('refreshBtn').focus();
    }
    function reset() {
        generation++;
        deleteCV = historyCV = null; deleting = historyBusy = false;
        deleteTrigger = historyTrigger = null;
        nextURL = null; seen = new Set();
        restoreVersion = null; restoring = false;
        $('restorePanel').classList.add('hidden');
        ['versionsClose','versionsCheckpoint','restoreConfirm','restoreCancel'].forEach(id => { $(id).disabled = false; });
        api.closeModal('deleteModal'); api.closeModal('versionsModal');
        $('deleteCVName').textContent = $('versionsCVName').textContent = '';
        $('versionsRows').replaceChildren();
        $('deleteConfirm').disabled = $('deleteCancel').disabled = false;
        $('deleteModal').setAttribute('aria-busy','false');
        $('versionsModal').setAttribute('aria-busy','false');
    }
    function openDelete(cv, trigger) {
        if (deleting || !api.requireLogin()) return;
        deleteCV = {id:Number(cv.id),name:title(cv)};
        deleteTrigger = trigger;
        $('deleteCVName').textContent = deleteCV.name;
        $('deleteError').classList.add('hidden');
        $('deleteStatus').textContent = '';
        api.openModal('deleteModal');
        $('deleteCancel').focus();
    }
    function cancelDelete() {
        if (deleting) return;
        deleteCV = null;
        api.closeModal('deleteModal');
        focusBack(deleteTrigger);
    }
    async function confirmDelete() {
        if (deleting || !deleteCV || !api.requireLogin()) return;
        const run = generation, cv = deleteCV;
        deleting = true;
        $('deleteConfirm').disabled = $('deleteCancel').disabled = true;
        $('deleteModal').setAttribute('aria-busy','true');
        $('deleteModal').focus();
        $('deleteError').classList.add('hidden');
        $('deleteStatus').textContent = 'Deleting CV…';
        try {
            const response = await api.fetch(`/api/cvs/${cv.id}/`, {method:'DELETE'});
            if (run !== generation) return;
            if (response.status !== 204) throw new Error('Unexpected deletion response');
            // HTTP 204 has no JSON body.
            api.onDeleted(cv.id);
            if (historyCV?.id === cv.id) closeHistory();
            deleteCV = null;
            api.closeModal('deleteModal');
            api.notify(`Deleted “${cv.name}”.`);
            focusBack(null);
        } catch(error) {
            if (run !== generation) return;
            $('deleteError').textContent = message(error,'delete');
            $('deleteError').classList.remove('hidden');
            $('deleteStatus').textContent = 'Deletion did not complete.';
        } finally {
            if (run === generation) {
                deleting = false;
                $('deleteConfirm').disabled = $('deleteCancel').disabled = false;
                $('deleteModal').setAttribute('aria-busy','false');
            }
        }
    }
    function historyPath() { return `/api/cvs/${historyCV.id}/versions/`; }
    function timestamp(value) {
        const date = new Date(value);
        return Number.isNaN(date.getTime()) ? 'Not available' : new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(date);
    }
    function closeHistory() {
        if (restoring) return;
        historyCV = null;
        historyBusy = false;
        api.closeModal('versionsModal');
        focusBack(historyTrigger);
    }
    async function openHistory(cv, trigger) {
        if (restoring || !api.requireLogin()) return;
        historyCV = {id:Number(cv.id),name:title(cv),version:cv.version};
        restoreVersion = null;
        $('restorePanel').classList.add('hidden');
        historyTrigger = trigger;
        historyBusy = false; nextURL = null; seen = new Set();
        $('versionsRows').replaceChildren();
        $('versionsCVName').textContent = historyCV.name;
        api.openModal('versionsModal');
        $('versionsClose').focus();
        await loadHistory();
    }
    async function loadHistory() {
        if (historyBusy || !historyCV || !api.requireLogin()) return;
        const run = generation, cv = historyCV, target = nextURL || historyPath();
        historyBusy = true;
        $('versionsCheckpoint').disabled = true;
        $('versionsMore').disabled = true;
        $('versionsModal').setAttribute('aria-busy','true');
        $('versionsError').classList.add('hidden');
        $('versionsStatus').textContent = 'Loading saved versions…';
        try {
            const url = new URL(target,global.location.origin);
            if (url.origin !== global.location.origin || url.pathname !== historyPath()) throw new Error('Invalid history URL');
            const path = url.pathname + url.search;
            if (seen.has(path)) throw new Error('Repeated history page');
            const response = await api.fetch(path);
            const body = await response.json();
            if (run !== generation || historyCV !== cv) return;
            const page = api.normalizeList(body);
            for (const version of page.items) {
                const row = document.createElement('tr');
                for (const value of [version.version,version.name,timestamp(version.created_at)]) {
                    const cell = document.createElement('td');
                    cell.textContent = String(value ?? ''); row.appendChild(cell);
                }
                const action = document.createElement('td');
                const restore = document.createElement('button');
                restore.type = 'button'; restore.className = 'secondary-button';
                restore.textContent = Number(version.version) === cv.version ? 'Current' : 'Restore';
                restore.disabled = Number(version.version) === cv.version;
                restore.addEventListener('click', () => {
                    if (restoring || historyCV !== cv) return;
                    restoreVersion = Number(version.version);
                    $('restoreDescription').textContent = `Restore version ${restoreVersion} of “${cv.name}” as a new version? Later history will be kept.`;
                    $('restoreError').classList.add('hidden');
                    $('restorePanel').classList.remove('hidden');
                    $('restoreCancel').focus();
                });
                action.appendChild(restore); row.appendChild(action);
                $('versionsRows').appendChild(row);
            }
            seen.add(path); nextURL = page.next;
            $('versionsStatus').textContent = page.items.length ? 'Saved versions loaded.' : 'No saved versions found.';
            $('versionsMore').textContent = 'Load older versions';
            $('versionsMore').classList.toggle('hidden',!nextURL);
        } catch(error) {
            if (run !== generation || historyCV !== cv) return;
            $('versionsError').textContent = message(error,'history');
            $('versionsError').classList.remove('hidden');
            $('versionsStatus').textContent = 'History could not be loaded.';
            $('versionsMore').textContent = 'Retry loading';
            $('versionsMore').classList.remove('hidden');
        } finally {
            if (run === generation && historyCV === cv) {
                historyBusy = false;
                $('versionsCheckpoint').disabled = restoring;
                $('versionsMore').disabled = false;
                $('versionsModal').setAttribute('aria-busy','false');
            }
        }
    }
    async function writeHistory(version) {
        if (restoring || historyBusy || !historyCV || (version !== null && !Number.isInteger(version)) || !api.requireLogin()) return;
        const run = generation, cv = historyCV, checkpoint = version === null;
        restoring = true;
        ['versionsClose','versionsCheckpoint','versionsMore','restoreConfirm','restoreCancel'].forEach(id => { $(id).disabled = true; });
        $('versionsModal').focus();
        $('versionsModal').setAttribute('aria-busy','true');
        $('versionsStatus').textContent = checkpoint ? 'Creating checkpoint...' : 'Restoring selected version...';
        try {
            const response = await api.fetch(`/api/cvs/${cv.id}/${checkpoint ? 'versions' : 'restore'}/`, {
                method: 'POST', body: JSON.stringify(checkpoint ? {expected_version: cv.version} : {version, expected_version: cv.version})
            });
            const result = await response.json();
            const restored = checkpoint ? await (await api.fetch(`/api/cvs/${cv.id}/`)).json() : result;
            if (run !== generation || historyCV !== cv) return;
            cv.version = restored.version; cv.name = title(restored);
            api.onRestored(restored);
            $('versionsCVName').textContent = cv.name;
            $('restorePanel').classList.add('hidden'); restoreVersion = null;
            $('versionsRows').replaceChildren(); nextURL = null; seen = new Set();
            await loadHistory();
            api.notify(checkpoint ? `Checkpoint ${result.version} created.` : `Version ${version} restored as version ${restored.version}.`);
            $('versionsClose').focus();
        } catch (error) {
            if (run !== generation || historyCV !== cv) return;
            const errorNode = $(checkpoint ? 'versionsError' : 'restoreError');
            errorNode.textContent = error.status === 409
                ? 'The CV changed elsewhere. Close history, refresh the dashboard, and review the current version before retrying.'
                : 'Could not confirm the version change. Refresh to verify the saved version before retrying.';
            errorNode.classList.remove('hidden');
            $('versionsStatus').textContent = 'Version change did not complete.';
        } finally {
            if (run === generation && historyCV === cv) {
                restoring = false;
                ['versionsClose','versionsCheckpoint','versionsMore','restoreConfirm','restoreCancel'].forEach(id => { $(id).disabled = false; });
                $('versionsModal').setAttribute('aria-busy','false');
            }
        }
    }
    function init(dependencies) {
        if (api) return;
        api = dependencies;
        $('deleteCancel').addEventListener('click',cancelDelete);
        $('deleteConfirm').addEventListener('click',confirmDelete);
        $('versionsClose').addEventListener('click',closeHistory);
        $('versionsMore').addEventListener('click',loadHistory);
        $('restoreConfirm').addEventListener('click', () => {
            if (Number.isInteger(restoreVersion)) return writeHistory(restoreVersion);
        });
        $('versionsCheckpoint').addEventListener('click', () => writeHistory(null));
        $('restoreCancel').addEventListener('click', () => {
            if (restoring) return;
            restoreVersion = null; $('restorePanel').classList.add('hidden');
            $('versionsClose').focus();
        });
        document.addEventListener('keydown',event => {
            const id = visible('deleteModal') ? 'deleteModal' : visible('versionsModal') ? 'versionsModal' : null;
            if (!id) return;
            if (event.key === 'Escape') {
                event.preventDefault(); event.stopImmediatePropagation();
                if (id === 'deleteModal') cancelDelete(); else closeHistory();
            } else if (event.key === 'Tab') {
                const controls = [...$(id).querySelectorAll('button:not(:disabled)')].filter(item => item.getClientRects().length);
                if (!controls.length) { event.preventDefault(); $(id).focus(); return; }
                const first=controls[0],last=controls.at(-1);
                if (event.shiftKey && document.activeElement === first && last) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last && first) { event.preventDefault(); first.focus(); }
            }
        });
    }
    global.M9Crud = {init,openDelete,openHistory,reset};
})(window);
