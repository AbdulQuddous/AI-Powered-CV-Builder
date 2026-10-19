# M5 career-based guidance

The Qwen interview now offers optional guidance for Student, Fresher, Junior,
Mid-Level, Senior and Executive profiles. The AI creation form exposes these choices;
the default remains Fresher. Existing `experienced`, `mid` and `junior` inputs
remain compatible. Users can also say `change my career level to senior`.

M10 remains unchanged: Student maps to `other`, Fresher to `fresher`, and the four
professional profiles to `experienced`. M5 stores the detailed choice in its
existing `question_profile` conversation state. A saved CV with only `experienced`
metadata defaults to Mid-Level guidance when starting a new interview; users can
choose a more specific profile. No extra career fields are persisted in CV JSON.

## Behavior

- Skills: offer 8–15 candidate skills from a bounded role vocabulary, with senior
  or executive emphasis where appropriate. Only the user can confirm possession.
  Known aliases identify duplicates. Known skills from other domains are flagged
  for review; transferable and unknown skills are never automatically discarded.
- Experience: suggest 3–5 relevant roles if available. Student and Fresher work
  history is optional. Junior guidance emphasizes delivery and collaboration;
  Mid-Level emphasizes ownership; Senior emphasizes technical decisions and
  mentoring; Executive emphasizes strategy, scope and organizational outcomes.
- Projects: suggest 2–3 strong projects for Student/Fresher and 3–5 where useful
  for other profiles. These are guidance ranges, never completion requirements.
  Ask for the problem, personal contribution, actual technologies and outcomes.
  Metrics require confirmation; qualitative results are valid.
- Education: identify missing degree, institution, field and completion date.
  Encourage confirmed coursework, awards or grades. Preserve optional-grade
  guidance and the existing year/month confirmation workflow.
- Certifications: suggest featuring 3–5 held credentials if available, or fewer
  or none. Relevant topic areas are discussion prompts, not claims that the user
  holds a named certification. There is no live course catalogue or paid-course
  recommendation.
- Length: flag excessive skills/entries and approximate word counts. The actual
  selected template and paginated preview determine length. Never shrink text,
  delete source facts or claim an exact page count from a heuristic.

Advice appears once on entering the relevant section. New overflow or skill
diagnostics can appear after the affected answer; unrelated follow-up questions
do not repeat old warnings. Explicit guidance is available at any interview step.
The collected draft review also includes a collapsed optional-suggestions panel.

## Commands

- `recommend skills`, `which projects should I include?`, `CV suggestions`
- `prioritize projects`, `prioritize experiences`, `prioritize certifications`
- `add another project`, `add another job`, `add a certification`
- `select projects 3, 1`, `select certifications 2, 1`
- `select experiences 1, 3, 5` (existing five-experience M10 limit)
- `remove Figma from my skills` (existing explicit removal workflow)

Prioritization ranks only supplied entries using transparent keyword relevance;
original numbers are shown and ties preserve source order. It proposes a shortlist,
not an automatic deletion. Selection commands explicitly choose the displayed
subset and order while keeping all original entries in chat. Invalid numbers
preserve the previous selection. Undo remains available. Save still requires
approval through M2 and uses its version checks. Repeated approvals cannot replay
subset indexes against a reordered saved CV or overwrite later manual edits.

An ambiguous `yes`, `all of them` or `use your suggestions` after guidance asks for
specific confirmed choices. `No` dismisses that guidance choice without skipping
the interview's current field. Users may also continue answering normally, skip
optional sections or finish an otherwise complete draft with fewer entries.

## Architecture and limits

`career_profiles.py` maps the six interview profiles to existing canonical values.
`role_guidance.py` contains stable skill vocabularies and certification topics.
`career_guidance.py` derives advisory text and ranks confirmed source entries,
reusing the existing skill aliases and sparse entry merge. It also includes saved
CV facts and pending confirmed edits when advising in edit mode.

The existing `question_engine.recommendations` entry point remains available.
Routing and presentation use the existing M5 response shape and intents. Qwen
continues extracting user facts; guidance does not call Qwen or Gemini. Suggested
skills and topics are excluded from extraction context and never enter
`cv_updates`. The extraction prompt reinforces that suggestions are not facts.

Role matching covers common software/data, design, delivery, marketing, finance
and leadership roles. Rankings are keyword hints, not semantic suitability scores.
Unknown domains get an explicitly general starting point and a request for more
specific role information. Guidance is not a guarantee of hiring or ATS outcomes.

Regression coverage: `tests/test_career_guidance.py`, existing M5 interview/import
and M10 contract suites, plus dashboard JavaScript tests for detailed AI profile
selection and the unchanged canonical manual-creation selector. Provider transports are disabled
in the regression environment; these checks do not benchmark the live Qwen model.
