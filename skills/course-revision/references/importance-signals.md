# Importance signals

Every concept starts at **1** and gains points for each signal, from every lesson
it appears in. Nothing ever reaches zero, so no concept is silently skipped.

Each signal is stored in the ledger **with its own evidence**, so any weight can
be traced back to the slide, the exam question or the objective line that caused
it. `ledger.py` recomputes `importance` from the stored signals on every read; it
is never accumulated in place, which is what makes a wrong weight a wrong signal
rather than an arithmetic drift nobody can find.

## The table

| Signal | Points | Evidence recorded | Counted |
|---|---|---|---|
| Exam signal in the lecture | +3 | the `exam_signals` entry, with its source ID | per signal |
| Appears in a past exam | +3 | `Past_2024-06-14.pdf 2b` | **per exam** |
| Covered in the lecture | +2 | an `S`, `T` or `H` ID cited in the section, or the `lectured` tag | once |
| Assessed in an assignment | +2 | the assignment number, from B's `assessed_in` | **per assignment** |
| Named in `Learning_objectives.md` | +2 | the matched line, quoted | once |
| Emphasised in the material | +2 | a `summary_slide`, `key_box`, `review_item` or `lecturer_stress` tag on a cited item | **once**, however many items carry it |
| Heavily highlighted by you | +1 | B's `[!tip] Heavily marked`, or `!` markers | once |

A lectured concept with an exam signal, one past-exam appearance and a learning
objective scores 1 + 3 + 3 + 2 + 2 = **11**. A plain lectured concept scores
**3**. A book-only concept with no signals scores **1** and stays in the pool.

**Book-only sections get no lecture bonus.** A section marked `not lectured` was
not covered in the lecture, whatever else is true of it.

> **Speculative.** The point values are a starting guess and are meant to be
> calibrated against one real course (spec open item 1). They are named
> constants at the top of `ledger.py`, so a calibration is one edit.

## Confidence

Two signals depend on model matching: the past-exam mapping and the learning
objectives. Both carry a confidence.

- `low` matches are **not scored.** They are listed in the report for the
  student to confirm, and scored on the next run once confirmed.
- A confirmed past-exam mapping survives every profile rebuild
  (`exam_profile.py write` keeps `confirmed: true` entries).

A question mapped to the wrong concept moves points onto material the exam never
asked about, and nothing downstream can detect it. That is why a weak match waits
rather than being taken.

## Assignments raise importance and nothing else

- The source is B's `assessed_in` frontmatter and the `G` items in B's
  extractions. **C never opens an assignment file**, and never reads a submission
  or a graded feedback file.
- Every `revise` run copies its lesson's `G` items into the course-wide index
  `Exams/.work/assignment_tasks.json` (`lookalike.py index`). Mocks read that
  index.
- A brief in the `## Assignments` table whose tasks are not yet in the index —
  because its lessons have no current notes — is **named** by `mock` and
  `status`. The look-alike filter cannot cover what it has not seen, and silence
  would read as coverage.
- No question may restate, paraphrase or re-parameterise a task, and no question
  uses an assignment's numbers, data or datasets.

## The mock weight

```
weight  = importance × recency × error
recency = min(1 + days_since_last_tested / 7, 3)        untested -> 3
error   = 1, +0.5 per graded wrong, +0.25 per partial,
             -0.5 per graded correct, floor 0.3, ceiling 3
```

- **Never zero.** Every non-retired concept stays in the pool, `mastered` ones
  included. The floor of 0.3 is what stops a concept answered right once from
  disappearing for the rest of the semester.
- **Missed concepts stay high** until two graded correct answers in a row.
- The ceiling of 3 stops one badly-missed concept from swallowing a whole mock.
- A **coverage floor across the series** sits on top of the weights: every
  in-scope concept appears in at least one mock before any concept appears a
  third time.

> **Speculative.** The factor shapes and constants are a first guess
> (spec open item 1). They live in `ledger.py`.

## Retired concepts

A concept B marks `retired` keeps its whole history, gets no new questions, and
is excluded from mock selection. `status` lists it. Its history is never deleted:
a retired concept's past failures are still evidence about the student.

## A past exam filed mid-semester

It is matched against **every** concept in `concepts.json`, not only the later
lessons, and re-scores every concept it maps to on the next run. Only the ledger
changes, so mocks use the new weights immediately. **Existing revision files are
not rewritten**; `status` lists the lessons whose top concepts changed, and the
student can regenerate them on request.

Notes that are iCloud placeholders are skipped during matching, never downloaded.
The questions that could only map there stay unmapped, are reported, and are
matched once those notes are available.
