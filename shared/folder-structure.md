# Folder structure and naming contract

**Authority: skill `course-setup` (A).** A creates every visible folder and performs every file
move, so if this document and A's behaviour disagree, A's behaviour is the bug and this document
is what gets corrected. B, C, D and E read this file and never contradict it.

Read this file before creating, naming, moving or looking for anything in a course.

## Contents

- [1. The tree](#1-the-tree)
- [2. Naming rules](#2-naming-rules)
- [3. slugify](#3-slugify)
- [4. `_config.md` at vault root](#4-_configmd-at-vault-root)
- [5. Reserved names](#5-reserved-names)
- [6. Private folders](#6-private-folders)
- [7. `.data/` ownership](#7-data-ownership)
- [8. `expects` and the presence evidence table](#8-expects-and-the-presence-evidence-table)
- [9. `Explanations/` is generated, never read back](#9-explanations-is-generated-never-read-back)
- [10. iCloud](#10-icloud)
- [11. Resolving the vault and the course](#11-resolving-the-vault-and-the-course)

---

## 1. The tree

```
Vault root/
├── _config.md                                  <- A creates and maintains
└── Study/2026-Spring/                          <- A creates (semester folder)
    └── ECON_Advanced_Econometrics/             <- course root, <CODE>_<Course_Name>
        ├── _Structure.md                       <- A, README of the conventions
        ├── _Inbox/                             <- A, unfiled material
        │   ├── _filing_log.md                  <- A, append-only audit trail
        │   ├── _conflicts/                     <- A, quarantined iCloud conflicted copies
        │   └── _undone/                        <- A, files set aside by undo
        ├── Weekly_overview.md                  <- A creates and maintains
        ├── Table_of_contents.md                <- A creates skeleton, B upserts blocks
        ├── Course_description.md               <- A, only if content exists
        ├── Learning_objectives.md              <- A; B upserts the slide goals block
        ├── Literature.md                       <- A, only if content exists
        ├── Books/
        │   ├── Wooldridge_Introductory.pdf
        │   └── Wooldridge_Introductory.index.md     <- A owns entirely, B reads only
        ├── Articles/                           <- A creates at init, B writes shared article notes
        ├── Videos/                             <- A creates at init, B writes shared video notes
        ├── Links/                              <- A creates at init, B writes shared link notes
        ├── Explanations/                       <- created on demand at E's first save (§9)
        │   ├── ECON_instrument-relevance_Explained.md
        │   └── .history/                       <- E private
        ├── .data/                              <- see §7
        ├── Lessons/
        │   └── 03_2026-03-12/                  <- A creates on first filing
        │       ├── ECON_L03_Overview.md        <- B writes, A never touches
        │       ├── notes_corrections.md        <- D, pinned at the folder root
        │       ├── Content/                    <- always created with the lesson
        │       │   ├── slides_lecture3.pptx
        │       │   ├── transcript_lecture3.md
        │       │   ├── notes_my_thoughts.md
        │       │   ├── handout_problem_set.pdf
        │       │   ├── videos.md               <- A creates or appends
        │       │   └── links_reading.md        <- A creates or appends
        │       ├── Articles/                   <- created only when an article is filed
        │       ├── Final_notes/                <- always created, B writes into
        │       │   ├── ECON_L03_Final_notes.md
        │       │   └── attachments/            <- B private
        │       └── .work/                      <- B private
        │           └── history/                <- B private; D adds *_pre-c-<id> versions
        ├── Tutorials/
        │   └── 02_2026-03-14/                  <- same internal structure
        ├── Assignments/                        <- A creates on demand, files briefs
        └── Exams/                              <- A creates the whole tree, never partially
            ├── Past_exams/                     <- A files, C reads
            ├── Mock_exams/                     <- C writes, A files attempts
            ├── Revision_questions/             <- C writes
            └── .work/                          <- C private
```

**Folders are created on demand.** There is no persisted list of folders a course "should" have, and
`validate` never recreates a folder the student removed, with these exceptions, which exist because a
skill writes into them on every run: `_Inbox/`, the course-root `Articles/`, `Videos/` and `Links/`,
a lesson's `Content/` and `Final_notes/`, and a missing subfolder of an existing `Exams/` tree.
`Explanations/` is **not** on that list (§9).

**`Exams/` is created as a whole tree or not at all** — `Exams/` plus `Past_exams/`, `Mock_exams/`,
`Revision_questions/` — in one of three cases: at init when the course has an exam, when the first
`past_exam`, `past_exam_solutions`, `mock_attempt` or `past_exam_attempt` is filed, or on the explicit
request "prepare revision folders".

**Creating a lesson or tutorial folder always creates `Content/` and `Final_notes/`.** B hard-fails
without `Content/`, so its creation is unconditional, including for a lesson whose only material is a
book chapter. `Articles/` is created only when an article is filed into it.

`Course_materials.md` is **not** created. A file with no defined purpose that B would read as
background context is worse than no file.

---

## 2. Naming rules

| Item | Rule |
|---|---|
| Course folder | `[<NN>_]<CODE>_<Course_Name>`, spaces to underscores, e.g. `ECON_Advanced_Econometrics` or `01_EBT_Emerging_and_breakthrough_Technologies`. The optional two-digit prefix carries the teaching order within a term, which alphabetical sorting alone would lose. Nothing reads the folder name for meaning: every skill keys on `code:`. |
| Course code | Uppercase `A-Z` and digits, 2 to 8 characters, **unique across the entire vault**, every semester included |
| Lesson/tutorial folder | `NN_YYYY-MM-DD`, regex `^(?P<num>\d{2})_(?P<date>\d{4}-\d{2}-\d{2})$`, zero padded so alphabetical sort equals chronological sort |
| Lesson subfolders | `Content/`, `Articles/`, `Final_notes/`, matched **case-insensitively** |
| Lesson folder root | Only `<CODE>_L<NN>_Overview.md`, `notes_corrections.md` and those three subfolders. **Nothing reads a lesson root**, so a source left there is invisible to the notes skill, which then reports complete coverage over material it never saw. `validate` proposes moving anything else into `Content/`. |
| Fixed folder names | `Lessons`, `Tutorials`, `Books`, `Articles`, `Videos`, `Links`, `Explanations`, `Content`, `Final_notes`, `Assignments`, `Exams`, `Past_exams`, `Mock_exams`, `Revision_questions`. Never localised, never re-spelled, never re-cased. |
| Content file prefixes | `slides_`, `transcript_`, `notes_`, `handout_`. There is no `book_` prefix: books are identified by living in `Books/`. |
| Books | Always `Books/` at course root, never inside a lesson. A book is **either a single file or a folder of chapter files** (see below). |
| Article source PDFs | Always the **lesson-level** `Articles/`. The course-level `Articles/` holds only B's generated notes. |
| Forbidden characters | `#`, `^`, `[`, `]`, `\|`, `:` in any folder or file name a skill creates or renames to |
| Structural names | Fixed English, whatever `notes_language` says |

**Two keys, not one.**

| Key | What it is | Where it lives |
|---|---|---|
| Folder name `<CODE>_<Course_Name>` | The **addressing** key: how a course is found on disk and in `active_courses` | The folder itself, plus `_config.md` |
| `code:` | The **naming** key: what prefixes every generated filename and wikilink target | `Weekly_overview.md` frontmatter |

A verifies on every run that the folder name carries `code:` as its code segment, ignoring any
`<NN>_` sort prefix. A disagreement means
one of them was hand-edited; it is proposed as a fix and never silently repaired, because either value
could be the intended one.

**Why generated files carry the course code.** Obsidian resolves `[[wikilinks]]` by filename
**vault-wide**, not per folder. Without a code and an `L`/`T` marker, lesson 3 of every course collides
on one name and Obsidian picks a target silently. This applies to attachments too.

### Names on filing

| Kind | New name |
|---|---|
| slides, transcript, notes, handout | `<prefix>_<slug>.<ext>` |
| article | `<author>_<year>.pdf`, no prefix |
| book | `<Author>_<ShortTitle>.<ext>` (original capitalisation kept, transliterated and stripped) |
| video and link lists | `videos.md`, `links_<slug>.md` |
| past_exam | `Exams/Past_exams/<CODE>_Past_<YYYY-MM-DD>[_P<n>].<ext>` |
| past_exam_solutions | `Exams/Past_exams/<CODE>_Past_<YYYY-MM-DD>[_P<n>]_Solutions.<ext>` |
| mock_attempt | `Exams/Mock_exams/<CODE>_Mock_<NN>_Attempt_<YYYY-MM-DD>.<ext>` |
| past_exam_attempt | `Exams/Mock_exams/<CODE>_Past_<exam date>[_P<n>]_Attempt_<YYYY-MM-DD>.<ext>` |
| assignment | `Assignments/<CODE>_Assignment_<NN>.<ext>`, plus `..._Submission.<ext>` and `..._Feedback.<ext>` |

### Generated file names

| File | Name |
|---|---|
| Lesson notes | `Final_notes/<CODE>_L<NN>_Final_notes.md` (`T` for tutorials) |
| Overview | `<CODE>_L<NN>_Overview.md` at the lesson folder root |
| Figure | `Final_notes/attachments/<CODE>_L<NN>_fig_<sourceID>_<slug>.png` |
| Shared article note | `Articles/<CODE>_<Author_Year_Slug>.md` |
| Shared video note | `Videos/<CODE>_<Channel_Slug>.md` |
| Shared link note | `Links/<CODE>_<Site_Slug>.md` |
| Extraction | `.work/A_<slugify(entry without the #range)>.md` |
| Notes archive | `.work/history/<CODE>_L<NN>_Final_notes_<stamp>.md`, `<stamp>` = `%Y-%m-%dT%H-%M-%S`. Hyphens, not colons: §2 forbids `:` in any name a skill creates, and the seconds make the name unique so no disambiguating suffix is ever needed. |
| D's pre-correction archive | `.work/history/<name>_pre-c-<id>.<ext>`, or `.data/history/...` for shared notes and `terms.json` |
| Revision file | `Exams/Revision_questions/<CODE>_L<NN>_Revision.md` |
| Mock exam | `Exams/Mock_exams/<CODE>_Mock_<NN>.md`, `..._Solutions.md`, `..._Feedback_<date>[_<n>].md` |
| Saved explanation | `Explanations/<CODE>_<concept-id>_Explained.md` |

**Course-code token.** When file names are compared, or a recorded path is looked up, the leading
`<CODE>_` is ignored and the rest of the name is matched. This is what makes a course-code rename
cost nothing: no skill has to re-run because of one.

---

## 3. slugify

Normative. Implemented once in `shared/scripts/naming.py`; nothing re-implements it.

1. Lowercase.
2. Transliterate diacritics to ASCII (`č`→`c`, `š`→`s`, `ž`→`z`, `é`→`e`, …).
3. Spaces, hyphens, dots and `/` become `_`.
4. Drop every forbidden character (§2).
5. Collapse runs of `_` into one.
6. Strip leading and trailing `_`.
7. Cap at 60 characters, cut at a word (underscore) boundary.

**Step 7 does not apply to extraction file names** (`.work/A_*.md`), which must stay unique per source.

Book and article names are the other exception: they keep their original capitalisation and are only
transliterated and stripped of forbidden characters.

---

## 4. `_config.md` at vault root

```yaml
---
courses_root: "Study/2026-Spring"
default_notes_language: auto
active_courses: ["Study/2026-Spring/ECON_Advanced_Econometrics", "Study/2026-Spring/CAUS_Causal_Inference"]
archived_courses: ["Study/2025-Autumn/STAT_Statistics_1"]
course_codes:
  ECON: "Study/2026-Spring/ECON_Advanced_Econometrics"
  CAUS: "Study/2026-Spring/CAUS_Causal_Inference"
  STAT: "Study/2025-Autumn/STAT_Statistics_1"
scaffolded_by: course-setup v1
---
```

- `active_courses` and `archived_courses` both hold **vault-relative paths**. One format everywhere.
- `courses_root` only says where A creates new courses.
- `archived_courses` is never matched by the resolution ladder; those courses are reached by explicit
  path only, and their codes stay reserved.
- `course_codes` is the **code registry**: every code ever assigned in the vault, with its course path.
  A writes it at init, adoption, code rename and new semester. B, C, D and E check uniqueness against
  it rather than scanning every `Weekly_overview.md`.
- `default_notes_language` is only the value A offers as a default for a new course. It is never a
  read-time fallback: every course carries its own `notes_language`, and that is the only value any
  skill reads per run.

**Version stamps.** Every scaffolding file A owns carries `scaffolded_by: course-setup v1` in its
frontmatter: `_config.md`, `Weekly_overview.md`, `Table_of_contents.md`, `_Structure.md`, every
`*.index.md`. A missing or outdated stamp is repaired by `validate`.

---

## 5. Reserved names

Each entry states its scope, because some apply only inside `Content/`. A treats every one of these as
already filed and never classifies it.

| Pattern | Scope | Meaning |
|---|---|---|
| `videos.md`, `video.md` | `Content/` | Assigned-video list, parsed by B |
| `links_*.md` | `Content/` | Assigned link list, parsed by B |
| `notes_corrections.md` | lesson or tutorial folder root, **pinned** | Skill D. A never moves, renames or opens it. |
| `Weekly_overview.md`, `Table_of_contents.md`, `_Structure.md` | course root | Structural files |
| `*.index.md` | `Books/` | Book indexes, A only |
| `_filing_log.md` | `_Inbox/` | A's audit trail. Never hand-edited. |
| `_conflicts/`, `_undone/` | `_Inbox/` | A's holding folders. **Never picked up by intake.** |
| `<CODE>_L<NN>_Overview.md` | lesson folder root | B's output |
| `<CODE>_L<NN>_Revision.md`, `<CODE>_T<NN>_Revision.md` | `Exams/Revision_questions/` | C's output |
| `<CODE>_Mock_<NN>.md`, `..._Solutions.md`, `..._Feedback_<date>[_<n>].md` | `Exams/Mock_exams/` | C's output |
| `<CODE>_Mock_<NN>_Attempt_<date>.<ext>` | `Exams/Mock_exams/` | Filed by A, read by C |
| `<CODE>_Past_<date>[_P<n>]_Attempt_<date>.<ext>` | `Exams/Mock_exams/` | Filed by A, read by C |
| `<CODE>_Past_<date>[_P<n>]_Feedback_<date>[_<n>].md` | `Exams/Mock_exams/` | C's output |
| `<CODE>_Past_<date>[_P<n>].<ext>`, `..._Solutions.<ext>` | `Exams/Past_exams/` | Filed by A, read by C |
| `<CODE>_Assignment_<NN>.<ext>`, `..._Submission.<ext>`, `..._Feedback.<ext>` | `Assignments/` | Filed by A. Briefs read by B and C as a signal; submissions and feedback read by nobody. |
| `<CODE>_<concept-id>_Explained.md` | `Explanations/` | E's output. Read by nobody else, ever (§9). |
| everything in `.data/` | course root | See §7 |

---

## 6. Private folders

A creates every **visible** folder. Each other skill may create only the folders listed for it here,
and nothing else.

| Skill | Private folders it may create |
|---|---|
| B | lesson `.work/`, `.work/history/`, `Final_notes/attachments/` |
| C | `Exams/.work/` and its subfolders |
| D | `.data/history/`. D additionally **adds** archive versions named `*_pre-c-<id>.*` to B's existing `.work/history/`, and changes or deletes nothing else there. |
| E | `Explanations/.history/` |

`Explanations/` itself is created by A, on demand, at E's first save.

---

## 7. `.data/` ownership

Twelve files at `<course>/.data/`. One owner each. "Writes" means the file's structure and content;
the narrow field-level grants are stated explicitly because they are the only places where a skill
writes into another skill's file.

| File | Owner | Others may read | Others may write |
|---|---|---|---|
| `terms.json` | B (A creates it empty) | C, D, E | D: `definition`, `history`, `corrected_by` only |
| `concepts.json` | B | C, D, E | nobody |
| `exam_profile.json` | C | A (filename lookup only, for undo safety), E (what the exam rewards) | nobody |
| `revision_status.json` | C | E (calibration, read-only, never recorded) | nobody |
| `revision_findings.json` | C | D | D: `status`, `closed_by`, `reason` only |
| `exam_glossary.json` | C | — | nobody |
| `corrections.json` | D | — | nobody |
| `source_errata.json` | D | B (applies it in Pass A) | nobody |
| `shared_corrections.md` | D | C (H2 header, `status`, `last_replayed` lines only), E (status lines always; `before:`/`after:` only for entries not `applied` at the notes' current `run`) | nobody |
| `history/` | D | — | nobody |
| `explain_findings.json` | E | D | D: `status`, `closed_by`, `reason` only |
| `explain_state.json` | E | — | nobody. **Never leaves E.** |

A never opens `corrections.json`, `source_errata.json`, `shared_corrections.md`, `history/` or
`notes_corrections.md`. It renames them only under the code-rename exception.

**No `.data/` file stores a course code or a lesson number in a key.** `terms.json` uses `L03`/`T02`
in `first_defined` and `seen_in`; `concepts.json` uses them in `sections[].lesson`; those are migrated
by their owners from A's renumber log blocks. C's four files store neither. This is what makes a
course-code rename need no JSON rewrite at all.

---

## 8. `expects` and the presence evidence table

`expects` lives in `Weekly_overview.md` frontmatter. Its vocabulary is closed:

`slides`, `transcript`, `book`, `notes`, `handouts`, `articles`, `videos`, `links`

Anything else is rejected at pre-flight rather than silently ignored.

**Every listed category becomes a stop-and-ask in B whenever a lesson lacks it.** List only what a
complete lesson in this course genuinely always has.

**What counts as present.** One table, because two independently written predicates would disagree and
produce a stop-and-ask on a lesson A considers complete.

| Token | Evidence in the lesson |
|---|---|
| `slides` | A file in `Content/` classified as slides |
| `transcript` | A `transcript_*` file in `Content/` |
| `book` | A `Chapters` cell in this lesson's row that resolves to a range, directly or through `cont.`. A `-` row does not count as present, and a lesson whose row is `-` is exempt from the `book` expectation. |
| `notes` | A `notes_*` file in `Content/` |
| `handouts` | A `handout_*` file in `Content/` |
| `articles` | At least one file in the lesson's `Articles/` |
| `videos` | A `Content/videos.md` **or** `Content/video.md` exists **and contains at least one link**. Both spellings are reserved names and the classifier accepts either, so this predicate must too: two predicates disagreeing about the same file is exactly what this table exists to stop. |
| `links` | A `Content/links_*.md` exists **and contains at least one link** |

### A serialised book

A lecturer who is writing the book as the course runs delivers it one chapter at a time, and the
chapters arrive with the week's material. The model holds it as **one book in a folder**:

```
Books/
├── EBT_Ortt_Matta_Reader/        <- one file per chapter
│   ├── Chapter_01.docx
│   ├── Chapter_02.pdf
│   └── ...
└── EBT_Ortt_Matta_Reader.index.md
```

The index carries `serialised: true` and `folder:` instead of `file:`, and its table gains a **File**
column, because page numbers restart at 1 in every chapter and a merged range would be a lie:

```markdown
| ID | Title | File | Pages |
|---|---|---|---|
| 2 | Chapter 2 | Chapter_02.pdf | 1-11 |
```

A `Chapters` cell then reads `2`, or `2-3`, and resolves to a **list of (file, range)** pairs rather
than one span. Chapters may be different formats; a `.docx` chapter simply has no page range, and the
whole file is the section.

**Why this is a book and not a pile of handouts.** Classified as loose files in `Content/`, chapters
land as handouts: they keep priority 1, so precedence survives, but they cite as `H` and become
indistinguishable from a worksheet, `expects: [book]` can never be satisfied, and the `Chapters`
column stays empty for the whole course. As a book they cite as `B2.3`, which is what the reader is.

A new chapter is filed into the folder and the index gains a row. Nothing is rebuilt, and no earlier
page number moves.

### `cont.` and `-` in the `Book` and `Chapters` cells

| Value | Meaning |
|---|---|
| a value | the reading for this lesson |
| `cont.` | the same reading as the row it continues |
| `-` | no reading at all (an unrelated guest lecture). Set only on the student's word, never inferred. |
| blank | **not filled in yet.** Never neutral: the notes skill's chapter check would pass vacuously and it would write notes with a whole priority-1 source missing while reporting 100% coverage. |

**Which row `cont.` continues.** A lesson continues the previous lesson. **A
tutorial continues the lesson named in its `Lesson` column**, because that is
what "the same reading as the lecture" means to a reader, and only falls back to
the previous tutorial when that column is empty. A `cont.` on the first row of
its type with no `Lesson` column to follow is a broken chain, reported as a
defect in the table rather than read as "no reading".

Chains are resolved by one helper, `shared/scripts/overview.py`, and nowhere
else: four implementations would disagree on the first lesson that continues a
lesson which itself continues another.

`expects_declined` sits beside `expects` in the same frontmatter and holds every token the student was
offered and refused. Without it, A's drift proposal repeats on every later lesson, which is exactly the
outcome the second-occurrence rule exists to avoid.

---

## 9. `Explanations/` is generated, never read back

`Explanations/` holds skill E's saved explanations. **It is tutor output, not course material, and no
other skill may read it.**

| Rule | |
|---|---|
| A | Creates it on demand at E's first save. Never at init, never recreated by `validate` if removed. Its classifier **never files anything into it**. |
| B | **Never reads it.** Never in `sources:`, `sources_stat` or `inputs`. Excluded from directory listings and staleness comparisons. |
| C | **Never reads it**, and never generates a question from anything in it. Freshness and `status` ignore it entirely. |
| D | **Never writes into it**, broken-anchor repair included. E repairs its own links. |
| E | Owns it. Archives to `Explanations/.history/`. |

**Why this is load-bearing.** If B ever ingests a saved explanation as a lesson source, model prose
enters `sources_hash`, becomes notes, C writes exam questions from it, and D corrects against it. The
student then revises from model output believing it is the lecturer's, and nothing on screen says so.
By the time it shows, the prose is woven through the notes, the term ledger and the question bank, and
it cannot be pulled back out. This is why A's `validate` carries a standing quarantine tripwire rather
than a one-time install check.

---

## 10. iCloud

The vault is iCloud-synced, so two failure modes are always possible and both are silent data loss.
Detection lives in `shared/scripts/icloud.py`; nothing re-implements it.

| Mode | What it looks like | Behaviour |
|---|---|---|
| **Evicted (placeholder)** | On APFS, a dataless file: `stat` reports the full logical size but zero allocated blocks. Older or non-APFS cases show a `.name.ext.icloud` sidecar, or a zero-byte file. `icloud.py` checks all three; none is hard-coded as the only signal. | Reading it returns empty content and would silently produce notes missing a whole source. Hard fail for that file wherever bytes are read. |
| **Conflicted copy** | A sibling whose stem carries a conflict suffix, e.g. `slides (matjaz's conflicted copy 2026-03-12).pptx`, or a trailing ` 2`. `icloud.py` matches a pattern set rather than one literal. | Writes are landing in a branch that may never be opened again. Quarantined from `_Inbox/` into `_Inbox/_conflicts/` by A; reported but **not moved** when already filed, because a filed file is content B may depend on. |

**Moving a placeholder is safe.** A move within the iCloud container is a rename and leaves the file a
placeholder, so filing proceeds and the report lists which filed files are not downloaded. A move to
another volume is a copy, which forces a download and fails when offline; that is warned about.

**Both detections are `stat`-only.** Nothing in this plugin downloads a file by reading it.

---

## 11. Resolving the vault and the course

One ladder, implemented once in `shared/scripts/vault.py`. Every skill uses it, because two skills
resolving the same request differently is not a tolerable outcome.

1. Explicit path.
2. Current folder, when the session is rooted in a single course.
3. `_config.md` → `active_courses` (vault-relative paths; `archived_courses` excluded), matched on the
   folder name first, then on the `course:` display name in each candidate's `Weekly_overview.md`.
4. **Ask. Never guess between two candidates**, for any action.

A adds one branch after resolution, because A is the skill that legitimately gets pointed at a folder
that is not yet a course:

| Resolved folder | A's branch |
|---|---|
| Has `Weekly_overview.md` with a `code:` | A conforming course. Proceed. |
| Exists, has content, no `Weekly_overview.md` | `validate` runs **read-only**. Ask: create a new course here, or adopt what is in it. |
| Exists, empty | Ask: create a new course here |
| Does not exist | Ask before creating anything. Never create a course folder from what may be a typo. |

**A is stricter still for `file`.** When B resolves wrong it writes a notes file that is visibly about
the wrong lesson. When A resolves wrong it moves files somewhere unexpected and that can go unnoticed
for weeks. So for `file`, even a single weak match is asked about.
