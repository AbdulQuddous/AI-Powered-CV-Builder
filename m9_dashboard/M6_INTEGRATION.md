# M6 dashboard integration

Current cross-module verification is in [the final system audit](../docs/FINAL_SYSTEM_AUDIT.md).
Import review now supports schema-driven corrections before explicit M2 creation.
M7 includes an AI Review link back to the dashboard. Real PDF output and real browser
workflows are tested in the final audit with mocked AI; live Gemini remains untested.

AI Review opens **Improve your CV** with two choices: **Improve whole CV** and
**Rewrite one part**. Both show current and suggested wording before an explicit save.
Generation never updates the saved CV.

## Files changed for this integration

- `templates/m9_dashboard/dashboard.html`: includes the review dialog and its assets.
- `templates/m9_dashboard/ai_review.html`: two improvement modes, shared job context, comparisons, selected approvals, and saved PDF controls. Missing-detail and job-fit checks are secondary tools.
- `static/m9_dashboard/css/ai_review.css`: responsive styles using the existing dashboard palette.
- `static/m9_dashboard/js/dashboard.js`: card action, shared authenticated client wiring, authentication cleanup, and invalidation after CV refresh.
- `static/m9_dashboard/js/ai_api.js`: existing M6 endpoints plus whole-CV tailoring, with a 60-second request timeout; uses M9's existing JWT helper.
- `static/m9_dashboard/js/ai_ui.js`: safe DOM presentation, including grouped suggestions, optional scores, error messages, and imported CV previews.
- `static/m9_dashboard/js/ai_review.js`: selected CV state, request guards, response reuse, approval, and versioned M2 saves.
- `templates/m9_dashboard/import_modal.html` and `static/m9_dashboard/js/import_cv.js`: optional M6 extraction after M4, review, template selection, and explicit M2 creation.
- `../m7_editor/static/m7_editor/js/editor.js`: accepts a known section name from the URL fragment when entering the existing editor.
- `../tests/test_m9.py`, `../tests/test_m9_ai.py`, `../tests/m6_dashboard.test.cjs`, and `../tests/editor.test.cjs`: template, API, state, approval, and editor-navigation checks.

`ai/services/tailoring.py` and `POST /api/ai/tailor/` add whole-CV wording proposals.
Selected rewrites also accept an optional job description and up to 5,000 characters
of saved text. No model, shared CV schema or database migration changes are required.

## API usage

Opening the dashboard or selecting a CV makes no M6 request. Whole-CV improvement
posts `{cv_id, expected_version, target_role, job_description}` to `/api/ai/tailor/`.
A target role or job description is required. The server reads the owner's saved CV
and makes one provider request for a combined review of its existing summary,
experience highlights, project descriptions/highlights and achievements. Contacts
are removed from provider context. Identical requests reuse an owner-scoped cache.
The result includes original/rewritten text at supported paths, reasons and advice;
it cannot change identity, employers, qualifications, skills or other factual fields.

Changing the target role or job description clears role-specific results. Changing the selected CV, detecting new saved data, or accepting a rewrite clears outdated analysis. Returning to the dashboard window checks the current saved CV without calling AI.

**Rewrite one part** operates on a saved summary, project description,
experience/project bullet or achievement. Its role and job description are optional.
Save clones the reviewed document and PATCHes `{data, expected_version}` through M2.
Whole-CV approval applies only checked suggestions in one save and one new version.
A conflict reloads current data and requires fresh suggestions.

Tailoring validation accepts capitalization, line-break and equivalent number-format
changes in confirmed source facts. It still rejects new skills, changed metrics and
facts transferred between projects or employers. If some wording changes are safe
and others cannot be verified, the review keeps the safe changes and displays a note
about the omitted suggestions. An entirely unsafe or structurally invalid response
still fails. Rejections log fixed reason codes and known field paths without CV text.

**Check missing details** uses local validation (`use_ai: false`). **Review job fit**
returns advice, using the existing optimize/suggestions endpoints. These tools are
grouped in a collapsed section and do not rewrite or save the CV. Provider errors
appear once, with a retry action where appropriate; job inputs are retained.

Importing calls M4 first. The optional AI extraction button then calls M6. Confirm and create new CV calls M2 only after review. Existing CVs are preserved. Templates come from M3.

## Run checks

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test tests cv_imports --settings=config.test_settings
.venv/bin/python manage.py test tests.test_cv_tailoring tests.test_m9_ai --settings=config.test_settings
node tests/m6_dashboard.test.cjs
node tests/m4_import.test.cjs
node tests/editor.test.cjs
```

AI responses are mocked in automated tests. PDF integration uses a mocked exporter; existing rendering/export tests remain part of the regression suite.

## Manual checks

1. Start `python manage.py runserver`, sign in at `/dashboard/`, and choose AI Review on a CV card.
2. Keep **Improve whole CV** selected. Paste a job description or enter a target role, then click **Suggest improvements for whole CV**. Confirm one `/api/ai/tailor/` request and no CV save.
3. Compare the current/suggested wording. Uncheck a change you do not want, then click **Save N changes**. Confirm one versioned save, with unchecked text and factual details preserved.
4. Select **Rewrite one part**, choose saved text, then click **Suggest a rewrite**. Compare and save that change, or discard it without a save.
5. Expand **Check missing details or review job fit**. Missing-detail checks require no AI call. Job-fit advice reuses an identical result without another AI request.
6. Open the editor from the footer or a job-fit suggestion and confirm approved wording is present.
7. Change the target role or select another CV. Previous results must disappear. Edit the CV in another tab and return; results must become stale.
8. Download saved PDF. Accepted wording should appear; discarded wording should not.
9. Import a PDF/DOCX, upload, and extract text through M4. Click Extract CV information with AI, review the proposed fields, choose a name and template, then confirm. No CV should be created before confirmation.
10. Simulate an unavailable provider or expired authentication. Check one readable error, retained job inputs, no saved CV changes, and successful retry after resolving the issue.

Live AI actions require the project's existing Gemini configuration. On 16 October
2026, a synthetic live Gemini review reproduced the reported 502: capitalization of
`python, django and rest apis` was incorrectly rejected as new facts. The captured
response passed the corrected validator, and a fresh live synthetic review also
passed. No application CV was sent or changed during these diagnostics. Automated
regressions continue to mock external AI calls.
