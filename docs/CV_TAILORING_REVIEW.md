# Saved-CV tailoring review

`POST /api/ai/tailor/` reviews the saved CV in one provider request. Its proposals
never save the CV. The dashboard applies only selected changes through the
existing M2 API with `expected_version`.

## Partial results

A `200` response can contain only the proposals that passed validation. The
server excludes rewritten metrics, unsupported named facts, added maintenance
duties, and changed architecture/leadership/assistance claims. It keeps valid
proposals from other fields. Invalid paths, duplicate paths and stale original
text invalidate the response. If every proposed rewrite fails, the existing
`502` / `factual_validation` response remains in place; failed generation is not
cached.

Partial responses use the existing `warnings: string[]` field. The first message
explains partial filtering; subsequent messages identify the field and reason
without exposing the rejected rewrite. The UI collapses these under “Why …
suggestions were left out.” The review summary and status report the accepted
count, rather than endorsing the discarded provider proposals. Identical-text
proposals do not become saveable changes.

Messages are produced from server-known field paths and fixed reason text.
Provider-supplied warning fields are rejected. Cached messages are checked
against those same allowed messages before reuse. Logs contain fixed codes and
paths, not candidate or provider text.

## Advice-only results

A successful review can return `changes: []`. This means it has no proposed
wording to save, even when it supplies useful advice. It does not establish
that every possible improvement has been exhausted.

The response's `summary` is review feedback, not the CV's professional summary.
The provider prompt and response schema state this explicitly. Empty reviews
receive a server-controlled no-changes message, so a copied or misplaced CV
profile is never presented as an unsaveable improvement. The client applies
the same display rule. Text in review feedback is never silently promoted into
a CV edit; all rewrites need an explicit path, original and replacement.

The UI labels these results “Advice for your CV” / “No changes to save” and
hides the save button. “Polish one part” opens the existing selected-text mode;
it makes no provider request until the user chooses “Suggest a rewrite.” The
normal comparison and versioned save then require explicit approval. Users can
also close the advice without changing the CV.

Results display the requested review focus and, when different, the CV's saved
target. These are allowed to differ for a career transition. Neither reviewing
for a different job nor approving a wording change rewrites the saved target
metadata. A reused cached review is identified on screen; repeated clicks with
unchanged data do not automatically make extra provider calls.

## Grounding checks

Equivalent forms include thousands separators, spaces or words for percentages,
and small number words before supported quantities (for example `over seven
years` and `over 7 years`). Values, occurrences, percentage signs, common time
units and quantity bounds remain protected. `over 7 years` cannot become
`7 years`, `at least 7 years`, or `over 7 months`.

The bounded technology glossary recognizes AWS / Amazon Web Services,
IaC / Infrastructure as Code, CI/CD expansions, Kubernetes / K8s and EKS
expansions, in addition to existing Node.js and REST API normalization. The
original entry must contain the equivalent technology. Job requirements and
another employer or project's facts do not establish entry-level evidence.

Prompts include per-field numbers and responsibility terms to preserve. They
request useful wording improvements without a required change count. An
`Architected` source cannot become `Built and maintained` unless its actual
responsibility is retained and the original also supports maintenance.

These are conservative lexical checks, not a semantic proof of every sentence.
Users still compare each proposal with its original before approving it.

The owner/model/payload-scoped cache uses operation `saved_cv_tailoring_v8`, so
older reviews are not reused under the new validation policy. Cached results
are validated again and concurrent CV version changes invalidate proposals.

## Job-focused wording

Both whole-CV and selected-text prompts share `JOB_FOCUS_RULES`. When a role or
JD is present, they ask the provider to prioritize the source's relevant work
and reorganize its evidence, rather than only substitute synonyms. For the
reported AI Engineer case, AI application and ATS contributions can lead the
summary, with Python/Django/API delivery and testing as supporting evidence.
AI coding assistance alone does not establish model training or production ML
deployment experience. Missing JD requirements remain gaps, not CV claims.

Selected rewrites now reuse `wording_rejection`, the same grounding checks as
whole-CV changes, instead of checking only newly introduced digits. A rewrite
cannot upgrade “comfortable” or “familiar” into “proficient” / “skilled” without
a corresponding source claim. Checks also cover deployment, training, production
and MLOps claims. Stated years, quantities and responsibility checks remain in
place. The selected-text endpoint uses only its supplied text as evidence; a
whole-CV summary can also draw on the saved CV's confirmed content.

Single-text cache operations `cv_rewrite_v2` and `cv_improve_v2` avoid older-policy
results. Cached single-text output is revalidated; invalid newly generated
rewrites are not cached. Each action still makes at most one provider invocation.
Existing API request fields, explicit approval and M2 versioned saves are unchanged.
These checks do not measure semantic writing quality or guarantee that every
provider response will be a better paragraph; users still compare the wording.

## Job description and whole-CV review

The dashboard's whole-CV action now requires both a target role and a job
description. The saved role is prefilled and can be changed for this application.
Missing inputs receive a specific message and focus returns to the missing field.
Selected-text rewriting retains optional job context. The API continues to accept
role-only or JD-only requests for compatibility with existing callers.

One Gemini request now asks for a structured job-priority review before rewriting.
The JD is the primary focus; a different role in the saved CV must not override it.
The prompt includes all populated editable sections, factual evidence paths and
per-field evidence boundaries. Work/project wording uses its own entry's facts;
the summary can synthesize the saved CV. Gemini is asked to lead with relevant
contributions, improve all useful wording across sections and explain each edit's
connection to the job, rather than merely substitute synonyms. Existing metrics,
responsibilities, proficiency and named-fact checks remain in force.

JD requests include a required `job_alignment` array in Gemini's output schema,
with up to six important requirements selected by server-issued IDs. The public
response resolves these references into the existing display fields:

- `requirement`: a short verbatim excerpt from the sanitized JD;
- `status`: `supported`, `partial` or `missing`;
- `evidence`: up to three exact CV excerpts with their factual source paths.

Metadata and personal details are not evidence sources. The server extracts literal
JD excerpts and provides numbered `job_requirements`; Gemini selects `requirement_id`
and `evidence_paths` instead of copying or paraphrasing text. The server supplies
the displayed requirement and a literal source excerpt. Legacy quoted responses
are still supported and must match the source. Supported/partial items require
evidence; missing items require an empty evidence list. Invalid references, blank
excerpts, repeated requirements and malformed notes are omitted, with a fixed
`job_alignment_warning`. Independently validated wording stays reviewable and can
be cached with that notice. Cached notes are checked again; unverified text is never
displayed or cached as evidence. Actual wording/schema/source-version failures
retain their strict error behavior. These are provenance checks, not semantic proof of qualifications:
the UI labels partial matches as related evidence and shows the actual excerpts.

`job_alignment` is an additive, optional field in the public review response.
Legacy responses without this field still work. The new Gemini schema requests
it for JD reviews; role-only generation retains the previous output schema.
The dashboard shows the job priorities, evidence and gaps above the proposed
changes. Missing qualifications remain advisory. Neither this assessment nor
the requested role is written into the CV; only selected wording changes are
saved through the existing versioned M2 update. Job details changing clears the
entire prior review. The v8 cache also separates earlier reviews from this flow.

New regression coverage is in `tests/test_whole_cv_job_alignment.py`, the Node M6
suite and the real-browser JD/evidence journey. The browser exercises the actual
Gemini SDK request/response path with a mocked network client, required-input
focus, desktop/mobile layout, review without persistence and approved saving.
No live model quality or availability claim is inferred from these mocked tests.

## Gemini schema rejection and provider diagnostics

The reported immediate 503 was reproduced using the configured model and fictional
data: a minimal connectivity request succeeded, but the full nested review schema
returned upstream `400 INVALID_ARGUMENT`. Removing only string-length bounds still
failed; a compact schema without nested string/array bounds was accepted. The app
had mapped every upstream failure to an undifferentiated temporary-outage message.

Whole-CV generation now reuses `gemini_compatible_schema(..., compact=True)`. It
keeps object structure, required fields, types, enum paths, statuses and property
restrictions. Character/item bounds are carried as generation descriptions and
strictly enforced against the original local response/evidence schemas. No local
CV contract, numerical guard, evidence check or approval rule was relaxed. Other
callers retain their existing schema-compatibility mode. Each request still makes
one provider invocation; there is no automatic retry with a different schema.
Google documents that [large or deeply nested structured-output schemas may be
rejected](https://ai.google.dev/gemini-api/docs/structured-output#limitations).

`AIProviderError` now carries fixed, allowlisted reason codes. The existing 503
error envelope/code remains compatible, with an optional `reason` for configuration,
credentials, permission, quota, model availability, invalid requests, timeout and
connection failures. Unknown failures retain the generic response. Logs contain
only operation, fixed reason and a validated numeric upstream code; raw SDK
messages, CV text and credentials are never logged or returned. The UI uses fixed
messages for these causes and retains input for explicit retry.

A live corrected whole-CV call using fictional content passed full local
validation and returned three requirement assessments. Development CV records
and environment credentials were not changed, and no personal CV was sent for
these connectivity/schema checks. Tests also verify rejected oversized output
despite the compact wire schema and safe quota/credential/error presentation.

## Paraphrased job notes must not block valid wording

The supplied Full Stack AI Developer JD reproduced `source_mismatch` against live
Gemini with a fictional CV. The failing value was one paraphrased job requirement
inside `job_alignment`; the CV evidence excerpts matched. The old implementation
incorrectly rejected the entire review for this optional editorial-note failure.

The reference-based schema removes this unnecessary copying task. JD excerpts are
bounded to 500 characters and 32 source candidates; Gemini selects up to six IDs
and factual CV paths. The public response keeps `requirement/status/evidence` fields.
No requirement text is synthesized by the server and metadata remains excluded
from candidate evidence. Literal CV excerpts are bounded for display.

Optional notes are validated separately from wording. Unverifiable notes are
excluded and only the server can emit the fixed notice. The notice is never a CV
edit or approval decision. A stale/mismatched proposed original, unsupported named
fact, inflated responsibility or changed metric still rejects or omits the wording
under the existing rules. CV version checks and explicit M2 approval are unchanged.

The exact reported JD is a regression fixture at
`tests/fixtures/full_stack_ai_job.txt`. Live verification after this change returned
six valid job notes without a source mismatch, using fictional CV data and no save.
Browser coverage verifies both the new reference response and a legacy paraphrased
note alongside a verified rewrite, including approval and retained JD text.

## Retain independently valid job-fit notes

A successful `200` review can still omit optional notes; that message does not
mean the CV request failed or that suggestions were saved. Notes are now checked
individually so one malformed item cannot discard other verified requirements.
The display keeps the first six distinct valid requirements and at most three
distinct, verified citations per item. Extra notes/citations are bounded before
display; an unsupported citation is never promoted into proof. Wording and CV
approval rules are unchanged.

If an item fails provenance or structure checks, the remaining valid notes stay
visible with the existing server-owned notice. Fresh and cached results follow
the same validation. Fixed diagnostic logs report valid/invalid counts and the
schema/source-error counts without job or CV text. The v8 cache avoids reusing
earlier reviews that discarded the whole notes section. Regression and browser
coverage includes a mixed valid/invalid notes response with a selected wording
save, and oversized/duplicate note and citation lists.

## CV refresh behavior

Opening a review loads its saved CV. AI actions check the latest CV before
generation, saves use M2's version check, and explicit refresh remains available.
Window-focus checks run at most once per minute since the latest read/check;
there is no polling timer. A changed CV clears stale proposals and explains
that a new review is needed. Switching windows rapidly makes no extra reads.

## Regression coverage

- `tests/test_tailoring_grounding.py`: number formats/units/bounds, technical
  aliases, responsibility preservation, partial messages, cache validation and
  identical-text filtering.
- `tests/test_job_focused_writing.py`: the supplied AI Engineer JD and summary,
  a grounded reordering, rejection of the reported proficiency inflation,
  shared prompt policy, cached-output validation and API source preservation.
- `tests/test_cv_tailoring.py`, `tests/test_m9_ai.py`: API authorization,
  owner-scoped caching, stale versions, prompt context and approval persistence.
- `tests/m6_dashboard.test.cjs`: omission presentation, focus throttling,
  fresh checks before AI requests, stale proposal clearing and selected saves.
- `tests/browser_e2e.py`: DevOps partial-result reproduction, Gemini SDK-shaped
  mocked response, selected saves, and retry. Uses synthetic CVs and mocked
  providers; it does not send a live AI request.

Read-only inspection of CVs 22 and 23 helped reproduce the reports. Development CV
records were not changed by the fix or browser tests.
