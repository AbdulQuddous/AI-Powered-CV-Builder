# M6 dashboard integration

AI Review loads the selected CV through M2 and sends the complete `data` document to M6. AI proposals are never saved automatically.

## Files changed for this integration

- `templates/m9_dashboard/dashboard.html`: includes the review dialog and its assets.
- `templates/m9_dashboard/ai_review.html`: health, role analysis, suggestions, field selection, comparison, approval, and saved PDF controls.
- `static/m9_dashboard/css/ai_review.css`: responsive styles using the existing dashboard palette.
- `static/m9_dashboard/js/dashboard.js`: card action, shared authenticated client wiring, authentication cleanup, and invalidation after CV refresh.
- `static/m9_dashboard/js/ai_api.js`: the six existing M6 endpoints and a 60-second request timeout; uses M9's existing JWT helper.
- `static/m9_dashboard/js/ai_ui.js`: safe DOM presentation, including grouped suggestions, optional scores, error messages, and imported CV previews.
- `static/m9_dashboard/js/ai_review.js`: selected CV state, request guards, response reuse, approval, and versioned M2 saves.
- `templates/m9_dashboard/import_modal.html` and `static/m9_dashboard/js/import_cv.js`: optional M6 extraction after M4, review, template selection, and explicit M2 creation.
- `../m7_editor/static/m7_editor/js/editor.js`: accepts a known section name from the URL fragment when entering the existing editor.
- `../tests/test_m9.py`, `../tests/test_m9_ai.py`, `../tests/m6_dashboard.test.cjs`, and `../tests/editor.test.cjs`: template, API, state, approval, and editor-navigation checks.

M6, M5, M2, M4, M8, and shared schemas require no backend changes for this integration.

## API usage

Opening the dashboard or selecting a CV makes no M6 request. Health Check sends `use_ai: false`. Optimize for Role explicitly sends the complete CV, target role, and optional job description. View Suggestions reuses that result; if requested independently, it calls the existing suggestions endpoint. Identical analysis requests in the current review reuse the frontend result, in addition to M6's existing backend caching.

Changing the target role or job description clears role-specific results. Changing the selected CV, detecting new saved data, or accepting a rewrite clears outdated analysis. Returning to the dashboard window checks the current saved CV without calling AI.

Rewrite and Improve operate on an actual saved summary, project description, experience/project bullet, or achievement. Apply clones the saved document, changes only the selected field, and PATCHes `{data, expected_version}` through M2. A conflict requires a fresh suggestion; no blind retry overwrites newer edits.

Importing calls M4 first. The optional AI extraction button then calls M6. Confirm and create new CV calls M2 only after review. Existing CVs are preserved. Templates come from M3.

## Run checks

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test tests cv_imports --settings=config.test_settings
node tests/m6_dashboard.test.cjs
node tests/m4_import.test.cjs
node tests/editor.test.cjs
```

AI responses are mocked in automated tests. PDF integration uses a mocked exporter; existing rendering/export tests remain part of the regression suite.

## Manual checks

1. Start `python manage.py runserver`, sign in at `/dashboard/`, and choose AI Review on a CV card.
2. In DevTools Network, confirm selection only reads M2. Click Health Check and confirm `/api/ai/validate/` sends `use_ai: false`.
3. Enter the target role, optionally add a job description, and click Optimize for Role. Check warnings, strengths, gaps, score (when supplied), and suggestions.
4. Click View Suggestions. It must not send another AI request for the same analysis.
5. Choose a saved text field, click Rewrite with AI or Improve with AI, and compare the original and proposal. Discard must send no PATCH. Apply must PATCH the selected CV with its expected version.
6. Open the editor from a suggestion and check that its section opens. Confirm unrelated projects and personal information are unchanged after accepting a rewrite.
7. Change the target role or select another CV. Previous results must disappear. Edit the CV in another tab and return; results must become stale.
8. Download saved PDF. Accepted wording should appear; discarded wording should not.
9. Import a PDF/DOCX, upload, and extract text through M4. Click Extract CV information with AI, review the proposed fields, choose a name and template, then confirm. No CV should be created before confirmation.
10. Simulate an unavailable provider or expired authentication. Check readable errors, preserved saved CV data, and successful retry after resolving the issue.

Live AI actions require the project's existing Gemini configuration. A live provider request and a visual browser walkthrough are separate from the mocked automated checks.
