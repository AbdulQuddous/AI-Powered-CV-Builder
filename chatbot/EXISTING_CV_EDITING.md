# Continue with AI for an existing CV

M5 starts a focused editing conversation when `cv_id` refers to an owned CV containing personal information, career metadata, or other CV sections. It reads M2's saved document as context and asks:

> What would you like to add or edit in your existing CV?

The dashboard sends the same create-session and message payloads. No endpoint, public response field, shared CV schema, or frontend state-machine logic is added.

Example flow:

1. Continue with AI on a populated CV.
2. Send `I want to enter another project`.
3. Provide its name, description, and technologies together or answer the missing-detail follow-ups.
4. M5 returns to asking what else to add or change.
5. Send `finish`, then click Save collected details to CV.
6. View the CV: the new project is included and the existing entries remain.

Corrections to an existing project collect only the changed fields. Personal corrections do not restart contact collection. Saved facts stay unchanged until the existing explicit M2 save action.

## Implementation

- `services/existing_cv_conversation.py`: saved-CV context, local editing selectors, focused proposals, follow-up questions, and legacy-session upgrade.
- `services/conversation_service.py`: selects editing mode and reuses the existing Gemini and persistence pipeline.
- `services/state_manager.py` and `response_normalizer.py`: small mode-specific branches; original new-CV interview behavior remains intact.
- `services/prompt_builder.py`: adds an editing instruction after the original system controls. The existing JSON response schema is retained; provider intent distinguishes new-project collection from corrections before backend normalization.
- `views.py`: resumes older active sessions with saved-CV context and preserves their message history. Proposals newer than the saved document are retained during upgrade.
- `../cvs/chat_import.py`: transfers staged edits through M2, keeps explicit project additions separate, and makes approval retries idempotent. Unchanged metadata is not reapplied from an old snapshot.
- `../tests/test_existing_cv_chat.py`: initial message, project follow-ups, corrections, ownership, resuming, grouped updates, explicit additions, retry safety, and original interview behavior.

A new session without a CV, or with an entirely empty CV document, uses the original interview. Existing completed sessions remain completed; Continue with AI creates a new editing session using the current saved CV. M2 still controls ownership, validation, persistence, and versioning.

## Verify

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py test --settings=config.test_settings
```

Tests mock Gemini. For a manual check, refresh `/dashboard/`, click Continue with AI on a populated CV, add a new project, finish, explicitly save, and preview the result. Test a location correction and confirm unrelated fields remain intact.
