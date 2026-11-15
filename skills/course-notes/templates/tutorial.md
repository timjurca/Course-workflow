---
course: {{course}}
type: tutorial
number: {{number}}
date: {{date}}
title: {{title}}
language: {{language}}
covers: L{{nn}}
sources: [{{sources}}]
sources_hash: {{sources_hash}}
inputs:
  overview_row: "{{overview_row}}"
  overview_row_normalised: "{{overview_row_normalised}}"
  assignment_rows: [{{assignment_rows}}]
  errata: [{{errata}}]
sources_stat:
  - {path: {{source_path}}, size: {{source_size}}, mtime: "{{source_mtime}}"}
coverage: {{coverage}}
highlights: {{highlights}}
exam_signals: []
assessed_in: []
flags: [{{flags}}]
generated: "{{generated}}"
run: "{{run}}"
generator: course-notes v1
---

# {{number}} - {{title}}

> [!summary]- Contents
> - [[#{{heading}}]]

## Definitions
<!-- still first, and still ordered by first appearance -->

**{{term}}** - {{definition, identical to the ledger's}} [{{id}}]

## Problem {{n}}: {{what it asks}}
<!-- concept: {{concept-id of the lesson section this connects to}} -->
<!-- A tutorial creates no concept of its own. The ID is read from the lesson
     section the Connects to link points at. A problem with no such link carries
     no ID and is reported. -->

**Setup:** ... [{{id}}]

**Method:** ... [{{id}}]

**Worked solution:**
1. ...
2. ...

**Common mistakes:** {{what the tutor flagged}} [{{id}}]

**Generalizes to:** {{the class of problems this method covers}}

**Connects to:** [[{{code}}_L{{nn}}_Final_notes#{{heading}}]]

## Recap

Three to six sentences on what this tutorial practised.

## Uncovered material
<!-- only when Pass D found gaps -->

## My additions
<!-- protected -->
