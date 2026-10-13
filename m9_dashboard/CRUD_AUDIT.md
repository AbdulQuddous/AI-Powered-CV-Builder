# Dashboard CV CRUD audit

## Existing functionality verified

The dashboard route is `/dashboard/`, served by `m9_dashboard/views.py` and `urls.py`. Its template is `templates/m9_dashboard/dashboard.html`, and `static/m9_dashboard/js/dashboard.js` contains the existing authenticated `apiFetch` helper. JWT credentials remain in `sessionStorage.cv_access`.

M2 already implements create, list, retrieve, PATCH, DELETE, duplication, and version history in `cvs/views.py`, `serializers.py`, `models.py`, `services.py`, and `urls.py`. Owner-scoped lookups enforce permissions. M2 handles transactions, snapshots, and version conflicts. No M2 production code changes are needed.

Previously working dashboard features:

- Manual creation: name, role, career level, template, then the existing M7 editor.
- Authenticated listing, paginated reads, search, template filters, sorting, and statistics.
- Edit navigation to `/cvs/{id}/edit/`; the editor saves through M2 using `expected_version`.
- Authenticated M8 preview.
- M2 duplication and dashboard refresh.
- Chatbot-assisted creation, M4/M6 import, AI review, approved rewriting, and saved PDF download.

Missing or incomplete frontend features were deletion, read-only version history, career-level display on cards, and identification of the new duplicate. Repeated Create/Duplicate submissions also lacked explicit in-flight guards.

## Implemented changes

- Delete and Version history actions on each card.
- Delete confirmation names the actual CV, includes Cancel/Delete, and explains that M2 also deletes its saved versions.
- DELETE runs only after confirmation. Controls stay disabled while it is running; repeated submissions are ignored. The empty 204 body is never parsed as JSON.
- Success removes only the deleted record from dashboard state and recalculates cards, filters, statistics, and empty states. A toast confirms the deleted title.
- Failure retains the card and displays a retry message. Expired authentication uses the existing login flow and clears private UI state.
- Late list responses cannot restore a CV that was deleted while the request was pending.
- Browser resume references for the deleted CV are removed, its active chat UI closes, and existing AI results are invalidated. M5 contracts and stored chat history stay unchanged.
- Version history displays version number, historical CV title, and creation timestamp. Older pages are loaded through the existing API. History pagination accepts only the same origin and the selected CV's history path.
- Career level now appears on each card.
- Duplication identifies the returned CV name and ID, preserves the source, updates the dashboard, and prevents repeated in-flight requests for the same source.
- Create uses its existing implementation with an explicit submission guard.
- Dialogs support keyboard cancellation, focus containment, focus return, loading status, and error announcements. Event registration is guarded against duplication.

## Files changed

| File | Purpose |
| --- | --- |
| `templates/m9_dashboard/dashboard.html` | Include the CRUD dialogs and controller. |
| `templates/m9_dashboard/crud_modals.html` | Confirmation and read-only version-history dialogs. |
| `static/m9_dashboard/js/cv_operations.js` | Deletion, history reads/pagination, keyboard handling, and error states through the existing API helper. |
| `static/m9_dashboard/js/dashboard.js` | Card actions/details, duplicate identification, submission guards, deletion state updates, and protection against stale list responses. |
| `static/m9_dashboard/css/dashboard.css` | Delete controls and responsive history table styling. |
| `../tests/test_cvs.py` | Empty 204 deletion, failed deletion, expired JWT, nonmutating history reads, and chatbot-created CV deletion. Existing tests cover create/read/update, foreign ownership, unauthorized requests, and version conflicts. |
| `../tests/test_m9.py` | Dialog/template/static asset checks. |
| `../tests/dashboard_crud.test.cjs` | CRUD UI actions, cancellation, failures, duplicate clicks, authentication, statistics, history pagination, keyboard behavior, and response races. |
| `CRUD_AUDIT.md` | Audit findings, endpoint map, verification commands, and manual guide. |

M4, M5, M6, M8, M10, M7 editor behavior, and all existing backend contracts are preserved.

## Existing endpoints reused

| Operation | API |
| --- | --- |
| Create | `POST /api/cvs/` |
| List | `GET /api/cvs/` |
| Read / update | `GET` / `PATCH /api/cvs/{id}/` |
| Delete | `DELETE /api/cvs/{id}/` |
| Duplicate | `POST /api/cvs/{id}/duplicate/` |
| History | `GET /api/cvs/{id}/versions/` |

## Verification commands

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test --settings=config.test_settings
node tests/dashboard_crud.test.cjs
node tests/m6_dashboard.test.cjs
node tests/m4_import.test.cjs
node tests/editor.test.cjs
```

Backend tests use test records and mocked AI providers. Frontend tests run the real JavaScript with a mocked browser/API environment.

## Manual verification

Use a test account and disposable CVs.

1. Start the server and refresh `/dashboard/`. Create a CV with all four fields, edit it in M7, and save. Verify its card shows title, role, career level, template, and updated date.
2. Check search, template filtering, and sorting. View the saved preview; confirm existing AI review and PDF download remain available.
3. Duplicate the CV. Verify a new card and a toast naming its ID/title, copied data, unchanged original, and updated totals.
4. Open Version history. Confirm timestamps and the versions created by edits. Close it; viewing history must not create or delete snapshots.
5. Click Delete. Confirm the correct title appears. Click Cancel or press Escape; no DELETE should appear in DevTools Network, and the card/statistics must stay unchanged.
6. Reopen Delete and confirm. Check one DELETE request with status 204, removed card, updated totals, and success notification. Delete the final disposable CV to check the empty state.
7. Switch DevTools Network offline before confirming deletion. Verify the error is visible, the card remains, and retry becomes available after reconnecting.
8. Check rapid repeated clicks: Create, Duplicate, and Delete must each create only one in-flight request for that action.
9. Expire/sign out the test session, then attempt deletion. Existing login behavior must appear; the saved record must remain.
10. With two test accounts, verify each list contains only its own CVs. Authenticated access to the other account's CV/detail/history/delete endpoints must return 404.
11. Create a CV through the chatbot save flow. Delete it from the dashboard and check that manual creation, new chat sessions, imports, and editor workflows still work.

## Limits

Version history is read-only; M2 has no version-restoration endpoint. Successful deletion removes the CV and its snapshots according to M2's existing cascade behavior, while M5 chat sessions are retained. If a DELETE response is lost, the frontend cannot know whether the server committed it; refresh the list to verify before retrying. No live Gemini calls or visual browser walkthrough are required by the automated checks.
