# Grading rubric

Grading is where being a yes man costs the most. A generous mark is pleasant to
receive, arrives weeks before the exam, and is indistinguishable from a real one
until the exam says otherwise.

## Contents

- [1. Before marking](#1-before-marking)
- [2. What earns marks](#2-what-earns-marks)
- [3. What loses marks](#3-what-loses-marks)
- [4. The mark scheme and its provenance](#4-the-mark-scheme-and-its-provenance)
- [5. The feedback file](#5-the-feedback-file)
- [6. Into the ledger](#6-into-the-ledger)
- [7. The readiness verdict](#7-the-readiness-verdict)
- [8. Grading a real past exam](#8-grading-a-real-past-exam)

---

## 1. Before marking

1. The attempt is a file **A filed**. A file attached to the grading request is
   not graded: say "filing via course-setup first" and stop.
2. Read it with `shared/scripts/ocr.py` for a scan or a photograph.
3. **Every uncertain reading is quoted back and confirmed before marking.**
   C never grades a guess about what the student wrote. This is not politeness:
   marking a misread word wrong puts a false failure into the ledger, and the
   ledger is what the readiness verdict is built from.

## 2. What earns marks

Partial credit **per marking point**, from the solutions file.

- A different but valid route earns the marks. Where the numbers differ from the
  solution, re-check by script (`verify_calc.py`) before deciding anything: the
  student may be right and the solution wrong.
- Reasoning is what is marked, **not keywords**. An answer with the right words
  in the wrong relation earns nothing for that point.

## 3. What loses marks

| Situation | Effect |
|---|---|
| Correct result, wrong reasoning | The reasoning points are lost. The result points may stand |
| Vague answer | Loses points for vagueness, named as such. "Roughly right" is not a mark |
| Right idea, wrong direction | No marks for that point. Say which direction the notes give |
| Missing a marking point entirely | That point's marks, and the point is quoted in the feedback |

**No praise padding.** The flaw comes first in every question's feedback, before
anything that went well. A student skims; whatever is first is what is read.

## 4. The mark scheme and its provenance

Layered, and **always labelled**:

1. `printed` — points on the exam paper or in the official solutions
2. `course_info` — grading rules from `Course_description.md` or from an
   announcement in a lesson overview
3. `estimated` — C allocated the marks by question type and effort

An `estimated` scheme lowers the confidence of every grade and every verdict
built on it, and says so in both. **C never presents an estimate as official.**
`exam_profile.py write` returns the caveat text; put it in the feedback file and
in the verdict.

## 5. The feedback file

Name: the attempt's filename with `_Attempt_` replaced by `_Feedback_`, so the
date is the **attempt** date and a same-day `_2` suffix carries over.

`ECON_Mock_01_Attempt_2026-06-02_2.pdf` → `ECON_Mock_01_Feedback_2026-06-02_2.md`

Per question: the score, **the flaw first**, then what a full answer needed, then
the link into the notes section. Plus the hidden line

```markdown
<!-- concept: instrument-relevance · score: 0.5 -->
```

which is what makes the ledger rebuildable from the feedback files alone after a
loss. It is not optional.

The grade is labelled **"estimate, not an official grade"** at the top, with the
mark-scheme source beside it.

## 6. Into the ledger

Results enter with `by: graded`. Nothing else ever enters the ledger — revision
files have no checkboxes and there is no self-assessment input, so no generous
self-marking can inflate a verdict.

| Evidence | Error factor |
|---|---|
| Graded wrong | Full increase |
| Graded partial | Half increase |
| Graded correct | Full decrease |

A concept becomes `mastered` only after **two graded correct answers in a row**.
A concept never graded stays `untested`, and the mock coverage floor forces
untested concepts in, so everything is eventually measured.

Graded tutorial-style questions count toward the **lesson** concept.

## 7. The readiness verdict

Every mock report and every `status` ends with a plain verdict, built only from
ledger data.

- Too little data gives **"unknown"**. Never "looking good".
- Name the concepts that are failing and the ones never tested.
- An `estimated` mark scheme is stated in the verdict itself.
- Every skip the student asked for appears, with its date, in **every later**
  verdict.
- A concept with repeated graded failures may be handed to **course-explain**:
  *"you lost marks on instrument relevance twice — ask course-explain why."*
  That is the only place C names another skill for content.

```
Readiness  NOT exam-ready
           L05 Instrument exogeneity: missed 2 of 2 graded
           L08 Panel fixed effects: never tested
           Mastered 9 of 31 concepts, 12 never graded
           Skipped by request: L07 Bootstrap (2026-05-30)
           Mark scheme: estimated (no points on past exams)
           Instrument exogeneity has failed twice -> ask course-explain why
```

## 8. Grading a real past exam

Same flow, against an attempt A filed as
`<CODE>_Past_<date>[_P<n>]_Attempt_<date>`. Marked with the exam's **official**
solutions where they exist, or with C's own solutions **labelled as such**.

Output goes to `Mock_exams/`, with `_Attempt_` replaced by `_Feedback_`.

The feedback says plainly that the student has now seen this exam, and that it is
not used as a test again.
