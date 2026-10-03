---
course: {{course}}
type: lesson
number: {{number}}
date: {{date}}
title: {{title}}
language: {{language}}
sources: [{{sources}}]
sources_hash: {{sources_hash}}
inputs:
  overview_row: "{{overview_row}}"
  overview_row_normalised: "{{overview_row_normalised}}"
  assignment_rows: [{{assignment_rows}}]
  errata: [{{errata}}]
sources_stat:
  - {path: {{source_path}}, size: {{source_size}}, mtime: {{source_mtime}}}
coverage: {{coverage}}
highlights: {{highlights}}
exam_signals:
  - {text: "{{signal_text}}", concept: "{{signal_concept}}", source: "{{signal_source}}"}
assessed_in: [{assignment: "{{assignment_no}}", task: {{task_no}}, concept: "{{task_concept}}"}]
flags: [{{flags}}]
generated: {{generated}}
run: {{run}}
generator: course-notes v1
---

# {{number}} - {{title}}

<!-- The same sentence, byte for byte, as the overview's. verify.py compares
     them: two summaries of one lesson that drift apart are worse than one. -->
**In one line:** {{the lesson's claim, in a sentence a reader can hold}}.

<!-- The warning banner appears only when there is something to warn about.
     Delete it entirely when flags is empty. -->
> [!warning] Needs checking
> {{n}} formulas read by OCR: [{{id}}], [{{id}}]
> {{n}} handwritten highlights, spans may be imprecise: [{{id}}!]

<!-- Present only when the transcript opened with a recap (§6.2). One line;
     never expand it, or the previous lesson's notes are duplicated here. -->
**Recap of [[{{code}}_L{{prev}}_Final_notes]]:** {{topic}}, {{topic}}

**What to remember:** [[#What to remember]] - Claude's ranking of what to hold, not the lecturer's.

<!-- Generated LAST by build_toc.py infile, from the headings actually written. -->
> [!summary]- Contents
> - [[#{{heading}}]]

## Definitions
<!-- ordered by first appearance in the lesson, never alphabetically -->

> **{{term}}** ({{lang}}. *{{translation}}*)
> "{{verbatim definition from the source}}" [{{id}}]

**{{term}}** ({{lang}}. *{{translation}}*) - two to four sentences when no
verbatim definition exists, with the formula and a short example where they
help. [{{id}}, {{id}}]

## {{Concept heading, never numbered}}
<!-- concept: {{concept-id}} -->

> [!important] Assessed in [[{{code}}_Assignment_{{nn}}|Assignment {{n}}]], task {{n}}

Explanatory prose in short paragraphs. Bullets only where the content is
genuinely enumerable. Every claim carries a compact source marker, written as
the extracted ID verbatim and nothing else. [{{id}}, {{id}}]

$$\text{the formula exactly as the source writes it, never as an image}$$

where

- $x$ ... what this symbol stands for, in the source's own terms [{{id}}]
- $y$ ... one line per symbol, never a paragraph [{{id}}]

==A short highlighted passage, up to two sentences, reproduced verbatim.== [{{id}}!]

> [!tip] Heavily marked in the source [{{id}}]
<!-- a highlight spanning a paragraph or more: a salient region, not a quote -->

The slide gave X; the lecturer corrected it to Y. [{{id}} corrected by {{id}}]

![[{{code}}_L{{nn}}_fig_{{sourceID}}_{{slug}}.png]]
*Figure (slide {{n}}): caption.* [{{id}}]

> [!note] Your note
> {{the student's own point, kept as a callout, never as a standalone claim}} [N{{nn}}]

> [!important] Exam signal
> "{{what the lecturer said}}" [T{{nn}}]

**Connects to:** [[#{{other heading}}]], [[#{{other heading}}]]

## {{Concept heading}}
<!-- concept: {{concept-id}} -->

> [!info] In the book, not lectured

Content the lecture never covered, included because it was highlighted.
[{{id}}, not lectured, {{id}}!]

## Assigned readings

### [[{{code}}_{{Author_Year_Slug}}]]
One paragraph of orientation, then the link. The full summary lives in the
shared note. [{{id}}, {{id}}]
Related sections: [[#{{heading}}]]

## Assigned videos

### [[{{code}}_{{Channel_Slug}}]]
One paragraph on what it covers and why it was assigned. [V{{n}}.{{n}}]
Related sections: [[#{{heading}}]]

## Assigned links

### [[{{code}}_{{Site_Slug}}]]
One paragraph of orientation. [K{{n}}.{{n}}]
Related sections: [[#{{heading}}]]

## Recap

Three to six sentences stating the lesson's core claims. No new content, no new
source markers that appear nowhere else.

## What to remember

<!-- protected: replace everything OUTSIDE the pair below, never what is inside it -->
<!-- ranking:yours:start -->
**Your pins** - nothing pinned yet.
<!-- ranking:yours:end -->

> [!warning] Claude's judgement, not the lecturer's
> Nothing below is taken from the slides, the reader or the transcript. It is a
> ranking of what seems most likely to be examined, made from this lesson alone,
> and it can be wrong. The material itself is above; this is a reading aid.

**Must know**
<!-- at most ten. every bullet carries [judgement]. one clause saying why. -->

- {{the claim, formula or distinction to hold}} - {{why it was ranked here}}. [judgement] [{{id}}]

**Also likely**

- {{shorter entries, same shape}}. [judgement] [{{id}}]

## Uncovered material
<!-- present only when Pass D found gaps; delete the whole section otherwise -->
- [{{id}}] "{{what it said}}" - no section covered this

## My additions
<!-- protected: preserved verbatim on every regeneration, created empty when absent -->
