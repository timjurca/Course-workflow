# Note invariants

Everything in this file is a **cross-skill contract**. A marker, a frontmatter key, a hash rule or a
set of exact bytes defined here is matched as a literal string by at least two skills and often by a
script. Changing anything here is a change to every skill that reads it, so change it here first and
then in the skills, never the other way round.

## Contents

- [1. The marker vocabulary](#1-the-marker-vocabulary)
- [2. Source markers (B)](#2-source-markers-b)
- [2a. The judgement marker (B)](#2a-the-judgement-marker-b)
- [3. Correction markers (D)](#3-correction-markers-d)
- [4. Tier and provenance markers (E)](#4-tier-and-provenance-markers-e)
- [5. Collision check](#5-collision-check)
- [6. Concept IDs](#6-concept-ids)
- [7. Anchors and headings](#7-anchors-and-headings)
- [8. Protected blocks](#8-protected-blocks)
- [8b. Two raters, one union](#8b-two-raters-one-union)
- [9. Frontmatter keys](#9-frontmatter-keys)
- [10. Hash and freshness rules](#10-hash-and-freshness-rules)
- [11. The Pass A extraction contract](#11-the-pass-a-extraction-contract)
- [12. `Table_of_contents.md`: the exact skeleton](#12-table_of_contentsmd-the-exact-skeleton)
- [13. TOC marker blocks](#13-toc-marker-blocks)
- [14. `source_errata.json`](#14-source_erratajson)
- [15. The correction log](#15-the-correction-log)
- [16. Findings files](#16-findings-files)
- [17. Renumber blocks](#17-renumber-blocks)

---

## 1. The marker vocabulary

Three families, one namespace. Every marker in the plugin is a bracketed token inside note prose.
A parser that reads one family must be able to tell it from the other two by shape alone.

| Family | Owner | Shape | Section |
|---|---|---|---|
| Source markers | B | `[S22]`, `[B15.3]`, `[T11]`, `[A1.2]`, `[N03]`, `[C05]`, `[V1.6]`, `[K1.6]`, `[G1.3]`, `[H04]` | [§2](#2-source-markers-b) |
| Correction markers | D | `[source error: <ID>]`, `[student, sources differ: <ID>]`, `[unverified: <ID>]` | [§3](#3-correction-markers-d) |
| Tier and provenance markers | E | `[beyond course]`, `[differs from course: <ID>]`, `[W<n>]`, `[your note]` | [§4](#4-tier-and-provenance-markers-e) |

Two further B annotations share the bracket shape and are listed with the source markers because they
appear **inside** one: `[S22, OCR, verify]` and `[B15.7, not lectured, B15.7!]`.

One further B marker is a bare literal and belongs to no family above: `[judgement]`
([§2a](#2a-the-judgement-marker-b)). It is the only marker in the plugin that marks a claim as **not**
coming from a source.

---

## 2. Source markers (B)

Written by B, read by C, D and E. A marker is the ID of an atomic extraction item, and every ID that
Pass A emits must appear in the notes or in `## Uncovered material`; that is what Pass D checks.

| Prefix | Item | Example |
|---|---|---|
| `S` | Slide, or a bullet or speaker note on one | `S12`, `S12.3`, `S12n` |
| `B` | Book section | `B15.2` |
| `B…!` | Highlighted passage inside a book section | `B15.2!` |
| `T` | Transcript segment, **always indexed by file** | `T1.07` |
| `A` | Article, point | `A2.4` |
| `H` | Handout | `H04` |
| `N` | Student note | `N03` |
| `C` | Student annotation (sticky note, margin writing) | `C05` |
| `V` | Assigned video, caption segment | `V1.6` |
| `K` | Assigned link, segment | `K1.6` |
| `G` | Assignment task — **signal only, never in coverage** | `G1.3` |

Compact form: several IDs in one bracket, comma separated — `[B15.1, S12]`.

**Transcript ids carry the file index, always**, like `A2.4` and `V1.6`, even when a lesson has one
recording. The conditional form — bare `T07` for one file, `T1.07` for several — renumbers lesson 1's
ids the day a second recording is added, which detaches every correction anchored to one.

Qualified forms, all legal inside a marker:

- `[S16 corrected by T11]` — the lecturer corrected the slide.
- `[S22, OCR, verify]` — the text came from OCR and is listed in frontmatter `flags`.
- `[B15.7, not lectured, B15.7!]` — in the book, not in the lecture, and highlighted.
- `[T1.75, transcript only]` — a **specific** (a number, year, percentage or quantity) whose only
  support is a priority 2–3 source, while the slides and book are silent. Written by B when Pass D's
  `Unsupported specifics` check fires. Not a correction marker: nothing is wrong, the support is thin.
- `[S11.1, from image, verify]` — the text was read off a slide image because that slide has no text
  layer. Same standing as `OCR, verify`: a reading, not a transcription.

**Never numbered.** Section headings carry no numbers ([§7](#7-anchors-and-headings)).

---

## 2b. Figures (B)

A figure is a source, cited like any other, and it is **shown** when what it holds cannot survive
paraphrase: a curve's shape, a flow with branches, a mapping of one structure onto another, a table
whose alignment is the point. Decoration is not shown.

| Rule | |
|---|---|
| **File** | `Final_notes/attachments/<CODE>_L<NN>_fig_<sourceID>_<slug>.<ext>`, extracted from the slides or the book, never redrawn. The source id is in the filename, so a loose file is always traceable. |
| **Embed** | `![[<filename>]]` on its own line, in the body, beside the claim it supports. |
| **Caption** | One italic sentence directly under it saying what it shows, ending with the figure's source marker. Required: it is what survives a lost file or a reader with images off, and it is what makes the figure searchable. |
| **Coverage** | A figure's id counts like any other extraction item. Embedding it does not exempt it from being cited, and citing it does not require embedding it. |
| **Described means shown** | Text that describes a figure's **specific visual content** (its shape, axes, intercepts, labelled points, colours, one source's labels as against another's, "on the sketch", "the slide shows") requires that figure embedded beside the text, or the text rewritten so it no longer depends on the picture. This takes precedence over every reason for leaving a figure out. A student's sketch that a `Your note` callout talks about is embedded inside that callout. |
| **Who** | B writes them. D checks the mechanics (file exists, caption present, marker present, and that a lesson which read five or more items off images embedded at least one) and flags a figure the text describes without showing (`Described but not shown`, §16). Neither judges which figures are worth showing. |

The failure this prevents: LTM lesson 3 carried 45 `[…, from image, verify]` readings and embedded no
figure at all. Every picture it had read was available to its writer and to nobody else, and the
notes asserted what the pictures showed without ever showing them.

---

## 2c. The one disposable path (all skills)

`<lesson>/.work/renders/` is the **only** path any skill in this plugin may delete, and it holds
page renders and nothing else. **Every script that renders a page writes there**, and not into
`.work/` itself: renders dropped beside the extractions (`ocr_p0007.png`, `render_slide_19-19.png`)
sit outside the one disposable path, so nothing may remove them and they accumulate for good. Everything else in the vault is removed by the student, never by a
skill, and `undo` sets files aside in `_Inbox/_undone/` rather than deleting them.

The reason it is a rule and not a preference: deletion permission in this environment is granted per
connected-folder root and covers the whole subtree, so once the student approves a clean-up the
session *could* delete anything under the vault. The narrowness is this contract, not a lock, which
is why it is written here where all five skills read it, and why `validate` reports anything removed
outside that path.

---

## 2d. Symbols in running text (all skills)

Every mathematical symbol that any skill writes outside a display formula (in prose, tables,
callouts, blockquotes, definitions, questions, answers and explanations alike) is inline math,
`$e_P$`, `$e_{XZ}$`, `$X^{-1/2}$`, never plain text such as `e_P` or `X^(−1/2)`, and a literal
dollar amount in prose is written `\$530` or `USD 530` so that it cannot open a math span.

---

## 2a. The judgement marker (B)

`[judgement]` marks a line as **Claude's opinion about what matters**, not a statement taken from a
source. It exists because `## What to remember` ([§6](#6-concept-ids), [§7](#7-anchors-and-headings))
is the one place in a notes file where B writes something no extraction supports.

| Rule | |
|---|---|
| **Shape** | The exact literal `[judgement]`, lowercase, no arguments. Nothing is appended inside the bracket. |
| **Where** | Every bullet inside `## What to remember` carries it. It appears **nowhere else in the file**, and no other skill ever writes it. |
| **Beside source IDs** | A judgement line may also carry ordinary source markers pointing at what it refers to: `- Innovation is a marketing mix, not a product. [judgement] [S18.7]`. Two brackets, never merged into one. |
| **Coverage** | Source IDs cited inside `## What to remember` **do not count as cited.** `verify.py` removes the zone before it computes the cited set, so an opinion can never satisfy the coverage guarantee for material the body failed to cover. |
| **Reading it back** | C reads the zone only through the commit-first gate ([§8](#8-protected-blocks)). D never corrects it: there is no source a judgement can be wrong against. E never quotes it as course material. |

The failure this prevents is specific. Without a per-line marker, a bullet copied out of the zone into
a revision question or an explanation is indistinguishable from a sourced claim, and by the time it
shows, the opinion has been revised from and tested on as if the lecturer had said it.

---

## 3. Correction markers (D)

A correction normally leaves **no marker**: the history lives in the correction log. The three markers
below exist for the cases where the notes now say something the sources do not support, and the reader
has to be able to see that at a glance. **`<ID>` is always a source marker ID from [§2](#2-source-markers-b).**

| Marker | When | Consequence |
|---|---|---|
| `[source error: <ID>]` | The source itself is genuinely wrong and the notes now carry the correct statement. A one-line footnote states what the source says. | Never produces an erratum: the extraction stays a faithful record of the source. |
| `[student, sources differ: <ID>]` | The student overrode the sources and the correction was checked against them. | Stops C re-reporting the contradiction. |
| `[unverified: <ID>]` | The correction was applied on the student's word and **was not checked** against the cited location. | Never produces an erratum. Comes back in D's `review`. |

C treats all three as "already marked in the notes" and does not re-report the passage.
E treats a marked passage as settled and does not raise a tier-3 finding on it.

An erratum is a different thing from a correction marker: it repairs a **misreading** at the extraction
level and is invisible in the notes ([§14](#14-source_erratajson)).

---

## 4. Tier and provenance markers (E)

These appear only in E's chat answers and in files under `Explanations/`. **They never appear in a
notes file**, because nothing E writes is ever read back by another skill.

| Marker | Tier | Meaning |
|---|---|---|
| a B source marker | 1 | From the course material, reworded or unpacked by E |
| `[beyond course]` | 2 | Background, prerequisite, analogy, worked example, derivation, simpler framing |
| `[differs from course: <ID>]` | 3 | E or an external source conflicts with the notes or an extraction |
| `[W<n>]` | 4 | External, fetched, resolved in `## External references` |
| `[your note]` | — | The student's own writing, quoted back. **Not a tier.** Never evidence, never asserted, never a finding. |

Two further annotations appear in E artefacts and belong to no tier:
`[not machine-verified]`, on a derivation step or a number a script could neither confirm nor
contradict, and `[translation, verify]`, on a term rendered into the other course language without a
source for the rendering. Both are **honesty markers**, not claims about authority, and a parser must
accept them rather than reporting an unknown shape.

**Every claim that is not tier 1 carries its marker.** An unmarked claim in an E artefact reads as
course material, which is the failure the quarantine exists to prevent.

### The `Explanations/` banner

Verbatim at the top of every saved explanation:

```markdown
> [!warning] Not course material
> Written by course-explain. This is a tutor's explanation, not a source.
> It is not examinable content, it is not read by any other skill, and claims
> marked `[beyond course]`, `[differs from course: …]` or `[W<n>]` are not
> from your course material. The notes are the record.
```

### External reference block

```markdown
## External references

**[W3]** Stock, J. & Yogo, M. (2005), *Testing for Weak Instruments in Linear IV Regression*.
https://example.org/stock-yogo · retrieved 2026-03-12 · authority: standard reference
> "critical values for the Cragg-Donald statistic depend on the number of
> instruments and the tolerated bias relative to OLS"
```

Snapshot quote: at most 50 words, verbatim, always with URL and retrieval date. A link with no
snapshot rots; a snapshot survives.

---

## 5. Collision check

The three families are disjoint, and a parser can separate them without knowing which skill wrote the
file:

- A **source marker** starts with a single uppercase letter from `SBTAHNCVKG` followed immediately by a
  digit. Nothing else in the plugin has that shape.
- A **correction marker** starts with a lowercase word followed by a space, and contains `: ` before a
  source ID. Its three leading words (`source error`, `student, sources differ`, `unverified`) are a
  closed set.
- The **judgement marker** is the closed literal `[judgement]` and nothing else. It carries no colon, so
  it cannot be read as a correction marker, and it is not in the tier set, so it cannot be read as one
  of E's.
- A **tier marker** is either the closed literal `[beyond course]` or `[your note]`, or starts with
  `differs from course: `, or is `W` followed by digits. `W` is deliberately **not** in the source
  marker prefix set, and `differs from course` is deliberately not in the correction marker set.

Any script that parses markers must reject an unknown shape loudly rather than ignoring it. A silently
skipped marker is a silently uncovered item.

---

## 6. Concept IDs

A concept ID gives a section an identity that survives regeneration, rewording and renumbering. C keys
its revision history on it, D anchors corrections to it, E locates material by it.

- **Form:** the concept's first heading, lowercased, with every run of non-alphanumeric characters
  replaced by a **hyphen**. No course code, no lesson number. Never reused for a different concept.
  Use `shared/scripts/naming.py` → `concept_id()`; **do not use `slugify()`**, which maps spaces and
  hyphens to underscores because it is for file names. The two are deliberately separate functions:
  a concept ID is matched as `[a-z0-9-]+` inside `<!-- concept: … -->`, inside
  `Explanations/<CODE>_<concept-id>_Explained.md` and as a JSON key, and an underscored id is
  rejected by course-setup's stray-explain-file check. `Instrument relevance` → `instrument-relevance`.
- **Written in the notes** directly under the H2:

  ```markdown
  ## Instrument relevance
  <!-- concept: instrument-relevance -->
  ```

- **Registry:** `<course>/.data/concepts.json`, owned by B.
- **Fixed sections carry no concept ID:** `Definitions`, `Assigned readings`, `Assigned videos`,
  `Assigned links`, `Recap`, `What to remember`, `Check yourself`, `Course administration`,
  `Uncovered material`, `My additions`. Nor do the **zone headings** `Concepts` and `Cases`: a zone
  holds sections, it is not one.
- **Tutorials create no concepts of their own.** A tutorial problem section carries the concept ID of
  the lesson section its `**Connects to:**` link points at, and is appended to that concept's
  `sections` list with `"lesson": "T02"`. A problem with no such link carries no ID and is reported.
- **Retired:** a concept whose last section disappears is marked `retired: true`, never deleted, so
  history stays resolvable. E explains a retired concept and names its successor.

```json
{
  "applied_renumbers": ["c2d9"],
  "concepts": {
    "instrument-relevance": {
      "title": "Instrument relevance",
      "sections": [
        {"lesson": "L03", "heading": "Instrument relevance", "source_ids": ["S14", "S16", "B15.3", "T11"]},
        {"lesson": "L09", "heading": "Instrument relevance", "source_ids": ["S05", "T02"]}
      ],
      "retired": false
    }
  }
}
```

Bookkeeping keys sit at the top level; concepts live only under `concepts`. C's ledger has the same
shape, for the same reason.

**Reuse rule** (B, on re-run): a spine node keeps the ID of the previous section for this lesson whose
`source_ids` overlap it most, when the overlap is at least half of the smaller set. Otherwise a new ID.
D and E use the same rule when they need to find a successor concept, so all three agree.

---

## 7. Anchors and headings

- **Headings are never numbered.** A numbered heading breaks every link into it the moment a section is
  inserted above.
- **Links are heading anchors, never block references.** Notes are fully regenerated, so block IDs
  would churn: `[[ECON_L03_Final_notes#Instrument relevance]]`.
- **Heading stability:** when a concept ID is reused, the previous heading text is kept. Exactly two
  reasons sanction a change: the section's **subject changed materially**, or the section **moved to
  a different zone** and its old heading no longer reads correctly in the new one (a heading written
  to sit under study material can be wrong once the same concept is presented as a case or a recap).
  A zone move is logged exactly like a subject change. Any other rename is churn, and it costs every
  inbound link. A changed heading is listed in the run report either way.
- **A rename made inside a run is closed inside that run.** B rewrites links *it wrote this run* into
  sections *it renamed this run*, within this lesson's folder and the overview, via
  `check_links.py retarget`. Links from other lessons are not touched: those are ordinary broken
  anchors, reported by B and repaired by D through the concept ID.
- **`**In one line:**` is a fixed English label**, in a lesson's notes and in its overview, and the
  sentence after it is **identical in both**. It is not a heading and carries no anchor; it is matched
  as a literal line prefix. `verify.py` derives the overview path from the notes path
  (`<lesson>/Final_notes/<CODE>_L<NN>_Final_notes.md` -> `<lesson>/<CODE>_L<NN>_Overview.md`) and
  reports a mismatch. Two summaries of one lesson that drift apart are worse than one: neither can be
  trusted, and nothing on screen says which is current.
- **Structural headings are fixed English**, whatever `notes_language` says, because they are wikilink
  anchors matched as literal strings: `Definitions`, `Assigned readings`, `Assigned videos`,
  `Assigned links`, `Recap`, `What to remember`, `Uncovered material`, `My additions`, `My notes`, `My questions`,
  `Core summary`, `Used in L<NN>`, `External references`, and the three `Table_of_contents.md`
  sections `Lessons`, `Tutorials`, `Term index`.
- **A broken heading anchor is D's to repair**, as a logged `replace` on the link target only, with the
  right anchor looked up through the concept ID rather than guessed. A broken **file** link is reported
  only: it means a missing file, which belongs to A or B. E repairs its own links in `Explanations/`,
  because D never writes there.

---

## 8. Protected blocks

Four blocks are the student's own writing. They are **preserved verbatim by read-modify-write** on
every regeneration and created empty when absent.

| Block | File | Owner of the file |
|---|---|---|
| `## My additions` | lesson/tutorial notes, shared article, video and link notes | B |
| `## My notes` | `<CODE>_L<NN>_Overview.md`, saved explanations | B, E |
| `## My questions` | `Exams/Revision_questions/<CODE>_L<NN>_Revision.md` | C |
| `<!-- ranking:yours:start -->` … `<!-- ranking:yours:end -->` | inside `## What to remember` in lesson/tutorial notes | B |

The ranking block is the **inverse** of a TOC marker pair. In a TOC pair B replaces the bytes
*between* the markers and leaves the rest of the file alone; here B replaces everything *outside* the
pair and never touches what is inside it. The pair sits directly under the zone heading, above the
judgement callout, so a pinned item is read before the generated one. It holds no heading of its own —
a heading there would enter the course table of contents, which takes H3s.

A judgement cannot be wrong against a source, only disagreed with, so a disagreement is **not** a
correction. D does not open the zone, writes no log entry for it and replays nothing into it. The
ranking block is the whole mechanism for disagreeing.

### The commit-first gate

C forms its own view of what matters and must not be anchored by B's. Reading the notes would anchor
it, so the order is enforced rather than requested:

1. C asks for a **blinded** copy of the notes: the same file with `## What to remember` removed.
2. C writes its own list and **commits** it, from the whole-course vantage B is denied — past exams,
   the ledger, the error history.
3. Only once the commitment is stored does the gate return B's zone.

Both lists are kept side by side, so the pair is auditable afterwards and the order cannot be
reconstructed in the other direction. **B is denied the course vantage on purpose**: two raters that
see the same evidence agree by construction, and the agreement then means nothing.

---

## 8b. Two raters, one union

B judges one lesson from its own sources. C judges the whole course from what it has been tested on.
Neither is authoritative, and the deterministic ledger
(`course-revision/references/importance-signals.md`) stays separate as a third, traceable view.

- Revision covers the **union** of both lists. Anything either rater named gets questions, so no item
  is lost because one rater missed it.
- Items **both** raters named come first: two independent reads agreeing is the strongest signal
  available short of a past exam.
- The revision file **says which rater named each item**, so a divergence between what one lecture
  stressed and what the course tests is visible rather than averaged away.

Union, never intersection. The design can waste study time; it cannot hide material.

**Protection is against writes, not reads.** E may read all of them to locate a confusion, and marks
anything it quotes with `[your note]`. It writes into none of them, ever.

---

## 9. Frontmatter keys

Frontmatter keys and their enum values are **fixed English**, always.

### Lesson and tutorial notes (B)

`course`, `type` (`lesson`|`tutorial`), `number`, `date`, `title`, `language`, `sources`,
`sources_hash`, `inputs` (`overview_row`, `assignment_rows`, errata ids and `right` text),
`sources_stat` (list of `{path, size, mtime}`), `coverage`, `highlights`, `exam_signals`
(list of `{text, concept, source}`), `assessed_in`, `flags`, `generated`, `run`, `generator`.

### Overview (B)

`course`, `type`, `number`, `date`, `title`, `sources`, `coverage`, `generated`, `generator`.

### Shared article / video / link notes (B)

`authors`/`channel`/`site`, `year`, `title`, `url`, `duration`, `captions` (`auto`|`manual`|`none`),
`used_in` (list of `L<NN>`/`T<NN>`).

### Book index (A)

`book`, `file`, `pages`, `structure_built`, `descriptions` (`complete`|`partial`|`declined`),
`scaffolded_by`.

### `Weekly_overview.md` (A)

`course`, `code`, `notes_language` (`auto`|a language code), `expects`, `expects_declined`,
`scaffolded_by`.

### Saved explanation (E)

`concept`, `concepts`, `lessons`, `notes_run`, `source_ids`, `explain_depth`, `body_sha`, and on a
tombstone `superseded_by`.

`body_sha` is the hash of the body E last wrote, excluding `## My notes`. It is what makes a hand edit
detectable: the archive holds the *outgoing* version, not the last-written one, so without a stored
baseline E cannot tell its own prose from the student's edit of it, and "show the difference and ask"
has nothing to compare against.

**`notes_language: auto` means dominant source language, in both A and B. There is no second meaning.**
A resolves it once from whatever material exists, writes the concrete value in, and then stops
detecting. B resolves per run from the sources of the lesson it is processing.

---

## 10. Hash and freshness rules

| Value | Written by | Computed by | Meaning |
|---|---|---|---|
| `sources_hash` | B | `shared/scripts/source_hash.py` | Hash over the **contents** of every file in `sources:`, **including PDF annotation layers**. Annotating a chapter is therefore itself a reason to re-run. |
| `sources_stat` | B | B | `{path, size, mtime}` per source, so C can check freshness without reading any source. |
| `inputs` | B | B | The run's non-file inputs: the lesson's `Weekly_overview` row, every `## Assignments` row listing this lesson, and the id and `right` text of every D erratum covering this lesson's sources. |
| `run` | B | B | Timestamp identifying one B run. The extractions carry the same value. Written **quoted** in frontmatter (`run: "2026-11-13T15:31:51"`). |

**What `sources_hash` does not catch.** It covers contents, so renaming a lesson folder or renumbering
a lesson changes nothing it sees. `inputs` catches the renumber, because the overview row's `No` cell
changed. A says so at the time of the renumber as well.

**Comparison rules**, so that cosmetic churn is not mistaken for change:

- `inputs` rows are compared **by parsed cell values with spaces trimmed**, never by raw text, so a
  table re-padded by Obsidian is not a change.
- For an assignment row, only `No`, `File` and this lesson's own tasks are compared, so renumbering
  another lesson does not make this one stale.
- For a `cont.` row, `inputs` also records the **resolved** book and range, so a later correction to
  the earlier row makes this lesson stale too.
- Everywhere a file name is compared or a `sources_stat` path is looked up, the leading `<CODE>_`
  token is ignored.
- **Timestamps are written quoted** in frontmatter: `run`, `generated` and a `sources_stat`
  `mtime`. A bare `2026-11-13T15:31:51` is read by YAML as a datetime, prints back as
  `2026-11-13 15:31:51`, and then no longer equals the same `run` in an extraction header.
- **Every comparison of `run` values normalises both sides** with
  `shared/scripts/runstamp.py` → `norm_run()`, never `str()`, so notes written before the quoting
  rule (an unquoted value YAML already turned into a datetime) still compare equal.

**"Needs replay" is derived, never stored** ([§15](#15-the-correction-log)).

---

## 11. The Pass A extraction contract

`.work/A_<source>.md` is written by B and **read by C, D and E**. It is pinned here; changing it is a
contract change for four skills.

- File name: `A_<slugify(entry without the #range)>.md`, e.g.
  `Content/slides_lecture3.pptx` → `A_content_slides_lecture3_pptx.md`. Every extraction file starts
  with `A_`; **no other file in `.work/` does**. (`transcript_corrections_<entry slug>.md` deliberately
  carries no `A_` prefix for exactly this reason. It is named per transcript, not per lesson: one
  fixed name meant a lesson with two recordings could only ever keep the second one's log.)
- Header carries the run: `run:` and `sources_hash:`, equal to the notes frontmatter of the same run.
  A reader whose values do not match refuses to use the set.
- One item per line block: `ID`, optional `tags`, `text`.
- Text is **after** transcript normalisation and **after** D's errata have been applied, so no later
  reader ever sees a raw ASR error or a known misreading.
- IDs are exactly the IDs used in the notes markers.
- `tags` is a **closed list**: `lectured` (implicit on `S`, `T`, `H`), `summary_slide`, `key_box`,
  `review_item`, `lecturer_stress`, `exam_signal`, `not_lectured`, `errata`.
- Chunk boundaries are recorded, so Pass D can tell a lost item from a boundary artefact. An ID is
  never split across chunks.

```markdown
run: 2026-09-06T14:20
sources_hash: 8f3c...

### S22
tags: [summary_slide]
Relevance: first-stage F > 10 as a rule of thumb; weak IV biases 2SLS toward OLS.
```

---

## 12. `Table_of_contents.md`: the exact skeleton

A creates this file at init; B creates it if it is missing rather than stopping. Two skills writing two
different "minimal" shapes is how the file ends up with duplicate sections and no version stamp, so the
bytes are pinned here and read from here. `{{course}}` is the `course:` value from `Weekly_overview.md`.

```markdown
---
scaffolded_by: course-setup v1
---

# {{course}} - Table of contents

## Lessons

## Tutorials

## Term index
<!-- toc:terms:start -->
<!-- toc:terms:end -->
```

Frontmatter, H1, three section headings, the term marker pair. Lesson marker blocks are B's to create
on first run.

---

## 13. TOC marker blocks

B performs an **upsert**, never a raw append: it replaces the block between its own lesson markers,
creating the pair if absent, and rebuilds the term index wholesale from `terms.json`.

```markdown
## Lessons
<!-- toc:L03:start -->
### [[ECON_L03_Final_notes|03 - Instrumental variables]] · 2026-03-12
- [[ECON_L03_Final_notes#Why OLS fails under endogeneity|Why OLS fails under endogeneity]]
<!-- toc:L03:end -->

## Term index
<!-- toc:terms:start -->
| Term | Defined in | Also appears in |
|---|---|---|
| endogeneity | [[ECON_L03_Final_notes#Definitions\|L03]] | L09 |
<!-- toc:terms:end -->
```

- Marker pair: `<!-- toc:L<NN>:start -->` … `<!-- toc:L<NN>:end -->`, `T` for tutorials.
- Blocks are ordered by lesson number, so an out-of-order run still lands in the right place.
- **Only content between a lesson's own markers is ever modified.** That is what makes the file safe
  for two skills to share.
- **Zones are H2, sections are H3.** A lesson note is organised into fixed zones —
  `Definitions`, `Concepts`, `Cases`, `Recap`, `What to remember`, `Check yourself`,
  `Assigned readings`, `Course administration`, `My additions` — and each concept or case is an H3
  inside its zone. `What to remember` holds **no H3 at all**: its two tiers are bold labels, so the
  course table of contents never lists an opinion as if it were a concept. A case may use H4 for its parts. Obsidian anchors match any heading level, so
  `[[<CODE>_L03_Final_notes#Instrument relevance]]` resolves whether that heading is H2 or H3.
- **The course TOC lists the sections, not the zones.** `## Concepts` is not worth a link;
  the concepts inside it are. `build_toc` takes H3s when the document uses zones and falls
  back to H2s when it does not, so a flat document from an earlier run still works.
- **A alone migrates the marker pairs on a renumber.** B does not touch them again.
- **`Learning_objectives.md` carries one more B-written pair.** The course-level goals the
  lecturer shows on slides are identical in every lecture that shows them, so they live once
  at course root rather than ~900 duplicated words in each of thirteen lesson notes. B upserts
  them between `<!-- goals:slides:start -->` and `<!-- goals:slides:end -->` inside A's file,
  by the same rule as the lesson blocks: only the bytes between B's own markers are touched.
  They do **not** get a file of their own — `Learning_objectives.md` already holds the official
  catalogue objectives, and a second goals file at course root is a rival index.
- Markers damaged or missing for a lesson that has notes: B rebuilds that block from the lesson's
  `<CODE>_L<NN>_Overview.md`.

---

## 14. `source_errata.json`

Owned by D at `<course>/.data/source_errata.json`. Course-level, because books and articles are shared
across lessons. **B reads it and applies it; B never writes to it.**

```json
{
  "applied_renumbers": ["c2d9"],
  "errata": [
    {
      "id": "e-0002",
      "date": "2026-03-21",
      "lesson": "L03",
      "source": "Content/slides_lecture3.pptx",
      "item": "S22",
      "wrong": "first-stage F > 1.0",
      "right": "first-stage F > 10",
      "evidence": "slide image re-read, OCR misread the decimal point",
      "correction": "c-0003",
      "status": "active"
    }
  ]
}
```

**Application**, at the end of Pass A for each item, after transcript normalisation:

| Case | B's behaviour |
|---|---|
| The item carries that ID and contains `wrong` | Replace `wrong` with `right`, tag the item `errata` |
| The item already contains `right` | Apply nothing. The source itself was fixed. |
| Neither text is in the item | Apply nothing, and report the erratum as not applied |

**Statuses are D's**, derived from the extractions on D's next run: `active`, `obsolete` (the source
now carries `right`), `stale` (neither text is present — the source changed), `withdrawn`.

**Reach follows the source, not the lesson.** A lesson-local source (`Content/…`, the lesson's
`Articles/…`) applies in that lesson only. A course-level source (`Books/…`, or anything outside the
lesson folder) applies in **every lesson citing it**, and enters each of their `inputs`. D states which
lessons go stale **before** the student confirms.

**Scope limit.** An erratum exists only for a **misreading**. A source that is genuinely wrong is
corrected in the notes with `[source error: <ID>]` and never "repaired" in the extraction.

---

## 15. The correction log

`<lesson>/notes_corrections.md` for lesson and tutorial notes, `<course>/.data/shared_corrections.md`
for shared article, video and link notes. Same format. **D is the only writer**, and the file's first
line says it is never edited by hand.

**The file header**, before the first entry, and written by D alone:

```markdown
<!-- course-corrections:log v1 -->
<!-- applied_renumbers: c2d9, f1a7 -->

**Never edit this file by hand.** Every entry is written by the course-corrections
skill, and replay matches on the text recorded here.
```

The `applied_renumbers` marker is **per file**, not only in `corrections.json`. A chained renumber
(`L03→L04`, `L04→L05`) is not idempotent, so a migration interrupted between two log files would remap
one of them twice. A per-file stamp makes the migration resumable.

**The entries:**

````markdown
## c-0003 · 2026-03-21 · replace
group: g-0004
concept: instrument-relevance
section: "Instrument relevance"          # display only
file: Final_notes/ECON_L03_Final_notes.md
before: "first-stage F > 1.0"
after: "first-stage F > 10"
basis: source                            # source | user
evidence: "S22, slide re-read (OCR misread)"
origin: finding f-0007                   # finding f-NNNN | explain x-NNNN | uncovered S24 | user | scan
errata: e-0002
verified: sympy                          # sympy | numeric | marker | not machine-verified
status: applied                          # applied | absorbed | orphaned | pending | withdrawn
last_replayed: 2026-03-25T10:02 · run 2026-03-25T09:40
````

| Status | Meaning |
|---|---|
| `applied` | Present in the notes of the recorded `run` |
| `pending` | Written to the log but not in the notes (an interrupted run) |
| `absorbed` | B now writes the correct text by itself |
| `orphaned` | The passage could not be found after a rewrite |
| `withdrawn` | Withdrawn by the student or reversed by `undo`; kept for the history |

**Needs replay is derived, not stored:** `status: applied` **and** `last_replayed`'s run differs from
the notes' current `run`. B never touches this file, so the mismatch appears by itself.

**Open**, for C's gate and for D's `review`: any entry that is `pending`, `orphaned`, or needs replay.

**Who may read what.** B: nothing — it detects the file's presence and never opens it. C: the H2 header
and the `status` / `last_replayed` lines only. E: the status lines always, and `before:`/`after:` only
for entries that are not `applied` at the notes' current `run`. A: never opens it at all.

---

## 16. Findings files

Three inputs, one shape of problem. **D collapses findings from all three onto the same
(`concept`, `source`, anchor) into one proposal carrying every origin and every piece of evidence**, and
closing it writes the status back to each source file.

| File | Written by | D may set |
|---|---|---|
| `.work/D_verification.md` | B | — (a report, not a record) |
| `.data/revision_findings.json` | C | `status`, `closed_by`, `reason` |
| `.data/explain_findings.json` | E | `status`, `closed_by`, `reason` |

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

C's ids are `f-NNNN`, E's are `x-NNNN`, D's log entries are `c-NNNN` and groups `g-NNNN`.

### `.work/D_verification.md`

Written by B's `verify.py` at the end of every run, and **read by D** to find what needs correcting.
It is a cross-skill contract, so its shape is pinned here rather than left to whichever heading B's
renderer happens to emit. A reader must tolerate an unknown H2 and carry it through as unparsed
rather than dropping it: a silently dropped section is a clean review that missed everything.

```markdown
# Pass D verification

Notes: `Final_notes/ECON_L03_Final_notes.md`

Coverage: **112/112**

| Set | Count |
|---|---|
| extracted (G excluded) | 112 |
| placed in the spine | 112 |
| cited in the notes | 112 |
| discarded, non-content | 4 |
| assignment signals (G, not in coverage) | 3 |

## Unplaced (1)

_extracted by Pass A, in no spine node, not discarded_

- `S34`
```

H2 sections, each optional and present only when it has rows: `Unplaced`, `Uncited`,
`Citations with no extraction`, `Unrecognised markers`, `Decorated markers`,
`Quarantine: tier markers in a notes file`, `Quarantine breach in frontmatter`,
`Sections with no concept ID`, `Numbered headings`, `Extraction set disagrees with this run`,
`Malformed IDs`, `Down-weighted highlights`, `Uncertain readings`, `Broken links`,
`Unsupported specifics`, `Source spelling disagreements`, `Attribution in prose`,
`Judgement zone`, `Judgement drift`, `Summary line`, `Figures`, `Formulas`, `Plain symbols`,
`Described but not shown`.

`Unsupported specifics`, `Source spelling disagreements`, `Attribution in prose`,
`Plain symbols` and `Described but not shown` are the **writing gates**. Pass C is model work, so a rule stated only in SKILL.md is advice; each of these is
written by the model and checked by `verify.py`.

`Formulas` checks that every display formula uses notation a priority-1 source
uses, and that each of its symbols is explained in a legend directly below it. A
formula is reproduced like a table, in the source's own notation: restating a
book's worked arithmetic in symbols it never used is a claim wearing a source
marker.

`Plain symbols` enforces [§2d](#2d-symbols-in-running-text-all-skills) in the body: a token shaped
`<1-3 letters>_<1-4 alphanumerics>` or `<letter>^(...)` outside inline math, display math, code,
wikilinks, embeds, markdown links, HTML and URLs. File-name-like tokens (an `L<NN>`/`T<NN>` part,
an attachment name), source markers and the protected blocks are not flagged. Each row's backticked
token is the plain symbol, followed by its line and the inline-math form to write instead.

`Described but not shown` enforces the **Described means shown** rule of
[§2b](#2b-figures-b) in the body. It flags a source id when the text points at a picture of it (the
id is cited `from image` or `OCR`; or it is an `N`/`C` item in a callout that mentions a sketch or
drawing; or its paragraph says `Figure N`, `slide N shows` or `on the sketch`), an image file for
that id exists in `Final_notes/attachments/`, and no embed of that file appears in the same H3
section. Each row's backticked token is the source id, followed by the section, the trigger and the
attachment that is not shown.

`Judgement zone` is the fifth gate and covers `## What to remember`: every bullet carries
`[judgement]`, the marker appears nowhere else in the file, the top tier holds at most ten items, the
callout is present, and the ranking marker pair is intact. `Judgement drift` names what entered and
left the top tier since the previous run, read from the newest archive in `.work/history/`; with no
archive it reports that there is no baseline rather than reporting no change.

Rows are list items whose first backticked token is the item the row is about — an ID, a marker, or a
path. That is the only shape D parses; everything else on the line is prose for the student.

### Collapsing a finding that has no anchor

G17 collapses findings onto the same (`concept`, `source`, anchor). An uncovered item, or a B flag
against an *item* rather than a sentence, has no anchor in the notes. The key then degenerates to the
source alone, and such a finding joins a group **only when exactly one group could take it**. With two
candidates it stands alone.

Without that rule an unanchored flag on `S22` becomes a bridge that merges two findings about two
different sentences into one proposal, and the fix lands in the wrong place.

**An E finding is a report, not evidence.** D's evidence ladder is unchanged by one: a fix resting only
on E's claim is `basis: user` and carries `[student, sources differ: <ID>]`. A `basis: external` finding
hands D a snapshot, usable as corroboration, never as the primary source.

**Duplicate rules.** C checks its **own** findings of any status by (`type`, `concept`, `source`); a
`resolved` finding whose problem reappears is logged anew with `reopens: f-0007`, which is the alarm
that a replay was lost. E skips anything already carrying a D correction marker, listed in
`D_verification.md`, or matching an existing E finding by (`type`, `concept`, `source`) whatever its
status. D skips anything already in its log with the same `origin`.

---

## 17. Renumber blocks

Written by A to `_Inbox/_filing_log.md` when a lesson or tutorial is renumbered. B, C, D and E each
migrate their own records from these blocks, and each records the ids it has applied in its own
`applied_renumbers` list. **A never edits another skill's data file.**

```markdown
## renumber 2026-03-20T09:12:44 · id c2d9
type: renumber
moves: [L04 -> L05, L03 -> L04]     # L<NN> or T<NN>; one or more
renamed: [Lessons/03_2026-03-12 -> Lessons/04_2026-03-12, ...]
status: complete
```

Rules, identical in every skill and implemented once in `shared/scripts/renumber.py`:

- **All moves of a block are applied together**, through temporary names, so a chain or a swap never
  collides.
- A block is applied **once**; its id then goes into that skill's `applied_renumbers`.
- Migration happens on the next run that gets far enough to write. A run that stops earlier applies
  nothing, so "older than my latest run" always means "already applied".
- **A renumber block is never undone.** A wrong renumber is fixed by another renumber.
- On a **rebuild** of a data file: pending blocks are first applied to the files that survived, then
  the file is rebuilt, and `applied_renumbers` is pre-filled with every block id in A's log. A rebuild
  therefore never re-applies an old block and never skips a pending one.

Each skill supplies its own **field mapper** saying which of its fields hold `L<NN>`/`T<NN>` values:

| Skill | Fields migrated |
|---|---|
| B | `concepts.json` `sections[].lesson`; `terms.json` `first_defined` and `seen_in`; `## Used in L<NN>` headings and `used_in` lists in shared notes; the term index in `Table_of_contents.md` (**not** the lesson marker pairs — A already did those) |
| C | ledger and findings lesson references |
| D | `corrections.json` state and log file locations |
| E | `explain_findings.json` `lesson`; saved-explanation frontmatter `lessons`; and the `[[<CODE>_L<NN>_Final_notes…]]` **wikilink targets** inside `Explanations/*.md`, which are the part that actually breaks. The coverage index maps concept id to concept id and holds no lesson reference. Prose mentioning a lesson is never rewritten. |

---

## 18. The condensed revision notes (F)

`<lesson>/Final_notes/<CODE>_L<NN>_Revision_notes.md`. **F is the only writer.** It is a projection of
the sibling `<CODE>_L<NN>_Final_notes.md` and of nothing else: every claim in it is present there, so
the two can never disagree and a correction reaches it by re-running F.

**Frontmatter.** `of:` names the notes it projects. `notes_hash` is sha256 over the notes' **body**,
frontmatter excluded, so a frontmatter-only touch is not read as a content change. F is stale exactly
when that hash differs, which covers a B regeneration, a D correction and a hand edit with one test.

```yaml
type: revision_notes
of: Final_notes/FM_L03_Final_notes.md
notes_hash: 0a186e645599eee9be542281d0677b2b9e3c1f7a4d2b8c6e5a0f9d3b7c2e1a84
concepts: 25
depth: {must_know: 11, also_likely: 6, rest: 8}
generator: course-condense v1
```

**Concept comments are mandatory and exhaustive.** Every `<!-- concept: … -->` in the notes appears
exactly once here, whatever its depth. That is what lets `verify.py` match the two documents by set
comparison rather than by reading, and it is why a `rest` concept is one line and a link rather than
an omission.

**Markers split, and this is the only place in the plugin where any marker is dropped.** A marker that
says a claim may be **wrong** is carried inline and verbatim: `[source error: …]`, `[unverified: …]`,
`[student, sources differ: …]`, `[…, transcript only]`. A marker that says only **how the text was
obtained** (`from image, verify`, `OCR, verify`) is not repeated: the count goes in the banner. Source
ids are not carried at all; the `[[…#heading]]` link back to the full section is the trace.

**Contents, not calculations.** F carries what the lesson **states**: every general formula, every
concept, factual numbers (survey shares, dates, case facts). It never carries a worked example, a
calculation, a numeric result or a data table. A rule table (NPV > 0 accept, NPV < 0 reject) stays,
because it gets a point across; a data table is dropped and the link leads to it. A `$$` block that plugs in numbers is a calculation and is exempt from formula
coverage.

**Protected.** `## My additions` is the student's and survives every re-run verbatim, as in §8.

**Never written by F:** the final notes, the overview, `Table_of_contents.md`, anything in `.data/`,
anything under `Explanations/`. F touches no course-wide file at all, which is what makes it the
second parallel-safe operation in the plugin after B's figures pass (§2b).
