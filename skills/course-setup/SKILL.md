---
name: course-setup
description: >-
  Create and maintain a university course's folder structure in an Obsidian
  vault, file lecture material (slides, transcripts, notes, handouts,
  articles, books, past exams, assignment briefs, answer sheets, video and
  link lists) into the correct lesson or tutorial folder under the naming
  convention the other skills expect, and build the chapter index for the
  course textbook. Use whenever the user sets up a course, asks where to put
  material, hands over a file to be saved or filed, asks to check, fix, adopt
  or reorganise a course folder, undo a filing, rename a course code, start a
  semester, trim the filing log, or points at a folder that breaks the
  convention. Use it even when unnamed, and first whenever a file is attached.
  NOT this skill for study notes (course-notes), revision questions, mock
  exams or grading (course-revision), corrections to notes
  (course-corrections), or explanations (course-explain). It never writes
  notes and never solves assignments.
---

# course-setup

You own **every visible folder, every file move, and the book index.** Nothing
else in the plugin moves a file or creates a visible folder.

## Before anything else

1. Read `shared/runtime.md` and settle where the scripts run. The vault is on the
   user's computer; this plugin is not. Getting this wrong makes every gate pass
   against an empty directory.
2. Read `shared/folder-structure.md`. You are its authority: if it and your
   behaviour disagree, your behaviour is the bug and the document gets corrected.
3. For a request that might belong to another skill, read `shared/routing.md`.
   **A file attached to the request is yours first, always**, even when the same
   message asks for notes or grading. File it, then name the skill to run next.

## The actions

| Action | When | Shape |
|---|---|---|
| `init` | once per course | interview → folders → scaffolding → report |
| `file` | weekly | gather → propose one plan → confirm → move → log → report |
| `validate` | **every run** | scan → auto-fix the safe class → propose the rest |
| `undo` | rare | reverse the most recent filing batch |
| `rename code` | rare | rename files, rewrite link targets, verify |
| `prepare exams` | on request | create the whole `Exams/` tree |
| `new semester` | once per term | new semester folder, archive finished courses |
| `trim log` | on request | drop old filing batches, keep every renumber block |

`validate` is not only a command. It runs as the first step of `init` (to detect
an existing course) and as the last step of `file`.

## Resolving the course

Use `vault.py resolve`. The ladder is in `shared/folder-structure.md` §11 and is
the same one every skill uses. Then apply your one extra branch:

| Resolved folder | Branch |
|---|---|
| `Weekly_overview.md` with a `code:` | a conforming course, proceed |
| exists, has content, no overview | **validate runs read-only.** Ask: new course here, or adopt what is in it |
| exists, empty | ask: create a new course here |
| does not exist | ask before creating anything |

**For `file`, ask even on a single weak match.** When the notes skill resolves
wrong it writes a file that is visibly about the wrong lesson. When you resolve
wrong you move files somewhere unexpected and it can go unnoticed for weeks.

## Boundaries

**You write:** every visible folder, `_config.md`, `Weekly_overview.md` (both
tables), `_Structure.md`, the optional course-root prose files, the initial
`Table_of_contents.md`, an empty `.data/terms.json`, `Content/videos.md`,
`Content/links_*.md`, book indexes in full, and the filing log.

**You never author or alter content** in a file another skill owns. The list is in
`shared/folder-structure.md` §5 and §7. In particular you never open
`notes_corrections.md`, `corrections.json`, `source_errata.json`,
`shared_corrections.md`, `.data/history/`, or anything under `Explanations/`.

**Reading exceptions — five, and anything outside them is a defect:**

1. the supplied syllabus at init, that file only
2. the book being indexed, in full
3. the classification sniff: first page or ~500 words, never retained
4. chapter and topic inference: the lesson's own filed sources against the index
5. staleness and undo safety: `stat` plus **frontmatter only** of the notes
   skill's output, `stat` of feedback files, a filename lookup in
   `exam_profile.json`. Never a body, never a write.

**The one sanctioned exception** is a course-code rename or a lesson renumber,
where you may rename other skills' files, archives included, and mechanically
rewrite link targets and TOC markers inside them. Mechanical means: an exact old
token replaced in a file name, a wikilink target or a `<!-- toc:... -->` pair,
with a count reported. No prose is read or altered.

## file

**Intake.** `_Inbox/` at the course root, or an explicit path. Never
`_Inbox/_conflicts/`, never `_Inbox/_undone/`, never `_filing_log.md`. Files
attached in chat are written to `_Inbox/` first and then filed by the same path.

**Classify** with `classify.py`. It returns a kind, a confidence and any exam or
assignment signal words it found.

- `low` rows are **never applied.** They stay in `_Inbox/` unless the student
  confirms them in the reply.
- **Any exam or assignment signal caps a row at `low`**, whatever else matched.
  A past exam misfiled as a handout becomes a priority-1 lesson source for the
  notes skill and is invisible to the revision skill, and nothing downstream can
  detect that. Propose the most likely of the five kinds and ask.

**Infer the overview row** with `infer_row.py` when the lesson has no row yet. It
matches the deck and transcript against the book index's *section descriptions*,
not titles, and returns a proposed range with a confidence and a caveat. Blank
cells are not neutral: the notes skill's chapter check would pass vacuously and
it would write notes with a whole priority-1 source missing while reporting 100%
coverage. `cont.` and `-` are both legal and complete; a blank cell never is.

**One plan, one table, for the whole batch.** Everything decided appears in it:
destinations, new names, new folders, the overview row and its basis, the
tutorial-to-lesson mapping, any book index to build, and every row that will stay
in `_Inbox/`. Write nothing before approval.

```
Filing 5 files into ECON_Advanced_Econometrics

| # | Source                     | Destination                      | New name                    | Conf |
|---|----------------------------|----------------------------------|-----------------------------|------|
| 1 | _Inbox/Lecture3.pptx       | Lessons/03_2026-03-12/Content/   | slides_lecture3.pptx        | high |
| 5 | _Inbox/scan.pdf            | ?                                | ?                           | low  |

New folders: Lessons/03_2026-03-12/{Content,Final_notes}
Weekly_overview: new row
  lesson | 03 | 2026-03-12 | Instrumental variables | Wooldridge | 15.1-15.4
  Topic and chapters inferred from slides + transcript vs the book index (med).
Book index: Wooldridge, 878 pages, ~118 sections. Building it takes a while. Build it now?
Row 5 is low confidence and stays in _Inbox unless you tell me what it is.

Apply?
```

**Reply protocol:**

| Reply | Effect |
|---|---|
| approval, no mention of a row | that row keeps its destination — **unless it is `low`**, which stays in `_Inbox/` |
| a correction to a filename only | applied directly, at `high` |
| a correction to a row's **kind, lesson number, type or date** | recompute the derived block and **reprint the amended plan**, then re-ask |
| a correction naming a forbidden destination | **the whole batch aborts before any file moves**; name the row and the reason |
| an explicit rejection | that row stays in `_Inbox/` |

The reprint exists because the plan's safety property is that everything decided
appears in it. "Row 1 is lesson 4, not 3" silently changes the folder set, the
row number, the date and the inferred chapters.

**Apply** with `apply_plan.py`. It opens the log block before anything moves and
appends each row as it completes, so an interrupted run is always recoverable.
Moves are moves for anything from `_Inbox/`; for an external path, ask once per
batch whether to move or copy, defaulting to move, and the answer is recorded.

**Ask, never infer, for:** which lesson a tutorial covers (the lag between a
lecture and its tutorial varies), which lessons and tasks an assignment brief
covers, and which exam a solutions file or an attempt belongs to.

**After filing into a lesson that already has notes**, say so: the notes are now
stale, and name the notes skill. Never edit them, never invoke it.

## validate

Run `validate.py scan`. It returns findings in three classes and you treat them
differently:

- **auto** — cannot lose data. Apply with `--apply-auto` and report. An
  auto-appended overview row is **incomplete by construction**: report it as
  needing completion with the line quoted, rather than as fixed.
- **propose** — touches an existing file. Show it, confirm it, then apply. After
  **any** folder rename, run `check_links.py rewrite` and report the counts.
- **report** — not yours to touch, or needs a decision.

Two report rows are a **standing tripwire**, not a check, and they are the most
important output this skill produces:

| Row | Meaning |
|---|---|
| `quarantine_breach` | a notes file names a path under `Explanations/` in `sources`, `sources_stat` or `inputs`. Tutor prose has been ingested as course material. **Never auto-fixed:** deleting the path would not remove the prose from the body. The remedy is to restore the quarantine rule in the notes skill and re-run notes for that lesson. |
| `stray_explain_file` | a file under `Explanations/` that is not `<CODE>_<concept-id>_Explained.md`, or an explain data file outside `.data/` |

They verify a boundary maintained in four other skills, so an edit to the notes
skill can break it without touching the explain skill. That is why they run every
time rather than once at install.

**Read-only is not optional.** On a folder that is not yet a conforming course,
every finding becomes a proposal, because init and adoption both promise that
nothing is written before approval and validate runs before that approval.

**A renumber is the heavy case.** Before moving anything, list every `cont.` row
whose predecessor changes and ask, per row: keep `cont.`, or freeze it to the
reading it currently resolves to. Then rename the notes and revision files and
their archives, rewrite link targets and the TOC marker pairs (**you alone
migrate those**), update the overview `No` cell, tutorial `Lesson` cells and the
same-type entries in the Assignments table, and write a renumber block. The other
skills migrate their own records from it; you never edit their JSON. Tell the
student to re-run notes, because the body still shows the old number.

## Book index

`book_index.py`. Structure first, so chapter ranges resolve immediately even if
the run is interrupted. Then descriptions, section by section, saved as they go,
resuming from the last one written.

Descriptions are built **eagerly for the whole book**, because `infer_row.py`
matches a lesson's slides against them. Lazy descriptions make that circular.
Report the size and ask once before starting; a decline is recorded in the
index frontmatter and never proposed again.

Failure modes: no outline and no findable contents page → ask for the
chapter-to-page mapping and write it from the answer. No text layer → titles
only, no page ranges, and warn that the notes skill will stop and ask. A
placeholder → hard fail for that file, continue with the rest of the batch.

## rename code

The most destructive thing you can do. `rename_code.py plan` first, always: it
prints the file count, the link count and the folder rename. Apply only after
confirmation, then re-run the link check and report what is still unresolved.

No `.data/` file is rewritten, by contract rather than luck. No skill needs a
re-run afterwards: file-name comparisons everywhere ignore the course-code token.

## adoption

Triggered when `init` is pointed at a folder that already exists. Run the
identity questions and the interview first, so the migration plan can use the
real code and language, then the full read-only scan, then print the complete
plan file by file, then apply. Two rules worth stating out loud to the student:

- Hand-written notes found in the folder become `Content/notes_<slug>.md`, never
  content under `Final_notes/`. They are priority-3 sources, which is what they are.
- An existing folder literally named `Final_notes` with hand-written content is
  reported and not touched. Ask: the notes skill will overwrite that path.

## Destructive operations

You delete exactly two things: an empty folder during `undo`, and old archive
versions in a cleanup the student asked for after seeing the size report. Nothing
else, ever.

- Remove a non-empty folder → **refuse.** Print the absolute path so it is one
  click away in Finder, list what is inside, and offer to move the contents to
  `_Inbox/` first so the folder becomes empty.
- Remove a file → refuse, same pattern.
- Overwrite a scaffolding file you own → allowed, **after showing what changes**.
- Overwrite anything else → refuse.

The vault is iCloud-synced: a deletion reaches every device within seconds, and
gets there before the student notices the mistake. `undo` sets files aside in
`_Inbox/_undone/` instead, which intake never picks up again.

## undo

`undo.py inspect` first. It reverses **the most recent `## batch` block and only
that one**; renumber and code-rename blocks are never undone. It refuses, by
name, when a file has been edited since it moved, when the notes skill has since
run on an affected lesson, when a book index it built is now cited, when the
revision skill has used a filed exam or graded an attempt, or when a renumber or
code-rename block follows the batch in the log. An `open` block is reported, not
undone: offer to complete or roll it back explicitly.

## Language

`notes_language: auto` means **dominant source language**, in this skill and in
the notes skill. There is no second meaning.

You usually run before any source exists, so: detect from the syllabus, course
description, book titles or course name; failing that write your prose in the
language of the conversation and leave `auto`. Re-resolve on the first run where
real material is filed, write the concrete value in, and **then stop detecting**.
Re-detection happens only on explicit request; otherwise the README flips
language every week.

**Never follows the setting:** folder names, file names, prefixes, frontmatter
keys and enum values, the `Table_of_contents.md` section headings, marker
comments. A Slovenian course gets `Lessons/` with a Slovenian README inside it.

## Reporting

One report per run. At most one line per phase while working.

```
ECON_Advanced_Econometrics, filed 4 items

Filed      slides, transcript, 1 article -> L03 (2026-03-12, new folder)
           1 book -> Books/
Index      Wooldridge: 24 chapters, 118 sections described
Overview   row added: lesson | 03 | 2026-03-12 | Instrumental variables | Wooldridge | 15.1-15.4
           topic and chapters inferred, med confidence
Unfiled    1 item left in _Inbox (scan.pdf, low confidence)
Structure  conforming
Warnings   L03 already has notes, now stale -> re-run notes for L03
           2 filed files are iCloud placeholders, not downloaded
Log        _Inbox/_filing_log.md · batch b7f3 · undo available
```

**Always end with the next step**, naming the skill to run. You never invoke
another skill.

## Things that are always true

- Two courses match, or one matches weakly and the action is `file` → **ask.**
- A destination already exists → never overwrite. Propose a `_2` suffix or ask.
- A code is already used by any course in any semester → refuse, suggest another.
  A reused code produces colliding file names and Obsidian resolves them silently.
- The student asks you to file into `Final_notes/` → refuse, propose
  `Content/notes_<slug>.md`.
- The student asks you to fix notes → the corrections skill. To explain content →
  the explain skill. To solve an assignment → **no skill does this.**
- Nothing to do → say so in one line. A no-op run is a valid outcome.
