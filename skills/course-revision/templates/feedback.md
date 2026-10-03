---
course: {{course}}
attempt: "{{attempt_filename}}"
exam: "[[{{exam_filename}}]]"
attempt_date: {{attempt_date}}
score: {{total_score}}
out_of: {{total_marks}}
mark_scheme: {{mark_scheme_source}}
graded: {{graded}}
generator: course-revision v1
---

# {{exam_display}} · Feedback, {{attempt_date}}

> [!warning] An estimate, not an official grade
> Marked against {{solutions_basis}} with a **{{mark_scheme_source}}** mark
> scheme. {{mark_scheme_caveat}}

**{{total_score}} / {{total_marks}}**

<!-- Per question: the flaw first, then what full marks needed. The hidden
     comment is what lets the ledger be rebuilt from these files alone. -->

## Question {{n}} - {{score}} / {{marks}}
<!-- concept: {{concept_id}} · score: {{score_fraction}} -->

**Flaw.** {{what_went_wrong}}

**What full marks needed.** {{what_was_required}}

**Concept:** [[{{code}}_{{key}}_Final_notes#{{concept_heading}}]]

---

## Readiness

{{verdict}}

{{skipped_lines}}

Mark scheme: {{mark_scheme_source}}
