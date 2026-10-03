# Question types, difficulty and answer rules

Read this before writing a single question. The rules here are what keep a
revision file from being a pleasant read that measures nothing.

## Contents

- [1. The four types](#1-the-four-types)
- [2. The difficulty floor](#2-the-difficulty-floor)
- [3. How many questions](#3-how-many-questions)
- [4. Answer rules](#4-answer-rules)
- [5. Tutorials](#5-tutorials)
- [6. What a question may never be](#6-what-a-question-may-never-be)

---

## 1. The four types

| Type | Answer shape | When it is allowed |
|---|---|---|
| `definition` | From `terms.json`. Blockquoted with its source marker **only when the entry has `verbatim: true`**; otherwise plain prose with the marker. | Always. Attach it to the concept where the term is first defined, never to a fixed section. |
| `explain` | A short model answer, then **Marking points**: what a grader must see. | Always |
| `calculation` | A worked solution, step by step, script-verified (`verify_calc.py`). | Always |
| `mcq` | Four options, and why each wrong option is wrong. | **Only when the exam profile contains MCQ.** No past exams means no MCQ. |

The `verbatim` rule is B's plagiarism guard, not a formatting preference. A
definition quoted verbatim without its blockquote and marker reads as the
skill's own wording of the lecturer's sentence.

`application` is not a fourth file type; it is an `explain` or `calculation`
question that puts the method in a setting the notes did not use. It counts
toward the difficulty floor.

## 2. The difficulty floor

**At least 50% of a revision file's questions are `explain`, application or
`calculation`.** Never mostly recall.

This cannot be switched off by request. "Give me easier questions" **adds**
easier ones; it never removes the hard ones, and the report says so in one line.

The threshold is speculative and meant to be calibrated against one real exam's
mix (spec open item 2). `coverage.py` enforces whatever it is set to.

## 3. How many questions

Coverage decides, with **no upper cap**:

- at least **one question per concept**
- at least **one question per exam signal**, and a question must **cite the
  signal's source ID**
- **one extra** per past-exam appearance of the concept
- concepts with importance **5 or more** get at least **two** questions of
  **different types**

`coverage.py check` computes all four and the difficulty floor in one pass.
On a gap: **one** repair pass, then a loud flag in the file and in the report.
It never loops.

## 4. Answer rules

- Every answer links its concept section:
  `[[ECON_L03_Final_notes#Instrument relevance]]`
- **Every claim carries B's source marker**, in the verbatim ID form: `[S16]`,
  `[B15.3]`, `[S16 corrected by T11]`
- Detail that is in B's extraction but not in the notes body is allowed and
  **marked**: `[S22, not in notes]`. It is also a candidate `gap` finding for
  skill D — run it through `findings.py`, which drops it if B already flagged it
- OCR and uncertainty flags inherited from the notes are carried into every
  answer that uses the flagged material
- A question never asks for something the notes and extractions do not contain.
  **No invented facts, numbers or citations.** If the material does not support a
  question, write fewer questions
- Terms in the exam language come only from `terms.json`, a past exam or
  `exam_glossary.json`. Otherwise: source-language term, bracketed guess, and
  `[translation, verify]`

## 5. Tutorials

Tutorials get their own file, `<CODE>_T<NN>_Revision.md`, written from the
tutorial notes, and it is **calculation and application heavy**.

A tutorial question reuses the **method** of a solved problem with **new numbers
or a new setting**. Never the solved problem itself: the student already has the
worked answer, so re-asking it measures nothing.

Concept mapping comes from B. Each tutorial problem section carries the concept
ID of the lesson section it practises. A problem with no ID is matched to a
concept of the lesson named in the overview's `Lesson` column, the match is shown
in the report, and an uncertain match is asked about. If the `Lesson` column is
empty too, **ask**. Never infer from dates.

## 6. What a question may never be

| Never | Why |
|---|---|
| A restatement, paraphrase or re-parameterisation of an assignment task | The answer sits directly under it. That is the assignment, solved. `lookalike.py check` decides; borderline cases are read by you |
| A copy of a past-exam question | Past exams and their official solutions are reference material: they set the depth, the marking style and the format. They are never mock content |
| A copy of a revision-file question, in a mock | All mock questions are new |
| The same text as an earlier question for that concept | Repeats are reworded or placed in a new context |
| Anything built on a saved explanation | `Explanations/` is tutor output. C never reads it and never generates a question from anything in it |
| A question whose calculation failed verification | Dropped, counted in the report, and logged as a `suspect` finding when the notes' own formula is the cause |
