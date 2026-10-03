# Correction types: operations, the two kinds of wrongness, and gaps

Read this before writing the plan for a `correct` or `review` run. `SKILL.md`
has the rules that hold everywhere; this file has the ones that depend on what
kind of error you are looking at.

## 1. The three operations

| Operation | Use | Anchor | What `apply.py` does |
|---|---|---|---|
| `replace` | a wrong formula, number, definition, claim or term | the wrong text itself | swaps the located span |
| `insert_after` | a detail that is missing | a quote the new text follows | inserts after the span, on its own line when the anchor ends a line |
| `delete` | a claim no source supports, or a duplicate | the text to remove | removes the span, and the whole line when the span already covers one, so no empty line is left behind |

Every operation is located by `anchor.py`, which matches on a
whitespace-collapsed copy and writes to the real bytes. A re-padded table or a
re-wrapped list is therefore not a miss, and a heading renamed between runs is
not a near-miss that gets "fixed" anyway.

**Two occurrences is as much a failure as none.** `find` returns every hit and
never picks. Show them and ask which, or correct all.

## 2. The two kinds of wrongness

This is the distinction that decides whether an erratum is written, and getting
it backwards puts a claim into the extraction that the source never made.

| Kind | Meaning | In the notes | In the extraction |
|---|---|---|---|
| **Misreading** | the extraction does not match the source: OCR, a broken PDF text layer, a bad transcript segment | corrected, **no marker** | an **erratum**, so the notes skill stops repeating it |
| **Wrong source** | the source really does say the wrong thing | corrected, `[source error: <ID>]` plus a one-line footnote stating what the source says | **nothing.** The extraction is the record of what the source says |

You can only tell them apart by opening the cited location. If you did not open
it, you are in neither case: you are in `[unverified: <ID>]`, and an unverified
correction never produces an erratum, because an erratum asserts what the source
says and nobody looked.

### The footnote

One line, in the course's resolved `notes_language`, beside the corrected
passage. It states what the source says and what is right. It does not explain
why, does not teach the concept and does not work an example — that is
course-explain's.

> The slide states F > 1.0; the standard threshold is 10. [source error: S22]

## 3. Filling gaps

`## Uncovered material` from the notes skill and `gap` findings from the revision
skill are **missing content, not wrong content**. They are the one case where you
add text rather than change it, and the rules are strict because the failure mode
is model prose entering the notes under a borrowed source ID.

1. **Content comes only from extraction items that have an ID.** You write
   nothing from your own knowledge. `verify_fix.py marker` fails the fix if the
   inserted text carries no marker, or carries one that is not in this run's
   extractions.
2. **The user's own material belongs in `## My additions`**, which you never
   touch. If they want a note of their own added, that is where it goes and it is
   theirs to write.
3. **Placement** is `insert_after`, inside the section of the concept the item
   belongs to, with the **normal source marker** (`[S24]`). That is the notes
   skill's convention, not a correction marker. A gap fill leaves no correction
   marker at all.
4. **In the same correction**, retire the item's line from `## Uncovered
   material`, update `coverage:` in the frontmatter, and remove the warning
   callout once coverage is complete. Those three are the only things outside
   the anchor that a correction may touch, and `apply.py` calls them the
   declared edit set. Anything else changing is a failed write.
5. **`D_verification.md` is not edited.** You know the item is handled from your
   own log (`origin: uncovered S24`), so `review` does not propose it again.
6. If a later notes-skill run places the item itself, the entry becomes
   `absorbed`.

## 4. What is not a correction

| Request | Answer |
|---|---|
| "this is confusing", "explain X", "derive it", "make it simpler" | course-explain. Your evidence-only reason for a rejected correction is the whole of what you say about content. |
| "the overview for L03 is wrong" | a notes-skill re-run fixes the overview; you do not correct it |
| "the table of contents is out of date" | it is rebuilt from the headings; correct the heading instead |
| "rewrite this section, it reads badly" | that is a rewrite, which is the notes skill's |
| "add my own summary here" | `## My additions`, written by the user |
| "delete lesson 4" | course-setup, and it sets files aside rather than deleting |

## 5. Choosing `basis`

`basis: source` when the extractions, or the cited location, support the fix.
`basis: user` in all three marked cases, and that includes every fix resting on
a course-explain finding alone: a finding is a report, not evidence.

A `basis: external` explain finding carries a snapshot with a URL and a
retrieval date. It may **corroborate** what an extraction says. It can never be
the primary source, and it never turns a `user` basis into a `source` one.

## 6. Verification, per type

| Type | Check | `verified:` |
|---|---|---|
| formula in LaTeX | parsed and compared with expressions found in the evidence text | `sympy`, or `not machine-verified` when it does not parse or nothing corroborates it |
| number or computed result | recomputed | `numeric` |
| filled gap | the inserted text carries a source marker whose ID is in the extraction | `marker` |
| text claim | the quote and its ID go in the plan; the user's confirmation is the check | `not machine-verified` |

`not machine-verified` is a normal, honest outcome and it is printed in the plan.
A fix whose check **fails** — a recomputed number that disagrees, a gap fill with
an invented ID, a "correction" equivalent to the text already there — is
**dropped**, counted in the report, and never repaired by the model.
