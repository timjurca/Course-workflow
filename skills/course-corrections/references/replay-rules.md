# Replay: statuses, matching, groups

Read this before running `replay`, and before answering a question it asks.

## 1. Why replay exists

The notes skill regenerates a lesson from its sources and knows nothing about
the correction log — by design, so that the notes stay a function of the
material. Every fix is therefore gone from the file the moment it re-runs.
Replay is what makes a correction survive, and the log is what makes replay
possible.

## 2. The one hard rule

> **Nothing is re-applied silently into a rewritten passage.**

An automatic move to the most similar sentence is the silent change this plugin
exists to avoid: the notes would then contain a confident claim that no one
placed and nothing on screen would say so. `anchor.py candidates` ranks, it never
chooses, and an unanswered question leaves the entry open.

## 3. The four cases

`replay.py plan` classifies every entry that needs replay, in log order.

| Case | Detection | Result |
|---|---|---|
| `absorbed` | the `after` text is already in the concept's section — or, when the concept was renamed or merged, in its successor's | nothing written; status `absorbed`. The notes skill now writes the correct text by itself |
| `reapply` | the `before` text is still there verbatim | re-applied, status `applied`, `last_replayed` updated with the new run |
| `rewritten` | neither is there, the concept still exists | **ask.** Candidates ranked by shared source IDs and token overlap. Answered: re-applied at the new anchor. Declined or unanswered: `orphaned` |
| `concept_gone` | the concept id is not in the file any more | **ask**, with the successor found by the notes skill's own reuse rule. Exactly one candidate: propose it. Otherwise `orphaned` |

The absorbed check runs **before** the concept check, so a fix that the notes
skill now writes by itself is never turned into a question about a renamed
section.

### The successor rule

The same one the notes skill uses to reuse a concept id, implemented once in
`anchor.py successor`: the candidate section in the same lesson whose
`source_ids` overlap the old one's by at least **half of the smaller set**. Two
candidates that both qualify is not a tie to break — it is the case where replay
asks, and `orphaned` if there is no answer.

### What a re-placed entry records

When a question is answered, the entry's `concept` and `before` are updated to
where the fix actually landed, so the next replay starts from there rather than
from a passage that no longer exists.

## 4. The statuses

| Status | Meaning | Comes back in `review`? |
|---|---|---|
| `applied` | present in the notes of the recorded `run` | only when it needs replay |
| `pending` | written to the log but not in the notes — an interrupted run | yes |
| `absorbed` | the notes skill now writes the correct text itself | no |
| `orphaned` | the passage could not be found after a rewrite | yes |
| `withdrawn` | withdrawn by the user, or reversed by `undo` | no; kept for the history |

**Needs replay is derived, never stored:** `status: applied` **and** the run in
`last_replayed` differs from the notes' current `run`. The notes skill never
touches the log, so the mismatch appears by itself.

**Open**, for the revision skill's gate and for `review`: `pending`, `orphaned`,
or needs replay. `orphaned` alone is a warning for the revision skill rather than
a block, because there is nothing to replay until the entry is re-placed.

## 5. Order, groups and scope

- Replay runs on **one lesson**. Entries in the same `group` are applied together
  within that lesson, and the report names the group so the other lessons of the
  group can be replayed too.
- `scan` runs **first**, so a hand edit is never overwritten unnoticed. A
  `hand_edit` state is settled with the user before any entry is re-applied.
- Every re-applied fix is **re-verified** before it is written: the surrounding
  text is new even when the anchor is not, and a formula that matched the old
  evidence may not match the new.
- A refusal from `apply.py` — a protected block, a forbidden target, two spans on
  one passage — aborts the **whole** run. A partial apply leaves the user not
  knowing what moved, which is worse than doing nothing.

## 6. When replay is not the answer

| Situation | Answer |
|---|---|
| the notes `run` is unchanged and the body differs | that is a hand edit: `scan` |
| the gate fails check 5 | the notes are stale: re-run the notes skill first, then replay everything together |
| the entry is `orphaned` and the passage is genuinely gone from the course | withdraw it with `correct`; it stays in the log |
| the corrected text is wrong in the new material | withdraw the entry and make a new correction; do not edit an old one |
