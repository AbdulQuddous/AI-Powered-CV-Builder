# M10 shared contracts — version 1.0

## Ownership and boundaries
`shared/` contains only schemas, enum declarations, examples and documentation.
It must not import Django, query a database, invoke Grok, render PDFs or run business logic.
M1 owns accounts, password hashes and token lifecycle. Other modules use
`request.user.pk` and `request.user.email` after DRF authentication. Internal identity DTO:
`{"user_id":123,"email":"user@example.com"}` matches user_schema.json exactly.
The profile response additionally contains `full_name`; it is not the identity DTO.
Future Django relations must use settings.AUTH_USER_MODEL, never import accounts.User.
Identity does not imply ownership: each future module must filter records by authenticated
owner, never trust a user_id supplied in a request body.

## CV contract
cv_schema.json is the authoritative content format. Required keys must always be present;
unknown keys are rejected at every object level. Blank strings and empty lists permit
incomplete drafts. Missing values are empty strings, never null. Dates are YYYY-MM or
empty. `end_date` is empty for current work; cross-field date ordering and readiness
validation belong to the CV module, not M10. Validate JSON Schema using Draft202012Validator
and FormatChecker. Format checks alone do not prove a CV is ready to export.

Maximum experience entries: 5. Three entries is advisory, not a schema minimum.
Never invent experience to meet a suggestion; freshers may use zero entries.
Skills are strings; education, experience, projects, certifications and languages have
explicit object structures in the schema. Achievements are strings.
`career_level`: fresher, experienced, other; blank allowed only for incomplete drafts.
`template_id`: stable opaque catalogue key; blank allowed in drafts. Template module
must confirm that a nonblank ID exists and supports the CV schema version.
CV ID, owner ID, status, timestamps and revision belong to the future persistence envelope,
not the CV content JSON. Status enum: draft, ready, archived. Status transitions are owned
by the future CV module. No persistence or status transition API is implemented here.

## Chat and template contracts
chat_schema.json defines a persisted, user-visible message DTO, not a Grok request.
IDs are UUID strings and created_at is RFC3339. It excludes system prompts and internal
reasoning. A chat module will own request/response APIs and conversation state; this
contract does not permit a client to submit assistant messages or overwrite a CV.
Template schema is catalogue metadata; no filesystem paths or executable HTML.
Empty target_roles means general-purpose. Compatibility is explicit through
supported_cv_schema_versions. Type values: ats, modern, classic.

## Authentication HTTP API (implemented)
All paths end in `/`. Bodies and successful nonempty responses use application/json.
Private endpoints require `Authorization: Bearer <access>`.

| Method / path | Body | Success | Authentication |
|---|---|---|---|
| POST /api/auth/register/ | email, password, optional full_name | 201 profile | public |
| POST /api/auth/login/ | email, password | 200 access + refresh | public |
| POST /api/auth/refresh/ | refresh | 200 access + rotated refresh | public |
| POST /api/auth/logout/ | refresh | 204 empty | access token |
| GET /api/auth/me/ | none | 200 profile | access token |
| PATCH /api/auth/me/ | full_name | 200 profile | access token |

Profile example: {"user_id":123,"email":"user@example.com","full_name":"Example User"}.
Token response: {"access":"<jwt>","refresh":"<jwt>"}.
Registration does not log in automatically. Login separately.
Emails are trimmed and lowercased; uniqueness is also enforced case-insensitively in DB.
Passwords are 10–128 characters at registration, validated by Django, stored hashed,
and never returned. PATCH accepts only full_name. Email changes require a future
verification flow and are not supported. Password reset and email verification are
outside this increment.

Errors from DRF: {"error":{"code":"validation_error","details":{"email":["..."]}}}.
Details can be field errors or a detail object. Codes: validation_error (400),
authentication_failed (401), permission_denied (403), not_found (404),
method_not_allowed (405), throttled (429), request_error (other handled errors).
Proxy errors, unmatched URL errors and unexpected 500 errors are outside this envelope.
Duplicate email, weak password, unknown registration/profile fields: 400.
Bad credentials, invalid/expired access or refresh: 401. Anonymous private access: 401.
Malformed/revoked logout refresh or token belonging to another user: 400.
Register/login/refresh use a shared `auth` throttle scope of 20 requests/minute/IP.
Default local-memory throttling is per process and is not a distributed abuse defense.

Refresh tokens rotate and the old token is blacklisted. Clients must store the returned
replacement and serialize refresh requests; concurrent refreshes are not guaranteed
single-use atomically. Logout revokes the submitted refresh, not every device session.
Issued access tokens remain valid for up to five minutes. Client must delete both tokens
on logout. Default refresh lifetime is seven days; rotation renews that lifetime.
No absolute session expiry is implemented. Token responses must never be logged.

## Compatibility policy
Version 1.0 is frozen after adoption. Any field removal/rename/type change or stricter
constraint requires a new schema version and explicit migration in the owning module.
Because objects reject unknown properties, added fields also require a new supported
version. Never silently reinterpret an old document. Keep old schemas available while
stored CVs use them. Python enum values must match JSON schema enums; tests verify this.
Module implementers must propose changes here before changing producer/consumer payloads.
