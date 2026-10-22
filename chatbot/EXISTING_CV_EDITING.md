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

Switching sections clears the previous question and optional proficiency follow-up.
`cancel` leaves the current editing step and retains previously collected proposals.
`finish` opens the draft review when the required details for an active new entry
are complete. An unfamiliar language name can be confirmed with `yes, add it`.
An unclear certification requires its full title and issuer if available, for
example `Certification: Google AI Essentials — Google`; a simple `yes` cannot add
it. Obvious random labels are rejected before the confirmation flow, including
labels inside pasted JSON. A title with a recognized subject, issuer or credential
code can be collected directly. These checks establish naming intent and input
quality; they do not verify credentials.

Employer and job-title fields reject clear activities, skills, languages, contact
details and abusive messages. For example, `lamb cooking` leaves the company
question open, while `Chef` is a valid job title. Unusual business names can be
clarified with `Company: NAME`; ambiguous company/title prose uses Qwen instead of
blindly filling a field. `add xperience` opens experience without creating a job.
Separate employer, title and responsibility answers complete the same active entry.

Saved languages are context, so an unrelated message cannot copy them into a new
answer or start a proficiency question. `show collected information` lists pending
changes in plain text, including new projects and requested skill removals, without
repeating general career advice. Incomplete active additions are shown separately.

## Implementation

- `services/existing_cv_conversation.py`: saved-CV context, local editing selectors, focused proposals, follow-up questions, and legacy-session upgrade.
- `services/conversation_service.py`: selects editing mode and reuses the existing Qwen extraction and persistence pipeline.
- `services/edit_controls.py` and `message_routing.py`: scoped follow-ups, section changes, cancellation and confirmation.
- `services/extraction_guard.py` and `optional_answers.py`: ground optional facts in the reply and clarify ambiguous naming intent before adding them.
- `services/entity_validation.py` and `field_validation.py`: enforce entity types and reject obvious noise for local, structured and model-generated proposals alike.
- `services/progress_review.py`: concise, read-only review of unsaved changes.
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

Tests mock providers. For a manual check, refresh `/dashboard/`, click Continue with AI on a populated CV, add a new project, finish, explicitly save, and preview the result. Test a location correction and confirm unrelated fields remain intact. Also try an unrelated travel message at the language question, switch to certifications, cancel an unclear title, and review the pending changes.
