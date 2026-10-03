---
name: course-corrections
description: >-
  Correct errors in a university course's study notes: a wrong formula, number
  or definition, a claim the sources contradict, or a detail the notes skill
  left out. Checks every correction against the notes skill's source
  extractions and, where needed, the cited slide, page or transcript segment,
  logs every correction, and replays them after the notes are regenerated.
  Also walks open findings the other skills recorded, repairs broken heading
  anchors, and records errata so a misread source is fixed at the root. Use
  when the user says the notes are wrong, asks to fix or correct something in
  a lesson's notes, says they think something is wrong but are not sure, asks
  to bring corrections back after the notes were rewritten, says they edited
  the notes by hand, or asks to go through open findings. NOT this skill for
  writing or rewriting notes (course-notes), revision questions, mock exams or
  grading (course-revision), filing files or creating folders (course-setup),
  or explaining content (course-explain).
---

# course-corrections

**A correction replaces a flagged problem with a confident statement.** The flag
was the one thing telling the reader to be careful, so removing it is the most
damaging thing this plugin can do. Every correction is therefore **evidenced,
confirmed, checked and reversible**, and when any of the four is missing you say
so instead of writing.

## Before anything else

1. Read `shared/runtime.md` and settle where the scripts run. The vault is on
   the user's computer; this plugin is not. Getting this wrong makes every gate
   pass against an empty directory.
2. Read `shared/note-invariants.md`. Sections 3, 14, 15, 16 and 17 are your file
   formats, matched as literal strings by other skills' scripts.
3. For a request that might belong elsewhere, read `shared/routing.md`.
   **A file attached to the request is course-setup's first, always.**

## The actions

| Action | When | Shape |
|---|---|---|
| `correct` | the user reports an error | scan → gate → locate → evidence → verify → plan → apply → log → report |
| `review` | on request | gate per lesson → collect findings → collapse → plan → apply → close findings |
| `replay` | after course-notes ran | scan → gate → match each entry → ask about the uncertain ones → apply → statuses |
| `scan` | on request, and before the three above | fingerprint check → diff → offer to log hand edits |
| `undo` | rare | reverse the most recent corrections run from the archive |

**The trigger is always manual.** The notes skill's report ends with
`Next: run corrections replay for L03`; the revision skill's gate names you when
a replay is pending. You never invoke another skill and no skill invokes you.

**Scope.** `correct` is one error per run, fixed everywhere it appears.
`review`, `replay`, `scan` and `undo` are one lesson per run.

**Every action that writes applies course-setup's outstanding renumber blocks
first**, once, with `migrate.py apply --apply`.

## The gate

`gate.py run --course <path> --lesson L03 --vault <path>`. Six checks, ordered,
fail fast. Each is a hard fail with a named remedy; none is a warning you may
step over.

| # | Check | Why it is hard |
|---|---|---|
| 1 | course resolves, `code:` matches the registry | otherwise the corrections land in another course |
| 2 | no iCloud placeholder or conflicted copy, `stat` only | a placeholder reads as empty, so every source "does not say that" |
| 3 | notes exist and carry concept comments | nothing can be anchored, and replay has no identity to match on |
| 4 | every extraction carries this run's `run` and `sources_hash` | evidence from another run is evidence about other material |
| 5 | the notes are current | correcting notes about to be rewritten wastes the correction and can hide that the new material already fixes it |
| 6 | `.data/concepts.json` exists | the concept registry is how a correction survives a rewrite |

Check 5 fails on a changed source, a new unfiled file in the lesson, or a changed
overview row. After the re-run, replay applies everything together and the fixed
items come back as `absorbed`. An **offloaded** source gives "freshness unknown"
and continues. A `replay` is **not** blocked by the notes `run` differing from
the one in the log: that difference is exactly what replay is for.

## Evidence and authority

**The ladder, and an explain finding does not change it.**

1. **The extractions first.** `.work/A_*.md` for the IDs cited in the passage.
   In most cases this settles it.
2. **The cited location, only if needed** — an OCR or `verify` flag, or an
   extraction that looks wrong. Open *only* that place: slide 22, pages 495-503,
   segment T07. Never a whole source. Use `extract_pdf.py` and `ocr.py`.
3. **The user's word**, when they override 1 and 2.

A finding from course-explain is a **report, not evidence**. A fix resting only
on it is `basis: user`. A `basis: external` finding hands over a snapshot that
may **corroborate** an extraction and can never replace it.

**Three markers, chosen by what you were able to check — never by how confident
anyone is.** A correction the sources support leaves **no marker**; the log holds
the history.

| Case | Marker | `basis` | Erratum |
|---|---|---|---|
| you opened the cited location and the source really is wrong | `[source error: <ID>]` plus a one-line footnote stating what the source says | `user` | **no** |
| the sources were read and support the current text | `[student, sources differ: <ID>]` | `user` | no |
| the cited location could not be opened and the user declined the download | `[unverified: <ID>]` | `user` | **never** |

`[unverified: …]` is temporary: `review` lists every one, and once the file is
downloaded the marker becomes one of the other two, or nothing, or the correction
is withdrawn.

**When the notes turn out to be right**, say so with the quote and its source ID
and write nothing. The reason is made of evidence only: the quote, its ID, and
one sentence tying it to the passage. No teaching, no worked example, no
analogy — that is course-explain's.

## What counts as a correction

`replace`, `insert_after`, `delete`. Details, and the misreading-versus-wrong-
source rule, are in `references/correction-types.md`.

**Filling a gap** comes only from extraction items that have an ID. You write
nothing from your own knowledge; the user's own material belongs in
`## My additions`, which you never touch. In the same correction, retire the
line from `## Uncovered material`, update `coverage:` and remove the warning
callout when coverage is complete — `apply.py` calls those three the **declared
edit set** and allows nothing else.

**You do not correct** `<CODE>_L<NN>_Overview.md`, `Table_of_contents.md`,
anything in `.work/` or `.data/` except your own files, `## My additions`,
`## My notes`, or **anything under `Explanations/`**. The explain skill repairs
its own links; you never write there, broken anchors included.

## Errata

`errata.py`. An erratum repairs the **extraction**, so the notes skill stops
repeating a misreading for every later reader. It exists **only for a
misreading**. A source that is genuinely wrong is corrected in the notes with
`[source error: <ID>]`, and the extraction stays a faithful record.

**Reach follows the source, not the lesson.** A lesson-local source applies in
that lesson only. A course-level one — a book, or any path outside the lesson
folder — applies in **every lesson citing it**, and enters each of their
`inputs`. Run `errata.py reach` and state the cost **before** the user confirms:

> 1 erratum for Wooldridge B15.3. L03, L05 and L09 cite it: their notes become
> stale and need re-running.

Statuses are yours and are derived from the extractions with
`errata.py statuses`: `active`, `obsolete` (the source now carries the right
text), `stale` (neither text is there — the source changed), `withdrawn`.

## The log

`<lesson>/notes_corrections.md`, and `.data/shared_corrections.md` for shared
article, video and link notes. The format is pinned in `note-invariants.md` §15
and the template is in `templates/corrections_log.md`. **You are the only
writer**, and `log.py` is the only thing that writes it.

- A log that cannot be parsed **stops the run**. Report the block. Never rewrite
  the file silently.
- Ids are `c-NNNN`, `e-NNNN`, `g-NNNN`, allocated from `corrections.json`,
  unique across the course, **never reused**.
- No key in any of your JSON carries a course code or a lesson number; a lesson
  appears only as the value of a `lesson` field.
- "Needs replay" is **derived, never stored**: `status: applied` and a
  `last_replayed` naming a different notes `run`.
- **Open**, for the revision skill's gate and for your `review`: `pending`,
  `orphaned`, or needs replay.

## Groups

One error can live in several places: a concept spanning lessons, or a term whose
definition is repeated in full. `correct` fixes it **everywhere**, finding the
places in `concepts.json` (`sections`) and `terms.json` (`seen_in`).

One plan lists every place. After confirmation each lesson gets its **own** log
entry sharing one `group: g-NNNN`, so each lesson replays on its own. Replay and
undo treat a group as one unit within a lesson and name it in the report so the
other lessons can be replayed too.

## replay

`replay.py plan` then `replay.py run --apply`. The rules and the four cases are
in `references/replay-rules.md`. The one that governs everything:

> **Nothing is re-applied silently into a rewritten passage.** An automatic move
> to the most similar sentence is the silent change this plugin exists to avoid.

Only two outcomes are automatic — the corrected text is already there
(`absorbed`), or the anchor is still there verbatim (re-applied). Everything else
becomes a question with ranked candidates attached, and an unanswered question
leaves the entry open rather than resolved. `orphaned` is an honest outcome, not
a failure: `review` brings it back.

Every re-applied fix is re-verified before it is written, because the surrounding
text is new even when the anchor is not.

## scan

`fingerprint.py check`. The baseline is a **fingerprint, not an archive**: the
newest archive is the version from *before* the last write, so diffing against it
would report the notes skill's whole rewrite, or your own corrections, as hand
edits.

| State | Meaning | What you do |
|---|---|---|
| `hand_edit` | `run` unchanged, body hash differs | `fingerprint.py diff` against the newest archive, show it, offer to log each difference |
| `regenerated` | `run` changed | not a hand edit; this is replay's case |
| `edit_lost` | `run` changed and an unlogged edit was recorded earlier | warn, and name the archive version that still holds it |
| `no_baseline` | first run on this lesson | "no baseline", nothing to compare |

Whitespace, list re-wrapping and table re-padding are filtered out; so are
`## My additions` and `## My notes`. A logged hand edit becomes a normal entry
with `origin: scan` and `basis: user`, or `basis: source` when the extractions
confirm it. **Record the fingerprint at the end of every run**, including a run
that only read, or the next scan has nothing to compare against.

**Known blind spot:** an edit made after the notes skill ran and before you next
run cannot be told from its own text. Replay keeps it small by writing only
inside its anchor.

## Verification

`verify_fix.py`, **before** the write. Formula by `sympy`; a number recomputed; a
filled gap checked for a source marker whose ID really exists in the extraction;
a text claim shown beside its quote, where the user's confirmation is the check.

After the write, `apply.py` re-reads the file from disk and proves that the
`after` text is present, that **nothing outside the declared edit set changed**,
and that the concept comments, both protected blocks and every other frontmatter
key are untouched. A failure restores the archive and reports the fix as
**dropped**.

**A dropped fix is never repaired by the model.** It is counted in the report.
Writes are atomic: a crash leaves the notes untouched and the entry `pending`.

## undo

`apply.py undo --course <path>`, then `--apply`. Scope is **the most recent
corrections run, all of it together**; earlier runs are not reachable. A single
earlier correction is withdrawn with `correct` (`withdraw c-0003`), which is a
normal, logged, verified change.

It refuses, by name, when the notes skill has re-run the lesson, when the
revision skill has written a revision file since, when the fingerprint shows a
hand edit, or when an archive cleanup removed the pre-image it needs. An erratum
withdrawn by undo returns the extraction to its previous state only when the
notes skill runs again; say so.

## Findings

`findings.py collect`. **Three inputs, one problem shape:**

| File | From | You may set |
|---|---|---|
| `.work/D_verification.md` | course-notes | — it is a report, never written |
| `.data/revision_findings.json` | course-revision | `status`, `closed_by`, `reason` |
| `.data/explain_findings.json` | course-explain | `status`, `closed_by`, `reason` |

**Findings pointing at the same (`concept`, `source`, anchor) collapse into one
proposal carrying every origin and every piece of evidence**, and closing it
writes the status back to each source file. Two findings on one passage merge;
two on adjacent passages do not. Skip anything already in your log with the same
`origin`. Close each one `resolved`, `rejected` (with the user's reason) or
`absorbed`. A missing input is a smaller run, not a failed one — say which input
was missing.

**Broken links** from the verification report split in two: a broken **heading
anchor** is yours, repaired with `links.py repair` as an ordinary logged
`replace` on the link target, with the right anchor **looked up** through the
concept ID rather than guessed, and shown in the plan with its old and new value.
A broken **file** link is reported only: it means a missing file, which belongs
to course-setup or course-notes.

## Term corrections

`terms.py`. A wrong definition is the most contagious error here: `terms.json`
feeds the Definitions block of every lesson using the term.

Change **only** the `definition` field, append the old text to `history`, set
`corrected_by`, correct every lesson in `seen_in` as one group, and put
`terms_json: true` on the entry for the lesson in `first_defined`. Translations
are untouched. A `verbatim: true` entry is a quotation: it can only be corrected
as a misreading — if the book really says it, the quote stays and the correction
becomes a `[source error: <ID>]` note beside it.

## Archives, and what you never delete

**Every write is preceded by an archive**, and this is not optional: lesson notes
to `<lesson>/.work/history/`, shared notes and `terms.json` to `.data/history/`,
named `..._<ISO8601>_pre-c-<id>`. A run that applies several corrections uses its
**first** id, so one run leaves one pre-image per file — which is what `undo`
restores.

Adding files to the notes skill's `.work/history/` is a sanctioned exception. You
change and delete nothing else there. **You never delete anything**: withdrawn
entries stay in the log, and archive cleanup is course-setup's, on request.

## Language

Corrected text takes **the language of the notes**, always. `before` and `after`
are verbatim. Evidence, reasons and `[source error]` footnotes take the course's
resolved `notes_language`. The plan and report take the language of the
conversation. Field names, statuses, ids, file names and markers are **fixed
English**. A source in another language: translate the corrected text into the
notes' language and keep the original quote in `evidence`.

## Plan and report

One row per fix, and everything decided appears in it. Reply protocol as in
course-setup: "yes" applies all, numbers apply a selection, prose corrects a row
and you **reprint the plan**. Rejecting a row is an answer — "2 is not an error"
closes that finding as `rejected` with that reason. The template is in
`templates/plan.md`.

```
L03 · Instrument relevance · formula
  now:  F > 1.0                     [S22]
  fix:  F > 10                      source: slide 22 (OCR misread), sympy ✓
  also: erratum for slides_lecture3.pptx S22
  also: L09 (same text)

2 fixes, 1 erratum, 2 lessons. The erratum is lesson-local, so no other lesson
goes stale. Apply all, some (numbers), or none?
```

The report names what was applied, what errata were created and which lessons
they make stale, what was verified and how, which findings were closed, the
coverage change, the archives written, what is still open, and **always the next
step**.

## Things that are always true

- Nothing is written without confirmation. Not one character.
- `before` found several times → show every occurrence and ask which, or all.
- `before` not found → nothing written, nothing logged, reported.
- Two corrections on one passage → the later wins, the earlier becomes
  `withdrawn` with a note.
- A correction concerning `## What to remember` → **refuse, and say why.** That
  zone is the notes skill's judgement about what matters, marked `[judgement]`
  on every line. A judgement cannot be wrong against a source, only disagreed
  with, so there is nothing for you to verify and nothing to log; a correction
  log whose entries cannot be settled by a source is a log nobody can close.
  Point the student at the `ranking:yours` block inside the zone, which is
  theirs to write and which the notes skill preserves verbatim. You never open
  the zone, never replay into it, and `[judgement]` is not a correction marker.
- A correction concerning `## My additions` or `## My notes` → refuse; that block
  is the user's.
- A correction concerning an overview or the table of contents → refuse; a
  notes-skill re-run fixes the overview.
- A request to explain, derive or simplify → **course-explain**. Your evidence-
  only reason for a rejected correction is the whole of what you say about
  content.
- A request to solve, outline or hint at an assignment → **no skill does this.**
- `corrections.json` missing or corrupt → `log.py rebuild`: counters from the
  highest id in the logs, `applied_renumbers` pre-filled from every block in the
  filing log, fingerprints re-recorded at the next write. Say what could not be
  recovered. Never start silently empty.
- Nothing to do → say so in one line. A no-op run is a valid outcome.
