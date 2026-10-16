# Conversational CV assistant implementation

Date: 16 October 2026. This report describes the chatbot changes made on top of the
existing, already-modified workspace. Unrelated user changes were preserved. No
application records were reset, no model was downloaded, and no live Gemini call was made.
The earlier `FINAL_SYSTEM_AUDIT.md` remains a historical system audit.

## Follow-up fix: Talha interview and project identity loop

A read-only inspection of the affected active chat confirmed two incomplete projects,
`Django web application` and `REST API`, extracted from a professional profile paragraph.
The earlier literal project title had been rejected after model rewriting. Every later
anonymous description matched both rows, producing a generic ambiguity error without
an entry-selection mechanism. The portfolio query string also triggered prose handling
because of its `?`, and the informal `i bs ... from university ...` answer missed the
bounded education parser.

Whole HTTP(S) URLs, including query strings and complete Markdown links, now pass
directly to the pending contact-field validator before question detection. The evidence
guard silently removes unchanged context contacts repeated by the model; it still
rejects new unmentioned contacts. The verified qualification parser accepts the informal
`i bs software engineering from university of minawali` wording, preserving the stated
university spelling and asking only for the missing graduation date. Explicit skill
aliases work as lists or single answers. An affirmative responsibility sentence such as
`Building sclabable and maintainable backend system` remains intact without model use.

Project titles are collected literally, with request phrases such as `i Want to add`
removed. A professional profile paragraph is retained as summary text and cannot create
project titles from technology categories. Descriptions supplied before a title are
staged until the project is named. Clear description answers remain verbatim and collect
only explicitly mentioned technologies. The server tracks the active project entry and
checks each project's own completeness rather than combining answered fields across
different rows. Model context includes that active entry. Existing-CV editing continues
to use its separately scoped draft workflow.

When multiple real projects are ambiguous, the assistant lists their names and numbers.
A number or unique name applies the queued details to that entry; the description need
not be repeated. Invalid selections preserve the queue. Selection changes the target,
not its title, and unrelated projects remain unchanged.

Unsaved creation chats with the exact evidenced profile-split error recover on owner
resume, draft inspection or the next turn. Recovery requires a prior literal title and
the same multi-project extraction still present in state; edited entries, saved CVs,
other owners and unverified histories are excluded. It separates the profile, restores
the intended title, and recovers descriptions/technologies explicitly supplied in the
subsequent blocked project turns. Matching undo snapshots and review/progress metadata
are updated under a row lock. Original messages are retained. A read-only preview using
the actual affected history found this proof, proposed one `Ai base interview plateform`
entry and advanced to certifications. That preview performed no application writes.

Manual check: refresh the dashboard and resume the same chat. Inspect collected details
to confirm one intended project, a separate professional summary, the latest supplied
description and its explicitly stated technologies. Continue with certifications. On
a new chat, try the original query-string portfolio URL, informal degree, title request,
profile paragraph and detailed description. The direct transcript journey now requires
zero model calls. No schema migration or dependency change is needed.

Verification: all **269 Django tests** passed on SQLite (116.355 seconds) and PostgreSQL
(114.379 seconds). After the responsibility-sentence case found in the browser journey,
all **150 final chatbot regressions** passed on both databases, including the 18 new
project-flow/evidence tests. All **105 JavaScript tests** and all **15 Chromium journeys**
passed. The complete Talha browser journey asserts zero Qwen calls for its explicit
answers and verifies the saved CV contains one intended project and a separate summary.
The other new browser journey exercises numbered selection and continued technology
collection without changing the other project. System checks, migration-drift checks
and `git diff --check` passed. Live application inspection/recovery preview was read-only;
automated suites used isolated records and mocked AI providers.

## Follow-up fix: grouped education answers and natural completion

The shared transcript showed `I completed Bs Software ENgineering from University
of Mianwali` losing its university, while provider-generated dates triggered evidence
warnings. The next `start date 2022 end 2026` answer reached the university's scalar
fallback and became its name. A specialized, bounded parser now handles qualification,
explicit specialization, institution, labeled start/graduation dates, date ranges,
named months, and simple graduation sentences before scalar extraction or Qwen.
It combines stated fields in one entry and asks only for missing details. A bare
qualification does not invent a specialization, and a year does not invent a month.
Multiple or ambiguous entries still require identification. Academic validation also
rejects date-only university names from provider output. A follow-up containing dates
does not clear a still-unanswered institution correction.

For example, the degree answer collects the degree, Software Engineering and University
of Mianwali; `start date 2022 end 2026` then adds both years without replacing the
university. `start date September 2022 end June 2026` collects `2022-09` / `2026-06`.
Year-only answers remain intact in collection/source history; the existing M10 save
format requires month precision and retains its existing warning/omission behavior
for year-only dates. No month is filled in silently. Use actual `YYYY-MM` dates when
known and needed in the saved CV.

Existing unsaved creation drafts with a history-proven date-as-university error recover
on resume/draft inspection. A single matching degree answer can restore its university;
contradictory accepted universities, later corrections or multiple entries require
clarification. Undo/progress/review decisions are updated, while saved CVs and message
history remain unchanged. Previously combined `English urdu saraiki hindku` entries
also recover through the existing history-based language repair.

After a certificate or other saved-CV edit, the follow-up explicitly says to enter
`finish` or `nothing else` when done. `No other thing`, `nothing else`, `no thanks`,
and similar exact completion phrases finish at review without calling Qwen. An early
finish attempt cannot turn into a degree or bypass missing interview details. Saving
remains an explicit separate action.

Other concrete extraction mistakes in this transcript are covered too: `Frontend
Developer at bitech` separates job title/company; the highlighted React/Next/Node list
retains `Next.js` and `Node.js`; all four stated languages remain separate; and `Giki
ai advance bootcamp issue date agust2026` separates the title and explicit `2026-08`
issue date. The self-harm utterance now pauses CV collection for a supportive safety
check, with no facts or interview progress changed; quoted project/workplace content
is excluded from that deterministic check.

Restart Django if needed and refresh the dashboard. Resume the same unsaved chat to
inspect recovered education; use **Correct collected details** if already completed.
For a new interview, try the grouped degree answer, labeled dates and certificate
editing sequence above. No schema migration or new dependency was introduced.

Verification: the complete **251-test Django suite passed on SQLite** (129.266 seconds)
and **PostgreSQL** (140.427 seconds). After the final conservative recovery guard and
its additional regression, **37 education/optional-section tests passed again on both
databases**. All **105 JavaScript tests** and **13 Chromium journeys** passed, including
grouped education through canonical CV saving and certificate editing followed by
`No other thing`. System checks, migration-drift checks and `git diff --check` passed.
AI providers were mocked; application records were not changed by these tests.

## Follow-up fix: AI conversation startup and Retry

The chat-session endpoint rejected an older `junior` selection with the same
102-byte HTTP 400 response reported by the user. A read-only check of the running
dashboard confirmed it already served the updated canonical choices, so an older
open page remained a possible source of the request. Chat startup also discarded
the API's validation message, showing a connection failure instead. Its Retry handler
lost the original CV selections and an explicitly requested conversation ID.

Both manual and AI input serializers now accept the two former dashboard choices:
`junior` and `mid` normalize to canonical `experienced`. A junior AI session retains
its `junior` question profile. M10 and stored CV documents retain their existing enum;
unrecognized values remain validation errors. No saved records are rewritten.

An invalid startup request now returns to the creation form with the actual field
error and retained values. Message-validation errors preserve the input and allow
correction without presenting a network Retry button. Retry for a failed startup
retains CV name, role, level, template and explicit resume ID. Successful startup
closes the creation form; logout/reset discards its pending retry context.

Restart Django if needed, refresh `/dashboard/` with Ctrl+Shift+R, and start Create
with AI again. A valid initial request creates a conversation with HTTP 201 before
any Qwen call. No schema migration is required. The new regressions first reproduced
both legacy-value rejections and all four frontend startup/error/retry failures.

Verification: all **228 Django tests passed on SQLite** (110.774 seconds), the
**5 creation regressions passed on PostgreSQL**, all **105 JavaScript tests** passed,
and all **11 Chromium journeys** passed. The new browser journey submits an old Junior
choice, receives a real invalid-template error, corrects it, simulates one temporary
startup failure, retries, and verifies persisted name/role/template/career/profile
with one conversation and no saved CV. System checks, migration-drift checks and
`git diff --check` passed. Only isolated test records and mocked AI providers were used.

## Follow-up fix: Create CV returns HTTP 400

The shared manual/AI creation form offered `junior` and `mid`, while M2 and M10
accept `fresher`, `experienced` and `other`. Reproducing the old `junior` request
produced the same 102-byte HTTP 400 response shown in the server log. Its wrapped
field error was hidden because the dashboard only understood string error messages.

The form now renders its career choices from the shared `CareerLevel` enum:
**Fresher**, **Experienced**, and **Other**. The API client displays wrapped field
validation and canonical document errors with readable labels, retaining form values
for correction and retry. Existing contracts and saved documents are unchanged.
Refresh `/dashboard/` with Ctrl+Shift+R after the development server reloads; no
migration is needed. The initial 401 followed by refresh/retry HTTP 200 is successful
token renewal and is unrelated to this validation failure.

Verification: **42 targeted Django tests** and **101 JavaScript tests** passed.
The new API regressions submit every rendered career/template combination and start
AI sessions for every rendered career value without creating empty saved CVs.
Nine existing Chromium journeys passed; the new tenth journey passed after correcting
its test-only assertion to inspect persisted initial chat state. It verifies a real
template-validation error, successful Experienced manual creation after retry, and
Other AI creation. System checks, migration-drift checks and `git diff --check` passed.
No application records or live AI providers were used during verification.

## Follow-up fix: language proficiency, summaries and late certificates

The transcript exposed three separate routing mistakes. A proficiency suggestion was
prepended to the next summary question instead of becoming a pending question; the
summary fallback stored the entire combined answer; and creation-mode section requests
handled additional projects/education/experience while ignoring certificates at review.

Language proficiency now has its own optional interview step. `English urdu Hindi`
becomes three named entries, with no invented proficiency. Commas, `and`, semicolons
and known compound language names are supported. Unpunctuated lists are split only
when every name is recognized; unknown compound names remain intact. An answer such
as `English professional, Urdu native` fills proficiency. `skip` or `keep these
unspecified` keeps the language names and moves to the summary question. Partial
proficiency answers retain the remaining languages as pending. Finishing can leave
only this optional proficiency step unspecified; required questions still block finish.

Explicit combined answers such as `keep these unspecified and summary is Software
Engineering graduate ...` apply the unspecified choice and store only the summary
body. Ordinary summary prose is preserved. Section commands are recognized before
generic CV questions and scalar extraction: `i want to add certificate`, the reported
`i wan to add certificate`, `Can I add a certificate?`, and additional-certificate
requests open the certification question. The collected title is appended and the
interview returns to review. Saved-CV editing supports the same requests. Exact finish
typos `fnish`, `finsh`, and `finsih` use the normal guarded completion path, without
sending those words to Qwen or generating unrelated evidence warnings.

Unsaved creation sessions, including completed drafts, recover the two known stored
answer bugs when resumed, inspected or reopened. Recovery requires matching original
user messages before splitting a combined language entry or removing the explicit
unspecified/summary instruction. It also cleans the undo snapshot and invalidates old
review decisions. Original history, unrelated facts and saved CVs are preserved. Owner
checks and row locks protect the repair. It is a lazy data repair; no schema migration
or application-wide rewrite is required.

Manual check: restart Django, refresh the dashboard, and resume the same chat. Inspect
the draft to verify separate English/Urdu/Hindi entries and the clean summary. If it
is already completed, select **Correct collected details**, send `i want to add
certificate`, supply the real certificate title, then `finish`. Review and save.
For a new interview, verify proficiency and summary appear on separate turns; also
try the original combined answer to verify both parts are handled correctly.

Files: `chatbot/services/section_answers.py`, `optional_section_recovery.py`,
`message_routing.py`, `question_engine.py`, `local_extractor.py`,
`conversation_service.py`, `chatbot/views.py`, `tests/test_chat_optional_sections.py`,
and the existing system/browser regression suites. Provider calls remain mocked in
automated verification; these explicit messages require no Qwen or Gemini calls.

Verification: all **223 Django tests passed on SQLite** (112.862 seconds) and
**223 passed on PostgreSQL** (115.558 seconds), including the 13 new regression tests.
All **99 JavaScript tests** and **9 real Chromium journeys** passed. The new browser
journey reproduces the exact combined answer, late certificate request and `fnish`,
then verifies the saved canonical summary, three languages and certificate. Django
system checks, migration-drift checks and `git diff --check` also passed. No new
migration, dependency, live provider call or application-record rewrite was required.

## Follow-up fix: direct abusive replies

The phrases `o shutup`, `what a fuck`, and `are you idiot` bypassed the original narrow
conduct patterns and reached the short-answer parser, which stored them as company,
job title and responsibilities. The new conduct check runs before every field parser.
It recognizes direct dismissals, second-person insults, threatening statements and
standalone profane exclamations with common spacing/interjection/punctuation variants.
Quoted workplace incidents and ordinary criticism are still eligible input. Unclear
questions or messages addressing the assistant go to local interpretation before they
can be treated as literal CV values.

Clear abusive replies now produce a brief professional boundary, preserve the current
question, and return empty CV updates with zero Qwen/Gemini calls. This is covered at
company, role, responsibilities, personal, education, projects, skills, certification
and summary questions, including saved-CV editing.

Recovery also applies to active, unsaved interview drafts with matching user/assistant
history. On resume or the next turn, fields proven copied from standalone hostile
utterances are excluded from accepted experience, including their undo snapshot.
Question/completion/field status is rebuilt from the remaining facts, while personal
information, projects and original message history are preserved. Ownership and row-lock
checks protect recovery; stale clients must reload the updated session.

Restart Django and refresh the dashboard. Reopen the same chat from Resume AI chat.
For an affected draft, expect the experience question again. Supply real experience or
say `no experience` as a fresher. Repeating any of the three reported abusive phrases
should keep the same question and leave collected facts unchanged.

Files: `chatbot/services/content_handling.py`, `message_routing.py`,
`conversation_service.py`, `chatbot/views.py`, `tests/test_chat_conduct.py`, and
`tests/browser_e2e.py`. No model/schema change, dependency or migration was introduced.

Verification: the 12 new conduct tests and all 80 targeted chatbot regressions passed;
the real browser suite passed 8 journeys; all 99 JavaScript tests passed. The conduct
tests were first executed against the previous implementation and reproduced the
reported false progression. The complete Django suite passed **210 tests on SQLite**
(110.623 seconds) and **210 tests on PostgreSQL** (111.931 seconds). The 12 new tests
are included in those totals. Django system checks, migration-drift checks and
`git diff --check` also passed. No migration is required.
No live provider calls or application-record changes were made during these checks.

## Follow-up fix: sequential education answers and duplicate errors

The manual transcript exposed a gap in the original tests: separate degree and university
answers created two education fragments. Later anonymous answers could not be merged, while
field flags incorrectly advanced even when the merge failed.

- New collection-context merging completes the single current entry using its accepted identity.
  Distinct entries and explicit additional-entry drafts remain separate. Ambiguous merges retain
  both data and progress instead of marking rejected values collected.
- An affected active interview can repair the exact degree-then-university fragmentation pattern
  on its next message when persisted history confirms it. Explicit additional entries, grouped
  entries and conflicting facts are not automatically merged. Previously rejected field-of-study
  text is asked for again rather than silently promoted into accepted data.
- Direct graduation answers such as `2026`, `2026-06`, `I graduate in 2026` and
  `I am graduated in 2026` work without a model call. Date validation remains in place.
- Validation feedback is shown once in the assistant bubble. The separate error area remains
  available for failed requests/provider outages.

No database schema change or migration is required. Restart Django and hard-refresh the
browser. Resume the affected chat and answer the pending graduation question, for example
`2026-06`. If field of study is requested again, enter it once; the earlier degree, university
and contact details are preserved.

Files: `chatbot/services/collection_memory.py`, `conversation_service.py`, `message_routing.py`,
`m9_dashboard/static/m9_dashboard/js/dashboard.js`, `tests/test_chat_collection_regressions.py`,
`tests/dashboard_crud.test.cjs`, and `tests/browser_e2e.py`.

Follow-up verification: **198 Django tests passed on both SQLite and PostgreSQL**, **99 JavaScript tests passed**,
and **7 browser journeys passed**, including the manual transcript. Six added backend tests
cover sequential education/experience, common graduation phrasing, recovery, distinct-entry
protection and unchanged progress after ambiguity. Two added JavaScript tests verify single
validation display and retained provider-error retry behavior. Django checks, migration-drift
checks and `git diff --check` passed. No live model calls or application-record repairs were
performed by these tests; recovery happens when the affected user next submits a message.

## Assessment and baseline

The existing implementation already had JWT ownership checks, persistent M5 sessions,
optimistic concurrency, M2 chat import/versioning, seeded existing-CV editing, M6 structured
Gemini services, and M9/M11 resume/save UI. Those services remain in place.

The collection fallback used M5 Gemini, personal fields were accepted without conversational
validation, question order was shared across career levels, and the saved-CV adapter could
mistake a changed entry identity for a new entry. The old normalizer also allowed a provider's
completion flag to finish an otherwise collected interview without a separate user finish.

Before implementation, the existing SQLite suite passed **130 tests**, and the seven existing
JavaScript files passed (88 individual tests). The initial sandboxed PostgreSQL attempt could
not connect. PostgreSQL was subsequently verified outside the network sandbox against an
isolated test database; do not describe that later run as a pre-change baseline. Browser
baseline journeys were not rerun before modification.

## Architecture and boundaries

1. M5 normalizes whitespace and deterministically identifies clear questions, off-topic requests,
   hostile commands, corrections, skips, progress, undo and finish.
2. Simple field answers and skill lists are extracted without a provider request.
3. Ambiguous natural language uses **server-side local Qwen**, not Gemini. It receives the active
   question, role/profile, and a bounded relevant section or active entry, without user/CV IDs
   or the whole conversation history.
4. A strict internal JSON extraction schema derives partial field definitions from M10. Unknown
   keys/enums and malformed JSON are rejected. Literal-fact evidence checks reject unmentioned
   skills, employers, degrees, contact values, language proficiency and inferred dates/months.
   Python validators then run on both deterministic and model-derived values.
5. Valid siblings enter PostgreSQL conversation state; invalid/uncertain values receive targeted
   clarification. The deterministic question engine selects the next field.
6. Explicit user finish builds the draft through the existing M2 chat adapter and validates M10.
   A provider cannot mark the session complete. The user can inspect or reopen an unsaved completed
   draft for corrections.
7. Optional final review uses the **existing M6 provider factory**, with explicit external-processing
   approval and a fingerprint of the draft the user inspected. Personal/contact fields are omitted.
8. Review results remain proposals. The user selects accepted changes or rejects all; only the
   ordinary M2 Save action creates/updates a CV and its version history.

M10 is unchanged. There is no second persisted CV schema, chatbot model/table, CV persistence
service, queue, Docker setup, Redis requirement, frontend framework or replacement dashboard.
Legacy provider clients and prompt helpers remain available for compatibility but are not the
active collection path. Existing M6 endpoints are unchanged.

## Configuration and local Qwen

The local environment contained older `QWEN_BASE_URL` and `QWEN_MODEL` settings for an unavailable
OpenAI-compatible service on port 8001. Those settings and `.env` were preserved. Active chat
uses dedicated settings to avoid reinterpreting that older configuration:

```dotenv
CHAT_LLM_PROVIDER=qwen_local
CHAT_QWEN_BASE_URL=http://127.0.0.1:11434
CHAT_QWEN_MODEL=qwen3.5:4b
QWEN_TIMEOUT=60
FINAL_REVIEW_PROVIDER=gemini
```

They have usable defaults and are documented in `.env.example`. Gemini credentials/model remain
under existing M6 settings. No credentials are logged or reproduced here.

Ollama's `/api/tags` returned `qwen3.5:4b` and `qwen3:8b`. The client uses native `/api/chat`,
`stream:false`, `think:false`, JSON Schema in `format`, temperature 0, an 8192 context budget
and 1800 output tokens. It disables proxy environment inheritance and performs no automatic
retry, model download, cloud fallback, browser-to-Ollama request, tool call or database write.
The implementation follows the [official Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
and [structured output documentation](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx).

Timeouts, missing models, stopped Ollama, malformed/truncated responses and unsupported output
return safe errors without committing a partial turn. Simple deterministic fields continue
working during a Qwen outage. The new opt-in `manage.py qwen_smoke` command uses synthetic facts,
measures each inference, and never writes a CV or calls Gemini.

## Python validation and conversation behavior

- **Email:** Django EmailValidator, surrounding whitespace trimmed, case/content preserved;
  non-.com domains accepted. An incomplete `name@` receives a specific explanation. Format
  validation makes no claim about inbox existence.
- **Phone:** pinned `phonenumbers==9.0.41`, explicit international country codes and Pakistani
  national mobiles; unsupported national formats request a country code. Formatting is preserved.
- **Name:** Unicode letters/combining marks, spaces, common apostrophes, hyphens and initials;
  single names accepted; numeric/empty values rejected without AI.
- **URLs:** Django HTTP/HTTPS URLValidator; unsafe/incomplete schemes rejected.
- **Dates:** year or YYYY-MM source precision, real month ranges, chronological ordering and
  current/end-date contradictions. M10 dates remain YYYY-MM or blank. Existing adapter warnings
  explain when an unknown month cannot be saved, while the source year stays in conversation state.
- **Grades:** scale-aware fractions/percentages; impossible/negative scores rejected, bare numeric
  grades request a scale. Grades remain optional; neutral omission guidance is available.
- **Skills:** list/prose/space-separated known skills, alias normalization and equivalent duplicate
  removal; C++, C#, Node.js and .NET preserved. No arbitrary ten-skill ceiling. M10's actual
  100-item ceiling is enforced with a clarification and retained source message.
- **Education/experience/projects/certifications:** sparse fields are validated before merging.
  Supported optional source details remain in conversation state where M10 lacks a field.
  Existing M2 conversion still owns canonical job_title/highlights/date/proficiency mapping.

State tracks accepted data, field status, invalid fields, uncertain fields, skipped sections,
current question, profile, undo snapshot, source overflow, selected displayed experiences,
existing CV/version and targeted proposals. Legacy sessions upgrade lazily; messages remain
persisted. Up to 20 UUID request receipts prevent repeated submissions from appending turns.
A changed session timestamp yields 409 instead of overwriting newer state.

CV-related help preserves the current question and does not store the question as a qualification.
Clear weather/sports/joke/unrelated coding requests receive a brief redirect without advancing.
Direct insults, threats and database-instruction attempts receive a professional boundary.
Workplace incidents, quoted insults and ordinary criticism are eligible CV input rather than
being rejected by a profanity substring blacklist. More ambiguous wording uses local interpretation.

## Adaptive questions and recommendations

M10 stores `fresher`, `experienced`, `other` (or blank). Student is stored as `other`; student,
junior, senior and executive question profiles stay internal. Existing stored metadata is preserved.

Students/freshers start with education, skills and projects. Experienced profiles prioritize
employment. Senior responsibility questions ask about ownership, mentoring and technical decisions;
executive questions ask about leadership scope, strategy and business impact. Experienced users
who report no employment receive one clarification, can confirm absence, and get a suitability
warning. Freshers can skip experience without repeated requests. One employer/project/certificate
is accepted; certifications and achievements can be skipped entirely.

Long lists trigger relevance/readability guidance, not silent deletion. Skills stay in the
canonical array; category organization is suggested for presentation. Extra experiences remain in
source state; users select up to five with `select experiences 1, 2, 3, 4, 5` before saving. Projects
and certifications retain all entries unless the user chooses otherwise. Length guidance is an
estimate; no one-page PDF guarantee or fabricated rendering measurement is made. Role suggestions
mention technologies only conditionally and never add them to the CV.

## Existing-CV editing and final review

Continue with AI seeds the existing saved JSON/template/metadata/version and asks what to change.
It does not restart the interview. Personal corrections, skills, named skill removal, summary,
projects, experiences, education, certifications, achievements and languages use the existing
editing state and M2 adapter. New project drafts retain explicit-add behavior. Language proficiency
is optional and is never inferred from the language's name.

Targeted institution/degree/job-title/project-description changes resolve a saved entry. Multiple
possible targets require selection; changing an institution updates that entry instead of appending
an incomplete degree. Unrelated sections are preserved. Named skill removal is a reviewable
proposal; ambiguous removals do not execute. Undo restores the preceding accepted state.

M2's expected_version and owner checks remain authoritative. The UI supplies the version initially
loaded for existing-CV edits, rather than silently choosing a newer editor version. Conflicts keep
the old proposals and offer a fresh chat on the latest CV; the earlier chat remains discoverable.
Saved completed drafts cannot be reopened for replay: Continue with AI creates a fresh editing
session. Unsaved completed drafts can reopen for corrections before review/save.

Final review returns `overall_feedback`, `suggestions`, `proposed_changes`, `missing_information`
and `warnings`. Successful reviews are stored in existing conversation JSON and reused by owner,
full draft fingerprint, provider/model configuration and response contract revision. PostgreSQL
owner/session locks serialize concurrent final reviews. A changed draft/configuration needs a fresh
approval. Failed calls are retryable; exactly-once network delivery is not promised.

Only existing summary, experience highlight and project description/highlight strings can be
proposed for rewriting. Exact original text, allowed target paths, duplicate paths, new numbers,
new named facts and conservative lexical grounding are checked. New facts must remain questions
or suggestions. These checks deliberately reject some otherwise valid paraphrases. Approval of
selected indexes changes the pending proposal, not a saved CV. Rejected suggestions are never
saved. A Gemini failure leaves the ordinary validated Save path available.

## API contracts and changed files

Existing create/list/detail/message endpoints and their response fields remain compatible. Message
input optionally adds `request_id` and `expected_updated_at`. M5 message responses still contain
exactly `assistant_message`, `intent`, `section`, `cv_updates`, `next_action`; internal controls
are not exposed. Existing completion behavior is intentionally tightened to require explicit finish.

New owner-scoped endpoints under `/api/chat/sessions/{uuid}/`:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `draft/` | GET | Canonical draft and fingerprint; no AI call |
| `reopen/` | POST | Correct an unsaved completed draft |
| `final-review/` | POST | Explicit consent + inspected fingerprint; optional Gemini review |
| `final-review/decisions/` | POST | Approve selected server proposal indexes, or reject all |

Files changed/added specifically for this request:

| Files | Purpose |
| --- | --- |
| `chatbot/services/field_validation.py` | Central contact/name/URL/date/grade/section validation and skills |
| `chatbot/services/extraction_guard.py` | Evidence checks on model-proposed facts |
| `chatbot/services/message_routing.py` | Deterministic intents, corrections, skipping, content handling and presentation |
| `chatbot/services/question_engine.py` | Profile-driven progression and relevance/length guidance |
| `chatbot/services/qwen_client.py` | Native Ollama client, strict derived extraction contract, bounded context |
| `chatbot/services/conversation_service.py` | Integrate routing/validation/state, explicit completion, receipts/concurrency |
| `chatbot/services/state_manager.py` | Delegate next-question selection while retaining existing state transitions |
| `chatbot/services/{conversation_router,local_extractor,response_normalizer,prompt_builder}.py` | Retained compatibility helpers; clarify inactive/neutral provider documentation |
| `chatbot/{views,serializers,urls}.py` | Optional input controls, safe errors, draft/reopen/review/decision endpoints |
| `chatbot/management/{__init__,commands/__init__,commands/qwen_smoke}.py` | Explicit synthetic local smoke command |
| `ai/services/final_review.py` | M6 provider reuse, privacy minimization, proposal checks and persistent reuse |
| `cvs/chat_import.py` | Accepted snapshot, targeted patches, removals, display selection and approved rewrites through M2 |
| `config/settings.py`, `.env.example`, `requirements.txt` | Dedicated local chat configuration and phone validation dependency |
| `m9_dashboard/static/m9_dashboard/js/dashboard.js` | Draft/review controls, consent, decisions, correction, original version, retry metadata |
| `m9_dashboard/templates/m9_dashboard/dashboard.html` | Existing chat UI extended with review/edit/skip/undo/progress controls |
| `tests/test_conversation_intelligence.py` | New offline unit/integration/lifecycle/provider/approval regressions |
| `tests/{test_chatbot,test_existing_cv_chat,test_system_audit}.py` | Switch collection mocks to Qwen and require explicit finish; preserve prior assertions |
| `tests/dashboard_crud.test.cjs`, `tests/browser_e2e.py` | Consent/review/correction/conflict and saved-CV language journeys |
| `README.md`, `docs/FINAL_SYSTEM_AUDIT.md`, this report, `docs/QWEN_SMOKE_RESULTS.json` | Current behavior, configuration, verification and manual guide |

## Original implementation verification (before the follow-up fix)

The following results were recorded from completed runs. Tests use temporary media, isolated
databases and mocked providers; the opt-in local smoke test is reported separately. No Gemini
credentials or live Gemini service were exercised.

| Check | Executed result |
| --- | --- |
| Django full suite, SQLite | **192 passed**, 108.104 seconds |
| Django full suite, PostgreSQL | **192 passed**, 117.545 seconds; isolated `test_...` database |
| New chatbot tests included in each full run | **62 passed**; these are included in 192, not additional tests |
| JavaScript, seven files run individually | **97 passed**, zero failures; includes nine added chat/review/retry checks |
| Real Chromium → HTTP → Django → isolated database | **6 journeys passed**, 18.367 seconds; AI mocked |
| Django system check | No issues |
| Migration drift | `makemigrations --check --dry-run`: no changes detected |
| Installed dependency consistency | `pip check`: no broken requirements |
| Changed tracked-file whitespace | `git diff --check`: clean |
| Live local Ollama | Installed primary model verified; **7/7 structured examples and expected-fact checks passed** after prompt improvements |
| Targeted live project-title guard recheck | Passed: Django/PostgreSQL retained, generic title withheld for confirmation, **24.763 seconds** |
| Live Gemini | **Not run**; all Gemini verification is mocked |

The six browser journeys cover authentication/profile/refresh/logout; manual CV editing,
rendering/download/history/CRUD; AI creation/resume/completed-draft correction/consent/approved
review/M2 save; DOCX import/review; existing M6 rewrite rejection/approval; and adding Urdu to an
existing CV with the same ID and one new version. The browser fixtures never contact Gemini
or Ollama. PDF/DOCX regression tests use the actual exporters.

Live local structured-extraction results (synthetic data only):

| Message | Seconds | Accepted facts / classification |
| --- | ---: | --- |
| My name is Ali Khan. | 22.492 | Name extracted |
| My email is ali@gmail.com. | 23.780 | Email extracted |
| I worked at ABC for six months. | 28.368 | ABC retained; no invented job title, employment type or technologies |
| I made a Django project using PostgreSQL. | 26.208 | Technologies retained; subsequent title-guard recheck asks for actual project title |
| I want to add Urdu to my CV. | 23.560 | Urdu retained, proficiency unspecified |
| Change my email to ali@outlook.com. | 23.680 | Corrected email extracted |
| Who won the cricket match? | 22.710 | Off-topic; no CV updates |

The seven-case inference range was **22.492–28.368 seconds**, median **23.680 seconds** on this
machine during verification. This is too slow for every form answer, which is why ordinary
names/emails/lists/known corrections bypass Qwen. It is an observed measurement, not an
idle-machine benchmark or a guaranteed response time.

The first exploratory local pass returned structured JSON for all cases but omitted an email,
misclassified a project statement and inferred unsupported employment/proficiency details. Those
findings led to explicit extraction examples, stricter uncertainty instructions and stronger
literal-fact guards. The subsequent seven-case pass succeeded. A generic source-derived project
label was then guarded separately and rechecked successfully. Raw synthetic measurements and
the final recheck are preserved in [QWEN_SMOKE_RESULTS.json](QWEN_SMOKE_RESULTS.json).

No live failure was induced in an application session. Timeout/unavailable/malformed-response
state preservation is covered by offline integration tests; the live smoke command itself
makes no database writes. No deployment, Git commit or application migration was performed.

## Provider calls by workflow

| Workflow | Local Qwen | Gemini |
| --- | --- | --- |
| Obvious invalid field | 0 | 0 |
| Direct valid field / supported skill list | 0 | 0 |
| Ambiguous natural language | 1 local request when needed | 0 |
| Clearly off-topic / direct hostile message | 0 | 0 |
| Existing CV edits | Only when deterministic interpretation is insufficient | 0 |
| Draft inspection / correction / decisions / M2 save | 0 | 0 |
| Explicitly approved final review | 0 | One successful uncached M6 request; subsequent unchanged approved draft uses stored result |

Provider failures may require a controlled retry; a successful provider response lost before
persistence cannot be guaranteed exactly once. Automated assertions check call budgets and
failure preservation. The live smoke command intentionally forces seven local provider requests
to inspect the model, including inputs that ordinary chat handles without a provider.

## Remaining limitations

- Deterministic syntax/evidence checks cannot prove every semantic statement. Local understanding
  can still need clarification, especially for translations, ambiguous edits and unusual phrasing.
  Literal checks prefer confirmation over silently accepting a newly inferred qualification.
- Professional-help responses cover common CV questions; this is not an unrestricted general
  assistant. Multilingual interpretation relies on local Qwen; the UI/CV language is not replaced
  with an unsupported M10 language-setting field.
- Employment type, project contribution and current-study status can stay in source state but
  have no dedicated M10 fields. M10 permits one project URL; additional source facts do not
  introduce new canonical fields. Unknown date months remain blank with explicit adapter warnings.
- Skill category organization is guidance/presentation; no unsupported grouping object is persisted.
  Length is guidance, not a measured PDF page count. No new renderer pagination estimator was added.
- Final rewrite grounding is conservative and can reject good synonyms. Semantic quality needs
  user review; malformed/unsupported reviews fail safely and do not block saving without AI.
- Successful reviews are persisted in PostgreSQL chat state, unlike M6's existing process-local
  analysis cache. SQLite functional tests do not establish PostgreSQL row-lock concurrency;
  dedicated multi-worker load/chaos testing was not performed.
- UUID message receipts retain the last 20 submitted IDs. Clients omitting IDs retain legacy
  timestamp/concurrency behavior. Arbitrarily old retries are not an unlimited exactly-once ledger.
- An ambiguous edit/removal requires identifying the entry; arbitrary destructive model commands
  are not executed. A version conflict requires reviewing the latest CV; no automatic rebase
  overwrites editor changes.
- Real Gemini remains untested. Broader deployment/security limitations in the historical audit
  are outside this chatbot change and are not claimed resolved.

## Manual testing guide

1. Install updated requirements in the existing virtual environment. Restart Django. No schema
   migration was introduced. Existing normal project migrations still apply. Defaults select
   installed `qwen3.5:4b`; verify `ollama list` locally and keep Ollama on a private interface.
2. Open `/dashboard/`, hard-refresh, sign in, select Create with AI, a target role, fresher and a
   template. Confirm a chat starts without creating an empty saved CV.
3. Supply `Ali Khan`, then an invalid email such as `333f.com`: expect an inline explanation and
   the same pending email question. Supply `ali@university.edu.pk`, a Pakistani/international
   phone and location. Skip optional professional links. No AI calls are needed for those fields.
4. Supply degree/institution/field/graduation date, skills such as `Python Django DRF MySQL Git`,
   a project name, `It manages employees.`, and `Django, PostgreSQL`. Say no experience as a fresher.
   Skip certifications/achievements or supply confirmed details. Languages and summary can be
   entered or skipped. A grouped sentence can instead supply several fields through local Qwen.
5. Ask `Can I include my final-year project instead?`, `Who won the cricket match?`, and `You are
   stupid.` while collecting: help/redirection should retain accepted information/current question.
   A workplace incident or quoted text should not be treated as abuse automatically.
6. Use Show collected information. Correct email, undo once, and correct it again. Finish when
   ready. Review collected draft. Use Correct collected details to reopen an unsaved draft;
   finish again after making a correction.
7. Optional Gemini review requires the visible consent checkbox. With an authorized configured
   Gemini account, inspect its proposals, approve selected wording or reject all, and then Save.
   Repeating the same approved unchanged review should reuse the stored result. Save remains
   available if Gemini is unavailable. **Live Gemini use is a separate user action; it was not
   performed for this implementation.**
8. Save without review too. Confirm the dashboard card, editor, preview, PDF/DOCX and version
   history. Template/metadata/contact/source facts should match confirmed information.
9. Reopen Continue with AI on that saved CV. Say `I want to add languages`, then `Urdu native`
   or `English professional, Urdu native`, and finish/save. Verify the same CV ID, one additional
   version and unchanged unrelated sections. Try `Add C++ to my skills`, `Remove Java from my
   skills`, `Change my university to FAST`, or a project-description correction. Multiple education
   entries should prompt for an entry number before changing the institution.
10. Change the saved CV in the editor while its chat is open. Saving the stale chat should show
    a conflict, preserve proposals, and offer Open latest CV in a new chat. The old chat remains
    available through Resume AI chat. Never recover by silently replacing newer editor changes.
11. Stop Ollama temporarily: direct validation still works; an ambiguous natural-language turn
    fails with a retryable message and unchanged accepted state. Restart it and retry.
12. Run offline suites and the optional synthetic smoke command:

```bash
.venv/bin/python manage.py test --settings=config.test_settings --noinput
for suite in tests/*.test.cjs; do node "$suite" || exit 1; done
.venv/bin/python manage.py qwen_smoke --output /tmp/qwen-smoke.json
```

For PostgreSQL, pass the existing local connection privately as `TEST_DATABASE_URL`; Django
creates its separate `test_...` database. Browser reproduction uses
`RUN_BROWSER_E2E=1 E2E_VENDOR_DIR=/tmp/cv-audit-vendor` with the existing Chromium helper and
locally cached copies of the existing Alpine/Tailwind libraries. All browser AI is mocked.
