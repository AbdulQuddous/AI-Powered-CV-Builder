# M7 — CV Editor (Django Templates + Tailwind + Alpine.js)

## Existing backend contract (not replaced)
- M1 owns JWT/login and user identity.
- M2 owns JSON, CV permissions, updates, versions, and version-conflict validation.
- Shared schema (`shared/schemas/cv_schema.json`) is the only source of truth.
- M5/M6 AI and M8 renderer use exactly the saved JSON; M7 does **not** transform it or generate PDFs.
- No M7 database models, migrations, serializer, or duplicate CV endpoint.

## Install as a new app into your existing project
Copy the `m7_editor` directory to your Django project root (beside `manage.py`).

`config/settings.py` (or whichever base settings your project imports):

```python
INSTALLED_APPS += ["m7_editor"]
```

`config/urls.py`: preserve existing urlpatterns, append:

```python
from django.urls import include, path
urlpatterns += [path("", include("m7_editor.urls"))]
```

Django uses its default app-template loader (`APP_DIRS=True` in the DjangoTemplates backend) and `django.contrib.staticfiles`.

A prebuilt Tailwind CSS file is already included at `m7_editor/static/m7_editor/css/editor.css`, so the initial page can load without npm. For rebuilding the CSS after you change template classes, copy `styles/editor.input.css` and `package.json` next to `manage.py`, then:

```bash
npm install
npm run css:build
```

Start Django:

```bash
python manage.py runserver
```

Browse `http://127.0.0.1:8000/cvs/1/edit/` (replace `1` with a real CV id). For CSS work, run `npm run css:watch` in a second terminal. Production: include built CSS in deployment and run `python manage.py collectstatic`.

## Authentication

M7 initially calls the authorized M2 API with same-origin cookies and with any existing JWT in `sessionStorage` under `cv_access`, `access`, or `access_token`. If it gets a 401/403, it shows a login form that calls `POST /api/auth/login/` with `{username,password}` and reads `{access}` (or `{data:{access}}`). This is a standalone starter integration; the endpoint path/credentials keys must match your actual M1 contract.

For production prefer your existing secure HttpOnly cookie / CSRF login if one exists. JavaScript-readable storage for an access token can be exposed by an XSS bug; avoid long-lived refresh tokens in browser JS, enforce a strict CSP, and do not ship the current CDN version without checking your site's CSP and asset strategy. The UI route serves an **empty shell only**; the M2 API enforces object-level ownership and actual data access.

## Critical M2 adapter check

Inspect `m7_editor/static/m7_editor/js/api.js`:
- `normalizeResponse()` accepts `{data:{id,cv_data,version}}`, `{id,content,current_version}`, etc. and dynamically detects the document field.
- `buildPatchBody()` currently sends `{[documentField]:cvJSON, expected_version: version}`; the **exact** PATCH serializer/request body was not available from the project source, so map these keys to M2's real field names **before use**. Never weaken M2's optimistic locking to make it work.
- If M2 returns a CV as a direct JSON resource without version metadata, expose a version in the response instead of allowing blind writes.
- If M2 uses an HTTP `If-Match` header instead, adjust `request()` and `buildPatchBody()` in this adapter, not in editor.js.
- If M1 login URL differs, change the one `api.login()` line.

## Behavior
- Manual editing for Personal, Summary, Experience, Education, Projects, Skills, Certifications, Achievements, Languages.
- Preserves all unknown CV keys (including `schema_version` and `meta`) without conversion.
- `add`, `remove`, `reorder` list entries; fields are driven by the loaded row shape.
- Empty Experience/Education/Projects use known M5 row shapes; other blank lists default to string entries unless an existing row shows their true shape. Check shared schema before adding new object types in those sections.
- Multiline arrays are edited as one item per line and kept as arrays. Nested objects not supported by scalar controls are left untouched.
- Save is explicit, not automatic. Conflicts (HTTP 409/`version_conflict`) show Export Draft / Reload Latest, never silently overwrite.
- The live pane is a plain **content** preview, not the final PDF design. M8 handles PDF rendering.

## Run checks

```bash
node --test tests/*.test.cjs
python -m compileall -q m7_editor
python manage.py test m7_editor --settings=config.test_settings
```

After integration, test browser: valid token -> load; change summary -> save; refresh -> persists; add/move/delete experience -> save; open same CV in two tabs, save in first, save in second -> conflict, no overwrite; another user's CV id -> M2 denies access; expired token -> sign-in; export unsaved draft; unknown JSON keys survive.

**No changes to M1–M6 endpoints or migrations are required.**
