# course-workflow

A Claude Pro plugin that runs a university course inside an Obsidian vault. You hand it your slides,
transcripts, readings and own notes; it files them, writes one consolidated study document per
lesson, checks that nothing was left out, and then helps you revise: condensed revision sheets,
practice questions and mock exams, corrections that survive a rewrite, and a tutor that explains
from your own material.

**Built for Obsidian.** Everything it writes is Markdown, but it relies on Obsidian's links
(`[[...]]`), embedded images, callout boxes and math. In another Markdown app the text is readable;
those parts do not display.

This is the instruction manual. It assumes no knowledge of the plugin.

- [Requirements](#requirements)
- [Quick start](#quick-start)
- [1. What it does](#1-what-it-does)
- [2. Install](#2-install)
- [3. Set up your first course](#3-set-up-your-first-course)
- [4. The folder convention](#4-the-folder-convention)
- [5. The weekly rhythm](#5-the-weekly-rhythm)
- [6. What to say, per job](#6-what-to-say-per-job)
- [7. When something blocks you](#7-when-something-blocks-you)
- [8. The rules that bite](#8-the-rules-that-bite)
- [9. Undo and recovery](#9-undo-and-recovery)
- [10. Developing the plugin](#10-developing-the-plugin)
- [11. Design rules](#11-design-rules)

---

## Requirements

- **[Obsidian](https://obsidian.md)** and a vault, which is a folder on your own computer. A new,
  empty vault is fine. Syncing it (iCloud, Obsidian Sync, anything else) is optional.
- **Claude Pro or higher.** Either the **Claude desktop app** with your vault folder connected to the
  conversation, or **Claude Code** running on the same computer as the vault. Which plans include
  plugins: see [Use plugins in Claude](https://support.claude.com/en/articles/13837440-use-plugins-in-claude).
- **Your course material as files:** slides (`.pptx` or `.pdf`), transcripts, the textbook as a PDF
  or EPUB, articles, your own notes. Claude asks before it installs any extra Python package a
  format needs.

The plugin cannot work without access to the vault. Claude in a browser, with no folder connected,
can only tell you so.

---

## Quick start

1. **Install the plugin.** Download the newest `.plugin` file from the
   [Releases page](https://github.com/timjurca/Course-workflow-plugin-claude/releases/latest). In Claude, go to **Customize → Plugins → Add → Upload
   plugin** and choose it.
2. **Connect your vault.** In the Claude desktop app, start a conversation and add your vault
   folder to it.
3. **Create a course.** Say **"set up a new course"** and have the syllabus at hand. Claude asks a
   few questions and builds the folders.
4. **Hand over the first lesson's material.** Say **"file these"** with the files attached, or put
   them in the course's `_Inbox/` folder and say **"file my inbox"**. You approve a plan before
   anything moves.
5. **Write the notes.** Say **"write the notes for L01"**. When they are done, try **"condense L01"**
   for a revision sheet, or **"quiz me on L01"**.

From there, [the weekly rhythm](#5-the-weekly-rhythm) is the routine, and
[what to say, per job](#6-what-to-say-per-job) lists the requests each part understands.

---

## 1. What it does

| Skill | Owns | Never does |
|---|---|---|
| `course-setup` | every visible folder, every file **move**, the book index, the filing log | write notes |
| `course-notes` | one consolidated study document per lesson, from every source, coverage checked by set arithmetic | move files, write questions |
| `course-revision` | revision questions, mock exams, grading, a durable record of what you know | write notes, copy an assignment task |
| `course-corrections` | fixing errors in notes, logging every fix, replaying them after a rewrite | write notes from sources, explain |
| `course-explain` | explaining the material as a tutor, grounded in your notes | write into any file another skill owns |
| `course-condense` | a short scannable revision sheet per lesson, projected from the finished notes | read a source, add anything the notes do not say |

Two rules hold everywhere and explain most of the behaviour you will see:

- **No skill solves an assignment.** Every one refuses, however the request is phrased.
- **No skill invokes another skill.** Each finishes, then names the one to run next. You run it.

### You do not name skills

Ask in plain language. The routing is in [`shared/routing.md`](shared/routing.md), which is the
definition, not a summary. Three routes are decided by **what is on disk**, not by how you phrase it:

| You say | Where it goes |
|---|---|
| "summarise lesson 3" | notes current → `course-explain`. Notes missing or stale → `course-notes` |
| "study lesson 3" | notes current → `course-revision`. Missing or stale → `course-notes` |
| "why was my answer wrong?" | feedback exists → `course-explain`. No feedback → it names `course-revision` and stops |
| "condense lesson 3", "the short version" | `course-condense`, whatever the notes' state, though it warns if they are stale |

The asymmetry is deliberate. Sending "summarise lesson 3" to the wrong skill either costs a
paragraph or overwrites every correction you ever made, so the default points away from the
expensive direction. Saying **regenerate**, **redo** or **write the notes** always reaches
`course-notes`, because it names the artefact instead of asking a question.

**Attach a file and `course-setup` goes first, always.** Every other skill stops and says so.

---

## 2. Install

Download `course-workflow-<version>.plugin` from the [Releases page](https://github.com/timjurca/Course-workflow-plugin-claude/releases/latest) and
add it in Claude under **Customize → Plugins → Add → Upload plugin**. The plugin is installed **on
your account**, so it is available in every conversation. To update, upload the newer file the same
way.

**Connect the vault in every conversation that uses the plugin.** The plugin and your vault are
usually on two different machines: the plugin lives where Claude runs, your vault lives on your
computer. Every script in this plugin walks the vault, so without access it would report an empty
course; instead it stops and says so. The details are in [`shared/runtime.md`](shared/runtime.md).

**One thing appears in your vault that you did not make:** the first time it runs, the plugin
copies its scripts into `<vault>/.course-plugin/`, a dotted folder Obsidian does not show. That is
where the checks actually run. If your vault syncs, the folder syncs with it, so every computer you
use has it. Claude compares `<vault>/.course-plugin/VERSION` with the installed plugin and refreshes
the folder after an update. Leave it in place.

---

## 3. Set up your first course

Say: **"Set up a new course"**, and have the syllabus to hand.

`course-setup init` runs an interview, then creates the folders, the scaffolding files and an empty
term ledger. Three answers matter more than the rest:

| Answer                          | Why it matters                                                                                                                                                                                            |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **The course code/abreviation** | Must be unique across your **whole vault**, every semester included. A reused code produces colliding file names and Obsidian resolves them silently. 2 to 8 characters, uppercase and digits.            |
| **The textbook**                | If you supply one, say yes to building the index. It takes a while and it is what lets the plugin resolve "chapters 4 and 7" into real page ranges later. A decline is recorded and never proposed again. |
| **The language**                | `auto` means the dominant language of your sources. Folder names, file names and structural headings stay English regardless.                                                                             |

Then hand over your material: **"file these"** with the files attached, or drop them in
`_Inbox/` and say **"file my inbox"**.

Filing always shows you **one plan table** before it moves anything: every destination, every
rename, every new folder, and the row it will add to `Weekly_overview.md`. Nothing is written until
you approve. Reply "yes", or with numbers to apply a selection, or correct a row in prose and the
plan is reprinted.

> **Low-confidence rows are never applied on a silent yes.** They stay in `_Inbox/` until you say
> what they are. Anything that looks like an exam or an assignment is capped at low confidence
> whatever else matched, because a past exam misfiled as a handout becomes a priority-1 source for
> your notes and nothing downstream can detect that.

---

## 4. The folder convention

You do not have to create any of this by hand. Knowing it helps you see when something is misfiled.

```
Vault root/
├── _config.md
└── Q1/                                       semester folder
    └── 01_EBT_Emerging_and_breakthrough_Technologies/     [NN_]<CODE>_<Course_Name>
        ├── _Structure.md            the conventions, written for you
        ├── _Inbox/                  unfiled material + _filing_log.md
        ├── Weekly_overview.md       the lesson table: number, date, topic, book, chapters
        ├── Table_of_contents.md
        ├── Books/                   the textbook and its .index.md
        ├── Articles/  Videos/  Links/        shared notes, course-wide
        ├── Explanations/            created on demand, by course-explain only
        ├── .data/                   term ledger, concept registry, findings
        ├── Lessons/
        │   └── 03_2026-09-22/       NN_YYYY-MM-DD, zero padded
        │       ├── EBT_L03_Overview.md
        │       ├── notes_corrections.md      the correction log
        │       ├── Content/         slides_, transcript_, notes_, handout_
        │       ├── Articles/        created only when an article is filed here
        │       ├── Final_notes/     your study document
        │       └── .work/           extractions, drafts, verification, history
        ├── Tutorials/               same internal structure
        ├── Assignments/
        └── Exams/
            ├── Past_exams/  Mock_exams/  Revision_questions/
```

Three things worth internalising:

- **Nothing reads a lesson folder root.** A source file left there, rather than inside `Content/`,
  is invisible to `course-notes`, which will then report complete coverage over material it never
  opened. `validate` catches this and proposes moving it.
- **Content files need their prefix.** `slides_`, `transcript_`, `notes_`, `handout_`. A deck
  without `slides_` is not seen as a deck.
- **Books live in `Books/` at the course root**, never inside a lesson. There is no `book_` prefix:
  living in `Books/` is what identifies a book.

Full contract, including `slugify` and how the vault and course are resolved:
[`shared/folder-structure.md`](shared/folder-structure.md).

---

## 5. The weekly rhythm

```
   lecture happens
        |
   [1]  file the material          "file these"           course-setup
        |
   [2]  write the notes            "write the notes for L03"   course-notes
        |
   [3]  read them, fix what is wrong   "L03 says X, that is wrong"   course-corrections
        |
   [4]  condense it for revision    "condense L03"         course-condense
        |
   [5]  test yourself              "quiz me on L03"       course-revision
        |
   [6]  ask about what you missed  "I do not understand X"     course-explain
```

Step 1 before step 2, always. The rest is as needed. Before an exam, add
**"build me a mock exam"**, then file your attempt and say **"grade this"**.

Each run ends by naming the next step. Follow it or ignore it, but it is the plugin telling you what
it thinks is now stale.

---

## 6. What to say, per job

Plain language. These are examples, not commands.

### Filing and structure, `course-setup`

| Job                              | Say                                       |
| -------------------------------- | ----------------------------------------- |
| File this week's material        | "file these" (attach), or "file my inbox" |
| Check the folder is sane         | "check my course folder"                  |
| Adopt a folder you built by hand | "set up a course here" pointed at it      |
| Index the textbook               | "build the book index"                    |
| Rename a course code             | "rename the code to XYZ"                  |
| Undo the last filing             | "undo that filing"                        |
| Create the exam folders          | "prepare revision folders"                |
| Start a new term                 | "start a new semester"                    |
| ...                              | ...                                       |

### Notes, `course-notes`

| Job                                          | Say                       |
| -------------------------------------------- | ------------------------- |
| Write a lesson's notes                       | "write the notes for L03" |
| Redo after new material                      | "regenerate L03"          |
| Add figures to notes that only describe them | "add the figures to L03"  |
| ...                                          | ...                       |

### Corrections, `course-corrections`

| Job                       | Say                                              |
| ------------------------- | ------------------------------------------------ |
| Something is wrong        | "L03 says the threshold is 1.0, it should be 10" |
| Not sure it is wrong      | "I think this is wrong but I am not sure"        |
| After a regeneration      | "bring my corrections back"                      |
| You hand-edited the notes | "I edited L03 by hand"                           |
| Walk the open findings    | "go through the open findings"                   |
| Reverse the last run      | "undo that correction"                           |
| ...                       | ...                                              |

### Revision, `course-revision`

| Job | Say |
|---|---|
| Practice questions | "quiz me on L03" |
| Mock exam | "build me a mock exam" |
| Mark your attempt | "grade this" (after filing it) |
| Readiness | "am I ready?" or "what is still open?" |

### Condensed notes, `course-condense`

| Job                             | Say                                                                  |
| ------------------------------- | -------------------------------------------------------------------- |
| Short version of a lesson       | "condense L03"                                                       |
| A revision sheet before an exam | "make me a revision sheet for L03"                                   |
| A whole course at once          | "condense all of EBT" (safe to run in parallel, unlike regenerating) |
| Check they are up to date       | "are my revision sheets current?"                                    |
| ...                             | ...                                                                  |

A revision sheet carries **contents, not calculations**: every concept and every
formula, rule tables (NPV > 0 accept, NPV < 0 reject), the lesson's figures and factual
numbers, but no worked examples, calculations or data tables. Those stay in the full
notes, one click away.

### Tutor, `course-explain`

| Job                     | Say                                         |
| ----------------------- | ------------------------------------------- |
| Explain a concept       | "I do not understand the valuing principle" |
| Derive a result         | "show me why that follows"                  |
| Why an answer was wrong | "why was my answer to Mock 01 Q3 wrong?"    |
| What to learn first     | "what do I need to know before X?"          |
| Keep an explanation     | "save that explanation"                     |
| ...                     | ...                                         |

---

## 7. When something blocks you

A skill that stops has usually found something real. The checks are hard failures on purpose: none is a warning you can step over. Here is what each refusal actually means.

| What it says | What happened | What to do |
|---|---|---|
| **"no Final_notes file"** | You asked for questions or corrections on a lesson with no notes | Run `course-notes` first |
| **"the notes are current" fails** | A source changed, or a file was filed since the notes were written | Regenerate that lesson. The report names the file |
| **"notes predate concept ids"** | Notes written by an older version | Regenerate that lesson once |
| **"every extraction belongs to this run" fails** | The evidence on disk is from a different version of the material | Regenerate. A notes `run:` written with or without quotes compares the same, so a quoting difference never causes this |
| **iCloud placeholder** | A file is in the cloud, not downloaded on this machine | Open the folder in Finder and let it download, then retry |
| **conflicted copy** | iCloud made a duplicate | Move it aside, nothing is ever merged automatically |
| **`quarantine_breach`** | Tutor prose from `Explanations/` was ingested as course material | Serious. Regenerate that lesson and report it |
| **a correction is `orphaned`** | The passage it anchored to no longer exists after a rewrite | Re-place it on one of the candidates offered, or leave it orphaned |
| **"blank chapter range"** | A `Weekly_overview.md` row has no chapters | Fill it in. A blank is never read as "no reading": that would pass the coverage check vacuously |

### `Plain symbols` in the verification report

`course-notes` lists every mathematical symbol it wrote as plain text (`e_P`, `q_11`, `X^(−1/2)`)
under `Plain symbols` in `.work/D_verification.md`, each with the inline-math form to use instead.
It never blocks the write. Fix the rows by regenerating the lesson or with `course-corrections`.
`course-condense` fails its `symbols` check for the same reason, so a revision sheet never copies a
plain symbol forward.

### `Described but not shown` in the verification report

When the notes describe a picture (an intercept, a labelled point, "the slide shows", "on the
sketch") whose image is already in `Final_notes/attachments/` but is not embedded in that section,
`course-notes` lists it under `Described but not shown` in `.work/D_verification.md`. It never
blocks the write. Ask for "add the figures to L03": the figures pass embeds the flagged images, a
student sketch inside its `Your note` callout. Text that only made sense with the picture and cannot
take one goes to `course-corrections` to be reworded.

### Coverage numbers are not a score

`coverage: 664/664` means every extracted item was placed and cited. It does **not** mean every
source was read. A lesson whose articles were never opened can report a confident 100% over the
sources it did see. If you added readings to a lesson, check they appear in the notes' `sources:`
list, and regenerate if they do not.

---

## 8. The rules that bite

**One lesson at a time, per course.** `terms.json`, `concepts.json` and `Table_of_contents.md` are
course-wide and have no locking, so two regenerations in one course at once means last-writer-wins
and one lesson's concepts vanish silently. Batch mode exists and is strictly sequential. Two
different courses in parallel is fine. Two operations are exceptions, because they touch none of
those files: course-notes' figures pass, and **the whole of course-condense**. Either can run on
many lessons of one course at once.

**Nothing is written without your confirmation.** Not one character. Every plan is shown first.

**Deletion is off.** No script in this plugin deletes anything. `course-setup undo` moves files to
`_Inbox/_undone/`, which intake never picks up again, rather than removing them. If a real delete is needed you are asked once, per folder, and it is permanent with no Trash.

**If your vault syncs through iCloud**, that has three consequences: a deletion reaches every
device in seconds, a file may be a placeholder rather than real content, and Python must be told not
to write `__pycache__` into your vault. The scripts handle the third; the first two are why the
checks above exist. A vault that does not sync skips all three.

**`Explanations/` is quarantined.** Tutor prose is never read back as a source by any other skill.
`course-setup validate` carries a standing tripwire that verifies this every run, because the
boundary is maintained in four skills and an edit to one could break it without touching the others.

**Symbols are inline math.** Every symbol in running text, tables, callouts and definitions is
written `$e_P$`, `$e_{XZ}$`, `$X^{-1/2}$`, never `e_P` or `X^(−1/2)`, which Obsidian shows literally
and which can turn the words between two underscores italic. A dollar amount in prose is `\$530` or
`USD 530`, so it never opens a math span. Every skill follows this (`shared/note-invariants.md` §2d).

**Timestamps in frontmatter are quoted.** `run:` and `generated:` are written as
`run: "2026-11-13T15:31:51"`. Left bare, YAML reads a timestamp with seconds as a date, and a gate
comparing it with the extractions would see two different runs. The scripts compare runs in one
normalised form, so older notes with a bare value still work; do not unquote them by hand.

**One Claude conversation per vault at a time.** Two conversations working in the same vault share
the script folder and the course-wide records, and neither can see what the other is doing.

**Your own writing is protected.** `## My additions`, `## My notes` and `## My questions` are yours.
Every skill preserves them verbatim and `course-corrections` refuses outright to write into them.
`## What to remember` holds Claude's ranking, marked `[judgement]`; the `ranking:yours` block inside it is yours and is preserved.

---

## 9. Undo and recovery

| Situation | Route |
|---|---|
| A filing went wrong | "undo that filing". Reverses the most recent batch only. Files go to `_Inbox/_undone/` |
| A correction was wrong | "undo that correction". Reverses the most recent corrections run, from its archive |
| An older correction was wrong | "withdraw c-0003". A normal, logged, verified change |
| Notes were regenerated and you lost an edit | The previous version is in `.work/history/`. Corrections are replayed from `notes_corrections.md` |

Every write archives first. Lesson notes go to `<lesson>/.work/history/`, shared notes and the term
ledger to `.data/history/`. Undo refuses, by name, when something has happened since that would make
the reversal unsafe: notes regenerated, a revision file written, a hand edit detected.

---

## 10. Developing the plugin

For changing the plugin itself. Using it needs none of this.

**Build a package from this repository.** Bump `version` in `.claude-plugin/plugin.json`, zip the
tree (leave out `.git/`, `.claude/` and `dist/`), name it `course-workflow-<version>.plugin` and
install it as above. For local development, Claude Code can load the source tree directly, which
skips packaging:

```bash
claude --plugin-dir /path/to/course-workflow
```

The code lives in three places and they are not the same:

| Where | What | Changes take effect |
|---|---|---|
| The plugin directory | `SKILL.md`, references, templates, and the scripts | after a repackage and reinstall |
| `<vault>/.course-plugin/` | **the scripts that actually run** | immediately |
| Your source tree | the version you edit and package from | on the next build |

So a script fix reaches the vault bundle and works at once, while a change to a `SKILL.md` or a
`shared/*.md` needs a repackage. Keep the source tree and the bundle in step, or you will debug a
fix that is not running.

To release: bump `version` in `.claude-plugin/plugin.json` **and** `<vault>/.course-plugin/VERSION`
together, then rebuild the package from the source tree. The bundle refreshes when the two versions
differ, so a release built from a tree missing a hotfix will silently overwrite it.

---

## 11. Design rules

These are the constraints the code is built around. They explain why it behaves as it does.

- **Everything deterministic is a script.** Model work is judgement and prose; anchors, statuses,
  archives, hashes, set arithmetic and writes are code.
- **One implementation of anything two skills depend on.** A second slugify is a second behaviour
  waiting to drift, and nothing detects the drift. This has been violated twice and both times the
  copies diverged in ways that silently produced wrong answers.
- **Nothing is written unconfirmed**, and everything destructive is archived first and reversible.
- **A blank is never treated as a zero.** A missing chapter range, a lost term ledger and an
  un-downloaded source are all stop-and-ask, because each otherwise produces notes that look
  complete and are not.
- **Scanning nothing is a failure.** A check that finds no files reports that it found none, rather
  than reporting success.
- **Two matches are as much a failure as none.** Anything that locates a passage returns every
  occurrence and never picks between them.

## Repository layout

```
course-workflow/
├── .claude-plugin/plugin.json
├── shared/                      loaded by all five
│   ├── runtime.md               where the scripts run, and how they reach the vault
│   ├── folder-structure.md      the naming contract; course-setup is its authority
│   ├── note-invariants.md       markers, concept IDs, hashes, every cross-skill file format
│   ├── routing.md               which skill answers which request
│   ├── formats.md               extension to handler
│   └── scripts/                 modules every skill imports rather than re-implements
└── skills/
    ├── course-setup/            SKILL.md + templates + scripts
    ├── course-notes/
    ├── course-revision/
    ├── course-corrections/
    ├── course-explain/
    └── course-condense/          SKILL.md + 1 template + 3 scripts
```
