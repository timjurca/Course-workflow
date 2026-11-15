---
name: course-notes
description: >-
  Synthesise one university lesson or tutorial folder (slides, transcript,
  assigned chapters, articles, videos, links, the student's own notes and
  highlights) into a single consolidated Markdown study document with a
  definitions block, concept sections, verbatim source markers, a shared term
  ledger and a mechanically verified coverage check. Use whenever the user
  asks for final, lecture or study notes for a lesson, tutorial, week or
  seminar, or says process, write up, consolidate, redo or regenerate a
  lesson, even when unnamed. Use it too when they ask what a lesson was about
  and its notes are missing or stale (if they are current, course-explain).
  NOT this skill for filing, moving or renaming files (course-setup, which
  runs first whenever a file is attached), revision questions, mock exams or
  grading (course-revision), fixing wrong notes or replaying corrections
  (course-corrections), or explaining and simplifying (course-explain). It
  never files material and never solves assignments.
---

# course-notes

You turn **one** lesson or tutorial folder into one study document, and you
prove mechanically that nothing was dropped.

## Before anything else

1. Read `shared/runtime.md` and settle where the scripts run. The vault is on
   the user's computer; this plugin is not. Getting this wrong makes every gate
   pass against an empty directory and produces notes from no sources at all.
2. Read `shared/folder-structure.md` and `shared/note-invariants.md`. Skill A is
   the authority on the first; the second is a contract with four skills, and
   §11, §12 and §13 pin bytes you write.
3. Read `references/source-hierarchy.md`. It settles priority, highlights and
   conflicts, and the writing passes need all three.
4. For a request that might belong elsewhere, read `shared/routing.md`. **A file
   attached to the request belongs to course-setup first, always.** Say so and
   stop.

## The one routing rule that is decided by state

*"Summarise lesson 3"* and *"what was lesson 3 about?"* are **not** yours by
default. Look at the notes:

| State on disk | Owner |
|---|---|
| `Final_notes/<CODE>_L03_Final_notes.md` exists and is current | **course-explain** |
| missing, or stale (`sources_hash` or `inputs` moved) | **you** |

Sent wrongly to you, that question runs a four-pass pipeline built to run once
per lesson, overwrites every correction skill D applied, and forces a replay.
Sent wrongly to course-explain it costs a paragraph. An explicit *regenerate*,
*redo* or *write* always reaches you, because it names the artefact.

## Run scope

**One run is one lesson or one tutorial.** Never two in one context.

Resolve with `vault.py resolve`; the ladder is `folder-structure.md` §11.
Two candidates, or one weak one: **ask**.

Batch mode is opt-in and strictly sequential — one lesson finished and written
before the next begins, only paths and the term ledger crossing the boundary.
A lesson whose `sources_hash` **and** `inputs` both match its last run is
skipped and reported. Within one session context is shared by definition;
sequential processing plus disk intermediates reduces contamination but does not
eliminate it. For a hard guarantee, one lesson per session.

## The figures pass: adding pictures to notes that already describe them

**A second action, additive, for notes written before the Figures rule existed.**
A normal run embeds figures as part of Pass C and never needs this. It exists
because Pass D's `Figures` gate flags a lesson that read images and showed none,
and a gate whose only remedy is "rewrite the whole document" is a bad gate.

Trigger: the student asks for figures on a lesson, or the gate flagged one. It
is **never** part of a normal run.

**What it may change, and what checks that.** Two kinds of edit are legal:
whole inserted lines, which is how an image and its caption arrive, and markers
added to a line, either into an existing group or as a new one, which is how a
claim read off an image gets said so. Nothing may be deleted and no word outside
a bracket may change. `figures.py` enforces it rather than trusting it: it
strips every bracket group, normalises whitespace and requires the remainders to
match, so a changed word fails, and it refuses to let an existing marker be
dropped.

Inserted lines are checked too, not merely counted: each must be an embed, a
caption, a callout wrapper or blank. Without that, a new paragraph or a whole
new section would pass, which is Pass B and C work under a name that promises
pictures.

```bash
# the candidate goes in .work/, never beside the notes: Final_notes/ is what
# the student reads, and a second full copy of the notes appears in Obsidian
python3 scripts/figures.py check --before <notes>.md --after <lesson>/.work/<notes>.candidate.md
python3 scripts/figures.py apply --before <notes>.md --after <notes>.candidate.md \
    --notes <notes>.md --work <lesson>/.work --apply
```

`apply` archives the old version into `.work/history/` before writing, and
writes nothing at all if `check` fails.

**Re-derive; do not trust the previous run.** The lessons that need this pass
are exactly the ones whose last run left no `from image, verify` markers to work
from, so anchoring on those markers would make the pass work only where it is
least needed. Decide from the images themselves.

Render **the union of check 2b's list and every slide id already carrying
`from image, verify` in the notes.** Neither alone is enough: 2b missed slide 14
of LTM lesson 3, which the notes cite from an image and which turned out to be
one of the six figures worth having, while the markers alone sit on 43 mostly
prose lines and make a far worse shortlist than looking at the pictures. Reuse
cached renders when `sources_hash` still matches; otherwise render again, into
`.work/renders/`.

**Content the notes never captured is reported, never captured here.** Adding a
picture of a claim the notes do not make is not an addition, it is Pass B and C
work under the wrong name, and it would break the edit contract. List it in
`D_verification.md` and in the run report as a reason to regenerate the lesson,
and leave the notes alone.

**Every image inspected is accounted for**, in `.work/figures_record.md`, its
own file. Not `D_verification.md`: `verify.py` rewrites that wholesale on the
next run and would delete the only trace of the judgement no script can check.
List each image as embedded or rejected **with the clause that decided it**:
decoration, a repeat of a diagram already embedded, an ordinary table
reproduced structurally, or already written out in the prose beside it. On the
first real run the clause that did nearly all the work was the last one: on
notes that thorough, almost every picture had already been transcribed, and it
took 28 candidates down to 6.

**Embedding a figure can make the prose around it stale**, and the contract
gives you no legal way to fix it. "Two figures set up the argument" reads wrong
once one embed shows both; "the table below" points at the wrong thing once an
image sits between. You may not reword it. **Report it** as a finding for
`course-corrections`, naming the line.

**A figure from the student's own notes is embedded inside the priority-3
callout**, never in the body on its own. If no such callout exists in the notes
yet, insert the whole `> [!note] Your note` block: a callout wrapper is one of
the legal insertion shapes precisely so this case is reachable. `N` and `C` items are never a standalone
claim ([source-hierarchy](references/source-hierarchy.md) §1), and putting the
image inside the callout inherits that for free, so a hand-drawn sketch can
never be read back as the lecturer's.

**Parallel-safe, unlike a regeneration.** The pass writes only the notes file,
`Final_notes/attachments/` and `.work/`. It never touches `terms.json`,
`concepts.json` or `Table_of_contents.md`, because no heading changes. Two
lessons in the same course can therefore run at once.

## Boundaries

**You write:** `Final_notes/<CODE>_L<NN>_Final_notes.md` including its
`## What to remember` zone but never the `ranking:yours` block inside it, the slide-goals marker block in `Learning_objectives.md`,
`Final_notes/attachments/*`, `<CODE>_L<NN>_Overview.md`, shared notes in the
course-root `Articles/`, `Videos/` and `Links/`, your own marker blocks and the
term index in `Table_of_contents.md`, `.data/terms.json`, `.data/concepts.json`,
and everything in the lesson's `.work/`.

**You create only three folders:** `.work/`, `.work/history/`,
`Final_notes/attachments/`. Every visible folder is skill A's. A missing
course-root `Articles/`, `Videos/` or `Links/` is a stop-and-ask to run
course-setup validate, not something you create.

**You never read:**

| Never | Why |
|---|---|
| `Explanations/` | Tutor output. Never in `sources:`, `sources_stat` or `inputs`; excluded from every directory listing and every staleness comparison. If model prose ever entered `sources_hash` it would become notes, then exam questions, then something skill D corrects against — and nothing on screen would say so. |
| `Exams/` | course-revision owns it entirely. |
| Assignment submissions and feedback | Briefs are read as a signal; these are read by nobody. |
| `notes_corrections.md` | Detected at pre-flight, **never opened**. The count of corrections is skill D's to report. |
| `corrections.json`, `shared_corrections.md`, `.data/history/` | Skill D's. |

**You read exactly one skill D file:** `.data/source_errata.json`, as data, and
you write to no skill D file ever.

**Protection is against writes, not reads.** `## My additions` and the
overview's `## My notes` are preserved verbatim and never written by you;
course-explain may read them, and marks anything it quotes `[your note]`.

## Pre-flight

`preflight.py check --course <c> --lesson L03 --vault <v>`. Ordered, fail fast,
nothing written.

| # | Check | On failure |
|---|---|---|
| 1 | folder is `NN_YYYY-MM-DD` and `Content/` exists | hard fail |
| 1b | `code:` present, and mapped to this course in `_config.md` `course_codes` | stop and ask |
| 2 | no iCloud placeholders **in scope** | hard fail, list them |
| 3 | no conflicted copies **in scope** | hard fail, ask to resolve |
| 2b | every slide has a text layer (text-light, picture-heavy slides listed) | stop and ask; read those slide images |
| 4 | every unprefixed `.md` in `Content/` resolved; no exam or assignment file there | stop and ask |
| 4b | every extension has a handler in `shared/formats.md` | stop, propose a row, apply only on approval |
| 5 | every `expects` token present | stop and ask, list what is missing, offer to proceed |
| 5b | a **staple** this lesson lacks that most sibling lessons have (`slides`, `transcript`, `notes`, `book`) | stop and ask. `expects` only covers what skill A declared, and an undeclared category is the one that goes missing unnoticed |
| 6 | every chapter resolves to a page range | stop and ask |
| 7 | Python dependencies for the formats in scope | ask before installing |
| 7b | `yt-dlp` for assigned videos | **warn only**; videos degrade, they never block |
| 8 | `sources_hash` and `inputs` match the last run (batch only) | skip and report |
| 9 | `notes_corrections.md` at the lesson folder root | **warn and continue** |
| S1/S2 | course-root note folders; `terms.json` and `concepts.json` states | stop and ask |

Checks 2 and 3 are **scoped**, not course-wide: this lesson's folder, the books
its row cites, the shared notes this run will write, the course-root files it
reads, the briefs listing it, and `_filing_log.md`. Never `_Inbox/`, never other
lessons. The course-wide version deadlocked — `_Inbox/` is the most
conflict-prone folder in the vault and skill A will not delete a conflicted
copy, so one stray conflict there blocked every lesson with no exit.

**Check 9 is detection only.** Say: *this lesson has corrections; regenerating
will need them replayed*, and end the report with the replay step. Do not open
the file, and do not invent a count.

**A notes-only lesson is permitted.** If the only sources are `notes_*` or `C`
items, run, add the banner from `templates/lesson.md`, and mark every section
`[N-only, unverified]`.

## The four passes

Coverage is enforced by set arithmetic on IDs, not by instructing yourself to be
thorough.

```
Pass A  EXTRACT   each source in isolation      -> .work/A_<source>.md   scripts
Pass B  SPINE     merge into an ordered outline -> .work/B_spine.md      model
Pass C  WRITE     section by section            -> .work/C_draft.md      model
Pass D  VERIFY    setdiff(extracted, cited) = 0 -> .work/D_verification.md  script
Pass C' REPAIR    only on gaps, exactly once, then report. Never loops.
```

One line of narration per pass while working. Nothing more.

### Pass A — extraction (scripts)

Every atomic item gets an ID, and `extraction.py` validates the shape before the
file is written. A malformed ID is silently uncovered forever: it matches no
marker, so Pass D reports it as a gap that no repair pass can close.

| Source | Script | IDs |
|---|---|---|
| `.pptx` slides | `extract_pptx.py` | `S12`, `S12.3`, `S12n` |
| `.pdf` book, article, handout | `shared/scripts/extract_pdf.py`, then `extract_annotations.py` | `B15.2`, `B15.2!`, `A2.4`, `H04` |
| scanned `.pdf`, images | `shared/scripts/ocr.py`, then `detect_marks.py` | same, every item flagged `[…, OCR, verify]` |
| `.docx` | `extract_docx.py` | by section (`--sections`) or by block; comments become `C` items |
| `.epub` | `extract_epub.py` | section anchors, not pages |
| `.md`/`.txt` transcript | `normalize_transcript.py` | `T1.07`, **always indexed by file** |
| `videos.md`, `.vtt`/`.srt` | `fetch_video_captions.py` | `V1.6` |
| `links_*.md` | `fetch_video_captions.py link` | `K1.6` |
| assignment brief | `extract_assignment.py` | `G1.3`, signal only |

All of them write through `scripts/extraction.py`, which owns the Pass A file
format, validates every ID before the file exists, and applies skill D's errata.
It is the one module here that is not in the spec's script list: the alternative
was six copies of a format three other skills parse, which is the exact failure
`shared/` exists to prevent.

Four things that are easy to get wrong:

- **A slide that is one equation or one figure extracts to almost no text.**
  `extract_pptx.py` emits an ID for the picture and the table anyway. Without
  it, Pass D reports full coverage while the densest slide is missing.
- **A PowerPoint diagram is a group of shapes, and every label in it is live
  text.** `extract_pptx.py` recurses into groups and emits **one item per
  top-level group**, leaf text in reading order with repeats collapsed
  (`Go/no-go ×7`). Walking only the top level silently dropped slide 23 of EBT
  lecture 1 — the advanced stage-gate model, the lecture's culminating artefact.
- **A slide whose content is a picture has no text to extract.** Pre-flight
  check 2b flags text-light, picture-heavy slides. Read those slide images and
  emit their content tagged `[<id>, from image, verify]`. Slide 11 of EBT
  lecture 1 is the course schedule as an image, and until it is read nothing can
  notice that it contradicts `Weekly_overview`.
- **Transcript frontmatter is not a segment.** `normalize_transcript.py` strips
  it and keeps `duration`, `recording_date` and the speaker count as metadata:
  `recording_date` is the only mechanical evidence that a file named
  `transcript_lesson_2.md` is in fact lesson 1's second half.
- **Transcript normalisation runs before segmentation**, against a vocabulary
  built from the slides and the book. A garbled term poisons the sections and
  the term ledger at once.
- **Figures are extracted, never redrawn**, into
  `Final_notes/attachments/<CODE>_L<NN>_fig_<sourceID>_<slug>.<ext>`. Which of
  them belong in the notes is decided in Pass C; see
  [Figures](#figures-show-them-do-not-only-describe-them).
- **Tags are a closed list** (`note-invariants.md` §11). A tag nobody else knows
  is a tag nobody else acts on.

Long sources chunk at roughly 8,000 words on a structural boundary. An ID is
never split across chunks, and boundaries are recorded in the header so Pass D
can tell a lost item from a boundary artefact.

**Then, last in Pass A, apply skill D's errata:**

```bash
python3 scripts/extraction.py errata --work <.work> --course <c> \
    --lesson L03 --sources <entry> ... --apply
```

`wrong` present → replace and tag `errata`. `right` already present → apply
nothing, the source was fixed. Neither present → apply nothing and **report it
as not applied**; the source changed, and its status is skill D's to set. A
lesson-local erratum reaches its own lesson; a course-level one (a book, or
anything outside the lesson folder) reaches every lesson citing that source and
enters each of their `inputs`.

### Pass B — the spine (model work)

Merging extractions into an ordered outline is judgement, and no script does it.
What the scripts do is the bookkeeping either side of it.

Write `.work/B_spine.md`: one node per concept, each listing the source IDs that
feed it, plus a `## Discarded` section naming every ID classified as
non-content, so the arithmetic still balances.

- **Order:** slide order; else book order; else transcript order. Book order may
  override slide order only when the slide sequence is demonstrably non-linear,
  and the deviation is recorded in the spine.
- **One H2 per concept**, typically spanning 3 to 8 slides, never one per slide.
  A section carrying neither a definition nor a substantive claim merges into
  its neighbour. Without this rule a 48-slide lecture comes out as 40 fragments
  whose `Connects to` lines outnumber their content.
- **Duplicate content merges.** Slides and book on the same point become one
  section citing both; the book's fuller wording governs where they agree.
- **Items fitting no node go to an unplaced list, never discarded.**

Then assign concept IDs — deterministic, and shared with three other skills:

```bash
python3 scripts/concepts.py assign --course <c> --lesson L03 \
    --nodes '[{"heading":"...","source_ids":["S14","B15.3"]}]' --apply
```

A node keeps the ID of the previous section for this lesson whose `source_ids`
overlap it most, when the overlap is at least half of the smaller set.
Otherwise a new ID. A reused concept **keeps its heading**, with exactly two
sanctioned reasons to change it: the section's subject changed materially, or
the section moved to a different zone and its old heading no longer reads
correctly there. Anything else is churn. The script reports every change; you
repeat it in the run report, because inbound links point at the old anchor.

**Tutorials create no concepts.** Pass `--tutorial` with each problem's
`connects_to` link; a problem with no link carries no ID and is reported.

### Pass C — writing (model work)

Section by section into `.work/C_draft.md`, each section generated with only its
own mapped extractions, definitions block first from the term ledger. On
completion, **atomic move** to `Final_notes/<CODE>_L<NN>_Final_notes.md`, so a
crashed run never leaves a half-written notes file.

Shapes live in `templates/`: `lesson.md`, `tutorial.md`, `overview.md`,
`article.md`, `video.md`, `link.md`.

**The document has a fixed shape.** Slide order is not study order: a deck
interleaves administration and learning goals between content, and following it
faithfully is how the learning objectives end up in the middle of a study
document. The zones are always these, in this order:

| Zone | Holds |
|---|---|
| *(top matter)* | the one-line summary, source-conflict warnings, a one-line pointer to `## What to remember`, then the `Contents` callout |
| `## Definitions` | the term ledger's entries for this lesson |
| `## Concepts` | one **H3** per concept, in the order the material builds |
| `## Cases` | one **H3** per case, **H4** for its parts |
| `## Recap` | three to six sentences, no new markers |
| `## What to remember` | your pinned block, then Claude's ranking. **Not from a source** |
| `## Check yourself` | *this lesson's* goals, as a test |
| `## Assigned readings` | what to read next |
| `## Course administration` | a link to the overview; the detail lives there |
| `## My additions` | protected |

Slide order still governs the order **within** `## Concepts`.

**A case is one unit.** Everything belonging to a case is contiguous under its
own H3 so it reads or skips as a whole, and its figures sit with it. But the
**generalisation drawn from a case stays a separate concept**: the case is the
evidence, the claim is what gets examined, and a later lesson may support the
same claim with a different case. *Xerox and Canon* is a case; *a fitting
organization is the binding constraint* is a concept that links to it. A case
carries a concept id like any other section, so a lecture that returns to it
attaches to the same id.

**Course-level learning goals are not repeated per lesson.** They are identical
in every lecture that shows them. They live in the course root's
`Learning_objectives.md`, inside the marker pair
`<!-- goals:slides:start -->` / `<!-- goals:slides:end -->`, which is the only
part of that file this skill owns: everything outside the markers is the
student's. Upsert them with `build_toc.py goals` (see [Tables of contents and
links](#tables-of-contents-and-links)), then link the lesson to that file and
keep only the goals that are this lesson's own.

A separate `Course_learning_goals.md` was the obvious shape and the wrong one:
it would be a second index of the same material, competing with a file the
student already keeps, and nothing would say which of the two is current.

### Figures: show them, do not only describe them

A curve's shape, a flow with branches, a mapping of one structure onto another,
a table whose alignment is the point: prose can describe these and cannot show
them. Describing one and leaving it out asks the student to trust a paraphrase
of exactly the thing a paraphrase loses. **Figures come from the slides or the
book, and the ones that carry content go into the notes.**

**A figure earns its place when any of these holds:**

- the notes argue *from* it, and the claim cannot be checked without seeing it
- it was read `[…, from image, verify]` and what it holds is spatial or
  relational rather than a list of words (if the picture was a list of words,
  write the words instead)
- it is a table markdown **cannot** hold: merged cells, a matrix laid over a
  picture, cells that are arrows. An ordinary table is reproduced as a markdown
  table, never as an image, because a table image is not searchable, not
  diffable and unreadable with images off, which is the same argument the
  caption rests on
- the source itself treats it as a numbered artefact the course refers back to,
  Figure 5.1, Table 2.4

**It does not when:**

- it is decoration: a portrait, a stock photo, a lecture-hall shot, a section
  divider, a logo
- it only repeats text that is already written out beside it
- it is an ordinary table: reproduce it structurally instead
- the same diagram is already embedded elsewhere in these notes; a deck that
  reuses one pattern figure across six slides needs it once, and the one worth
  keeping is whichever copy adds something (an arrow, a moved marker). This
  clause does more work than any other: on EBT lesson 6 it took the candidates
  from thirteen to four

**How, in the body, beside the claim it supports:**

```markdown
![[EBT_L05_fig_S23.2_slide_23.png]]
*Figure (slide 23): resources against four stages, Discovery, pre-NPD,
Development, Commercialization. A falling research curve and a rising
commercialization curve cross low in the middle, and the trough between them is
the Valley of Death.* [S23.2, from image, verify]
```

The caption is one italic sentence saying **what it shows**, and it ends with
the figure's source marker. It is not optional and it is not a title: if the
file is ever lost or the vault is read somewhere images do not render, the
sentence is what survives, and it is also what makes the figure findable by
search.

**Getting the file.** A `.pptx` figure is already extracted by
`extract_pptx.py` into `Final_notes/attachments/`. A PDF deck or a book figure
comes from `extract_pdf.py images --pages N-N`, which pulls the embedded
rasters; when the figure is vector and no raster exists, render the page with
`ocr.py pdf --pages N-N` and crop to the figure. Name it
`<CODE>_L<NN>_fig_<sourceID>_<slug>.<ext>` like any other attachment, so the
figure carries its source id in its own filename.

**A PowerPoint figure that is a picture with vector shapes drawn over it has to
be rendered, not extracted.** `extract_pptx.py` writes out the picture part
alone, so the arrows, braces, call-outs and strike-throughs on top of it are
missing from the file it hands you, and those are usually the argument. Render
the whole slide instead and name it with the slide-level id
(`<CODE>_L<NN>_fig_S12_slide_12.png`) so it does not collide with the extracted
picture's own `S12.3` filename.

Figures are extracted, never redrawn. A redrawn causal diagram with one arrow
reversed is confidently wrong and undetectable at revision time.

Pass D's `Figures` gate checks the mechanics: that every embed points at a file
that exists, that each one carries a caption and a source marker, and that a
lesson which read five or more items off rendered images embedded at least one
of them. It cannot judge which figures are worth showing, so that judgement is
yours, and the run report says how many you embedded against how many images
you read.

### The one-line summary

Directly under the H1, before any warning:

```markdown
**In one line:** a corporation is a legal person separate from its owners, and
almost everything in corporate finance follows from that separation.
```

One sentence a reader can hold, stating what the lesson *claims*, not what it
covered. "This lesson covered three levels of analysis" is a table of contents;
"a technological innovation process cannot be understood at one level" is a
claim.

**It is the same sentence as the overview's, byte for byte.** Write it once and
put it in both files. `verify.py` compares them and reports a mismatch: two
summaries of one lesson that drift apart are worse than one, because neither can
then be trusted and nothing says which is current.

Why it is here and not only in the overview: opening the notes gave a warning
banner and a twenty-entry contents list before a single claim. The reader had to
open a second file to find out what the lesson was about.

### `## What to remember`: the one thing here that is not from a source

Everything else in the notes is traceable to an extracted item. This zone is
**your judgement about what matters**, and it is the reason the `[judgement]`
marker exists (`note-invariants.md` §2a). Write it, and write it honestly.

The shape, verbatim:

```markdown
## What to remember

<!-- ranking:yours:start -->
**Your pins** - nothing pinned yet.
<!-- ranking:yours:end -->

> [!warning] Claude's judgement, not the lecturer's
> Nothing below is taken from the slides, the reader or the transcript. It is a
> ranking of what seems most likely to be examined, made from this lesson alone,
> and it can be wrong. The material itself is above; this is a reading aid.

**Must know**

- One line of claim, then one line of why it was ranked here. [judgement] [S18.7]

**Also likely**

- Shorter entries, same shape. [judgement] [B25]
```

Five rules, all of them checked by `verify.py`:

- **Every bullet carries `[judgement]`**, and the marker appears nowhere else in
  the file. Per line, not per section, because a line travels and a section
  boundary does not: a bullet pasted into a revision question has to still say
  what it is.
- **`Must know` holds at most ten items.** Selection is the whole value of the
  zone. With no cap it grows every run until it is the table of contents again,
  at which point it says nothing. `Also likely` is short and has no hard cap.
- **The warning callout is present**, above the generated list and below the
  pins.
- **The ranking block is preserved verbatim.** It is the inverse of a TOC pair:
  you replace everything *outside* `<!-- ranking:yours:start/end -->` and never
  what is inside it. Create it empty when absent. This is the student's only way
  to disagree, and a judgement cannot be wrong against a source, only disagreed
  with, so D never touches the zone at all.
- **No H3 inside the zone.** The tiers are bold labels. An H3 here would enter
  the course table of contents as if it were a concept.

**Judge from this lesson only.** What the lecture spent time on, what the goals
slide asked for, what the book stated as a definition, what carries a
`summary_slide`, `key_box`, `review_item` or `lecturer_stress` tag, what the
student wrote down, what an exam-signal callout marks. You do **not** open past
exams, the revision ledger or the error history: skill C judges the same lesson
from exactly that whole-course vantage, blind to yours, and two raters that see
the same evidence agree by construction and tell nobody anything
(`note-invariants.md` §8b). The difference between the two views is the finding.

Every item states **why**, in one clause. A ranking you cannot argue with is a
ranking you cannot use.

Source IDs cited here **do not count toward coverage**. An opinion can never
satisfy the coverage guarantee for material the body failed to cover, so cite
freely; it changes no arithmetic.

**State the fact and its explanation. Never narrate who said it.**

The source marker already carries provenance, so "the lecturer says X [T1.12]"
says nothing that "X [T1.12]" does not, and it costs the reader the concept. In
EBT lesson 1 this produced 56 attribution phrases and one section, *How this
course and its reader came about*, containing no examinable content at all.

Forbidden in prose: *the lecturer*, *a student*, *the room*, *the slide notes*,
*he says/adds/frames*, speaker names, and personal biography. `verify.py`
reports every occurrence under `Attribution in prose`.

Attribution is allowed in exactly six places, because there it **is** the
content:

1. A cross-source conflict — `[S16 corrected by T11]`.
2. A priority-3 student claim, inside its `> [!note] Your note` callout.
3. A claim resting only on transcript while slides and book are silent — `[T1.75, transcript only]`.
4. A verbatim quote, in a blockquote.
5. An **exam signal** callout: the emphasis itself is the examinable fact, and a
   paraphrase loses its force.
6. A **live case discussion**: the options proposed and rejected are content.
   Write the option and why it fails, never who offered it.

The rewrite is usually shorter and clearer. 75 words to 33, same IDs cited:

> ~~The worked example is the lecturer's own blocked questionnaire. Early in his
> PhD he designed a postal survey… A student in the room supplies the answer:…~~
>
> **Theory must precede data collection.** Without a theory stating what is to
> be established there is no basis for deciding what to measure, and the
> resulting data cannot be analysed. `[T1.14, T1.16, T1.17, T1.18]`

- **Headings are never numbered.** A numbered heading breaks every link into it
  the moment a section is inserted above.
- Every concept section carries `<!-- concept: <id> -->` directly under its H2.
- **No length target, no compression ratio, no word cap.** A section is finished
  when every ID mapped to it is represented. If that makes the document long,
  the document is long.
- Tables reproduced structurally, never summarised into prose.
- **Formulas are reproduced in the source's own notation, exactly as the source
  writes them, and every symbol is explained directly below.** A formula is a
  table: you copy it, you do not restyle it. If the book works an example in
  numbers, the notes work it in numbers; you do not generalise it into symbols
  the book never used. If the book writes it in symbols, those symbols are the
  ones the notes use, and where a slide and the book differ the book's notation
  governs, by the same rule that gives the book's fuller wording precedence.

  ```markdown
  $$NPV = \sum \frac{CF_t}{(1 + r)^t}$$

  where

  - $NPV$ ... the net present value of the investment [B4.1]
  - $CF_t$ ... the cash flow in period $t$ [B4.1]
  - $r$ ... the discount rate per period [B4.1]
  ```

  The legend is not optional and it is not prose: one line per symbol, the
  symbol, then what it stands for, then its marker. A formula whose symbols are
  undefined is one the student cannot use under exam conditions, and a formula
  in notation no source used is a claim wearing a source marker.

  `verify.py` checks both halves against the priority-1 extractions. It reads
  one and two character identifiers and Greek macros; words inside `\text{}`
  are prose and are not checked, so a step labelled *corporate tax* is fine.
- **Every mathematical symbol in running text is inline math**
  (`note-invariants.md` §2d). Definitions, concept prose, tables, callouts,
  blockquotes, exercises and `## What to remember` follow the same rule as a
  `$$` block's legend. Obsidian shows a plain `e_P` literally, and two
  underscores on one line can turn the words between them italic.

  | Write | Never |
  |---|---|
  | `$e_P$`, `$r_E$`, `$P_0$` | `e_P`, `r_E`, `P_0` |
  | `$e_{XZ}$`, `$q_{11}$`, `$Y_{OLD}$`, `$Div_1$` | `e_XZ`, `q_11`, `Y_OLD` |
  | `$X^{-1/2}$`, with an ASCII minus inside the maths | `X^(−1/2)` |
  | `\$530` or `USD 530` | `$530` |

  A subscript or superscript of more than one character goes in braces. A
  verbatim quote from a source keeps its words, but the symbols inside it are
  still wrapped: that is formatting, not rewording. A literal dollar amount in
  prose never opens a math span. `verify.py` reports what it finds under
  `Plain symbols`.
- **A student note earns a callout only when it adds or diverges.** A note that
  duplicates a source is cited inline on the sentence it duplicates; coverage is
  satisfied without interrupting the concept. In a callout that does survive,
  quote the note verbatim and then state in one line what it adds or where it
  differs — never describe the note.
- Shared article, video and link notes are **additive**: touch only your own
  `## Used in L<NN>` section and append to `used_in`. `## Core summary` is
  written once and thereafter only extended.

**Carry the ranking block forward before you write.** Read it out of the notes
file you are about to overwrite and paste it back unchanged:

```bash
python3 ../../shared/scripts/judgement.py ranking \
    --notes <Final_notes/<CODE>_L<NN>_Final_notes.md>
```

Absent, or no notes file yet: create the pair empty. This is the same
read-modify-write discipline as `## My additions`, and it fails the same way if
skipped, by silently deleting something the student wrote.

**Close your own renames before Pass D.** `concepts.py assign` already told you
which sections changed heading, as `heading_changed` with `previous_heading`. A
link you wrote earlier in this same run into one of those sections is now
pointing at an anchor that no longer exists, and it is yours, not D's: D repairs
breaks it finds later across the vault, and there is no reason to hand it one
this run created and can see:

```bash
python3 ../../shared/scripts/check_links.py retarget --vault <vault> \
    --note <CODE>_L<NN>_Final_notes --scope <this lesson's folder> \
    --map "<previous_heading>=<new heading>" --apply
```

Run it once per renamed heading, or pass several `--map` pairs at once, before
`build_toc.py`, so the `Contents` callout is built from repaired links.

- **`--scope` is not optional in practice.** Bound it to this lesson's folder
  and run it a second time scoped to the overview. A link from **another
  lesson** into a section you renamed is a genuine cross-lesson break: report
  it, leave it, and let D repair it through the concept ID, exactly as with any
  other rename.
- `stale_aliases` in the output lists links whose visible text still reads as
  the old heading. The anchor is already fixed; the alias is prose, so fix it
  where you find it and do not leave it for a script.

### Pass D — verification (script)

```bash
python3 scripts/verify.py report --work <.work> --notes <notes> \
    --run <ts> --hash <h> --extras '{...}' --apply
```

```
unplaced = ids_extracted - ids_placed - ids_discarded
uncited  = ids_placed   - ids_cited
```

Both empty, or one repair pass over exactly the missing IDs, then one
re-verification, then stop. **Never loop.** Surviving gaps go into
`## Uncovered material`, into `coverage: 110/112`, into a warning callout and
into the report. **Incomplete coverage never blocks the write** — notes with a
flagged gap beat no notes.

`verify.py` also rejects unknown bracket shapes loudly, flags decorated markers
(`[B §15.1]` matches nothing), flags a tier marker found in a notes file as a
quarantine failure, and flags numbered headings and sections with no concept ID.

**The writing gates run here too**, because Pass C is model work and a rule
stated only in prose decays:

| Section | Fires on | Pass C's answer |
|---|---|---|
| `Unsupported specifics` | a number, year, percentage or quantity whose sentence cites only priority 2–3 markers, and which appears in no slide, book or handout extraction | mark it `[<id>, transcript only]`, or drop the number |
| `Source spelling disagreements` | two authoritative sources spelling one proper noun differently, both outside the general word list | use the **majority** form and add a warning callout naming both |
| `Attribution in prose` | *the lecturer*, *a student*, *he says* and friends, outside a blockquote and outside `## Definitions` | rewrite as the claim |
| `Formulas` | a display formula using symbols no slide, book or handout uses, or one whose symbols are not explained in a legend directly below it | copy the source's notation; write one legend line per symbol |
| `Plain symbols` | a `<1-3 letters>_<1-4 alphanumerics>` or `<letter>^(...)` token in the body outside inline or display maths, code, wikilinks, embeds, links, HTML and URLs; file-name-like tokens, source markers and the protected blocks are skipped | wrap it as the row says: `$e_P$`, `$e_{XZ}$`, `$X^{-1/2}$` |
| `Judgement zone` | a bullet with no `[judgement]`, the marker outside the zone, more than ten in `Must know`, a missing callout, a missing or misplaced ranking pair, an H3 in the zone | fix the zone; none of it blocks the write |
| `Summary line` | `**In one line:**` missing from the notes or the overview, or the two texts differing | write the one sentence, identically, in both |

None of them blocks the write. They are reported, and the run report says
how many survived.

`verify.py` also reports **judgement drift**: what entered and left `Must know`
since the previous run, read from the newest archive in `.work/history/`, with
rewordings paired rather than reported as one departure plus one arrival. Model
judgement is not deterministic, so an invisible reshuffle is one nobody can
question. No archive means no baseline, and the report says so rather than
reporting no change.

## Terms

`terms.py`. Definitions are **repeated in full in every lesson where the term
appears**; the ledger exists so the repeated text is identical, not so it can be
omitted. Prefer a verbatim quote from book or slides, always as a blockquote
with its marker — that is a plagiarism guard, so you can see at a glance which
words are the textbook's. Otherwise two to four sentences, plus formula and
example where they help. Bilingual whenever sources are mixed-language. Ordered
by first appearance, never alphabetically.

A later, materially different definition is a **refinement**: the old text moves
to `history` and the notes link back. **An entry carrying `corrected_by` is
never overwritten** — skill D put it there. If the source behind it changed,
report the conflict and still leave it alone.

## Tables of contents and links

`build_toc.py`, at the end of the run:

1. `infile --notes <path> --apply` — the collapsed `Contents` callout, built
   from the headings **actually written**, so it cannot drift.
2. `upsert --course <c> --key L03 --code <CODE> --notes <path> --apply` —
   replaces only the bytes between this lesson's own markers. Missing file:
   created from the skeleton pinned in `note-invariants.md` §12, never
   improvised. Damaged markers: rebuilt from `<CODE>_L<NN>_Overview.md`.
3. `terms --course <c> --code <CODE> --apply` — term index rebuilt wholesale.

Then `shared/scripts/check_links.py check` on what this run wrote and on links
pointing into it. Report broken file links and broken heading anchors;
**repair neither here.** A broken anchor is skill D's to fix from your report; a
broken file link means a missing file, which belongs to A or B.

The single exception is the `retarget` call in Pass C, already made by this
point: a link this run wrote into a section this run renamed, inside this
lesson's folder or the overview. That break is created and closed inside one
pass, so it never reaches the report. Everything wider stays D's.

## Artefacts and re-run semantics

| Path | Re-run |
|---|---|
| `Final_notes/<CODE>_L<NN>_Final_notes.md` | full rewrite, `## My additions` and the `ranking:yours` block preserved |
| `<CODE>_L<NN>_Overview.md` | full rewrite, `## My notes` preserved |
| `Articles/`, `Videos/`, `Links/` shared notes | **additive**, per-lesson sections |
| `Table_of_contents.md` | upsert of this lesson's block, term index rebuilt |
| `.data/terms.json`, `.data/concepts.json` | read and updated, never pruned |
| `.work/A_*.md`, `B_spine.md`, `C_draft.md`, `D_verification.md` | overwritten |
| `.work/transcript_corrections.md` | overwritten. No `A_` prefix: that namespace is extractions only |
| `.work/history/<CODE>_L<NN>_Final_notes_<stamp>.md`, `<stamp>` = `%Y-%m-%dT%H-%M-%S` | appended before overwrite. Skill D **adds** `*_pre-c-<id>.md` versions here; leave them alone |

Nothing is pruned automatically — deleting needs a per-session grant, and skill
A reports archive size and cleans up on request.

**Skill D's edits are not merged.** Between runs D corrects passages, places
items from `## Uncovered material` and adjusts `coverage:`. A regeneration
overwrites all of it. That is why check 9 warns and why the report ends with the
replay step.

Frontmatter carries `sources`, `sources_hash`, `sources_stat`, `inputs`,
`coverage`, `highlights`, `exam_signals`, `assessed_in`, `flags`, `generated`,
`run`, `generator`. **Write `run:` and `generated:` quoted**, in the notes and
in the overview, as the templates do: `run: "2026-11-13T15:31:51"`. Bare, a
timestamp with seconds is read by YAML as a datetime, no longer equals the
same `run` in the `.work/A_*.md` headers, and every gate that checks the
extractions against the notes fails (`note-invariants.md` §10). Get all four
source values from one call:

```bash
python3 scripts/preflight.py sources --course <c> --lesson L03 --sources <entry> ...
```

`inputs` records the overview row, the assignment rows listing this lesson, and
the id and `right` text of every erratum covering this lesson's sources — so a
new or withdrawn erratum makes the notes stale. Rows compare by **parsed cells
with spaces trimmed**; a table re-padded by Obsidian is not a change. File-name
comparisons ignore the leading `<CODE>_`, so a course-code rename costs nothing.

`sources_hash` covers file **contents**, annotation layers included: annotating
a chapter is itself a reason to re-run. It covers nothing else, so a folder
rename or a renumber does not move it — `inputs` catches those, because the
row's `No` cell changed. Say plainly that such a lesson must be re-run.

## Renumbering

On the next run that passes pre-flight **and writes notes**, before anything is
written, apply every unapplied renumber block from `_Inbox/_filing_log.md`:

```bash
python3 scripts/concepts.py migrate --course <c> --apply
python3 scripts/terms.py migrate --course <c> --applied <ids> --apply
```

All moves of a block go together. Then the `## Used in L<NN>` headings and
`used_in` lists in shared notes, and the term index in `Table_of_contents.md`.
**Not the TOC marker pairs** — skill A already migrated those. Block ids go into
`applied_renumbers` in `concepts.json`, so each is applied once. A run that
stops earlier applies nothing, which is what makes "older than my latest run"
mean "already applied".

## Language

`notes_language: auto` means **dominant source language**, resolved per run from
this lesson's sources. Never follows the setting: folder names, file names,
prefixes, frontmatter keys and enum values, structural headings, marker
comments. Quotes stay in their original language; terms go bilingual.

## Reporting

One report per run.

```
Lesson 03 (2026-03-12), Advanced Econometrics

Sources    4 (slides 48, book §15.1-15.4 / 21pp, transcript 9.4k words, notes 6 items)
Marks      14 highlights (11 embedded, 3 handwritten), 4 margin annotations
Videos     2 assigned (1 captions fetched, 1 metadata only)
Extracted  112 items  ->  spine: 9 sections, 23 subsections
Written    ECON_L03_Final_notes.md  (4,100 words, 31 formulas)
Coverage   110/112  ⚠️ 2 uncovered -> .work/D_verification.md
Terms      14 defined (3 new, 11 reused), 1 kept as corrected by course-corrections
Errata     2 applied (S22, B15.3), 1 not applied: source changed (S07)
Links      41 checked, 0 broken, 2 retargeted after a rename in this run
TOC        Table_of_contents.md updated (L03 block, term index rebuilt)
Flags      2 OCR formulas, 3 handwritten highlight spans need verification
Concepts   9 (7 reused, 2 new), 1 heading changed (zone move): "IV intuition" -> "Instrument exogeneity"
Remember   6 must-know, 4 also-likely · drift: 1 in, 1 out, 1 reworded (judgement, not a source)
Figures    6 embedded of 14 images read; the rest were decoration or repeats
Assessed   Assignment 1 tasks 3, 4 mapped; task 5 not covered in this lesson
Next       corrections exist for L03 -> run course-corrections replay, then revision
```

**Always end with the next step, naming the skill to run.** You never invoke
another skill.

## Things that are always true

- Two courses or two lessons match → **ask.** Never guess.
- A blank `Chapters` cell is never "no reading". That is `-`. Stop and ask.
- No book index for the cited book → stop and ask for course-setup. You never
  build one.
- An unknown extension → stop, propose a row for `shared/formats.md`, apply only
  after approval. Never guess a handler.
- An exam, mock, attempt or assignment file in `Content/` → stop and ask to
  refile through course-setup. Never a lesson source.
- A `book_`-prefixed file in `Content/` → stop and ask. Books live in `Books/`.
- `terms.json` or `concepts.json` missing while the course has notes → **stop.**
  Say what will drift, and start a new one only on confirmation. On a course
  with no notes yet, create it empty and continue.
- An assigned video or link that will not fetch → list it, flag it, continue.
  Never attempt credentials, never follow a paywall. A link resolving to a PDF
  over ~40 pages is reported as something to file through course-setup, not
  fetched inline.
- The user asks you to fix or correct existing notes → course-corrections. To
  explain content → course-explain. To write revision questions → course-revision.
- The user asks you to solve, outline or hint at an assignment → **refuse.** No
  skill in this plugin does this.
- Nothing to do → say so in one line. A no-op run is a valid outcome.
