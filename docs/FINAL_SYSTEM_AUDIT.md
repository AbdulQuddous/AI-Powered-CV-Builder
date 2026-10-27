# Final system audit — AI-Powered CV Maker

> Historical audit of 14 October 2026. The subsequent local-Qwen chatbot implementation,
> final-review workflow and current test evidence are documented in
> [CHATBOT_IMPLEMENTATION_REPORT.md](CHATBOT_IMPLEMENTATION_REPORT.md).

Audit date: 14 October 2026. Source of truth: the actual repository, installed environment,
resolved Django routes, automated tests and real Chromium journeys. This report supersedes
the earlier dashboard audits. No production deployment or real Gemini smoke test was performed.

## A — System status

**Overall: PARTIAL. Deployment: NEEDS WORK.**

The implemented CV workflows pass their regression and integration checks, including five
real browser → HTTP → Django → isolated database journeys. AI providers are mocked in those
journeys. The application is usable for local testing; passing tests does not establish live
Gemini availability or production security. Previously committed secrets, tracked private
uploads and development security settings prevent an unconditional production PASS.

Baseline before changes: **113 Django tests passed on PostgreSQL; 74 frontend tests passed**.
Final: **130 Django tests passed on both SQLite and PostgreSQL; 88 frontend tests passed;
5 explicit browser journeys passed**. New audit integration tests account for 17 of the
130 Django tests; they are not an additional 17 on top of that total.

Existing working modules were retained. Changes repair confirmed gaps or add missing
connections through existing module ownership. No framework, provider SDK, schema,
database model or dependency version was replaced. User records, uploaded files and Git
history were not reset, deleted or rewritten.

### Actual structure and dependencies

| Area | Actual implementation |
| --- | --- |
| Project configuration | `config/settings.py`, `config/urls.py`, `config/test_settings.py` |
| Accounts | `accounts/models.py`, `serializers.py`, `views.py`, `urls.py`; email-based user; JWT |
| CV persistence | `cvs/models.py`, `services.py`, `validation.py`, `serializers.py`, `views.py`, `urls.py`, `chat_import.py` |
| Catalogue | `templates_app/models.py`, `serializers.py`, `services.py`, `views.py`, `urls.py` |
| Import | `cv_imports/models.py`, `serializers.py`, `views.py`, `services/validators.py`, `import_service.py`, `extractors.py` |
| Conversation | `chatbot/models.py`, `serializers.py`, `views.py`, `services/`, `prompts/cv_assistant.py` |
| Intelligence | `ai/views.py`, `serializers.py`, `services/`, `llm/`, `schemas/contracts.py`, `validators/rules.py` |
| Editor | `m7_editor/views.py`, `templates/m7_editor/editor.html`, `static/m7_editor/js/{api,editor,live_preview}.js` |
| Rendering | `m8_renderer/views.py`, `services/{renderer,context_builder,pdf_exporter,docx_exporter}.py`, `templates/cv_templates/` |
| Dashboard/chat UI | `m9_dashboard/views.py`, `templates/m9_dashboard/`, `static/m9_dashboard/js/` |
| Contracts | `shared/schemas/`, `shared/enums/`, `shared/api/API_CONTRACT.md`, `shared/examples/cv_draft.json` |
| Tests | `tests/test_*.py`, seven `tests/*.test.cjs` suites, module tests; opt-in `tests/browser_e2e.py` |

The environment uses Python 3.12, Django 5.2.18, DRF 3.18.3, psycopg 3.3.6,
google-genai 2.29.0, OpenAI SDK 3.26.0, pypdf 6.19.0, python-docx 1.2.0 and
WeasyPrint 70.0. Installed packages match the pinned requirements; `pip check` passes.
There is no npm manifest or React application. The existing UI uses Django Templates,
JavaScript, Tailwind and Alpine 3.17.4; the editor includes prebuilt CSS.

M5 actively uses Gemini's OpenAI-compatible interface; M6 uses google-genai directly.
Both configured model names are `gemini-3.5-flash-lite`; this is a configuration finding,
not evidence that the provider currently accepts that model. `AI_PROVIDER`/QWEN variables
are not active provider selectors. The retained Groq compatibility client is inactive.

## B — Module status

“PASS*” means tested with mocked external AI. “Connected” describes the intended UI
workflow, rather than requiring a separate page for every internal service.

| Module | Backend status | Frontend status | Integration status | Test status | Remaining issues |
| --- | --- | --- | --- | --- | --- |
| M1 Accounts | PASS: register/login/me/refresh/logout | Connected; profile, renewal and server logout | PASS | Backend, 14 auth + 6 transport JS tests, browser | TLS/CSP/token storage policy; no password recovery/email verification |
| M2 CV management | PASS: owner-scoped CRUD, snapshots, duplicate, checkpoint, restore | All principal actions connected | PASS | Backend, 24 CRUD JS tests, browser | Existing PATCH/checkpoint API permits omitted expected_version; UI always supplies it |
| M3 Templates | PASS: real catalogue, details, compatibility | Selectors connected for manual/AI/import creation | PASS | Catalogue tests; three real PDF themes | Legacy catalogue DTO differs from unused M10 template contract; no separate gallery |
| M4 Import | PASS: upload, details, extraction | Upload/recover/extract/review connected | PASS | Import tests, 11 JS tests, PDF/DOCX integration, browser | No OCR; interrupted synchronous extraction needs operational recovery |
| M5 Conversation | PASS*: deterministic/local extraction plus bounded Gemini fallback | M11 chat, seeded AI creation, server resume list | PASS* | Chat/existing-CV tests, new regressions, browser | Live model untested; conversation DTO differs from unused M10 chat contract |
| M6 Intelligence | PASS*: six operations, validation and cache | Health/analysis/suggestions/rewrite/improve/import extraction | PASS* | M6 tests, 13 JS tests, integration/browser | Semantic truth still needs review; local cache is per process |
| M7 Editor | PASS shell; M2 owns persistence | Schema-compatible fields, explicit save, A4 preview, zoom/navigation | PASS | 13 editor + 7 preview JS tests, Django/browser | Draft pane is continuous; final print pagination belongs to M8 |
| M8 Rendering | PASS: HTML, real PDF, DOCX | Preview and downloads connected | PASS | Real exports, A4/text checks, browser PDF download | Production native-library/static configuration needs deployment verification |
| M9 Dashboard | PASS empty shell; no CV persistence | CRUD/statistics/filtering/dialog coordination | PASS | Django, JS, rendered asset checks, browser | Existing CDN policy must be finalized for deployment |
| M10 Shared contracts | PASS canonical CV validation | Schema drives editor/import controls | PARTIAL across all DTOs | Contract and boundary tests | Frozen template/chat contracts are not the existing legacy API DTOs |
| M11 Chat frontend | Uses M5/M2, no independent backend | Create/continue/review/save/resume connected | PASS* | Chat JS and real browser journeys | Server sessions remain after CV deletion; linked deleted CV cannot be saved |
| Integration adapters | M2 `chat_import.py`; shared M1 JS transport | Sparse updates/import proposals/approved writes | PASS* | New cross-module and JWT tests | Plain create/import has no exactly-once guarantee after a lost response |

## C — Frontend/backend connection matrix

Frontend paths below are relative to the module's `static/.../js/` or `templates/`
directory unless fully qualified. Status PASS for AI actions uses mocked providers.

| Frontend feature | Frontend file | Backend endpoint | Method | Backend service | Status / evidence |
| --- | --- | --- | --- | --- | --- |
| Register/link/back to sign-in | M9 `dashboard.js`, `dashboard.html` | `/api/auth/register/` | POST | M1 RegisterView | PASS: auth/backend + JS |
| Sign in | M9 `dashboard.js`; M7 `api.js` | `/api/auth/login/` | POST | M1 LoginView | PASS: backend/JS/browser |
| Load profile | M9 `dashboard.js` | `/api/auth/me/` | GET | M1 MeView | PASS: backend/JS/browser |
| Save full name, visible success/Done | M9 `dashboard.js` | `/api/auth/me/` | PATCH | M1 MeView | PASS: backend/JS/browser; email readonly |
| Automatic access renewal | `accounts/static/accounts/js/session.js` | `/api/auth/refresh/` | POST | M1 RefreshView | PASS: rotated tokens, concurrent requests, real browser |
| Sign out/revoke refresh | Shared M1 script; M9 `dashboard.js` | `/api/auth/logout/` | POST | M1 LogoutView | PASS: JS/browser; local clear on outage |
| List/refresh/pagination | M9 `dashboard.js` | `/api/cvs/` | GET | M2 CVViewSet | PASS: owner/backend/JS/browser |
| Search/template filter/sort/statistics | M9 `dashboard.js` | Same owner-scoped list; local presentation | GET/local | M2 data, M9 presentation | PASS: JS; deletion statistics browser |
| Choose template | M9 `dashboard.js`, `import_cv.js` | `/api/templates/` | GET | M3 catalogue | PASS: catalogue/JS/browser |
| Manual creation: name/role/level/template | M9 `dashboard.js` | `/api/cvs/` | POST | M2 create_cv | PASS: backend/JS/browser |
| AI creation: same selected metadata | M9 `dashboard.js` | `/api/chat/sessions/` | POST | M5 create_chat_session | PASS*: no premature M2 CV; metadata reaches PDF |
| Edit card/section link | M9 `dashboard.js`, `ai_review.js` | `/cvs/{id}/edit/`, `/api/cvs/{id}/` | GET | M7 shell, M2 retrieval | PASS: JS/Django/browser |
| Read a CV | M7 `api.js`, M9 `dashboard.js` | `/api/cvs/{id}/` | GET | M2 owner lookup | PASS: backend/JS/browser |
| Save manual edits | M7 `editor.js`, `api.js` | `/api/cvs/{id}/` | PATCH | M2 update_cv | PASS: expected_version/conflicts/browser |
| Add/remove/reorder/enum/date/current-role fields | M7 `editor.js`, `editor.html` | Local draft; same PATCH on Save | Local/PATCH | M10 shape → M2 validation | PASS: editor JS/schema tests |
| Draft JSON export/discard/reload | M7 `editor.js` | Blob download / `/api/cvs/{id}/` | Local/GET | Editor; M2 reload | PASS: editor JS; no invented JSON-export endpoint |
| Live A4 preview/zoom/section scroll | M7 `live_preview.js`, `editor.js` | `/api/cvs/{id}/preview/` once; local draft DOM | GET/local | M8 template styles | PASS: preview tests/browser |
| Delete → Cancel | M9 `cv_operations.js`, `crud_modals.html` | No request | Local | Confirmation only | PASS: JS; CV retained |
| Delete → Confirm | Same | `/api/cvs/{id}/` | DELETE | M2 delete_cv | PASS: 204/no JSON, duplicate guard, failures, owner, stats |
| Duplicate/identify new record | M9 `dashboard.js` | `/api/cvs/{id}/duplicate/` | POST | M2 duplicate_cv | PASS: source preserved/backend/JS/browser |
| Version history/older pages | M9 `cv_operations.js` | `/api/cvs/{id}/versions/` | GET | M2 snapshots | PASS: dates/owner/pagination/JS/browser |
| Create checkpoint | Same | `/api/cvs/{id}/versions/` | POST | Existing M2 checkpoint_cv | PASS: current version, duplicate guard, conflict JS/browser |
| Restore → explicit confirmation | Same | `/api/cvs/{id}/restore/` | POST | M2 restore_cv → update_cv | PASS: new snapshot; later history retained |
| View saved CV/editor modal preview | M9 `dashboard.js`; M7 `editor.js` | `/api/cvs/{id}/preview/` | GET | M8 renderer | PASS: actual theme/text/owner |
| Download saved PDF | M9 `ai_review.js`; M7 `editor.js` | `/api/cvs/{id}/export/pdf/` | POST | M8 PDFExporter | PASS: real PDF parsed; browser file |
| Download saved DOCX | M7 `editor.js` | `/api/cvs/{id}/export/docx/` | POST | M8 DOCXExporter | PASS: existing real export/owner tests |
| Upload existing CV | M9 `import_cv.js`, `import_modal.html` | `/api/cv-import/upload/` | POST multipart | M4 validators/storage | PASS: actual PDF/DOCX and browser upload |
| Recover import status | Same | `/api/cv-import/{id}/` | GET | M4 owner-scoped detail | PASS: import backend/JS |
| Extract document text/retry | Same | `/api/cv-import/{id}/extract/` | POST | M4 process_cv_import | PASS: idempotence/concurrent409/unreadable422 |
| Extract structured CV proposal | Same | `/api/ai/extract/` | POST | M6 extraction | PASS*: no M2 save; explicit AI action |
| Correct proposal/select template/name | M9 `ai_ui.js`, `import_cv.js` | No write before approval | Local | M10-driven controls | PASS: JS/browser corrected name |
| Confirm import/create/open editor | M9 `import_cv.js` | `/api/cvs/` | POST | M2 create_cv | PASS: reviewed data persists; original retained |
| Discard import proposal | Same | No CV write | Local | Review state | PASS: JS; uploaded document retained by M4 |
| Open AI review/from editor | M9 `dashboard.js`, `ai_review.js`; M7 links | `/api/cvs/{id}/` | GET | M2 read | PASS: no AI request on opening |
| Rule-only Health Check | M9 `ai_api.js`, `ai_review.js` | `/api/ai/validate/` | POST `use_ai:false` | M6 rules | PASS: asserts provider never called |
| Optimize for Role | Same | `/api/ai/optimize/` | POST | M6 combined analysis | PASS*: mock/schema/cache tests |
| View Suggestions | Same | `/api/ai/suggestions/` if no reusable analysis | POST/local reuse | M6 combined analysis/cache | PASS*: one provider invocation for same analysis |
| Rewrite/Improve field | Same | `/api/ai/rewrite/`, `/api/ai/improve/` | POST | M6 writing | PASS*: bounded/validated text; numerical guard |
| Discard rewrite | M9 `ai_review.js` | No PATCH | Local | Proposal state | PASS: real browser asserts unchanged version |
| Approve rewrite | Same | `/api/cvs/{id}/` | PATCH | M2 update_cv | PASS*: targeted field, version check, browser persistence |
| Continue with AI on saved CV | M9 `dashboard.js` | `/api/chat/sessions/` | POST with cv_id | M5 owner-checked seeded edit mode | PASS*: asks what to add/edit, not fresh interview |
| Send chat message | Same, chat modal | `/api/chat/sessions/{uuid}/messages/` | POST | M5 process_user_message | PASS*: one question/grouped input/context/concurrency |
| Review/resume conversation | Same | `/api/chat/sessions/{uuid}/` | GET | M5 owner-scoped detail | PASS*: backend/JS/browser |
| Resume AI chat server list/load more | Same, `chat_sessions_modal.html` | `/api/chat/sessions/` | GET | M5 owner-scoped paginated summaries | PASS*: saved partial chat found in browser |
| Finish chat/save collected details | M9 `dashboard.js` | `/api/cvs/from-chat/` | POST | M2 chat_import/save_chat_cv | PASS*: approved M2 save; repeated chat save idempotent |
| Loading/errors/toasts/dialog keyboard support | Existing M9/M7 controllers/templates | Reuses each operation above | Local | Accessible status/focus/state | PASS: JS and real browser controls |

The public catalogue detail API `GET /api/templates/{id}/` is tested for API clients;
selectors already receive the necessary metadata from the list. There is no dedicated
image gallery/detail button. This is an optional presentation extension, not a broken
CV creation connection. M10/internal validation services do not need standalone screens.

Rendered verification: `/dashboard/` has **176 unique IDs and 10 discoverable local
assets**; editor shell has **8 unique IDs and 6 local assets**. Neither page has duplicate
IDs, missing literal controller references or missing static files. All **28 inspected
API path patterns resolve**; HTTP methods are verified by their view definitions/tests.

## D — Workflow results

| Workflow | Result | Evidence and boundary |
| --- | --- | --- |
| Manual CV creation | PASS | M2 backend; CRUD JS; real browser selects template/role/level and creates |
| AI CV creation | PASS* | Selected metadata → M5 → explicit M2 save → M8 PDF integration; real browser with mock Gemini |
| Previous CV import | PASS* | Actual PDF and DOCX text extraction; mocked M6 → editable review → M2 → editor/PDF; browser DOCX journey |
| CV editing | PASS | Canonical defaults/enums/dates/limits; real Alpine editor changes full name |
| CV saving/reopening | PASS | Browser PATCH and reload; integration GET confirms complete document |
| CV deletion | PASS | Owner/anonymous denial; confirm/cancel/fail/duplicate-click JS; real browser204 and statistics |
| CV duplication | PASS | M2 deep copy/source retained; frontend identifies returned record; browser |
| Version history | PASS | Backend timestamps/snapshots, safe pagination, browser history |
| Version checkpoint | PASS | Existing POST versions, expected_version; browser creates checkpoint4 |
| Version restoration | PASS | Backend retains1–3 and appends4; browser restore creates3 then checkpoint4 |
| AI suggestions | PASS* | Provider mocked; same role analysis cached/reused, zero database writes |
| AI rewriting | PASS* | Unsupported numerical output rejected; browser discard unchanged/apply persists |
| Resume chat | PASS* | Existing CV seeded edit mode; server summaries owner-scoped; browser leaves/resumes partial chat |
| PDF preview | PASS | Actual M8 HTML, all three themes, saved content, safe missing-template error |
| PDF download | PASS | Actual WeasyPrint bytes parsed with pypdf; required facts and A4 dimensions; browser downloaded file |
| DOCX download | PASS | Existing M8 real export tests and owner denial; not a separate browser journey |

Each PASS refers to the tested data and boundary. Live Gemini content/model availability,
production visual review and multi-worker load testing remain NOT TESTED.

## E — Security results

Checks included unauthenticated API access, cross-user CV/import/session/export/history
access, malicious/invalid uploads, ownership before write validation, stale writes,
JWT rotation/logout, same-origin credential forwarding, safe output presentation,
private caching, render-resource restrictions, tracked secret examples and deployment checks.

Fixed:

- Removed active hardcoded database credentials and provider fallback secret. Settings
  now use `DATABASE_URL`; secret examples and the tracked settings backup are sanitized.
- Removed development `/media/` serving. M4 reads documents directly from storage; UI
  does not need public raw uploads. Added future media/static build exclusions to Git.
- Disabled HTTP caching for private API responses; responses vary by Authorization.
- Added clickjacking middleware; UI shells themselves expose no saved CV data.
- Validated file signatures/DOCX container content, encryption flags and expanded size.
- Shared transport sends tokens only to same-origin `/api/`; expired authentication,
  concurrent renewal, logout and account-change races have explicit handling.
- M5 concurrent results cannot overwrite newer session state; provider failures do not
  persist partial chat messages. Message throttling and bounded provider timeout added.
- Restore requires ownership and current expected_version, within M2's transaction.

Existing protections retained: JWT-protected owner-scoped querysets; ORM database access;
M10 JSON validation; M8 escaping; PDF resource-fetch restrictions; M6 bounded input,
output validation and explicit user approval. Proposals do not grant persistence access.

Remaining risks are confirmed, not hypothetical deployment claims:

1. **Previously committed credentials require rotation.** Removing current source values
   does not remove them from older commits. Rotate applicable Django/provider/database
   credentials; decide separately how to remove sensitive Git history. No secret values
   are reproduced in this report and no history rewrite was performed.
2. **11 private upload files remain Git-tracked.** They were preserved. `.gitignore`
   prevents future accidental additions but does not untrack existing files. Review and
   remove them from repository/history through an approved release cleanup, without
   deleting the application originals. Production servers must not expose raw media.
3. **Current configuration is development configuration.** `check --deploy` reports
   security.W004/W008/W012/W016/W018: HSTS, HTTPS redirect, secure session/CSRF cookies,
   DEBUG. Production TLS/proxy/hosts must be configured and checks repeated there.
4. JWTs remain in JavaScript-readable sessionStorage to preserve the current architecture.
   CSP and the CDN/static asset policy need deployment review. Logout revokes refresh;
   an already-issued access JWT remains usable until expiry under the existing M1 contract.
   Access lifetime is **50 minutes**, refresh **7 days**; this audit did not change them.
5. Local-memory throttling/cache is per worker. Public multi-worker protection requires
   an agreed shared-cache or edge policy. No dependency was introduced for that policy.

The local ignored `.env` was kept private (mode600); its DATABASE_URL port was aligned
with the previously active local PostgreSQL instance, preserving host/name/user/password.
The audit did not change application records. Production settings were not fabricated.

## F — Issues fixed

| Issue / root cause | Affected files | Fix | Tests / verification |
| --- | --- | --- | --- |
| Credentials embedded in source/examples; DB env ignored | Config/settings/backup, README, env example | Environment DB; no fallback key; placeholders | Sanitized tracked-text scan; PostgreSQL suite |
| Raw private documents publicly served; future media trackable | config URLs, gitignore | Remove public route; ignore future uploads/builds | M4 media404 regression; 11 existing files preserved |
| Private JSON/file responses could enter caches | config middleware/settings | Private/no-store + Authorization Vary | Sensitive API response regression |
| Fresh installs lacked real catalogue data | M3 migration/test fixtures/services | Non-destructive three-theme seeds; empty compatibility lists are general | Fresh test databases, catalogue tests, three actual PDFs |
| Invalid template IDs saved; missing template file500 | M2 validation, M8 renderer | Reject unavailable ID; safe400 for missing file | No-save and missing-template tests |
| Refresh pair discarded; logout only local; renewal races | Shared M1 JS, M9/M7 transport/templates | Rotate/store pair, coalesce renewal, server revoke, stable identity guards | Six transport tests; auth/editor tests; real JWT browser |
| Gemini errors used a different exception class from views | M5 shared errors, clients/views | Common exception; safe429/502, bounded request/retries | Failed provider leaves chat unchanged |
| Concurrent chat responses could overwrite state | M5 conversation service | Lock/compare current updated_at and status before atomic message save | Stale snapshot409 regression |
| Deterministic prompts requested grouped fields | M5 normalizer | One next question; grouped incoming facts still extracted | QUESTION_MAP regression + chat tests |
| AI creation bypassed name/role/level/template selections | M5 creation DTO/service; M2 adapter; M9 creation | Additive optional seed fields, collect next missing detail, preserve selected metadata on approval | JS, cross-module PDF integration, browser |
| Cross-browser chat discovery had no server connection | M5 list DTO/view; M9 list modal/controller | GET summaries on existing sessions URL; owner pagination; resume existing detail | Isolation test; browser resumes partial chat |
| Restore missing; manual checkpoint had no button | M2 serializer/service/view; M9 CRUD/modal | Restore appends via M2 update; checkpoint reuses POST versions; version guards | Restore owner/conflict/history backend; CRUD JS; browser |
| Extension-only uploads and repeated/racing parse | M4 validators/import service | Signature/container/size checks; claim extraction once, completed result reuse | Spoof/empty/oversize/ZIP/unreadable/idempotence tests |
| Imported AI fields could not be corrected before Save | M9 AI UI/import/template/view | Public canonical schema drives editable local proposal, no premature write | Proposal correction JS and browser persisted correction |
| Editor controls omitted enum/limit/current role constraints | M7 editor/template/view | M10-driven fields; collection limits; preserve validation errors/draft | Editor schema regressions; real editor save |
| Target role could authorize invented rewrite numbers | M6 writing | Numerical claims must already occur in source prose | Unsupported99% rewrite rejected502 |
| Audit test could accidentally call external AI | Test settings/runner/concurrency fixture | Explicit mock; httpx sync/async transports fail closed; dummy test key | Final suites pass with external provider transport blocked |
| Existing docs described obsolete gaps/starter behavior | README/M7/M9 docs, this report | Document actual current behavior, mark earlier stage reports historical | Source/report cross-check |

One initial final-suite attempt exposed an unmocked concurrency fixture. It sent an invalid
test key, not the user's real key, and failed. The fixture was corrected; the test runner
now blocks SDK HTTP transport so accidental unmocked AI calls cannot reach providers.
Final results below are subsequent successful runs with that guard enabled.

## G — Test results

| Suite | Total | Passed | Failed | Skipped | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Django, SQLite | 130 | 130 | 0 | 0 | Complete discovery; 109.817s |
| Django, PostgreSQL | 130 | 130 | 0 | 0 | Complete discovery, isolated test database; 110.269s |
| Frontend cases | 88 | 88 | 0 | 0 | Seven suites run individually; aggregate runner also passed |
| New audit integration/regression tests | 17 | 17 | 0 | 0 | Included in both Django130 totals |
| Browser E2E | 5 | 5 | 0 | 0 | Explicit opt-in; final run14.788s; real local HTTP/DB/downloads; mocked AI |

Frontend breakdown: authentication14, CRUD24, editor13, preview7, import11,
intelligence13, shared JWT transport6. The installed Node aggregate runner reports
seven test-file successes; per-file runs expose the actual88 case count.

Commands executed:

```bash
.venv/bin/python manage.py test --settings=config.test_settings
node --test tests/*.test.cjs
node tests/dashboard_auth.test.cjs
node tests/dashboard_crud.test.cjs
node tests/editor.test.cjs
node tests/live_preview.test.cjs
node tests/m4_import.test.cjs
node tests/m6_dashboard.test.cjs
node tests/session.test.cjs
RUN_BROWSER_E2E=1 E2E_VENDOR_DIR=/tmp/cv-audit-vendor .venv/bin/python manage.py test tests.browser_e2e --settings=config.test_settings
.venv/bin/python manage.py makemigrations --check --dry-run --settings=config.test_settings
.venv/bin/python manage.py check --deploy --settings=config.test_settings
.venv/bin/python -m pip check
.venv/bin/python manage.py showmigrations --plan
```

The PostgreSQL run passed the existing local connection privately as TEST_DATABASE_URL;
no credentials were echoed. Exact wrapper:

```python
import os, subprocess, environ
environ.Env.read_env('.env')
run_env = dict(os.environ)
run_env['TEST_DATABASE_URL'] = os.environ['DATABASE_URL']
raise SystemExit(subprocess.run([
    '.venv/bin/python', 'manage.py', 'test', '--settings=config.test_settings'
], env=run_env).returncode)
```

Test settings always use an isolated database and temporary media. PostgreSQL needs
permission to create its separate `test_...` database. Never use a production connection
for these instructions. `makemigrations --check` found no missing model migrations;
`pip check` found no dependency conflicts. Deployment warnings are in Section E.

### Browser reproduction

`tests/browser_e2e.py` uses the installed Chromium/ChromeDriver through native WebDriver;
no Selenium or new package was installed. It requires the two existing frontend libraries
cached as `audit-libraries/alpine.js` and `audit-libraries/tailwind.js` beneath E2E_VENDOR_DIR.
The audit cached the application's existing CDN URLs (Alpine3.17.4 and Tailwind browser4)
under `/tmp/cv-audit-vendor`; browser requests use those local copies. Browser binaries
are currently at `/snap/chromium/current/usr/lib/chromium-browser/{chrome,chromedriver}`.
Other machines need their existing binary paths adapted in this test helper.

The five journeys cover profile/JWT renewal/logout; manual creation/editor/PDF/restore/
checkpoint/duplicate/delete; seeded AI creation/server resume/approval; actual DOCX import/
mocked extraction/correction/editor; and rewrite discard/apply. Tests manipulate temporary
accounts/CVs only. PDF output is real. Provider replies are controlled fixtures and do
not establish live AI quality. Keyboard/mobile visual behavior has JS checks and responsive
layout inspection, not an exhaustive device/accessibility certification.

## H — Contract verification

| Boundary | Result |
| --- | --- |
| Canonical CV document | PASS: `schema_version:1.0`, meta/personal/sections from unchanged M10 schema; strict unknown-key validation |
| M2 persistence ownership | PASS: create/update/delete/duplicate/checkpoint/restore/chat approval remain in M2 |
| M5 sparse CV updates | PASS through existing M2 adapter; not mistaken for a full saved document |
| M5 role/responsibilities/current dates | Adapter maps to M10 job_title/highlights/is_current; unknown month remains blank with warning |
| Career levels | M10 allows blank/fresher/experienced/other; M5 student maps to other with an explicit warning |
| M6 extraction/writing | Shape validated before proposing; M2 validates before approved persistence; no automatic save |
| M7/import controls | Public canonical schema drives enums/limits/defaults; no schema changes |
| Template selection | Saved meta.template_id reaches M8; modern/classic/developer produce actual distinct theme classes |
| Chat completion | Explicit `/api/cvs/from-chat/` reaches M2, preserves collected fields and selected metadata |
| Imported data | Reviewed M6 proposal POSTs M2 then reopens in M7 with the saved document |
| Existing endpoint compatibility | Existing request/response shapes preserved; optional chat seed fields and GET sessions are additive; restore is additive |
| All shared DTOs consistent | PARTIAL: published M3 catalogue and M5 session/message DTOs do not conform to unused shared template/chat schemas |

M10's `template_schema.json` expects template_id/template_type/schema_version and other
fields absent from the existing M3 DTO (id/category/supported_levels/etc.).
`chat_schema.json` expects UUID CV/message identifiers and a different envelope; actual
M2 CV/M5 message IDs are integers and existing conversation responses are richer.
Those API DTOs and frozen shared schemas were preserved to avoid breaking clients.
A separately designed, versioned adapter/migration is required for complete DTO adoption;
this report does not claim universal schema consistency.

M10 dates remain `YYYY-MM` or blank; a year-only answer is preserved in chat history,
not turned into an invented month. M10 caps experience at five entries; the editor
prevents an unsupported sixth addition and proposals receive validation errors.
No versioned CV contract, M4 response, M6 response or M8 response was replaced.

## I — Files modified

The complete file inventory follows. Paths are relative to the repository; the ignored
local `.env` adjustment described in Section E is deliberately not a committed file.

| File | Reason |
| --- | --- |
| `.env.example` | Replace secret examples with placeholders; document active provider settings. |
| `.gitignore` | Exclude future private uploads and collected static files. |
| `README.md` | Sanitize credential example; describe current application, test override and audit. |
| `accounts/static/accounts/js/session.js` | Share existing M1 JWT renewal, rotation, logout and same-origin transport. |
| `ai/services/writing.py` | Allow rewrite numerical claims only from source prose. |
| `chatbot/serializers.py` | Optional creation seed fields and owner-list summary DTO. |
| `chatbot/services/conversation_service.py` | Seed selected creation metadata and reject stale concurrent chat writes. |
| `chatbot/services/errors.py` | One error hierarchy for active and compatibility AI clients. |
| `chatbot/services/gemini_client.py` | Shared failures, request timeout, disabled SDK retries and output bound. |
| `chatbot/services/groq_client.py` | Use shared exceptions and remove raw response/error printing. |
| `chatbot/services/response_normalizer.py` | Ask one logical next question through deterministic prompts. |
| `chatbot/views.py` | Owner-scoped session listing and safe/throttled message errors. |
| `config/middleware.py` | Prevent private API response caching. |
| `config/settings.py` | Environment-owned DB/secrets, middleware and bounded/throttled M5. |
| `config/settings.py.bak` | Remove credential fallback from tracked inactive backup. |
| `config/test_settings.py` | Isolated media/database, dummy AI key and offline provider test runner. |
| `config/urls.py` | Remove unauthenticated raw media serving. |
| `cv_imports/services/import_service.py` | Atomic extraction claim, idempotent completed results, close storage handles. |
| `cv_imports/services/validators.py` | Check signatures, DOCX entries/encryption and expanded ZIP size. |
| `cvs/chat_import.py` | Preserve selected AI creation name/template; handle current end dates without false warnings. |
| `cvs/serializers.py` | Validate explicit restoration version and expected_version. |
| `cvs/services.py` | Restore owned historical content as a new validated snapshot. |
| `cvs/validation.py` | Reject unavailable template IDs before saving. |
| `cvs/views.py` | Expose additive restore action through M2. |
| `docs/FINAL_SYSTEM_AUDIT.md` | Full source-backed inventory, findings, fixes, evidence, limitations and release checklist. |
| `m7_editor/README.md` | Replace obsolete starter instructions with actual editor/API/test behavior. |
| `m7_editor/static/m7_editor/js/api.js` | Reuse M1 transport while keeping public login available and retaining token pair. |
| `m7_editor/static/m7_editor/js/editor.js` | Canonical collection/enum controls and clearing private data on denied reload. |
| `m7_editor/templates/m7_editor/editor.html` | Schema data, shared JWT asset, current-role/enum fields, versioned assets and navigation. |
| `m7_editor/views.py` | Pass public CV schema and editor asset revision to empty shell. |
| `m8_renderer/services/renderer.py` | Return a safe validation error for missing renderable template files. |
| `m9_dashboard/CRUD_AUDIT.md` | Mark original read-only-history audit historical; link current result. |
| `m9_dashboard/FRONTEND_AUDIT.md` | Mark old refresh/logout/resume limitations and counts historical. |
| `m9_dashboard/M6_INTEGRATION.md` | Document editable import review and new cross-module verification. |
| `m9_dashboard/static/m9_dashboard/js/ai_ui.js` | Build safe schema-driven proposal editing controls. |
| `m9_dashboard/static/m9_dashboard/js/cv_operations.js` | Confirmed restoration, checkpoint, version guards, history loading/errors/focus. |
| `m9_dashboard/static/m9_dashboard/js/dashboard.js` | Shared JWT identity/transport, seeded AI creation, server chat discovery, restored card state. |
| `m9_dashboard/static/m9_dashboard/js/import_cv.js` | Retain local proposal corrections, prevent editing while saving, show M2 validation details. |
| `m9_dashboard/templates/m9_dashboard/chat_sessions_modal.html` | Accessible owner-session discovery/resume dialog. |
| `m9_dashboard/templates/m9_dashboard/crud_modals.html` | Checkpoint action and explicit restore confirmation in history. |
| `m9_dashboard/templates/m9_dashboard/dashboard.html` | Shared JWT/schema asset ordering and Resume AI chat entry point. |
| `m9_dashboard/templates/m9_dashboard/import_modal.html` | Enable review corrections before explicit creation. |
| `m9_dashboard/views.py` | Expose public schema and include shared auth asset in revision. |
| `templates_app/migrations/0002_builtin_templates.py` | Seed three real catalogue entries without overwriting existing customization. |
| `templates_app/services.py` | Treat unrestricted roles/levels as general compatibility. |
| `templates_app/test_templates.py` | Isolate catalogue fixtures from non-destructive seed migration. |
| `tests/browser_e2e.py` | Five opt-in real browser/HTTP/isolated DB journeys with mocked AI. |
| `tests/dashboard_crud.test.cjs` | Seeded AI metadata, restore confirmation/conflict and checkpoint state regressions. |
| `tests/editor.test.cjs` | Canonical limits/enums and retained refresh pair/public login regressions. |
| `tests/m6_dashboard.test.cjs` | Editable schema-driven proposal correction and existing intelligence checks. |
| `tests/runner.py` | Fail closed on accidentally unmocked SDK HTTP transports. |
| `tests/session.test.cjs` | Six JWT concurrency/rotation/logout/identity/origin/failure regressions. |
| `tests/test_m9.py` | Verify updated history/restore UI without weakening old dashboard checks. |
| `tests/test_system_audit.py` | Seventeen cross-module security, workflow, PDF/import/concurrency regressions. |

**54 repository files changed/added.** No dependency manifest, CV model or M10 schema was changed.

## J — Remaining issues and limitations

### Confirmed unresolved release issues

- Development DEBUG/HTTPS/HSTS/cookie settings and public host policy need production
  configuration. Do not suppress Django's deployment warnings to claim readiness.
- Previously committed credentials need rotation; old commits and 11 tracked uploads
  need a separate repository cleanup plan. User files and Git history were preserved.
- `templates_app.0002_builtin_templates` is currently pending in the local application
  database. It ran successfully on fresh isolated test databases. Apply normal migrations
  before using the release; it does not overwrite existing catalogue IDs/names.
- Shared template/chat schemas and legacy public DTOs differ. Existing CV workflow adapters
  are compatible, but universal shared-contract adoption is incomplete. A versioned
  migration needs design rather than silently replacing established DTOs.

### Untested behavior

- Real Gemini access/model acceptance, quota and semantic output quality. The active
  model settings were inspected, not validated against a provider account.
- Production reverse proxy, TLS, hosts, media/static storage, backup restoration,
  multi-worker concurrency/load, monitoring and final CSP/CDN configuration.
- Full device matrix, screen-reader certification and prolonged browser usability.
- Dependency compatibility passed; no vulnerability database/CVE scan was run.

### Existing product/architecture limits and optional future work

- Image-only PDFs need OCR, which is not implemented; extraction fails clearly with422.
- AI schemas and numerical guards cannot prove every non-numerical statement. Review
  proposals and accept only supported facts. No promise of zero hallucinations is made.
- Year-only dates are retained in source/chat but cannot be persisted as invented months;
  confirm the month or leave the canonical date blank. Experience is limited to five by M10.
- Synchronous document parsing/PDF rendering may consume worker resources; upload and
  DOCX expansion limits are enforced, but production load was not measured. A process
  interrupted after claiming extraction can leave `extracting` status; no new task queue
  or timeout recovery endpoint was invented.
- In-flight creation/deletion/duplicate/restore/checkpoint guards prevent repeated clicks.
  Plain POST creation/import/duplicate cannot promise exactly-once persistence if a server
  commits and its response is lost. Refresh/check the list before retrying. Chat approval
  already reuses its saved CV and is separately tested for repeated calls.
- M6 cache is local-memory, keyed by user/input/model with an existing one-hour TTL.
  It is not shared across processes; simultaneous independent requests can both miss.
  The UI reuses one role-analysis result and AI calls occur only on explicit actions.
- JWT renewal coalesces within a page/tab; no cross-tab coordination or auth architecture
  replacement was introduced. Credentials should be used only on the same origin.
- A catalogue gallery, password recovery, email verification, admin product workflows,
  richer shared DTO adapters and asynchronous import recovery are optional follow-up work.
- Existing saved templates can later be disabled; restoring their snapshots then produces
  validation errors instead of saving a CV whose selected renderer is unavailable.

## K — Deployment readiness

**NEEDS WORK.**

| Area | Finding / required release action |
| --- | --- |
| Production settings | DEBUG false, actual hosts, TLS/proxy settings, secure cookies and HSTS after HTTPS; repeat check --deploy with actual release environment |
| Secrets | Source examples sanitized; rotate previously committed values; provision secrets outside Git |
| Database | Environment connection now honored; apply pending built-in-template migration; backup before release; isolated PostgreSQL tests passed |
| Static files | All referenced local assets resolve; configure STATIC_ROOT/serving and run collectstatic in release environment; decide CDN/CSP policy |
| Private media | Application no longer serves raw uploads; preserve originals while cleaning tracked copies; keep production storage inaccessible to anonymous requests |
| Authentication | JWT renewal/rotation and server logout tested; existing50-minute access lifetime and browser token policy need release approval |
| Authorization | Owner/anonymous denial covered for CV, chat, import, history and exports; empty UI shells do not disclose data |
| Logging | Active errors return safe messages; sensitive compatibility prints removed; configure production logging/monitoring without CV/token contents |
| Errors | Validation/auth/conflict/import/provider failures presented; lost-response exactly-once behavior remains limited |
| Dependencies | Existing pinned versions retained; pip check clean; native WeasyPrint works locally; production build/native libraries and vulnerability scan outstanding |
| AI provider | No live verification; separately run a minimal controlled smoke test only when explicitly authorized |
| Operations | Configure backups, restore drill, expired-token cleanup, shared/edge rate policy, health checks and monitoring |

No deployment, Git commit, Git-history rewrite, dependency upgrade or application-database
reset was performed. Tests used temporary media; no user upload cleanup was performed.

### Manual verification

1. Restart Django to load backend changes. Apply normal migrations to a backed-up local
   development database (`.venv/bin/python manage.py migrate`); do not reset it. Open
   `/dashboard/` and hard-refresh once so the new versioned JavaScript loads.
2. Register a temporary account, sign in, open My Profile, change full name and Save.
   Confirm the visible success state, then Done. Reopen to confirm the name persisted.
3. Create a manual CV with name, role, career level and each chosen template. Edit real
   personal/education/project/certification data using month fields; Save and reload.
   Check visible card metadata/search/filter/sorting and saved statistics.
4. Open the same CV in two tabs; save in one, then save the stale draft in the other.
   Expect409, retained draft and Reload Latest/Export Draft controls; no silent overwrite.
5. In Version history, Create checkpoint; verify a new timestamp/version. Restore an
   older row after confirmation; verify its contents return as a new latest version and
   all intervening versions remain listed. Cancel restoration to verify no write.
6. Duplicate the CV; confirm two records and an unchanged original. Cancel Delete once;
   then confirm deletion of the duplicate. Check one204 request, card removal, statistics
   and notification. Simulate a failed request: the card must remain visible.
7. View CV and download PDF/DOCX. Check actual content, chosen layout and A4 PDF pages.
   In the editor change a section, zoom the live preview, and select another section to
   confirm preview scrolling. Unsaved draft changes must not appear in saved downloads.
8. Upload a text PDF/DOCX and extract through M4. Inspect text and retry extraction.
   Unsupported/empty/oversize/spoofed documents should show errors; image-only PDF should
   report no extractable text. Raw `/media/...` URLs must not expose the document.
9. AI actions require an authorized configured provider for manual use; automated tests
   use mocks. For an import, extract a structured proposal, correct a field, select its
   template/name, and explicitly confirm M2 creation. No CV exists before confirmation.
10. Create with AI: choose metadata first, provide partial details, leave, use Resume AI
    chat and continue. Finish/review then explicitly save. Continue with AI on a saved CV
    should ask what to add/edit; try “I want to add another project,” then its details.
11. AI Review should make no AI request merely by opening. Health Check sends use_ai:false.
    Optimize once then View Suggestions should reuse that result. Discard a rewrite:
    noPATCH. Apply a supported rewrite: one versionedPATCH; verify PDF includes it.
12. Test another account/expired credentials: owner-only APIs deny private IDs; valid
    refresh renews automatically, invalid refresh returns sign-in, Sign out revokes the
    latest refresh. Verify logout clears cards, chats, proposals and profile fields.

These instructions exercise local product behavior. Any manual live AI action can incur
provider usage; no such action was executed as part of this audit.

## L — Final verdict

1. **Every implemented service connected?** Principal product services are connected:
   M1 auth/profile/renewal/logout, M2 CRUD/checkpoint/restore, M3 selection, M4 import,
   M5/M11 conversation, all six M6 actions, M7 editor and M8 exports. The catalogue
   detail API remains available to API clients without a separate gallery button;
   internal/shared validation needs no independent screen.
2. **Every major button works?** Tested principal controls pass. Static references are
   complete; automated browser coverage includes five full journeys, not every device.
3. **Manual creation?** Yes; real M2 creation and browser editor/save pass.
4. **AI creation?** Yes with mocked providers; selected metadata survives approval/save.
5. **Old CV upload/reuse?** Yes for text PDF/DOCX; reviewed data reaches M2 and M7.
6. **Save/reopen?** Yes; complete documents persist; stale saves are rejected.
7. **Edit/improve?** Yes; manual editing and approved M6 proposals use existing M2.
8. **Delete/duplicate?** Yes; confirmation204/errors/ownership/source preservation tested.
9. **Restore older versions?** Yes; explicit confirmation appends a new current snapshot.
10. **Preview/download real PDF?** Yes; actual exported text and A4 dimensions verified.
11. **User isolation/protection?** Application API ownership tests pass; production security
    remains incomplete until credentials/media/settings/operations are addressed.
12. **Shared schemas consistent?** Canonical CV: yes. All template/chat DTOs: no; legacy
    published envelopes differ from unused shared contracts and need a versioned plan.
13. **Broken frontend/backend connections?** No remaining failures found in the tested
    principal workflows. Live provider and production infrastructure remain unverified.
14. **Unnecessary AI requests?** No observed automatic AI calls on page/open/local edit;
    rule health is provider-free, role analysis reused, retries disabled. Independent
    concurrent cache misses/multiple workers can still produce separate explicit calls.
15. **Before production?** Rotate committed credentials; handle tracked private files/history;
    configure HTTPS/hosts/cookies/HSTS/CSP; apply migrations/collectstatic; private storage;
    backups/monitoring/rate policy; deployment/vulnerability checks and explicitly authorized
    provider smoke test. Resolve/version legacy DTO alignment if strict full M10 adoption
    is a release requirement.

## 2026-10-19 follow-up: workspace consistency and date confirmation

Dashboard, editor and template gallery now share one navigation include and a
navy/indigo application theme. Account, creation, import, chat and AI-review
dialogs inherit the same buttons, forms and focus styling. The editor groups
secondary downloads in an accessible native disclosure; save, preview and PDF
download stay visible. Navigation and section controls adapt to phones, and
mobile summary cards take less space. Workspace CSS remains outside CV frames
and export templates.

All three screens load a locally compiled utility stylesheet. Rebuild with
`npm ci && npm run build:css` when changing utility classes; theme changes also
invalidate editor/dashboard CSS asset versions. Details and browser commands
are in [WORKSPACE_UI.md](WORKSPACE_UI.md).

The reported date loop is fixed: a year with an unknown month no longer falsely
conflicts with a month in the same year, labelled pairs update both endpoints,
and short omission replies omit only the requested date. The reported completion
typo retains grouped education facts; a graduation year cannot justify an
invented start year. Proven mistakes in unsaved single-qualification drafts can
be recovered from accepted history, respecting later corrections, ownership and
saved CV boundaries. See [CHATBOT_INPUT_CLEANUP.md](CHATBOT_INPUT_CLEANUP.md).

Validation: 423 Django tests passed with seven optional browser tests skipped in
the default run; all seven browser journeys passed separately in Chromium.
All eight Node test files passed. Browser coverage includes real editing/save,
creation navigation, template filters/selection, 320px/390px phone layouts,
and one/multiple-page preview with PDF/exact Word downloads. New date coverage
includes interval validation, paired/partial corrections, omission and evidence
recovery. Provider calls remain mocked in automated regressions. Screenshots
use synthetic CVs; existing saved CV records were not modified.

## 2026-10-19 follow-up: partial tailoring review

The reported tailoring `200` was a partial result: the validator rejected a
numerical rewrite and an unconfirmed named fact while keeping another proposal.
The accepted “Architected” → “Built and maintained” wording exposed an additional
responsibility-preservation gap. Tailoring now protects the architecture claim
and rejects unsupported maintenance duties. Bounded number-format and technology
normalization reduces false rejections while retaining checks on changed
metrics, quantity bounds, common time units and entry-level evidence.

Partial reviews identify omitted fields and reasons, show an accurate accepted
count, and replace the provider's unqualified review summary. Identical-text
proposals are omitted. Existing saved-CV approval/version contracts are retained;
old tailoring cache entries are separated by a new operation version.

The review's window-focus handler now checks at most once per minute after the
latest CV read/check. Explicit actions still check current data, and a detected
change clears stale proposals with a clear message. This removes the observed
rapid focus-triggered GET requests. See [CV_TAILORING_REVIEW.md](CV_TAILORING_REVIEW.md)
for behavior, limits and regression coverage.

Validation: the full 436-test Django suite passed with seven optional browser
tests skipped. The final 50-test grounding/tailoring regression and all eight
Node test files also passed. Four Chromium journeys passed separately with
mocked providers and synthetic CVs, including
the DevOps partial-result reproduction and approval persistence. No live provider
request or change to development CV records was performed.

## 2026-10-19 follow-up: advice-only tailoring

The CV 23 report contained `changes: []`, with its existing professional summary
copied into the provider's review feedback. There was no new proposed text to
save. The source CV targets Graduate / Associate Software Engineer; the pasted
advice referred to DevOps. A requested review focus may differ from saved CV
metadata without changing that metadata.

The prompt and response-schema descriptions now distinguish editorial review
feedback from a professional summary. Empty reviews get a server-controlled
message, and the client also avoids showing a copied CV profile as an unsaveable
improvement. No feedback paragraph is silently converted into an edit.

The UI shows “Advice for your CV” and “No changes to save,” hides the save
button, offers “Polish one part,” and identifies the request's role focus and
saved target when different. Reused reviews are labelled. Opening the focused
mode causes no AI request; an explicit rewrite request and subsequent approval
use the existing single-text and versioned M2 save flows. Changing the job
details still invalidates earlier results. Tailoring cache operation v4 avoids
reusing prior-policy reviews.

Verification: the full 439-test Django suite passed with seven optional browser
tests skipped. The 72 focused backend tests and eight Node test files passed. Five
mocked-provider Chromium journeys passed, including desktop/phone advice-only
layout, cache reuse, explicit polishing and approval, partial results and retry.
Read-only inspection used CV 23; development CV data was not changed and no
live AI request was made. Details are in [CV_TAILORING_REVIEW.md](CV_TAILORING_REVIEW.md).

## 2026-10-19 follow-up: AI Engineer job relevance

The reported rewrite mostly substituted synonyms and strengthened “Comfortable”
into “Proficient.” Shared job-focus instructions now ask whole-CV and selected-text
rewrites to lead with relevant confirmed contributions and explain the change
in emphasis. For this source, AI-powered CV and ATS work can lead, supported by
Python/Django/API development and testing. The graduate/intern identity and
stated proficiency remain accurate; production ML deployment is not inferred
from AI coding assistance or a job requirement.

Selected-text writing now reuses the whole-CV wording guard, including numbers,
named facts, responsibility and proficiency checks. It also revalidates cached
output. New cache operation versions separate older proposals from the updated
prompt/validation policy. M5/M10 contracts and M2 explicit versioned approval
remain unchanged. No development CV was edited automatically.

Eleven new tests cover the supplied JD/source, a grounded reorder, rejection of
the reported inflation, unsupported training/deployment claims, cached validation
and both writing endpoints. The existing 83-test focused regression passed;
all eight Node test files and six mocked-provider Chromium journeys passed.
The new browser journey rejects the inflated rewrite, retains the JD for an
explicit retry, previews supported AI-focused wording and saves only after
approval. Automated verification did not call a live AI provider.

Final verification: 450 Django tests passed with seven optional browser tests
skipped in the default run; the six review/browser journeys passed separately.
All eight Node test files passed. Development CV records were unchanged.

## 2026-10-20 follow-up: admin and frontend routes

The reported `/admin/` 404 was caused by absent admin app and URL registration.
Admin, messages middleware and Django's admin route are now enabled. The three
built-in admin migrations were applied locally. Admin is accessed directly at
`/admin/`, without a frontend navigation link; `/` redirects to the dashboard. Administration uses email-based
staff login and normal session/CSRF/model permission checks. Custom user forms
preserve password hashing; JWT API authentication remains separate.

The endpoint inventory found that the improve client and template detail API
had no direct frontend invocation. The selected-text review now offers
Polish wording through the existing improve endpoint, retaining comparison,
explicit versioned approval, request deduplication and correct-operation retry.
Gallery preview refreshes template details and handles unavailable designs.
See [ENDPOINT_FRONTEND_AUDIT.md](ENDPOINT_FRONTEND_AUDIT.md) for the full route
and frontend connection map, setup and verification commands.

Five Chromium journeys passed against an isolated database, covering desktop
and mobile gallery flows, private previews, creation, refreshed metadata,
unavailable designs and admin email login/navigation. All eight Node test files
passed, including the polish action and retry tests. No live AI call was made.
The full Django regression run passed: 461 tests, with seven optional browser
tests skipped. System checks and the migration consistency check passed.

## 2026-10-20 follow-up: welcoming dashboard redesign

The dashboard now uses a warm light canvas with subtle grain, a pastel welcome
panel, teal-to-indigo primary actions, violet/coral details, elevated interactive
stats and a larger illustrated onboarding state. The original SVG illustration
and Inter variable font are served locally; the font's SIL license is included.
Navigation remains shared with the editor and gallery. No Admin link appears
on frontend pages, and CV document templates/export styles remain isolated.

Empty accounts offer AI creation, template selection and import through existing
flows. The welcome Create a CV action retains manual creation. A filtered list
with no matches instead offers Clear search & filters, preserving CV data and
statistics. Existing card actions, authentication and approval/version contracts
are unchanged. The dashboard also fixes hidden-button CSS precedence and adds
visible focus, loading feedback and reduced-motion handling.

Verification: 28 focused Django tests and all eight Node test files passed.
Ten Chromium journeys passed with an isolated database and synthetic CVs,
covering onboarding actions, desktop/mobile layouts, filter recovery, gallery
flows, admin direct access, editor navigation/edit/save, and download-menu
keyboard behavior. New dashboard checks cover 1440, 1024, 768, 390 and 320px
widths and reduced motion. CSS rebuilt locally; Django system checks passed.
No live AI provider call or development CV data change was performed.
See [WORKSPACE_UI.md](WORKSPACE_UI.md) for implementation and preview details.

## 2026-10-20 follow-up: visual template picker

The creation form's name-only template dropdown is now a visual picker shared
by manual and AI creation. It uses actual catalogue thumbnails, style labels,
search/filter controls, larger previews and explicit selected-template feedback.
The larger preview has a visible Use action. Users keep entered details while
comparing designs; filtering retains the chosen template. Guidance distinguishes
conventional and visual styles without claiming a universally best template.

The existing template ID and M2/M5 contracts are preserved, including gallery
handoffs. Loading/submission guards, retry with retained input, and a generation
guard prevent late catalogue responses from overwriting a reopened form.
Catalogue failure shows a default preview and explicit retry; backend availability
validation remains authoritative. Template search does not implicitly submit
the creation form. Previews use fictional sample content and do not create CVs.

Verification passed: 28 focused Django tests, all eight Node test files and
13 Chromium journeys covering visual manual/AI selection, retained fields,
retry, mobile layout, gallery handoffs and editor navigation. A separate native
Enter-key browser check confirmed search does not create a CV. New Node coverage
checks that late metadata cannot overwrite reopened forms. No live AI call or
development CV change was performed. Picker previews are linked in
[WORKSPACE_UI.md](WORKSPACE_UI.md).

## 2026-10-20 follow-up: ongoing education conversation

The reported education loop had three causes: the grouped parser missed
“studying in BS…”, the graduation sentence path did not accept “excpect”, and
education incorrectly shared current employment's completion-date prohibition.
Ongoing academic study now accepts a stated expected graduation date. The
employment contradiction and date-order/month checks remain in place.

Status-only replies do not invent a degree. One reply can capture the degree,
subject and university; the next question requests only missing information and
uses present-tense wording for ongoing study. Education-only evidence warnings
use plain language. Qwen's extraction instructions distinguish ongoing study
from current employment without changing the M5/M10 contracts.

An initially unnamed study-status row is completed by the subsequent degree
answer, using existing sparse-merge date preservation. For legacy unsaved
creation interviews, guarded user/accepted-assistant history can prove a split
status row and degree refer to the same qualification. Explicit additional
degrees, contradictions, ambiguous evidence and saved-CV editing are excluded.
Confirmed graduation dates survive canonical draft conversion and explicit save.
See [CHATBOT_INPUT_CLEANUP.md](CHATBOT_INPUT_CLEANUP.md) for examples and coverage.

Verification passed: the full Django suite ran 486 tests (15 optional tests
skipped), followed by 134 focused education regressions covering the final
month-preservation adjustment. All eight Node test files and three Chromium
education journeys passed. The browser reproduced the reported status-only,
grouped degree/university and misspelled expected-graduation answers without
repeating collected fields. System checks and whitespace checks passed. These
checks used isolated test data and mocked providers; no live Qwen request or
development CV change was performed.

## 2026-10-20 follow-up: grouped skills in CV documents

The reported skills list contained category labels joined to preceding skills,
such as `Problem Solving Full-Stack & APIs: Django`. M8 now recovers those
explicit boundaries and renders separate compact paragraphs with bold category
labels and comma-separated values, following the supplied Word reference.
Custom labels are accepted at the start of a skill entry or line. Unlabelled
skill lists keep their existing template styling; no role-based categorization,
skill invention or deduplication occurs.

Shared presentation partials cover all 50 built-in templates. M7's draft preview
uses matching normalization with shared test fixtures; editable Word uses a bold
label run per paragraph. Saved previews and exact-layout Word still share the
PDF pages. The M10 string-array contract and saved CV JSON remain unchanged.
Large groups can continue across pages without clipping. The editor explains
how to enter categories. Preview source hashes track the helper; all 50 gallery
thumbnail files remained byte-identical after regeneration.

The supplied CV 28 PDF and a read-only render of its saved record both have two
pages. Temporary regenerated review files stayed outside the repository; the
saved CV and supplied PDF/DOCX files were not modified. Implementation and input
examples are documented in [CV_TEMPLATE_SYSTEM.md](CV_TEMPLATE_SYSTEM.md#explicit-skill-categories).

Verification passed: full Django regression ran 496 tests (16 optional browser
tests skipped); eight focused grouping tests also passed, including the added
large-group pagination case. All eight Node test files and three opt-in Chromium
preview/download journeys passed. Coverage checks separate bold rows across all
50 templates, literal text escaping, retained values, editable Word runs and
byte-identical saved-preview/exact Word page images. System and whitespace checks
passed. Tests used isolated records; no live AI request was made.

## 2026-10-20 follow-up: Gemini whole-CV tailoring against a job description

The dashboard whole-CV flow now asks for both the target role and JD. Missing
inputs have specific inline errors and receive focus after controls are enabled.
Single-part rewrites retain optional job context. Existing role-only/JD-only API
callers remain compatible.

The existing single Gemini call now requests a job-priority evidence review
before proposing wording changes. Its input identifies every editable section,
factual source paths, per-entry evidence boundaries and preserved numerical and
responsibility constraints. The JD is primary, and a saved CV's old target role
cannot override the requested review target. Instructions prioritize relevant
confirmed work across the summary, experience, projects and achievements, rather
than only substitute synonyms. Facts in skills, education and certifications
inform the review without being rewritten.

The optional public `job_alignment` response field shows up to six verbatim JD
requirements, supporting CV excerpts and supported/partial/missing status. Source
paths exclude contacts and target-role metadata. Returned requirements and quotes
are checked against the submitted JD and exact CV source paths, including when a
review is cached. Fabricated excerpts, missing references, malformed shapes,
duplicates and blank evidence are rejected. These provenance checks are not a
semantic proof of qualification; users see the cited text and partial matches are
explicitly labelled related evidence.

The review remains a proposal. Only selected wording is saved through M2 with the
expected version; gaps, job context and the assessment are never inserted as CV
facts. Updated inputs invalidate prior reviews, and the v6 cache separates old
tailoring results. M5/M10 contracts are unchanged. See
[CV_TAILORING_REVIEW.md](CV_TAILORING_REVIEW.md#job-description-and-whole-cv-review).

Verification passed: 507 full-suite Django tests (16 optional tests skipped),
21 focused job-alignment/writing tests, all eight Node test files and five opt-in
Chromium journeys. The new SDK-shaped JD/evidence journey was rerun after the
final styling adjustment and passed. Coverage includes multi-section proposals,
JD-specific cache separation, malformed/fabricated evidence rejection, current
input validation/focus, desktop/mobile layout, partial/advice-only reviews, retry
and selected versioned saves. System and whitespace checks passed. Gemini network
responses were mocked; live model wording quality and availability were not tested.

## 2026-10-20 follow-up: immediate 503 from whole-CV generation

A live check confirmed the configured Gemini key/model accepted a minimal request.
The new nested full-review schema, using fictional CV data, reproduced upstream
`400 INVALID_ARGUMENT`. The app had hidden this under a generic 503 outage message.
String-bound removal alone still failed; removing nested string/array bounds from
the wire schema succeeded. Whole-CV generation now uses the existing schema
compatibility helper in compact mode, preserving required structure, enum paths
and property restrictions while moving bounds into descriptive generation guidance.
All original local size, item-count, evidence, fact and approval checks remain.

Provider failures now carry safe allowlisted reasons. Existing status/error-code
contracts remain, with optional reason metadata and fixed UI messages distinguishing
configuration, credentials, permission, quota, unavailable model, invalid request,
timeout and connection errors. Logs omit exception text and record only fixed codes
and a validated upstream status number. One request still makes one provider call;
retry remains explicit and retains the job context.

The corrected live whole-CV request returned three job requirements and passed
local validation, without persisting anything. Synthetic content was used for all
live checks; no real CV or contact details were sent, and credentials/model settings
were not changed. Details and provider documentation are linked in
[CV_TAILORING_REVIEW.md](CV_TAILORING_REVIEW.md#gemini-schema-rejection-and-provider-diagnostics).

## 2026-10-20 follow-up: source mismatch in optional job-fit notes

The exact supplied Full Stack AI Developer JD reproduced the error with fictional
CV data. One requirement in Gemini's `job_alignment` was paraphrased; its evidence
quotes matched. This optional-note failure had invalidated the whole wording review.

Generation now supplies numbered literal JD excerpts and asks Gemini to select
requirement IDs and factual source paths. The server resolves them into the
existing public requirement/evidence fields. Unknown references never become
claims. Unverified optional notes are omitted with a fixed server-owned notice,
while independently verified CV wording remains reviewable. Cached notes are
revalidated and the v7 cache separates old review behavior. Original-text mismatch,
unsupported wording, metric/responsibility and concurrent-version checks remain
strict. Only approved wording changes are persisted through M2; job context,
notices and unconfirmed qualifications are never inserted into the CV.

The corrected live request using that JD returned six verified job notes without
an error. No real CV content was sent or saved. The reported JD is retained as a
nonpersonal regression fixture; details are in
[CV_TAILORING_REVIEW.md](CV_TAILORING_REVIEW.md#paraphrased-job-notes-must-not-block-valid-wording).

Combined verification for the provider/schema and job-note fixes passed: full
Django regression ran 520 tests (16 optional tests skipped), 44 focused
alignment/grounding/writing tests passed, all eight Node test files passed, and
three explicit Chromium journeys passed for requirement references, the reported
paraphrased-note failure and quota retry. The earlier provider-focused regression
also passed 43 tests. System and whitespace checks passed. Live tests used only
fictional CVs; browser tests used isolated records and mocked SDK responses.

## 2026-10-20 follow-up: successful review with omitted notes

The reported `200` indicates a completed review; the warning concerned optional
job-fit notes. Their validation is now independent per requirement rather than
discarding the whole section. The UI receives up to six distinct verified notes,
with at most three distinct checked citations each. Invalid items are excluded
without losing valid siblings or approved wording. Strict source, factual and
approval checks remain unchanged, and fresh/cache validation uses the same policy.
Safe logs report retained/rejected counts and fixed error categories. The v8
cache separates earlier whole-section omission behavior. A live synthetic check
of the supplied JD also returned six valid notes; no real CV was read or changed.

Verification passed: 103 targeted tailoring, grounding, writing and provider
regressions, all eight Node test files and two Chromium review/save journeys.
System and whitespace checks passed. Browser tests used isolated synthetic data
and mocked Gemini responses.

## 2026-10-21 follow-up: shared JD tailoring for one part and whole CV

Both modes use a shared section-specific brief with literal JD references,
relevant contribution paths and permitted saved evidence. Whole-CV generation
requests actual replacement wording before editorial feedback and job-fit notes.
Single-part requests optionally bind to an owned CV/version/field; summaries
can synthesize saved CV facts, while employment/projects stay within their entry
and achievements retain selected-text scope. Existing text-only callers and
M5/M10 contracts remain compatible. Every save still requires explicit approval
through the versioned M2 update; role/JD edits invalidate pending proposals.

New grounding coverage protects quantity units, dates, original career identity
and proficiency, candidate responsibility and action/tool associations. A listed
skill cannot authorize deployment of that tool, a manager-led team cannot become
candidate leadership, and an education year or review count cannot become an
application/API count. Valid explicit same-entry facts remain available for
synthesis. These are bounded lexical checks rather than semantic proof.

Live Gemini checks used fictional CVs with no development database reads/writes.
Single-part AI/backend reviews returned different emphasis. A rough CV reviewed
for an AI application JD returned summary and project proposals that passed local
validation; polished examples also returned valid advice-only reviews. An earlier
call timed out and another attempted unsupported LLM wording, which validation
rejected. These smoke checks do not guarantee future model availability or quality.
Further implementation details are in
[CV_TAILORING_REVIEW.md](CV_TAILORING_REVIEW.md#shared-jd-priorities-and-saved-field-context).

Final verification passed: full Django regression ran 578 tests (16 optional
tests skipped), all eight Node suites passed, and three isolated Chromium
journeys passed for JD rewriting, whole-CV evidence review and approved saving.
System and whitespace checks passed. Browser providers were mocked; live smoke
results above used fictional data. The final regression includes the discovered
multiline numeric-unit issue and its whitespace-normalization fix.

## 2026-10-22 follow-up: scoped existing-CV conversation

The reported transcript exposed two separate problems: prior date, selection or
proficiency prompts could survive a section change, and saved language identities
could be copied into an unrelated model reply. Explicit section changes and local
corrections now reset the old editing context before collecting the new answer.
Optional language/certification identities require current-message evidence or an
explicitly selected correction target; an unrelated travel statement cannot copy
English/Urdu from the saved CV or start a proficiency question.

Unclear optional names remain provisional until the user confirms, supplies a
clearer title, cancels or switches sections. Recognized subject titles, credential
codes and explicit issuer/date/link details stay usable; unfamiliar languages are
confirmable and international orthography is preserved. This establishes naming
intent rather than verifying credentials. Mixed clear/provisional answers retain
the clear entries and keep the remaining question in the correct section.

`cancel` exits the active editing step while retaining earlier collected proposals.
`finish` clears obsolete auxiliary prompts without bypassing the required fields
of a new project, job or degree. Progress reviews show readable unsaved proposals,
requested removals, unfinished entries and items awaiting confirmation separately.
General career advice is available on request; automatic advice appears when the
user explicitly enters a section rather than after every accepted edit.

M5/M10 response and document contracts are unchanged. The existing versioned M2
approval flow still owns saving; these fixes do not alter saved CV content or
perform a database migration.

Verification passed: 654 Django tests ran successfully (16 optional browser/live
checks skipped), all eight Node test files passed, and system/whitespace checks
passed. The 76 new regressions cover scoped corrections, optional confirmation,
saved-fact grounding and readable pending reviews. Providers were mocked and all
records were synthetic; no live Qwen request or saved user CV was changed.

### Follow-up: wrong entity types and vague credential confirmations

The next transcript exposed remaining blind scalar parsing for employers and a
confirmation path that could turn an unclear label into a credential. Entity
checks now run before storing local, structured or Qwen-extracted proposals.
Obvious random labels such as `ter45fase4` are rejected even when accompanied by
issuer/date fields. A rejected certification identity cannot leave orphan issuer
or date updates. An unclear credential needs an actual title and issuer if
available, rather than an unqualified `yes`; skills and provider names alone also
need a specific credential title. Exam codes and unfamiliar genuine titles remain
usable without imposing a credential catalogue.

The bounded abuse recognizer includes direct `fool` utterances while retaining
quoted workplace content. Experience command typos are recognized locally.
`lamb cooking` stays at the employer question; company/title fields do not accept
clear skill, activity, language, date or contact values. Name-shaped employers and
common role titles remain local, while ambiguous prose uses Qwen with explicit
entity instructions. `Company: NAME` disambiguates an unusual business name.
Confirmed past work is allowed regardless of the target role, including culinary
work. A related partial-entry merge fix keeps separately supplied employer, role
and responsibilities in the same active new job without joining conflicting jobs.

These checks assess input type and plausibility, not real-world existence,
employment history or credential ownership. M5/M10 contracts, saved CVs and M2
approval/versioning remain unchanged.

Verification passed: 675 Django tests (16 optional checks skipped), all eight
Node test files, and system/whitespace checks. The 21 additional regressions cover
the reported transcript, typed entities in both chat modes, random labels in
structured/model outputs, real exam codes, unusual employer names, separate job
follow-ups and certificate punctuation/metadata. Providers were mocked; tests used
synthetic owned CVs and asserted that saved content/version stayed unchanged.

### Follow-up: skip-command typos at required personal fields

Letters-and-spaces name validation could accept `skip ot` as a name. A bounded
whole-message command check now recognizes one typing error in `skip it` while
requiring one of its two words to remain exact. `skip ot`, `ski[ it` and `skpi it`
therefore follow the existing skip policy: full name/email remain required with a
clear explanation, while optional fields can be skipped. These replies do not
call Qwen or become CV facts. The same handling covers optional date/proficiency
follow-ups.

A second check rejects skip-like names in extracted proposals unless the user
explicitly supplied a name or name correction. Single-word names are not fuzzy
matched; examples such as `Skip Smith`, `Ski Patel`, Unicode names and explicitly
stated `My full name is Skip` remain usable. Existing saved CVs and M5/M10 contracts
are unchanged.

Verification for skip handling passed: 684 Django tests (16 optional checks
skipped), including nine new command/name regressions. Provider calls were mocked
or blocked, and system/whitespace checks passed.

### Follow-up: optional section counts and literal answer cleanup

The initial interview now acknowledges the actual number of skills, complete
projects and certifications before moving on. Short lists offer `add more` or
`continue`: 8–15 relevant skills, 2–3 projects for students/freshers (3–5 for later
career levels), and 3–5 certifications only if already held. Long lists offer
prioritization advice while retaining every entry. Each short/long suggestion is
offered once per section and career level; choosing to add just one more does not
start a minimum-count loop. Existing-CV editing keeps its explicit add/review flow.

`yes` opens collection of the user's own details rather than adding suggested
facts. `continue`, `no` or `skip` dismiss the advice without skipping the collected
section. Users can finish with fewer entries, switch sections or correct contacts.
Only complete projects count toward these suggestions; unfinished projects still
collect their missing fields through the existing workflow.

Education parsing recognizes the full `excpected to end in 2027` clause, keeping
it out of the institution name while preserving the supplied institution wording.
Year-only dates still require the existing explicit month confirmation or omission
before saving. Certificate titles and issuers retain the user's wording through
validation and saving. The certificate-specific spelling dictionary and its
normalization module have been removed; there is no course/provider allowlist.

Known skills receive consistent casing. Fully recognized space-separated stacks
such as `Django Restapi React Ai NLP` become separate technology items, including
when received as a single provider list item. Unrecognized compound names remain
intact. M5/M10 contracts, provider selection and the explicit M2 save/approval
boundary are unchanged; there are no migrations or saved-user-record repairs.

The initial full regression run passed 697 Django tests (16 optional checks
skipped). After removing the spelling dictionary, 142 focused interview tests
passed, including the 13 count/cleanup regressions. The tests cover
optional continuation, adding without overwriting entries, prioritization without
deletions, section/contact changes during advice, literal cleanup and explicit
M10 draft/save output. Providers were mocked or blocked; whitespace checks passed.

### Follow-up: inline additions and field boundaries in the Quddous interview

The next interview exposed overly strict count-choice routing. A direct skills
list now answers the optional follow-up without requiring a separate `add more`
command. An explicit `Add more TITLE` project request starts that project's
description step, retaining the earlier project. Explicit certificate details can
also answer the count prompt. Suggested counts remain optional, and ambiguous
replies still require clarification rather than becoming CV facts.

The graduation parser consumes the whole `i am graduated in YYYY-MM` clause and
the sentence boundary, so `university of Mianwali. i am` cannot be saved as the
institution. Internship/employer parsing extracts the stated title from
`I completed an internship as a TITLE at COMPANY` (including the bounded
`intership` typo), rather than treating the whole sentence as a job title. A plain
`yes` to the experience question asks for the employer and role without invoking
Qwen or proposing a company.

Explicit technology-list introductions such as `Use following technologies` are
removed before splitting the list. Unfamiliar named tools remain valid without
a catalogue or credential spelling map. Project descriptions retain capitalized
tool names in explicit `using NAME` clauses with a clear clause boundary, so
`using Librosa,` does not silently omit Librosa. Ordinary phrases such as `using
browser recordings` and `using New York data` are not promoted to technologies.

Web fundamentals HTML, CSS and JavaScript are treated as supporting skills for
web/backend roles, including the Django/AI integration target in this interview.
An unchanged relevance warning is shown once across the count prompt and later
skills updates. Skills are never removed automatically; unrelated-domain advice
remains advisory. The M5 envelope, M10 document and explicit approval/save flow
remain unchanged.

Verification passed: 707 Django tests (16 optional checks skipped), including
10 additional regressions for this transcript and generic name/list boundaries.
The interview regression saves a synthetic CV through the API and checks the
institution, role, seven retained skills, both projects and explicit tool names.
Providers were mocked or blocked; no live user CV was modified. Whitespace checks
also passed.

### Follow-up: explaining why a conversational message was not added

Qwen's internal extraction schema now accepts an optional, bounded
`rejection_reason` for `off_topic` and `inappropriate` messages. The prompt asks
for one calm user-facing sentence about why the message is not CV information or
an actionable edit. It does not request private reasoning or another question.
The backend displays that sentence, acknowledges that nothing was added and
supplies the current question once. Existing-CV review avoids the redundant
`You can answer, switch...` footer. Missing or unusable model wording receives a
clear local explanation; recognized local rejections do not need a new model call.

Rejected-turn controls are restricted to classification and display feedback.
Model-supplied fields, profile changes, skips and completion cannot change the CV
or advance the interview. Feedback remains outside M10 and the public M5 response
keeps its existing fields. Invalid optional feedback does not invalidate otherwise
valid extraction; unknown properties and extracted CV facts remain strict.

Conversational auxiliary verbs with inserted digits, such as `ar4e you`, are
recognized for routing only. They reach Qwen before project title/description
parsing, while the original user message and CV values are preserved. Clear
recommendation requests such as `Recommend a movie...` also require interpretation
rather than becoming an employer name. Workplace quotes and ordinary criticism
retain their existing treatment.

Verification passed: 715 Django tests (16 optional checks skipped), including
eight new feedback/control regressions. Tests check the exact obfuscated message,
model-provided explanations, local fallbacks, unchanged pending questions and
saved CVs, malformed optional feedback and rejected profile/fact updates. Qwen
responses were mocked; its configured local endpoint was not reachable from this
environment for a live check. Whitespace checks also passed.

### Follow-up: experience fast paths bypassing semantic review

The experience transcript exposed two local shortcuts: a `My role is ...` label
accepted its value without the ordinary job-title confidence check, and an
unconditional short-answer path treated almost any text as responsibilities.
Labelled unfamiliar roles now use Qwen, and unclear duties are delegated rather
than stored as scalar answers. Common clear professional titles and action-based
duties retain their local paths. Articles in labelled job titles are stripped as
grammar, without changing the supplied occupation.

Qwen's prompt explicitly distinguishes claims of harming people from legitimate
investigative, medical, prevention and fictional work. Rejected turns use the
existing explanation channel and preserve the current question and confirmed
employer. Whole-value backend checks additionally reject obvious non-occupational
labels and direct person-harming duty claims if a model incorrectly proposes
them. These are scoped field checks, not a ban on crime-related vocabulary in
valid professional descriptions; unfamiliar plausible occupations remain usable.

The command `want to add expeerience` is recognized locally. At the final review
prompt, `nothing` means finish and does not invoke Qwen. It is not a global skip
for missing experience fields. No saved CV is changed until the existing approval
and save action; the M5/M10 contracts are unchanged.

Verification passed: 724 Django tests (16 optional checks skipped), including
nine new routing/entity regressions. Tests verify two Qwen calls for the reported
invalid answers, unchanged pending role/employer, rejection of incorrect model
proposals, legitimate investigative work, unfamiliar valid titles and local
completion on `nothing`. Providers were mocked or blocked, saved synthetic CVs
were unchanged, and whitespace checks passed.

### Follow-up: company-only answers during add-experience

The request `i want to add experiece` missed the local command parser, and a
lowercase employer ending in `limited` missed the employer-name fast path. A
model-proposed role could then produce an internal field-path warning; a partial
identity matching a saved employer could also switch an inferred addition into
editing before a job title had been supplied.

Fact-free section commands now reuse bounded one-typing-error matching for known
section nouns. Factual messages and names are not fuzzy-corrected. Generic legal
company suffixes include `limited`, without an employer-name catalogue. Switching
an inferred addition to an existing-entry correction requires the complete entry
identity; explicit additions remain additions at an already-used employer.

For new jobs, degrees and projects, contextual identities are limited to the
active draft. Saved entries and earlier proposals cannot supply an unmentioned
role, institution or title. Confirmed draft identities still accompany follow-up
details, and deliberate existing-entry corrections retain their context. Dropped
unsupported work facts get plain-language feedback and the actual next question.

Regression coverage includes the exact typo/lowercase-employer transcript,
unknown employers routed through mocked Qwen, unsupported or copied roles,
partial employer/education matches, and saving a distinct job at the same employer
without changing the saved job. The same-name project test now explicitly supplies
the project title in each user message rather than relying on a copied saved name.
The external M5/M10 contracts and explicit-save requirement are unchanged.

Verification passed: 180 focused Django tests and the full 732-test suite
(16 optional checks skipped). Providers were mocked or blocked. Synthetic saved
documents stayed unchanged until explicit save; the same-employer addition was
also verified through the save API. Whitespace checks passed.

### Follow-up: clear feedback for an unrecognized job title

The work-evidence warning obscured why a proposed role was rejected, and Qwen's
optional explanation was only retained for off-topic or inappropriate messages.
The same bounded display field is now retained for clarification and answers
explicitly requiring clarification. Valid explanations replace generic evidence
or missing-field notices without hiding independent field-validation errors.
Ordinary accepted answers ignore this feedback; it is not a CV fact or an action.

For an unclear title, the reply acknowledges that no job title was added and asks
the pending question once, with examples such as Developer, Designer or Intern.
If no usable model explanation exists, the fallback specifically says that the
job title could not be identified or confirmed. It no longer tells the user only
that work details were kept. Partial valid answers still retain confirmed facts,
and feedback does not claim that no title was added if another supported title
was accepted in the same answer.

Qwen is asked to explain the ambiguity of a typo or unfamiliar word without
assuming criminal intent, inventing a corrected occupation or demanding a known
job-title catalogue. Clearly harmful acts offered as positions get a contextual
explanation. HTML, links, extra questions, abusive text, malformed values and
oversized optional feedback use the existing bounded fallback. No extra model
request or public M5/M10 contract field was added.

A selected saved-entry field cannot turn a model clarification into an entry
patch and discard its explanation. Accepted patches retain their existing
validation/clarification metadata. Confirmed proposals and saved CVs remain
unchanged during rejected or unclear turns; normal collection resumes after a
valid title is provided.

Verification passed: the full 741-test Django suite (16 optional checks skipped),
followed by a 171-test focused recheck covering the final missing-explanation
fallback. The nine added regressions cover Qwen clarification feedback, the
reported inputs, invalid optional wording, partial valid answers, saved-entry
editing and honest feedback for supported sibling titles. Providers were mocked
or blocked; whitespace checks passed.

### Follow-up: random text accepted as a project title

The project-name fast path accepted almost any short response, and shared entity
validation did not check project names. A bare value such as `ters354d` therefore
advanced to the description question. Project names now reuse the existing noise
and conversational-answer checks, with clarification for ambiguous mixed codes.
The reply explicitly says that the name was not added and asks for the actual
project name. It keeps the name question active and preserves confirmed entries.

This does not require a dictionary of valid projects. Numeric, branded and
international names remain usable. A genuine unusual code can be explicitly
named with `My project is called ...` or an explicit structured name field;
the supplied title is preserved. Bare confirmation words do not become titles.
The same naming syntax is used by title extraction and intent validation.

When a proposed project name fails validation, its description and technologies
are withheld with that entry so they cannot attach to another project. Valid
sibling entries are retained. This applies to initial interviews, explicit
additions and provider proposals, with the existing M5/M10 contracts and save
approval unchanged. Qwen's prompt also asks for clarification of random project
names and preserves explicitly named unfamiliar projects.

Verification passed: 118 focused Django tests and the full 749-test suite
(16 optional checks skipped). Eight new regressions cover the exact input,
repeated noise and confirmations, existing-CV additions, add-more prompts,
incorrect provider proposals, sibling isolation, and explicit coded/numeric/
international project names. Providers were mocked or blocked. Saved synthetic
CVs were unchanged, and whitespace checks passed.

### Follow-up: validating project descriptions and technologies

Project names were guarded, but description and technology scalar shortcuts still
accepted random text. The shared project noise check now covers each field with
a field-specific retry. Noise, bare confirmations, contact-only values and tool
lists cannot complete the description. Meaningful descriptions may still mention
codes and real tools; these are whole-answer checks rather than word bans.

Technology strings and lists are normalized before checking each tool, including
comma, semicolon and newline lists. Invalid labels are withheld; valid tools in a
mixed list remain confirmed. An entirely invalid list keeps the technologies
question active, while partial acceptance explains that the recognized tools were
kept. Empty or punctuation-only lists also receive a clear retry.

A lone ambiguous description word and an unfamiliar single technology go through
Qwen instead of unconditional scalar storage. Unfamiliar internal tools remain
eligible, and the prompt asks for project-purpose/tool clarification rather than
inventing descriptions or a stack. Missing model explanations use human field
names instead of internal paths. The name/description/technology checks apply to
provider proposals as well as local extraction and initial/existing-CV flows.
The public M5/M10 contracts and explicit-save boundary are unchanged.

Verification passed: 192 focused tests, a final 34-test project-flow recheck, and
the full 758-test Django suite (16 optional checks skipped). Nine new regressions
cover the exact sequential failure, saved-CV additions, provider/structured data,
mixed and packed technology lists, unknown tools, meaningful code mentions and
plain-language clarification fallbacks. Providers were mocked or blocked; saved
synthetic CVs stayed unchanged until explicit save, and whitespace checks passed.

### Follow-up: source validation and unauthorized model transitions

The latest interview exposed a broader boundary problem: validating only model
proposals does not protect the original answer if Qwen reclassifies or rewrites
it. Whole self-descriptions such as `I am a serial killer` were not covered by
the responsibility checks. Qwen could also emit `skip`, `go_back`, `finish` or
`remove_information` without a matching user command and change interview flow.

Work answers now receive an independent source check before model proposals can
be used. Standalone harmful occupational claims, random codes and bare
confirmations cannot become work duties or benign invented paraphrases. Rejected
source turns discard proposed facts and profile/control changes while preserving
the employer, role and pending question. Genuine model rejection explanations
remain visible. Whole-value checks preserve investigative, medical, software and
fictional contexts rather than banning vocabulary.

Extraction output alone no longer authorizes skipping, undoing, finishing or
removing details. Those commands must come through the existing explicit local
routes; otherwise the assistant clarifies and retains the current step. A
fact-free internship acknowledgment, including a single typing error in
`internship`, locally advances to asking for the actual company and role. It
does not invent an employer or treat confirmed internship presence as invalid.

Verification passed: 194 focused Django tests and the full 766-test suite
(16 optional checks skipped). Eight new regressions cover the complete fresher
flow, adversarial model controls and paraphrases, acknowledgment typos, valid
investigative/fictional duties and genuine model feedback. Automated regression
providers were mocked or blocked; whitespace checks passed.

Live verification also passed against local `qwen3.5:4b`, using the real chat API
in an isolated in-memory database: seven flow checks with four actual model
calls. Qwen returned `intent=answer` and experience data for the harmful
self-description, reproducing the semantic error; backend source validation
blocked it and retained the responsibilities question. The current-code replay
also retained the technology question for `ters354d`, accepted the internship
acknowledgment, accepted a valid corrected responsibility, retained legitimate
investigative work and accepted an unfamiliar-to-the-local-parser technology.
No saved CVs or real user records were accessed or changed, and no non-Qwen
provider requests were made. Measured results are recorded in
`docs/QWEN_CONVERSATION_AUDIT_2026_10_27.json`.

### Follow-up: certification titles cannot be established by issuer metadata

`clear_certificate` previously treated any issuer, date or link as sufficient
evidence to accept the supplied title. This let a person descriptor become a
qualification after an issuer was appended. Title/type validation now precedes
metadata confidence. Whole person descriptors, including location qualifiers,
certificate labels and quotation marks, receive a clear retry and cannot advance
the section. Legitimate investigation, profiling, prevention and literary courses
remain eligible; unfamiliar course names do not require a fixed catalogue.

When evidence validation rejects a proposed certification name, its issuer/date/
link are withheld with it rather than becoming an anonymous qualification or
attaching to another entry. Known-invalid unconfirmed candidates no longer keep
asking for an issuer. Confirmed valid sibling entries are retained. No stored CV
is modified automatically.

The existing parser also handles an explicit polite add/include wrapper and one
typing error in the `issued by` cue, preserving the course title and issuer rather
than including `issud by ...` in the name. It does not rename course/provider
brands. Ambiguous free-form requests still go to Qwen. Its input now includes the
actual interview question, and qualification extraction uses shared fact rules
plus section-specific guidance instead of occupational rejection instructions.

Live testing initially caught Qwen rejecting a legitimate investigation course as
an act/person description. That false positive is retained in the audit history.
The final isolated API replay passes both the reported sequence and a genuinely
unstructured forensic-qualification request with actual `qwen3.5:4b` responses.
Qwen still proposed adding the invalid person descriptor in that replay; the
backend rejected it. Model classification and issuer metadata therefore remain
proposals, not proof of qualification type, authenticity or ownership. The public
M5/M10 contracts and explicit-save boundary are unchanged. Measured runs are in
`docs/QWEN_CERTIFICATION_AUDIT_2026_10_27.json`.

Verification passed: 218 focused tests and the full 777-test Django suite
(16 optional checks skipped), including eleven added regressions. Six final live
flow checks passed, with two actual local-Qwen calls and zero saved-CV writes or
non-Qwen provider requests. The earlier false-positive live runs remain in the
report for comparison. Whitespace checks passed.

### Follow-up: summary and narrative answers need content validation

The summary step previously stored any non-question plain-text answer directly,
so a paragraph claiming personal violence could complete that section and move
to review. A shared narrative check now covers summaries, project descriptions,
work responsibilities and achievements. It recognizes direct self-claims rather
than rejecting crime-related vocabulary. Quoted reporting, negation, legitimate
investigation/prevention work, fictional performance and computer process
termination remain eligible. A bounded typo check also handles the reported
`murdere` verb without fuzzy-matching legitimate `billed` or `filled` statements.

Both local field validation and the original-source extraction guard enforce the
check. A model cannot replace a rejected source with invented respectable prose,
silently skip it or finish the interview. Single-section JSON summaries are
decoded before validation. Invalid summary status retains the actual summary
question; independently valid achievement-list siblings are kept. New and saved-CV
editing conversations can accept a correction or an explicit skip afterward.
No stored CV is automatically rewritten.

Rejected turns now retain the authoritative current section, preventing a model's
unrelated section label from opening a personal-details edit. When Qwen provides
a clarification reason with no accepted facts, the assistant retains the reason
and explicitly acknowledges that nothing was added. Narrative extraction guidance
distinguishes the subject of professional work from a first-person act and
recognizes an introduction/profile-paragraph correction as a summary update.

The initial isolated live replay exposed both an omitted explicit acknowledgment
and a false rejection of a legitimate counterterrorism-analyst summary. Those
results are retained in the live audit history rather than omitted.
Redundant prompt guidance was shortened after the existing context-size regression
caught an oversized prompt; the original size limit was kept. The final live
replay passes all eight flow checks with two actual `qwen3.5:4b` calls. Its
synthetic saved CV is unchanged and no real user records or other providers are
accessed. Results, including the earlier runs, are recorded in
`docs/QWEN_SUMMARY_AUDIT_2026_10_27.json`.

Verification passed: 211 focused tests and the full 792-test Django suite
(16 optional checks skipped). Fifteen new regressions cover source/typed
validation, new/edit/review flows, valid corrections and skips, structured
summaries, valid achievement siblings, legitimate professional/quoted contexts,
model-created wording and controls, rejection explanations and section retention.
The M5 public response and M10 persistence contracts remain unchanged. Whitespace
checks passed.

### Follow-up: grouped project answers and skipped summaries

The John interview supplied a project heading, implementation bullets and named
technologies together, but only its title and a generic `AI` technology survived.
It also showed a professional summary after the user explicitly skipped that
section. Skills were explicitly pasted by the user, so retaining those skills is
correct; the selected senior interview profile alone is not evidence of senior
experience or of the industries and technologies in the unwanted summary.

CV-style project headings and bullet/newline descriptions now stay together in
the existing project-answer parser. Tools come from the supplied implementation
text, not the title. A heading year is retained in the description because M10
has no project-date field. The existing tool vocabulary recognizes Gemini;
unfamiliar tools still use the existing extraction paths. Updating a description
adds its literal tools to previously confirmed tools, while an explicit tools
answer can replace the stack. Both initial interviews and saved-CV proposals
retain their existing explicit-save behavior.

Copied interview input is trimmed only when it has an explicit transcript
wrapper and the exact current assistant question. The latest following answer is
processed normally, including content validation; the original user message is
retained in chat history and request receipts. A copied question without an
answer asks for details rather than becoming content or triggering generic CV
advice. Ordinary descriptions and quoted examples are not rewritten by this step.

Qwen cannot add an unsolicited summary while extracting another section. Explicit
summaries, genuine profile paragraphs, requested introduction changes and valid
CV JSON after an introductory sentence remain supported. Skipping the summary
in a new CV clears its unsaved value, and both current-state and legacy-history
draft import honor that skip. This also keeps an already-skipped legacy summary
out of preview/save without deleting historical messages. Skipping an edit to a
saved CV preserves its saved summary. Short `sip`, `skp` and transposed skip
typos are recognized only at optional profile-link questions; email validation
still rejects those values. The reported `finssh` finish typo follows the normal
completion checks.

The isolated live API replay passed seven checks with one actual local
`qwen3.5:4b` request. It covers a complete senior-profile interview, explicitly
entered skills, work duties, grouped project details, optional skip typos,
summary omission, completion, draft review and a separate copied-transcript
answer. It accessed no real user records, wrote no saved CVs and contacted no
other provider. Results are in `docs/QWEN_GROUPED_ANSWERS_AUDIT_2026_10_27.json`.

Verification passed: 198 focused tests and the full 812-test Django suite
(16 optional checks skipped), including twenty new regressions. Coverage includes
grouped data in both creation and editing, title/tool separation, description
updates, copied and empty transcripts, source-only summary authorization,
prose-prefixed CV JSON, current and legacy summary skips, saved-summary retention,
optional-link typos, explicit tool replacement and normal completion checks.
Public M5/M10 response and save contracts are unchanged. Whitespace checks passed.
