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
