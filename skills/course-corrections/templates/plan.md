<!--
The plan course-corrections prints in chat before it writes anything. Not a file
in the vault: this is the shape to follow in the conversation.

The safety property is that EVERYTHING DECIDED APPEARS IN THE PLAN. A correction
the user cannot see in the plan is a correction they did not confirm.
-->

```
ECON_Advanced_Econometrics, corrections for L03

1. L03 · Instrument relevance · formula
     now:  the rule of thumb is first-stage F > 1.0        [S22]
     fix:  the rule of thumb is first-stage F > 10
     why:  slide 22 re-read: "first-stage F > 10". OCR misread the decimal point.
     check: sympy ✓
     also: erratum for Content/slides_lecture3.pptx S22 (lesson-local)
     also: L09 carries the same sentence — same group

2. L03 · Instrument relevance · gap
     add:  "Stock-Yogo critical values depend on the number of instruments." [S24]
     after: "Weak instruments bias 2SLS toward OLS. [T11]"
     why:  finding f-0007 (course-revision) and ## Uncovered material — one problem
     check: marker ✓ · coverage 110/112 → 111/112

3. L03 · link · broken heading anchor
     now:  [[ECON_L09_Final_notes#Instrument relevance]]
     fix:  [[ECON_L09_Final_notes#Instrument strength]]
     why:  concepts.json: instrument-relevance is now "Instrument strength" in L09

Not proposed
  · broken file link [[ECON_L99_Final_notes]] in L03 — a missing file, which is
    course-setup's or course-notes'
  · x-0004 (course-explain) rests only on its own claim; if you want it applied
    it is basis: user with [student, sources differ: S14]

3 fixes, 1 erratum, 2 lessons, 2 findings closed.
The erratum is lesson-local, so no other lesson goes stale.
Apply all, some (numbers), or none?
```

<!--
Reply protocol, the same as course-setup's:

  "yes" / approval             applies every row
  numbers ("1 and 3")          applies that selection
  prose correcting a row       amend it and REPRINT THE WHOLE PLAN, then re-ask
  "2 is not an error"          that row is dropped and its finding is closed
                               `rejected` with that sentence as the reason
  silence about a row          NOT consent for a row carrying [unverified: …] or
                               resting on basis: user — ask about those explicitly

The reprint exists because one correction changes derived values. "Row 1 is
about L09, not L03" changes the group, the affected lessons, the erratum's reach
and which notes go stale.

Rows that must never appear in a plan: anything under `## My additions`,
`## My notes`, `Explanations/`, `.work/`, an overview or `Table_of_contents.md`.
scripts/apply.py refuses them, and a refusal aborts the whole run.
-->

<!--
The report, after applying. Always ends with the next step.

```
ECON_Advanced_Econometrics, corrections for L03

Applied    2 fixes (1 formula, 1 gap) in L03 and L09, 1 link repaired
Errata     1 new (slides_lecture3.pptx S22) → re-run notes for L03 to repair
           the extraction
Verified   1 formula by sympy, 1 gap marker checked, 1 not machine-verified
Findings   f-0007 resolved, f-0009 resolved, x-0003 rejected ("the slide really
           says 1.0; marked in the notes as a source error")
Coverage   110/112 → 111/112
Archive    2 versions in .work/history, 1 in .data/history
Open       1 orphaned correction (c-0002), shown at the next review
Next       re-run notes for L03, then replay, then revision
```
-->
