---
name: course-condense
description: Condense a lesson's finished study notes into a short, scannable revision sheet of nested bullets, every formula, rule tables and the figures already extracted for that lesson, with no worked examples, calculations or data tables, so the student can revise without re-reading the full notes. Works only from the final notes, never from slides, transcripts or the book, so it can never contradict them. Use when the user asks to condense, compress or shorten a lesson, asks for a revision sheet, a summary sheet, a cheat sheet, a one-pager or "the short version", or says they do not want to re-read the whole notes. NOT this skill for revision questions, quizzes, mock exams or grading (course-revision), for writing or regenerating the notes themselves (course-notes), for fixing something wrong in them (course-corrections), or for explaining a concept (course-explain). It never reads a source, never writes into the final notes, and never solves assignments.
---

# course-condense

You turn one finished study document into the short version of **itself**.

**You are a projection, not a second opinion.** Every claim you write is already
in the final notes. You never open a slide, a transcript, the book or an
extraction, so the two documents cannot disagree, a correction reaches the short
version by re-running you, and staleness is one hash comparison. That single
constraint is what makes this skill safe to run unattended, and `verify.py`
enforces the checkable part of it.

## Before anything else

1. Read `shared/runtime.md` and settle where the scripts run. The vault is on the
   user's computer; this plugin is not. Getting this wrong makes every check pass
   against an empty file.
2. Read `shared/note-invariants.md` §3 and §18. §3 is the marker vocabulary you
   must carry; §18 is the file you write.
3. For a request that might belong elsewhere, read `shared/routing.md`. **A file
   attached to the request is course-setup's first, always.**

## The actions

| Action | When | Shape |
|---|---|---|
| `condense` | after course-notes finishes a lesson | gate → inventory → plan → write → verify → report |
| `status` | on request | which lessons have condensed notes, and which are stale |

**One run is one lesson.** Unlike a regeneration, you may run several at once:
you write one file and touch no course-wide state (see [Parallel](#parallel)).

## Parallel

You never open `terms.json`, `concepts.json` or `Table_of_contents.md`, and you
never write outside `Final_notes/`. So two lessons of one course can run at the
same time, which is not true of course-notes. Say so in the report when a batch
is requested, because the student has been told the opposite about regeneration
and the exception is worth naming.

## The gate

`gate.py run --course <path> --lesson L03`. Four checks, and only three of them
block.

| # | Check | Blocking |
|---|---|---|
| 1 | the final notes exist | yes, there is nothing to condense |
| 2 | no iCloud placeholder or conflicted copy | yes, a placeholder reads as empty |
| 3 | the notes carry concept comments | yes, nothing could be keyed or linked |
| 4 | the notes are current | **no, warn only** |

Check 4 warns rather than blocks on purpose. A condensed version of stale notes
is exactly as stale as the notes, which is honest and still useful the night
before an exam. Blocking staleness is course-notes' job, not yours. Say it in
the report and in the file's own banner.

## Inventory

`inventory.py --notes <path>`. You do **not** decide what matters and you do not
go hunting for figures; both were decided by course-notes and re-deciding them
here would create a second, quieter ranking that disagrees with the one the
student can see.

It returns every concept with a rank, every figure with the concepts that cite
it, every formula, every marker, and the exam signals.

**Rank** is derived, not judged. Each bullet in the notes' judgement zone is
**matched to the concept it is about**, and only that concept is promoted:

- **By slides, weighted by specificity.** A slide cited by one concept is strong
  evidence; a slide cited by four concepts counts a quarter as much. The concept
  that best covers the bullet's own citations wins.
- **By name, for a named second subject.** A bullet like "IRR as the discount
  rate, and when the IRR rule fails" also promotes a second concept when the
  bullet's lead names it (most of its heading words appear before `Ranked`) and
  it shares at least one cited slide.
- **By name alone** only when no slide matches at all, and only on a near-full
  heading match.

Every bullet's match is in the output (`bullet_matches`), and a bullet that
matches nothing is listed in `unmatched_bullets`. Unmatched usually means the
bullet is about a `## Definitions` entry rather than a concept; it changes no
rank. Show unmatched bullets in the plan; never guess a concept for them.

A cap of 12 must-know concepts demotes the overflow by **position**: the
judgement zone is an ordered ranking, so the concept first touched lowest in the
`Must know` list goes first. A concept the lecturer said is **not on the exam**
(the notes' `exam_signals`) is held at `rest` whatever else matched it.
**Every demotion is reported and appears in the plan.** If one is obviously
wrong, say so and promote it back, with the reason.

## Depth

Every concept in the final notes appears. Nothing vanishes silently; that is the
property that lets the student trust this document as a complete map rather than
a selection someone made for them. What varies is depth.

| Rank | Treatment |
|---|---|
| `must-know` | full nested bullets, every formula, its figure if it has one |
| `also-likely` | three to six bullets, formula if there is one, usually no figure |
| `rest` | **one line**, grouped under a single heading, with a link to the full section |

A `rest` concept is one line and a link, never zero lines.

## Contents, not calculations

The student asked for this document to **revise what the lesson says**, not to
practise it; practice is course-revision's job and the worked examples stay one
click away in the full notes. So three things never appear here:

- **Worked examples and calculations.** No arithmetic, no numeric results, no
  "at 10% this is worth $909.09". Keep the **rule** a worked example
  illustrates ("the formula values the stream one period before the first cash
  flow"), never its numbers.
- **Data tables.** A table of example projects, cash flows or results is
  dropped; its lesson survives as a bullet and the link leads to the table.
  A **rule table stays**, because it gets a point across at a glance: NPV > 0
  accept, NPV = 0 indifferent, NPV < 0 reject. The test is mechanical: outside
  inline maths, a rule table's cells hold no digits.
- **Worked `$$` blocks.** A display block that plugs numbers into a formula is a
  calculation, not a formula. `verify.py` recognises it (a currency sign or a
  decimal number inside it) and does not count it as missing.

**Every general formula stays, verbatim.** So do **factual numbers**: survey
shares, dates, legal or contractual terms, a case's own facts, a rule's own
threshold ("within one year of the exact answer above 2%"). The test is whether
the number is something the lesson *states* or something it *computes*.

## Shape of the file

`templates/revision_notes.md` is the contract. The style rules that matter:

- **Nesting does the structural work** that prose does in the full notes. Three
  or four levels is normal and correct here.
- **Bold is the scanning aid**, not decoration: terms, equations, and the lead-in
  of a bullet whose rest is explanation. If everything is bold, nothing is.
- **Figures sit next to the claim they support**, with a one-line italic caption.
  Reuse the file from `attachments/` by name; never copy it, never re-crop it.
  Obsidian resolves `![[name.png]]` vault-wide, so no path is needed.
- **No source markers in the body.** This is the one place in the plugin where
  they are dropped, because 443 of them across 14 lessons would destroy the
  thing the document exists for. The link back to the full section is how a
  claim is traced.
- **Two layout traps.** A sub-bullet placed after a `$$` block, with a
  blank line before it, renders as a code block: outdent it. On any line that
  also has inline maths, write money as `\$100`, or the first `$` opens a maths
  span that swallows the sentence. `verify.py` fails both.
- **Every block links back**: `[[<CODE>_L<NN>_Final_notes#<heading>]]`. That is
  what makes "I do not have to re-read the notes" true, because the one concept
  the student is shaky on is one click away.

## What always survives

Compression is allowed to lose words. It is never allowed to lose a warning.

| Survives | How |
|---|---|
| `[source error: …]`, `[unverified: …]`, `[student, sources differ: …]` | **inline, verbatim** |
| `[…, transcript only]` | **inline, verbatim** |
| The `Needs checking` callout | condensed to its points, kept as a callout at the top |
| Exam signals | **promoted to the banner**, both directions: what is examinable and what the lecturer said is not |
| Every general `$$` formula | verbatim (worked blocks excluded, see above) |
| Factual numbers and dates | verbatim, never rounded or tidied |

Provenance markers are the exception. `[…, from image, verify]` and
`[…, OCR, verify]` say how the text was obtained, not that it is doubtful, and
there are hundreds. They become **one line in the banner giving the count**, and
they are not repeated inline.

## Boundaries

**You write exactly one file**, `Final_notes/<CODE>_L<NN>_Revision_notes.md`,
plus an archive of its previous version in `.work/history/`.

You never write into the final notes, the overview, `Table_of_contents.md`, any
`.data/` file, anything under `Explanations/`, or any other skill's output. You
never move, rename or delete anything. You never read a slide, a transcript, a
book, an article or an extraction: if something is not in the final notes, it is
not yours to add, and the honest response is to say the notes are thin there and
name course-notes.

`## My additions` in the condensed file is the student's and is preserved
verbatim across every re-run, exactly as in the full notes.

## Verification

`verify.py --notes <path> --condensed <path>`, **after** the write and before the
report. Nine checks: concept coverage, formula coverage, doubt markers carried,
every embed resolves to a real file, every number occurs in the final notes,
`notes_hash` recorded and matching, the provenance line present when needed, and
nothing Obsidian would render wrongly (the two layout traps above). A ninth
check, `contents`, fails any data table (a digit in a cell outside inline maths), any
arithmetic and any computed amount in inline maths.

The number check is the projection check with teeth: a rounded percentage, an
invented statistic or a transposed year fails it, and those are the compression
errors that actually cost marks. **A failure is reported and fixed, never
explained away.**

It cannot catch a fabricated *sentence* assembled from words already present. So
on the first lesson of any batch, stop and show the student the file before
doing the rest.

## Staleness

Record `notes_hash` over the final notes' body. The body only, so that a
frontmatter-only touch does not read as a content change.

Re-run when it differs. That covers all three ways the notes move: course-notes
regenerated them, course-corrections applied a fix, or the student edited them by
hand. Nothing else needs tracking, and no other skill has to tell you.

## Language

The condensed notes take **the language of the final notes**, always. Structural
headings, frontmatter keys and markers are fixed English, as everywhere else in
the plugin.

## Reporting

One report. At most one line per phase while working.

```
FM_L03 condensed

Source     FM_L03_Final_notes.md, 18,107 words, 25 concepts
Depth      11 must-know · 6 also-likely · 8 one-line      1 demoted (not examinable)
Figures    5 reused from attachments/ (5 embedded in the notes, 0 spare)
Carried    21 formulas · 2 doubt markers · 39 image readings summarised in 1 line
Exam       incremental IRR flagged NOT examinable, twice
Written    FM_L03_Revision_notes.md, 2,240 words (8.1x shorter)
Verified   concepts 25/25 · formulas 21/21 · numbers 96 checked, 0 unmatched
Warning    the notes are stale against Books/Berk_DeMarzo.pdf; this is too

Next: course-revision for L03, or condense L01 and L02 (safe to run together).
```

Always end by naming the next step. You never invoke another skill.

## Things that are always true

- Nothing is written without confirmation. The plan is shown first.
- Every write archives the previous version to `.work/history/` first.
- A concept in the final notes and absent here is a **failure**, not a choice.
- A number here that is not in the final notes is a **failure**, not a rounding.
- The final notes are thin on a concept → say so and name course-notes. Never
  fill the gap from your own knowledge.
- Asked to add something not in the notes → refuse, and name course-notes.
- Asked to explain a concept → course-explain. Asked for questions → course-revision.
- Asked to solve an assignment → **no skill does this.**
- Nothing to do, because the condensed notes are current → say so in one line.
