# Frontend connection audit — 14 October 2026

The dashboard's main CV workflows are connected to the existing backend. This audit did not change application behavior or introduce endpoints. Registration and asset-versioning changes from the preceding task remain in the working tree.

## Connections verified

| Module | Frontend entry point | Existing APIs used |
| --- | --- | --- |
| M1 accounts | Sign In, Register, My Profile | POST `/api/auth/login/`, POST `/api/auth/register/`, GET/PATCH `/api/auth/me/` |
| M2 CV management | Create, list, search/filter/sort, Edit, Delete, Duplicate, Version history | POST/GET `/api/cvs/`; GET/PATCH/DELETE `/api/cvs/{id}/`; POST `duplicate/`; GET `versions/` |
| M2 chat approval | Save collected details to CV | POST `/api/cvs/from-chat/` |
| M3 templates | Manual creation and import template selectors | GET `/api/templates/`; selected template ID persists through M2 |
| M4 document import | Import Existing CV: upload, recover status, extract text | POST `/api/cv-import/upload/`; GET `/api/cv-import/{id}/`; POST `extract/` |
| M5 conversation | Create CV with AI, Continue with AI, chat review/resume | POST `/api/chat/sessions/`; GET session detail; POST session messages |
| M6 intelligence | Import AI extraction, Health Check, Optimize, Suggestions, Rewrite, Improve | All six `/api/ai/` operations; proposals require explicit M2 save approval |
| M7 editor | Edit card action and AI review links | GET/PATCH M2 with `expected_version`; local draft preview, zoom and section scrolling |
| M8 rendering | View CV, editor Preview CV, PDF/DOCX downloads, AI Review PDF | GET `/api/cvs/{id}/preview/`; POST `export/pdf/` and `export/docx/` |
| M9 dashboard | Statistics, CRUD cards, authentication and modal coordination | Existing module clients; no independent CV persistence |
| M10 contracts | Producers, persistence validation and consumers | Internal shared schemas; no standalone screen required |
| M11 chat frontend | Dashboard chat modal and controls | M5 APIs and explicit M2 chat approval |

## Capabilities without a frontend interface

- **M1 token refresh:** Login currently stores the access token and discards the returned refresh token. `/api/auth/refresh/` is not connected; expired access requires another sign-in.
- **M1 server logout:** Dashboard Sign out clears browser state but does not call `/api/auth/logout/`. Connecting it requires retaining the refresh token expected by M1.
- **M2 manual checkpoint:** POST `/api/cvs/{id}/versions/` is available but has no manual checkpoint button. Existing saves already generate versions; history reading works.
- **M3 standalone catalogue:** Template details and preview images have no dedicated gallery. Template selection already uses the real catalogue.

These are additional interfaces, rather than broken routes in the current CV workflow. They should reuse existing APIs if added.

## Profile editing added after this audit

The signed-in dashboard header now has **My Profile**. Opening reads GET `/api/auth/me/`; Save sends only `{full_name}` through PATCH on that same M1 endpoint. Email is read-only. Close cancels unsaved changes. Loading, retries, duplicate-save protection, keyboard focus, and expired-session handling reuse dashboard utilities. Stale responses after closing or signing out cannot repopulate profile fields. Account edits do not modify saved CV documents. M1's backend contract is unchanged.

Verification for this addition: 20 account/dashboard Django tests and all 74 frontend tests passed. The earlier full-suite results below describe the audit before this addition.

## Limits

- Chat resume uses the current browser's saved session mapping or an explicit session URL. M5 has no session-list endpoint for cross-device conversation discovery.
- Version restoration is unavailable in the backend; frontend history is read-only.
- Live Gemini availability and response quality were not tested. Automated AI tests mock the provider.
- Styling depends on the existing external Tailwind/Alpine assets. Browser audit checks used the real local controllers with mocked API responses, not a production deployment.

## Verification results

- Django system check: passed.
- Full Django regression suite: **112 passed** against the isolated test database.
- All frontend suites: **68 passed** (authentication 8, CRUD 19, editor 11, live preview 7, import 11, intelligence 12).
- Rendered dashboard: **147 unique element IDs**, **9 discoverable local assets**, and no missing literal element references in dashboard controllers.
- Chromium walkthrough: Sign In/Register switching, login/listing, creation/template selector, import modal, AI review/health check, history, delete confirmation/cancellation, saved preview, chat opening, and all seven CV card actions passed with no JavaScript errors. API responses were mocked; no real accounts or CVs were changed.
- Existing backend tests verify owner-scoped access, version conflicts, rejected writes, deletion, import and rendering/export behavior.
- Test-generated upload files were moved to `/tmp/frontend-audit-test-uploads`; user-uploaded files were retained.

Commands:

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test --settings=config.test_settings
node --test tests/*.test.cjs
```
