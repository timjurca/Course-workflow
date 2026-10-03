<!--
The shape of Final_notes/<CODE>_L<NN>_Revision_notes.md. Not a file in the vault:
this is the contract to follow when writing one.

Every concept in the final notes appears exactly once, with a concept comment, so
verify.py can match the two documents. Depth is the only thing that varies.

Contents, not calculations: every general formula and every factual number
stays; no worked example, calculation, numeric result or data table appears.
A rule table stays, because it gets a point across at a glance.
-->
---
course: Financial Management
type: revision_notes
number: 03
date: 2026-09-22
title: Time Value of Money and Investment Decision Rules
language: en
of: Final_notes/FM_L03_Final_notes.md
notes_hash: 0a186e645599eee9be542281d0677b2b9e3c1f7a4d2b8c6e5a0f9d3b7c2e1a84
concepts: 25
depth: {must_know: 11, also_likely: 6, rest: 8}
figures: 4
generated: 2026-09-25
generator: course-condense v1
---

# 03 - Time Value of Money and Investment Decision Rules · revision

> [!abstract] How to read this
> The short version of [[FM_L03_Final_notes]]. Every claim here is in that file;
> nothing was added. Each heading links back to its full section.
> **Not examinable:** incremental IRR, said on the slide and again in the lecture.
> 39 statements in the full notes were read from slide images and carry a verify
> flag there.

<!-- A stale-source warning goes here too, when gate check 4 warned. -->

## Must know

### The three rules of time travel
<!-- concept: the-three-rules-of-time-travel -->
[[FM_L03_Final_notes#The three rules of time travel]]

- **Rule 1.** Only values at the same point in time can be compared or combined
    - a prohibition before it is a technique
    - two amounts in the *same* year may be added with no moving
- **Rule 2, forward.** compound: $FV_n = C \times (1+r)^n$
- **Rule 3, backward.** discount: $PV = C/(1+r)^n$
- **Order does not matter:** any route through the timeline gives the same value

### Net present value
<!-- concept: net-present-value-and-the-npv-decision-rule -->
[[FM_L03_Final_notes#Net present value and the NPV decision rule]]

$$NPV = PV(\text{benefits}) - PV(\text{costs})$$

| Outcome | Decision |
|---|---|
| $NPV > 0$ | accept |
| $NPV < 0$ | reject |
| $NPV = 0$ | marginal: indifferent, keep the status quo |
| several candidates | **choose the highest NPV** |

- a **barely positive** NPV is a borderline case, not an acceptance

## Also likely

### The interest rate as an exchange rate across time
<!-- concept: the-interest-rate-as-an-exchange-rate-across-time -->
[[FM_L03_Final_notes#The interest rate as an exchange rate across time]]

- Interest rate factor **$(1 + r_f)$**, discount factor **$1/(1 + r_f)$**
- $r_f$ is the rate at which money is borrowed or lent **without risk**

## Also in this lesson

One line each. Follow the link when you need the full treatment.

- **The law of one price**, equivalent cash flows must trade at the same price, or arbitrage follows. [[FM_L03_Final_notes#The law of one price and arbitrage]]
- **The incremental IRR**, the rate at which switching between two projects becomes profitable. *Not examinable.* [[FM_L03_Final_notes#The incremental IRR]]

## My additions

<!-- Yours. Preserved verbatim on every re-run. -->
