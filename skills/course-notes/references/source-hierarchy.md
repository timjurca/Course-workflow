# Source hierarchy, highlights and conflicts

Read this before Pass B. It settles three questions the writing passes ask
constantly: which source wins, what a mark on a page means, and what to do when
two sources disagree.

## Contents

- [1. The priority ladder](#1-the-priority-ladder)
- [2. Classifying a file](#2-classifying-a-file)
- [3. Books and chapters](#3-books-and-chapters)
- [4. Highlights](#4-highlights)
- [5. Annotations](#5-annotations)
- [6. Conflicts between sources](#6-conflicts-between-sources)
- [7. Transcript-specific rules](#7-transcript-specific-rules)
- [8. Assignment briefs](#8-assignment-briefs)
- [9. What is never a source](#9-what-is-never-a-source)

---

## 1. The priority ladder

| Priority | Source | Prefix | Role |
|---|---|---|---|
| 1 | Book chapters | `B` | Authoritative. Definitions preferred from here. |
| 1 | Lecturer slides | `S` | Authoritative. Determines section order. Speaker notes `S12n`. |
| 1 | Lecturer handouts | `H` | Authoritative. |
| 2 | Lecture transcript | `T` | Reasoning, emphasis, worked examples, corrections, exam signals. |
| 2 | Articles | `A` | Own shared note, linked to the concept sections. |
| 2 | Assigned videos | `V` | Own shared note. Content from captions. |
| 2 | Assigned links | `K` | Own shared note. `K`, not `L`: `L` already means lesson. |
| 3 | Student notes | `N` | Never a standalone claim. Callout plus a coverage requirement. |
| 3 | Student annotations | `C` | Same treatment as `N`. |
| — | Student highlights | `!` on the host ID | Not a source. Salience on a priority-1 item. |
| — | Assignment briefs | `G` | Not content. A signal that a concept is assessed. Never in coverage. |

**A marker is the ID verbatim.** `[B15.1]`, never `[B §15.1]`. Several IDs in
one bracket are comma separated: `[S14, B15.1]`. Pass D compares markers to
extracted IDs by exact string, so any decoration produces a false coverage gap
that no repair pass can close.

**Priority decides whose wording governs, not whose content survives.** Nothing
is dropped for being priority 3. A student note that contradicts the book is
kept as a callout beside the authoritative version, and the contradiction is
flagged.

`classify.py`'s `B_SOURCE` table matches this one exactly: kind, ID prefix and
priority all come from there, and there is nothing to reconcile.

> **A specific that only the transcript supports is not evidence.** A number, a
> year, a percentage or a quantity that appears in no slide, book or handout
> extraction carries `[<id>, transcript only]`. Prose that only the transcript
> supports is normal and needs no marker — most of a lecture is the lecturer
> talking. A *number* from ASR is the failure mode. `verify.py` checks it.

---

## 2. Classifying a file

1. **Filename prefix**, preferred: `slides_`, `transcript_`, `notes_`,
   `handout_`. Skill A applies these when filing, so an unprefixed file in
   `Content/` normally arrived by hand.
2. **Mandatory for `.md`.** Transcripts and student notes are both `.md`, so
   `transcript_` and `notes_` are required and an unprefixed `.md` is a
   stop-and-ask. Reserved names are exempt: `videos.md`, `video.md`,
   `links_*.md`, `notes_corrections.md`.
3. **There is no `book_` prefix.** Books live in `Books/` at course root and are
   identified by location. A `book_` file in `Content/` is a misfiling.
4. **Sniff** the rest with `shared/scripts/classify.py`, the same module skill A
   files with. One implementation, two callers: A maps the kind to a
   destination, this skill maps it to a priority and an ID prefix.
5. **Confirm the manifest only when something was sniffed.** A run where every
   file carried a prefix needs no confirmation.

**A past exam, its solutions, a mock or past-exam attempt, or an assignment file
found in `Content/` stops the run.** It is never used as a lesson source: a past
exam misfiled as a handout becomes priority-1 lesson material and is invisible
to course-revision, and nothing downstream can detect that.

---

## 3. Books and chapters

- The lesson's `Weekly_overview.md` row gives the book and the chapter list.
- `cont.` means the reading of the row it continues; `-` means no reading at all;
  **blank means the row is incomplete** and is a stop-and-ask. A blank cell
  treated as "no reading" produces notes missing a whole priority-1 source while
  coverage reports 100%.
- Chains resolve through `shared/scripts/overview.py`. A tutorial continues the
  lesson named in its `Lesson` column, and only falls back to the previous
  tutorial when that column is empty.
- **The index is matched on `book:` frontmatter**, case-insensitively, accepting
  a short form; the filename is a secondary key. A genuine tie is a question,
  never a guess, but three rules settle the ties that are not genuine:

  1. **An index with no chapter rows is not a candidate**, unless nothing else
     matched at all. A stub could never resolve a range, so it must not be able
     to block one.
  2. **Exact beats prefix beats substring.** A title equal to the cell ends it;
     otherwise a title *starting* with the cell outranks one merely containing
     it.
  3. Only inside the strongest surviving tier does a tie become a question.

  This exists because a solutions manual is titled as a **superstring** of the
  textbook it answers, so every short form of the textbook's name also sits
  inside the manual's name. No rewording escapes a bare substring test, moving
  "Solutions" to the front included, and the student ends up writing a full
  edition line into a table cell. Once the manual's own index is built, a bare
  author name is a real tie again and is asked about; the textbook's title is
  then the exact form that resolves it.
- **This skill never builds, extends or edits a book index.** Skill A owns it
  entirely, structure and descriptions alike, because A needs the descriptions
  to infer a lesson's chapters in the first place. A second builder here would
  produce a rival index beside A's and split the content across two files.

---

## 4. Highlights

A highlight is the student saying "this passage, in this authoritative source,
matters". It is a stronger signal than a note written later from memory, and it
**keeps the priority of its host**: `B15.2` stays priority 1.

Three effects:

1. **Coverage guarantee.** Anything highlighted appears in the body.
2. **Emphasis**, as Obsidian `==highlight==`, subject to the span rules.
3. **Section forcing.** Highlighted content the lecturer never covered still
   gets its own section, marked `[B15.7, not lectured]`. "In the book but never
   lectured" is a different exam risk and the notes must say which it is.

### By span

| Span | Treatment |
|---|---|
| up to ~2 sentences | verbatim `==text==` inline, exact wording guaranteed |
| ~3 to 8 sentences | concepts extracted, coverage at concept level, one `==mark==` on the single most load-bearing sentence |
| a paragraph or more | a **salient region**, not a quote: `> [!tip] Heavily marked in the source [B15.2]`, every concept inside covered, no verbatim reproduction, no inline marks |

`extract_annotations.py` returns the class; the treatment is the writer's.

### When a chapter is over-marked

The marks still count, but selection applies. In priority order:

1. definitions and named concepts
2. assumptions, conditions, scope restrictions
3. theorem, proposition or result statements
4. formulas and their variable definitions
5. causal or directional claims
6. stated exceptions and counterexamples

De-prioritised: worked examples, restatements, motivating prose, transitions,
historical asides.

**Every down-weighted highlight goes in `.work/D_verification.md`**, so the
selection is auditable rather than invisible.

### Where marks come from

- **Embedded PDF annotations** — `extract_annotations.py`. Highlights store quad
  points, not text, so the text is pulled from the rectangles and snapped to
  sentence boundaries. Raw quad text is ragged: partial words at the edges,
  mis-ordered text in two columns, spans broken across pages.
- **Handwritten marks on scans** — `detect_marks.py` tier 1 (saturation mask,
  cheap, deterministic), then a vision pass for pages in the assigned range
  where tier 1 found nothing, capped, confirmed above roughly 20 pages. Tier 2
  is the only thing that catches pen underlines, margin brackets, circled terms
  and asterisks, none of which have a saturation signature.

### Four weaknesses, written in deliberately

1. **Greyscale scans and photocopies defeat tier 1 entirely.** Yellow
   highlighter photocopies as light grey, indistinguishable from paper texture.
2. **Precision is mediocre.** Expect over-capture and occasional misses. Every
   handwritten-derived highlight carries `[highlight, handwritten, verify]` and
   appears in the verification report with its extracted span.
3. **False positives force content into the notes.** Accepted deliberately:
   over-capture beats dropping something the student actually marked.
4. **EPUB and Kindle highlights are unreadable.** Apple Books and Kindle store
   annotations in their own databases, not in the file. Say so once when a
   highlighted-looking EPUB turns up, then continue without them.

---

### When a student note earns a callout

A note gets its own `> [!note] Your note` callout **only when it adds or
diverges**: a formulation the sources do not have, a claim they do not make, or
a disagreement with them. A note that merely duplicates a source is **cited
inline on the sentence it duplicates** — coverage is satisfied and nothing
interrupts the concept.

Content of a callout that survives: **quote the note verbatim, then one line
stating what it adds or where it differs.** Never a description of the note.
"The six goals were copied down in full" is narration about a note, not a note.

## 5. Annotations

Sticky notes, typed comments and handwritten margin notes are `C` items,
priority 3, with the same treatment as student notes: never a standalone claim,
always a callout, always covered. DOCX comments are `C` items too.

---

## 6. Conflicts between sources

| Situation | Rule |
|---|---|
| The transcript **explicitly** corrects a slide ("ignore the typo on slide 12, the sign is negative") | The transcript wins. Write the corrected version, flag `[S12 corrected by T09]`. This is the one sanctioned exception to the ladder. |
| The transcript merely **differs** from a slide | The slide wins. Flag the difference. Neither is dropped. |
| The book contradicts the slides | Both stated, contradiction flagged, neither silently resolved. |
| Slides and book cover the same point | **One** section citing both. The book's fuller wording governs where they agree. |
| A source contradicts a student note | Write the authoritative version, keep the note as a callout, flag the contradiction. |
| A definition in `terms.json` carries `corrected_by` | Keep it. Skill D corrected it. If the source behind it changed, report the conflict and still do not overwrite. |

"Flagged" means visible in the notes and in the run report, not a silent note in
a work file.

---

## 7. Transcript-specific rules

- **Normalisation before segmentation.** ASR destroys exactly the vocabulary the
  notes are about. Build the vocabulary from slides and book first, then
  correct. Every correction is logged to `.work/transcript_corrections.md`.
- **Recap is named, never expanded.** One line:
  `**Recap of [[ECON_L02_Final_notes]]:** endogeneity, omitted variable bias`.
  Anything genuinely new inside the recap belongs to the current lesson. If the
  previous lesson was never processed, name the topics without a link.
- **Announcements** leave the notes body entirely and appear under
  `## Announcements` in the overview, with their dates.
- **Jokes, small talk, technical difficulties** are dropped and **counted** as
  `discarded, non-content`, so the coverage arithmetic still balances rather
  than quietly losing IDs.
- **Course administration** is dropped from the notes and written to the
  **overview** instead: the schedule, assignment logistics, grading, exam
  mechanics and room changes. Announcements already work this way; this widens
  the same route. Measured on EBT lesson 1, the notes carried 419 words of it
  while the overview carried 132, and four facts appeared in both.
- **Personal biography, the course-origin story and self-introductions** are
  dropped the same way. This class exists because the coverage guarantee
  otherwise forces the narrative into the notes: in EBT lesson 1, 43 of 447
  placed IDs were the lecturer's career, the reader's origin and the TA's
  background, and they had nowhere else to go.
  **The boundary is the claim, not the story.** A segment is discarded only
  when it carries no transferable claim. A segment that mixes anecdote with a
  claim is *kept* — the PhD-questionnaire story carries "theory must precede
  data collection" — and Pass C writes the claim without the anecdote. IDs stay
  atomic, so the set arithmetic is untouched.
- **Exam signals** become `> [!important] Exam signal` callouts and an
  `exam_signals` frontmatter list, each carrying its concept, so
  course-revision can consume them without re-reading a source.

---

## 8. Assignment briefs

In scope when this lesson's **prefixed** key (`L03`, `T02`) appears in the
`Lessons` cell of a `## Assignments` row in `Weekly_overview.md`.

**Read:** the task list, as `G<n>.<task>` items, and nothing else.
**Written:** a `> [!important] Assessed in [[...]], task n` callout on each
matched section, plus `assessed_in` in frontmatter.
**Never written:** task wording beyond a short title, worked steps, hints,
outlines, data, numbers, or any sentence that answers a task.
**Never opened:** `_Submission` and `_Feedback` files.

`G` IDs are excluded from Pass D. A task matching no section is reported as
"assessed but not covered in this lesson's material", never forced into one.

---

## 9. What is never a source

- **`Explanations/`.** Tutor output from course-explain. Never read, never in
  `sources:`, `sources_stat` or `inputs`, excluded from directory listings and
  staleness comparisons. If it ever entered, model prose would enter
  `sources_hash`, become notes, become exam questions, and be corrected
  against — and nothing on screen would say so.
- **`Exams/`** in full: course-revision owns it.
- **Assignment submissions and graded feedback.**
- **`notes_corrections.md`**: detected at pre-flight, never opened.
- **Structural files as prose:** `Weekly_overview.md`, `Table_of_contents.md`,
  `_Structure.md`, `*.index.md`, anything under `_Inbox/`. Read for their data
  where relevant, never as course material.

Background prose reading is exactly three files: `Course_description.md`,
`Learning_objectives.md`, `Literature.md`. Above roughly 3,000 words combined,
take only the parts relevant to this lesson's topic.
