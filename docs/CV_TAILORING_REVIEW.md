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

The owner/model/payload-scoped cache uses operation `saved_cv_tailoring_v5`, so
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
API request/response fields, explicit approval and M2 versioned saves are unchanged.
These checks do not measure semantic writing quality or guarantee that every
provider response will be a better paragraph; users still compare the wording.

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
