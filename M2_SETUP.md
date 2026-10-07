# M2 — CV Management

This package includes M1 + M10 + M2. For your already working project, add the `cvs/`
folder and `tests/test_cvs.py`. Keep your existing .env and database.

## Integrate with the verified M1 project
1. Add `'cvs'` to INSTALLED_APPS in config/settings.py.
2. Add `path('api/cvs/', include('cvs.urls'))` to config/urls.py.
3. Add `409: 'version_conflict'` to the codes mapping in accounts/exceptions.py.
   This is a generic error-envelope extension; M1 does not import M2.
4. Copy shared/api/M2_API_CONTRACT.md for the next module's handoff.
5. Apply and verify:
```bash
python manage.py migrate
python manage.py check
python manage.py test tests --settings=config.test_settings
```
Do not delete your database or rerun an initial project setup. M2's migration depends
on the configured user model. Requirements are unchanged from M1.
For a new installation follow README.md first, then this document.

## Design
- `models.py`: CV and CVVersion storage. Owner references AUTH_USER_MODEL.
- `validation.py`: loads unchanged M10 schema, expands draft defaults, checks dates.
- `services.py`: owner-scoped transactional creation, updates, checkpoints, duplication,
  deletion. Other backend modules should call these services using validated values;
  never update CV rows directly because that bypasses history and validation.
- `serializers.py`: request allowlists and response representations.
- `views.py`: authenticated HTTP routing and pagination.
- `urls.py`: all eight requested endpoints.

The canonical metadata exists once, inside CV.data.meta. API top-level metadata is
projected from it. This prevents drift between CV content and database columns.
No Grok, React, Tailwind, PDF or template-rendering imports exist in M2.
Template IDs are opaque strings; validating catalogue existence belongs to the future
integration with the template module. M2 stores drafts, not a guarantee of export readiness.

## Manual checks (Postman / Thunder Client)
Use M1 login to get an access token. Set Bearer auth on every request.
1. POST /api/cvs/ with the example below: expect 201, id, version 1 and expanded data.
2. GET /api/cvs/: expect a paginated result containing the new CV.
3. GET /api/cvs/{id}/: expect the same content.
4. PATCH /api/cvs/{id}/ with {"name":"Backend CV","expected_version":1}:
   expect version 2 and preserved CV content.
5. POST /api/cvs/{id}/versions/ with {"expected_version":2}: expect snapshot version 3.
6. GET /api/cvs/{id}/versions/: expect versions 3, 2, 1 with their original content.
7. POST /api/cvs/{id}/duplicate/ with {"name":"Second CV"}: expect a new id, version 1.
8. DELETE /api/cvs/{id}/: expect 204; subsequent GET returns 404. Duplicate remains.
9. Use another account: original owner's records must return 404, and list must exclude them.
10. Try six experience entries or stale expected_version: expect 400 or 409, no changes.

Create body:
```json
{
  "name":"Python Developer CV",
  "target_role":"Python Developer",
  "career_level":"fresher",
  "template_id":"modern",
  "data":{}
}
```
Data editing: first GET the document, edit its data object, then PATCH with the complete
`data` and the retrieved `expected_version`. Nested partial objects are deliberately
rejected to prevent accidental loss and unclear list-merge behavior.

## Verification limits
SQLite API tests exercise behavior, rollback and schema validation. PostgreSQL row-lock
concurrency must be verified on PostgreSQL; SQLite does not implement SELECT FOR UPDATE.
For PostgreSQL testing use a dedicated test user with CREATEDB and DATABASE_URL in the
environment. Do not use production data. Requests without expected_version deliberately
use last-write-wins after locking; use expected_version to detect stale edits.
