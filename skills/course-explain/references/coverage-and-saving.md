# Coverage, saving and staleness

Consulted while saving, re-saving, tombstoning or reporting `status`.

## The coverage index is the truth, not the folder

`.data/explain_state.json` maps **every concept an explanation covers** to **the
primary concept whose file holds it**:

```json
"coverage": {
  "instrument-relevance": "instrument-relevance",
  "instrument-exogeneity": "instrument-relevance",
  "endogeneity": "endogeneity"
}
```

A directory listing answers the wrong question. A concept explained inside
another concept's file has **no file of its own**, so listing `Explanations/`
would report it as unexplained and you would rebuild an explanation that already
exists three paragraphs down another page.

| Rule | |
|---|---|
| Concept IDs on both sides | never filenames. The filename is derived, so a course-code rename touches nothing in here. |
| **Own file always wins** | a concept maps elsewhere only while it has no file of its own. Saving its own explanation re-points its entry at itself. |
| The index is the truth | lookup, staleness and `status` read the index |
| See-also lines are cosmetic | written only during a normal full-replace save. A missing one is cosmetic, never corruption. |
| Retired keys are swept | `save` and `status` re-point them at the successor, or drop them and say so. Applies to the rejected list too. |
| Rebuildable | from `concept:` and `concepts:` across `Explanations/`. Say what was rebuilt. The **rejected list is not rebuildable**. |

The successor of a retired concept is found by **B's own ID-reuse rule**: the
surviving concept whose `source_ids` overlap it most, with the overlap at least
half of the smaller set. `coverage.py` implements it; course-corrections uses the
same rule, so both skills agree on where a retired concept went.

## Saving: one write mode, full replace

`save.py plan` then `save.py apply`. A save writes **one file and the state**,
never a partial edit to a second file, so a crash cannot leave two files
disagreeing.

Blockers `plan` returns, and what each means:

| Blocker | Meaning |
|---|---|
| `explanations_missing` | course-setup creates every visible folder, on demand, at your first save. The save stops and names that request. **Explaining is unaffected.** |
| `unknown_concept` | the ID is not in `concepts.json`, and you never invent one. Attach the material to an existing concept, or leave it in the conversation. |
| `no_course_code` | `Weekly_overview.md` carries no `code:`; the filename cannot be built |
| `tombstone` | a tombstone is never regenerated |
| a `markers.py` problem | missing banner, unknown marker shape, a `differs from course:` marker not naming a source ID, or a `[W<n>]` with no reference entry |

A save applies course-setup's pending renumber blocks first, across everything
you own, because a new file written beside records that still say `L03` leaves
the folder internally inconsistent at the one moment you are holding it open.

### Several concepts in one explanation

- **One primary concept**: the one the question is *about* — question focus,
  then higher `importance` in course-revision's ledger, then earlier
  `first_defined`.
- **Saved once**, in the primary's file. `concepts:` lists everything covered;
  `concept:` names the primary. Every covered concept enters the index **unless
  it already has a file of its own**.
- **Say which file you used**, every time.

### Hand edits

No content fingerprint is needed, unlike course-corrections'. Nothing else
writes into `Explanations/`, so what you last wrote is a reliable baseline: the
body's hash is stored as `body_sha:` in the frontmatter, and a mismatch means
the student edited the file.

`plan` then returns `hand_edited: true` and a diff of **what is on disk now
against what you would write** — which is exactly what they are about to lose.
Show it, ask, and only then `apply --confirm-hand-edit`. `## My notes` is
preserved either way, and the outgoing version is archived regardless, so a hand
edit is never actually destroyed.

Whitespace, blank-line runs and re-wrapping are filtered out of both the hash and
the diff. Obsidian re-pads a file on save, and that is not a hand edit.

### Re-saving in a different language

Say so and ask: replace in the new language, or keep the existing one.

## Tombstones

When the primary concept has been retired and the explanation is regenerated
against its successor:

1. archive the full current version;
2. write the new explanation to the **successor's** file;
3. leave the old file as a tombstone — `superseded_by:` in the frontmatter, a
   one-line pointer as the body, **`## My notes` preserved verbatim**;
4. re-point the coverage index at the successor.

Links keep resolving, the student's own block survives, the full text is in the
archive, nothing is deleted. A tombstone is never regenerated and `status` lists
it separately.

## Staleness: detect and offer, never repair

`stale.py check --concept <id>`, or `stale.py all` for the whole course.

| Check | What to say |
|---|---|
| `notes_run` differs from the notes' current `run` | "your saved explanation predates the current notes" — offer to regenerate |
| a cited source ID no longer exists | list the dead IDs, offer to regenerate |
| a correction or erratum has landed on a cited ID | "a correction has landed on material this explanation used" |
| the primary concept is retired | regenerate against the successor, leave a tombstone |
| a heading anchor is broken | **you repair your own links** — course-corrections never writes here |

**Never silently regenerate, and never silently serve a stale file.**

`stale.py links --apply` repairs an anchor by looking the heading up through the
**concept ID** in `concepts.json`, not by guessing at a similar heading. The
concept ID is the stable identity; the heading text is not. A broken *file* link
is reported only: a missing file belongs to course-setup or course-notes.

Archives are never pruned automatically. course-setup's archive size report and
its cleanup-on-request cover `Explanations/.history/`.

## The `status` report

```
ECON_Advanced_Econometrics, explanations

Saved      7 explanations, 5 current, covering 9 concepts
Stale      2  instrument-relevance (notes re-run 2026-09-06)
              two-stage-least-squares (2 cited source IDs gone)
Tombstones 1  overidentification-tests -> weak-instrument-tests
Rejected   3 framings recorded across 2 concepts
Findings   1 open (x-0003, L03, differs from S16) -> run corrections review for L03
Archive    4 versions in Explanations/.history
Depth      analogous (set 2026-03-02)
Pending    1 renumber block in course-setup's log, applied at the next save
Next       regenerate 2 stale explanations, or run corrections review for L03
```

`stale.py all` returns every number in it. If the state file was missing or
corrupt, say the rejected list is **empty**, not that it is complete.
