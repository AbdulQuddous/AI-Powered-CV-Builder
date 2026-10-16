# M7 manual CV editor

Open `/cvs/{id}/edit/` from the dashboard. Django serves an empty template shell;
M1/M2 authenticate requests and authorize the saved CV. The editor uses the existing
Django Templates, prebuilt Tailwind CSS, Alpine 3.17.4 and JavaScript architecture.
No npm manifest or React application is part of this repository.

## Backend connections

- GET `/api/cvs/{id}/` loads M2's `{id, name, data, version, ...}` resource.
- PATCH on the same URL saves `{data, expected_version}`. A stale version produces
  HTTP 409; the editor retains the draft and offers Reload Latest or Export Draft JSON.
- The shared `accounts/js/session.js` retains JWT access/refresh tokens in sessionStorage,
  renews once after 401 and rotates both tokens. Inline login uses M1's `{email,password}`.
- GET `preview/` loads M8's selected template; POST `export/pdf/` and `export/docx/`
  download the saved document. `/dashboard/?review={id}` opens its existing AI Review.

## Editing and preview

Personal, Summary, Experience, Education, Projects, Skills, Certifications,
Achievements and Languages are editable. Object defaults and enum/collection limits
come from M10's canonical CV schema. Dates use `YYYY-MM` or remain blank; current
experience is a checkbox. Arrays support add/remove/reorder and multiline items.
The editor preserves unsaved input when validation or transport fails and presents
M2 field errors. Five experience entries is the current shared schema limit.

Saving is explicit. Local draft preview makes no AI call and writes no database data.
The preview uses the selected M8 template CSS on an A4 sheet (210 × 297 mm), with
Fit width, 100% and 125% zoom. Selecting a section reveals its preview heading when
outside the visible area. Long draft content extends beneath the first page;
WeasyPrint owns final PDF page breaks. Downloaded PDF tests verify actual text and
A4 dimensions, rather than just the existence of a response.

## Verification

```bash
.venv/bin/python manage.py test --settings=config.test_settings
node tests/editor.test.cjs
node tests/live_preview.test.cjs
```

For cross-module results, opt-in browser instructions and production limitations,
see [the final system audit](../docs/FINAL_SYSTEM_AUDIT.md). Production still needs
an agreed HTTPS/CSP/static asset policy; template-shell accessibility does not grant
access to CV data without a valid JWT and the owner's authorization.
