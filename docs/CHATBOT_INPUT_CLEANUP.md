# Chat input cleanup

Contact validation checks email syntax and phone numbering rules. Numeric email
usernames such as `123qudd@gmail.com` are valid. Passing these checks does not
verify mailbox delivery or ownership of an address or number.

Pasted certification, achievement and language lists are parsed before ordinary
text splitting. JSON wrappers are not stored as names, and commas inside quoted
items remain part of the item. Duplicate keys, unsupported fields and ambiguous
fragments require clarification. Quoted achievement lists copied without their
opening bracket may include trailing closing container punctuation.

The explicit skill alias `Djnago` becomes `Django`; `Restapi` and `Restapis` become
`REST APIs`. Education parsing removes a trailing `degree` or `degrre` descriptor
from the subject. It does not broadly rewrite academic names or invent facts.
At the proficiency question, `keep as it`, `keep it as is` and similar explicit
choices keep the existing languages with unspecified proficiency.

Year-only answers remain in chat memory. Before completing a new interview, the
chat asks for a confirmed month because M10 dates use `YYYY-MM`. The user may
explicitly choose `omit this date`; the original year remains in the conversation.
At this confirmation prompt, `omit`, `skip` and `leave it blank` also omit only
that date. They retain the qualification or job. Date range checks compare
unknown months as year intervals: `2026-04` does not contradict an end year of
`2026`. Explicitly reversed month ranges still require correction.

A single reply such as `starting date 2022-09 ending date 2026-06` updates both
dates on the selected entry. A partial year in the same answer stays pending
without discarding the other confirmed month. The bounded completion typo
`I sompleted ... in 2026` retains the degree, institution and completion year;
the completion year cannot serve as evidence of a start date for model output.
Existing import warnings are also displayed in the collected draft review.
No M10 schema changes or database migrations are required.

When an unsaved creation draft is reopened, reviewed or saved, matching chat history can
repair the old JSON-as-certificate, language-control-text and bounded typo bugs.
Recovery includes the undo snapshot, invalidates prior wording-review decisions,
and leaves saved CVs, other users' sessions and unsupported corrections untouched.
Single-qualification date recovery can also remove a start year proven to have
been copied from a completion-only answer, or restore a labelled endpoint the
old confirmation route discarded. It requires user/accepted-assistant history,
respects later corrections and omissions, and explains the recovery once in chat.

Regression coverage: `tests/test_chat_review_cleanup.py`, including the reported
interview through M2 save, malformed contacts/lists, metadata preservation,
date confirmation/retry, and owner-scoped recovery.
`tests/test_chat_date_followups.py` covers the reported date loop, grouped typo,
paired/partial corrections, omissions, interval validation and recovery guards.

## Ongoing education and expected graduation

`I am currently studying` records study status without inventing a degree.
The next question asks which degree/course the user is studying and invites
the university and expected completion date in the same reply. Answers such as
`i am studying in BS Computer Science at HITEC University` capture degree,
subject and institution together. The chatbot then asks only for the expected
graduation date, using the known university name.

`I expect to graduate in June 2028`, `I excpect to graduate in 2028-06` and the
same phrase without `I` are recognized locally. The bounded `excpect` typo does
not change academic names or guess missing dates. Year-only answers stay
year-only; invalid months and definitely reversed ranges still need correction.

Ongoing education can include an expected end date. The current-employment rule
remains separate: a job marked current cannot have a completed end date. Study
status remains source-only and the confirmed graduation date survives M10 draft
conversion and explicit M2 save. No CV schema or database migration is needed.

For older unsaved interviews, accepted user/assistant history can prove that
an initial status-only education row belongs with the one subsequent degree.
The next chat turn can join those fragments before accepting the date retry.
This repair refuses saved-CV editing, explicit additional qualifications,
contradictory status, multiple named degrees and unsupported history. It does
not edit a saved CV or invent a missing institution/date. Ordinary status-only
answers now merge into the same active qualification and retain confirmed months.

`tests/test_chat_current_education.py` covers the reported exchange, grouped and
partial answers, the expected-date typo, validation recovery, safe legacy repair,
undo, preservation of confirmed dates, employment rules and approved saving.
The browser journey
`tests.browser_e2e.BrowserJourneys.test_current_education_and_expected_graduation_do_not_repeat_questions`
checks the actual chat interface with synthetic contact details and no live AI
request.
