# Findings for course-corrections

Consulted when a tier-3 conflict might be worth recording. The rule that a
tier-3 claim is never resolved silently is in `SKILL.md`; what is here is what
happens next.

## What becomes a finding

**A tier-3 claim, and nothing else**: your knowledge or a fetched source
conflicts with the notes or an extraction.

| Not a finding | Why |
|---|---|
| a gap you filled from your own knowledge | that is tier 2. The notes are not wrong, they are silent. |
| a `[your note]` | the student's own writing is never evidence. Quote it, name the confusion, and log nothing. |
| a rejected framing | that is a fact about **your** output, not about the notes |
| an item under `## Uncovered material` | an uncovered item is a gap; you log conflicts |

## Opt-in, always

State the conflict, show both versions, say which one the exam rewards — then
**ask**. Nothing is written without a yes. This is what keeps
course-corrections' review queue from filling with model opinion, which is
precisely the basis it refuses to act on alone.

`findings.py add` writes only with `--apply`.

## Duplicates: three places to look

`findings.py check --type differs --concept <id> --source <ID>` looks in all
three and returns `duplicate` with reasons:

1. **Your own findings**, matched on (`type`, `concept`, `source`) — **whatever
   their status**, not just open ones. A closed finding means
   course-corrections looked at it and decided; re-raising it is how a review
   queue becomes noise.
2. **course-corrections' own markers in the notes** — `[source error: <ID>]`,
   `[student, sources differ: <ID>]`, `[unverified: <ID>]`. A marked passage is
   settled.
3. **`D_verification.md`** — course-notes already flagged that item.

## The file

`.data/explain_findings.json`. You write it; course-corrections reads it and may
set `status`, `closed_by` and `reason`, and nothing else.

```json
{
  "applied_renumbers": ["c2d9"],
  "findings": [
    {
      "id": "x-0003", "date": "2026-09-18", "lesson": "L03",
      "type": "differs", "concept": "instrument-relevance", "source": "S16",
      "notes_text": "report the first-stage F and compare it with 10",
      "explain_claim": "the partial first-stage F is the relevant statistic",
      "basis": "external",
      "evidence": "[W3] Stock & Yogo (2005), retrieved 2026-03-12",
      "status": "open"
    }
  ]
}
```

- `id`: `x-NNNN`, allocated from `explain_state.json`, unique across the course,
  never reused. Deliberately not `e-NNNN`, which is the errata namespace.
- `type`: `differs` or `differs_source`.
- `basis`: `model` or `external`.
- `status`: `open`, then whatever course-corrections sets.

A confirmed finding is one of the two writes that **apply pending renumber
blocks first**: a finding carrying the old lesson number would point
course-corrections at the wrong lesson.

## How course-corrections reads it

**An E finding is a report, not evidence.** Its evidence ladder is unchanged by
one:

- a fix resting only on your claim is `basis: user`, and carries
  `[student, sources differ: <ID>]` in the notes;
- a `basis: external` finding hands over a snapshot, usable as **corroboration,
  never as the primary source**;
- in its log, the entry's `origin` is `explain x-0003`.

It also **collapses findings across its three inputs** — course-notes'
verification report, course-revision's findings and yours — onto the same
(`concept`, `source`, anchor), into one proposal carrying every origin and every
piece of evidence. course-revision's `contradiction` says *the notes disagree
with slide 22*; your `differs` says *the notes disagree with the field*.
Different claims, one passage, one fix. You and course-revision never read each
other's findings.

## When the file will not parse

Stop writing findings, report it, and **keep explaining**. A broken findings file
costs one feature; it is not a reason to stop answering the question.

## After writing one

Name the next step and stop: *"run course-corrections review for L03"*. You never
invoke it, and you never edit a note yourself.
