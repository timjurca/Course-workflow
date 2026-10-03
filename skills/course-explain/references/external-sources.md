# External sources

Consulted when reaching outside the course material. The two fences and the
absolute "never fetch during an assignment question" are in `SKILL.md`, because
they bind on turns where this file was never opened.

**You are the only skill in this plugin with network access.** Every other skill
is local by construction. That asymmetry is deliberate — the material is often
thin, and a tutor that cannot reach past a bad slide is a tutor with a bad slide
— and the rails below are the price of it.

## When to fetch

On your own initiative, whenever external material would make the explanation
materially better: the course material is thin, opaque or silent; a standard
result needs its actual statement; a worked example needs a canonical form.

**Not** for questions the notes already answer well. A fetch that adds nothing
still costs the student a citation to read and a budget slot.

## The authority ladder

Applied in order. **A lower rung never overrides a higher one.**

| Rung | What | `fetch.py` calls it |
|---|---|---|
| 1 | the course's own material — notes, extractions, the assigned book and articles | never fetched |
| 2 | standard reference works: the recognised textbooks, the original papers, official documentation, standards bodies | `standard reference` |
| 3 | institutional teaching material: university course pages, lecture notes from named departments | `institutional teaching material` |
| 4 | general web | `general web` |

`fetch.py` classifies by domain, and says `heuristic: true`, because it is one.
The judgement is yours. Rung 4 is used for orientation and for finding rungs 2
and 3; it is cited **on its own** only when nothing higher exists, **and you say
that is why**.

## The rails

Non-negotiable, all of them.

- **Announce.** Say you went outside, in the answer, *before* the fetched
  content. Never a silent fetch.
- **Snapshot.** Every fetched claim used in an explanation is recorded with its
  URL, its retrieval date, and a **verbatim quote of at most 50 words**. A link
  with no snapshot rots; a snapshot survives the page.
- **Never outranks the course.** A fetched source that contradicts the course
  material produces a **tier-3 claim**, not a correction — and a candidate
  finding, on confirmation only (`references/findings.md`).
- **Never during an assignment question.** `fetch.py get --assignment-context`
  refuses outright.
- **Never this course's assessment material.** If a fetched page turns out to be
  its solutions, a marking scheme or a solved past paper, discard it, say you
  did, and do not cite it. `fetch.py` flags the obvious cases; the rule is
  absolute regardless.
- **Only in service of an explanation.** Fence 2 applies to fetching as to
  everything else.
- **Provenance in the answer.** External claims are named as external.

## The budget

**3 fetched sources in one answer, 2 more across the follow-ups on the same
concept in one session.** Beyond that, say you have read enough and explain from
what you have.

The counters live in a scratch file **outside the vault** — session state, not a
record of the student's work — passed as `--budget-file`. `explain_state.json`
holds ID counters, `applied_renumbers`, the depth, the coverage index and the
rejected list, and nothing else. Without a budget file the counters are not
enforced and `fetch.py` says so; keep to the numbers by hand.

A context compaction makes the budget unenforceable. That is a known limit, not
a licence to ignore it.

## The reference block

Pinned in `shared/note-invariants.md` §4. `fetch.py block --refs refs.json`
renders it, so that four hand-written variants do not end up disagreeing.

```markdown
## External references

**[W3]** Stock, J. & Yogo, M. (2005), *Testing for Weak Instruments in Linear IV Regression*.
https://example.org/stock-yogo · retrieved 2026-03-12 · authority: standard reference
> "critical values for the Cragg-Donald statistic depend on the number of
> instruments and the tolerated bias relative to OLS"
```

- `W<n>` ids are **local to one file or one chat answer**, never global.
- Every `[W<n>]` used in the prose must be resolved in the block, and every entry
  in the block must be cited in the prose. `markers.py check` enforces both.
- Chat answers cite the same way and list the references at the end of the
  answer.

## When a fetch fails

Say so, explain from tiers 1 and 2, and **never invent a citation**. A plausible
reference to a paper that says something else is worse than no reference, because
it cannot be checked without leaving the vault.
