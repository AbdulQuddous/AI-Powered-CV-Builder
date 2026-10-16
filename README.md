# AI-Powered CV Maker

Django/DRF application with PostgreSQL, JWT accounts, CV management, templates,
PDF/DOCX import, local Qwen conversation, optional Gemini final review/intelligence, manual editing, rendering,
and the dashboard/chat frontend. Python 3.12 is used by the current environment.
Open `/dashboard/` after starting Django. The current verification results and
deployment limitations are in [the final system audit](docs/FINAL_SYSTEM_AUDIT.md).
Current chatbot behavior, local Ollama settings, test evidence and a manual guide are in
[the chatbot implementation report](docs/CHATBOT_IMPLEMENTATION_REPORT.md).

## 1. Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"
```
Put the generated value in DJANGO_SECRET_KEY in .env. Never commit .env.
On Windows activate with `.venv\Scripts\activate` and copy with `copy`.

## 2. Create PostgreSQL database
As a PostgreSQL administrator, run these SQL statements; choose your own password:
```sql
CREATE USER cv_user WITH PASSWORD 'your-database-password';
CREATE DATABASE cv_maker OWNER cv_user;
```
Set DATABASE_URL in .env to match. URL-encode special characters in credentials.

## 3. Start
```bash
python manage.py migrate
python manage.py check
python manage.py runserver
```
The custom user model must be configured before the first migration. For an existing
project with an already-migrated user model, plan a data migration rather than dropping
these files into it. This bundle is a standalone new-project foundation.

## 4. Try the API
```bash
curl -X POST http://127.0.0.1:8000/api/auth/register/ \
 -H 'Content-Type: application/json' \
 -d '{"email":"abdul@example.com","full_name":"Abdul","password":"MyDemo-Password-728!"}'
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
 -H 'Content-Type: application/json' \
 -d '{"email":"abdul@example.com","password":"MyDemo-Password-728!"}'
curl http://127.0.0.1:8000/api/auth/me/ -H 'Authorization: Bearer ACCESS_TOKEN'
curl -X PATCH http://127.0.0.1:8000/api/auth/me/ \
 -H 'Authorization: Bearer ACCESS_TOKEN' -H 'Content-Type: application/json' \
 -d '{"full_name":"Abdul Quddous"}'
curl -X POST http://127.0.0.1:8000/api/auth/refresh/ \
 -H 'Content-Type: application/json' -d '{"refresh":"REFRESH_TOKEN"}'
curl -X POST http://127.0.0.1:8000/api/auth/logout/ \
 -H 'Authorization: Bearer ACCESS_TOKEN' -H 'Content-Type: application/json' \
 -d '{"refresh":"LATEST_REFRESH_TOKEN"}'
```
Substitute real tokens locally. After refresh, use the new pair.

## 5. Run tests
```bash
python manage.py test tests --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
```
Test settings default to in-memory SQLite. To exercise PostgreSQL, pass a TEST_DATABASE_URL
for a dedicated test database user with CREATEDB permission. Do not use production data.

## Next-module handoff
Read shared/api/API_CONTRACT.md and all shared/schemas before building another module.
Use shared/examples/cv_draft.json for an empty draft. M10 has no business logic.
M1 never imports CV, chat, template, AI or PDF modules. New endpoints inherit authenticated
access by default, but their own views must still enforce record ownership.
Use `settings.AUTH_USER_MODEL` for relations and request.user for identity.
Account full_name and CV personal.full_name are independent: prefill a new draft if desired,
but profile changes must not silently overwrite saved CVs.

## Deployment notes
Use DEBUG=False, a unique secret, real ALLOWED_HOSTS and HTTPS. Configure trusted proxy
headers only for your actual proxy. No CORS is enabled; serve frontend under the same
origin or configure an explicit origin allowlist when adding the frontend.
Run `python manage.py flushexpiredtokens` daily using your host scheduler.
Run `python manage.py check --deploy` with production settings. Configure HSTS for your
actual domain and infrastructure. Local-memory throttling needs a shared cache or edge
rate limiting before multi-worker public deployment. Redis is not required for this module.
Email verification, password recovery and automatic deployment are not implemented.
Raw uploaded documents must remain private; do not expose the media directory through
the production web server. Apply migrations, including the built-in template catalogue,
and collect static files when deploying. Configure `GEMINI_API_KEY`, `GEMINI_MODEL`
and `M6_GEMINI_MODEL` for explicit AI actions; automated tests mock AI providers.

## References
- https://docs.djangoproject.com/en/5.2/topics/auth/customizing/
- https://django-rest-framework-simplejwt.readthedocs.io/en/stable/settings.html
- https://django-rest-framework-simplejwt.readthedocs.io/en/stable/blacklist_app.html

## Local conversational AI

Chat defaults to `CHAT_LLM_PROVIDER=qwen_local`,
`CHAT_QWEN_BASE_URL=http://127.0.0.1:11434`, `CHAT_QWEN_MODEL=qwen3.5:4b`,
and `QWEN_TIMEOUT=60`. Dedicated chat variables preserve older `QWEN_*`
OpenAI-compatible configuration. No model download is automatic.
Simple field validation/extraction avoids AI. Ambiguous language uses local Ollama;
Gemini is used only for an explicitly approved final chat review through M6.
The user approves proposed wording and saves through existing M2 versioning.
`manage.py qwen_smoke` is an opt-in local test using synthetic facts, with no CV writes
or Gemini requests. See the implementation report for complete verification and limitations.
