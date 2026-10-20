# Routes and frontend connections — 20 October 2026

The `/admin/` 404 came from missing admin application and URL registration.
Admin, messages and message middleware are now enabled. Django's built-in admin
migrations provide its action log. Admin is accessed directly at `/admin/`,
with no link in frontend navigation. `/` redirects to `/dashboard/`.

Admin uses Django session authentication, CSRF protection and staff/model
permissions. Sign in using a staff account's **email and password**. Dashboard
JWT login does not sign into admin, and an admin session does not authorize CV
APIs. Account administration uses the project's email-based user model and
Django's password forms. “View site” returns to the dashboard.

To create an administrator when none exists:

```bash
python manage.py migrate
python manage.py createsuperuser
```

## Connection inventory

All paths have a trailing slash. `{id}` is a CV ID, `{session}` a chat UUID,
and `{import}` an import ID. Private APIs retain JWT and ownership checks.

| Route / methods | Frontend connection |
| --- | --- |
| GET `/` | Redirect to dashboard |
| GET `/dashboard/` | Main workspace and dialogs |
| GET `/templates/` | Template gallery |
| GET `/cvs/{id}/edit/` | Manual editor |
| `/admin/` and built-in login/logout/model routes | Direct URL access; staff administration |
| POST `/api/auth/register/`, `/api/auth/login/` | Dashboard registration and sign in; editor sign in |
| POST `/api/auth/refresh/`, `/api/auth/logout/` | Shared session transport; Sign out |
| GET/PATCH `/api/auth/me/` | My Profile |
| GET/POST `/api/cvs/` | CV cards, gallery CV selector, manual/import creation |
| GET/PATCH/DELETE `/api/cvs/{id}/` | Editor, approved AI edits, template switch, delete dialog |
| POST `/api/cvs/{id}/duplicate/` | Duplicate card action |
| GET/POST `/api/cvs/{id}/versions/` | History and manual checkpoint |
| POST `/api/cvs/{id}/restore/` | Approved version restoration |
| POST `/api/cvs/from-chat/` | Approve and save collected chat details |
| GET `/api/templates/` | Gallery filters/pagination and creation selectors |
| GET `/api/templates/{template_id}/` | Gallery refreshes metadata before preview; unavailable designs show an error |
| POST `/api/cv-import/upload/` | Import document upload |
| GET `/api/cv-import/{import}/` | Import status/refresh |
| POST `/api/cv-import/{import}/extract/` | Extract document text |
| GET/POST `/api/chat/sessions/` | Conversation list and guided interview creation |
| GET `/api/chat/sessions/{session}/` | Open/resume conversation |
| POST `/api/chat/sessions/{session}/messages/` | Send chat message |
| GET `/api/chat/sessions/{session}/draft/` | Review collected draft |
| POST `/api/chat/sessions/{session}/reopen/` | Return to interview |
| POST `/api/chat/sessions/{session}/final-review/` | Explicit optional Gemini review |
| POST `/api/chat/sessions/{session}/final-review/decisions/` | Approve selected review suggestions |
| POST `/api/ai/extract/` | Parse imported text into a proposed CV |
| POST `/api/ai/validate/` | Check missing details |
| POST `/api/ai/optimize/`, `/api/ai/suggestions/` | Review job fit: role supplied / JD only |
| POST `/api/ai/tailor/` | Improve whole CV |
| POST `/api/ai/rewrite/` | Rewrite one part → Suggest a rewrite |
| POST `/api/ai/improve/` | Rewrite one part → Polish wording |
| GET `/api/cvs/{id}/preview/` | Editor live preview's saved template shell |
| GET `/api/cvs/{id}/preview/document/` | Saved page preview in editor/dashboard |
| GET `/api/cvs/templates/{template_id}/preview/` | Gallery sample or authenticated owner CV preview |
| POST `/api/cvs/{id}/export/pdf/`, `/api/cvs/{id}/export/docx/` | Editor downloads; AI review's saved PDF |

DRF's generated API root and format-suffix variants are alternative API entry
points; they do not need separate frontend buttons. Shared M10 schemas remain
internal contracts. No endpoint connects a frontend directly to storage or AI
providers. Wording proposals still require explicit, versioned M2 approval.

## Verification

`tests/test_admin_routes.py` covers home/navigation, static admin assets,
email-based login, CSRF, member/staff permissions, hashed account creation,
JWT/session separation, public catalogue/preview and 35 private method/path
combinations. Existing backend suites exercise authenticated workflow behavior.

The Node M6 suite covers the new polish action, approval, request deduplication
and retry retaining the correct operation. Opt-in gallery Chromium tests cover
actual HTTP previews, metadata refresh/unavailability, navigation to admin,
email login, account listing and returning to the workspace. Browser records
are synthetic and use an isolated test database; AI transports remain mocked.

Results: the full Django run passed (461 tests, seven optional skips), all eight
Node test files passed, and all five gallery/admin Chromium journeys passed
separately. Django system checks and migration consistency checks passed.

```bash
python manage.py check
python manage.py test --settings=config.test_settings --noinput
node --test tests/*.test.cjs
RUN_GALLERY_BROWSER=1 python manage.py test tests.test_template_gallery_browser --settings=config.test_settings --noinput
```
