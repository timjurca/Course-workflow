# Derivations

Consulted while building one. The rule that a derivation is **tier 2 unless the
course shows that derivation** is in `SKILL.md`, because it binds whether or not
you have opened this file.

## Why step-by-step and not the endpoint

A derivation is the one output where **the answer can be right and the path
wrong**. The student is not learning the answer — they already have it, from the
slide — they are learning the path. An endpoint check certifies precisely the
failure that matters least, and it certifies it confidently.

So every step is checked against **its predecessor**, never against the
conclusion.

## The four step outcomes

`verify_calc.py derivation --steps steps.json`, where each step is
`{"expr": "...", "label": "step 3: substituting y = X·beta + u"}`.

| Outcome | When | What appears in the answer |
|---|---|---|
| `ok` | the difference from the previous step simplifies to zero | a tick, or nothing |
| `failed` | a numeric counterexample was found | **nothing.** Fix it and re-check. |
| `assumption` | the step's label says it assumes, substitutes, defines, imposes or takes a limit | the label, verbatim: *"step 4: assuming plim(Z'u/n) = 0" — **assumption, not derived*** |
| `unchecked` | the step did not parse, or the comparison is not decidable | `[not machine-verified]`, **at the step** |

A step carrying an assumption is **exempted from the equivalence check and
labelled**, never silently skipped. A derivation that quietly assumes its
conclusion is the most persuasive wrong answer there is, and it is the failure
this whole procedure exists to prevent.

## The aggregate rule

If **more than half the transitions went unchecked** — unparseable plus exempt —
say that **the derivation as a whole is not machine-verified**. The script
returns `aggregate_not_machine_verified`.

The first step is a premise, not a transition, so it is out of the denominator.
Unchecked counts assumptions as well as parse failures, because both leave the
reader with a line nothing verified; counting only the parse failures would let a
chain of five assumptions come back as fully checked.

## Parsing, and why it usually works now

`verify_calc.py` binds **every bare identifier as a symbol** and every called
identifier as an opaque function, rather than letting sympy's own namespace
decide. Without that, `beta` is the beta function, `E` is Euler's number and
`S`, `I`, `N`, `Q` and `O` are all something other than the variables the
lecturer wrote on the board, and a real econometrics step returns a `TypeError`
instead of a check. `pi`, `oo`, `zoo` and `nan` keep their sympy meanings; the
usual function names (`exp`, `log`, `sqrt`, `Sum`, …) keep theirs.

A consequence worth knowing: a step containing `E(...)`, `Var(...)` or
`plim(...)` is compared as **opaque functions**, so an identity like
`Var(a·x) = a²·Var(x)` comes back `undecidable`, not `failed`. That is honest —
sympy has no axioms for those — and it is why `undecidable` is marked
`[not machine-verified]` rather than treated as an error. Treating it as an error
would make you discard a correct line, re-derive it, and then refuse to show a
worked example at all.

Anything containing a non-mathematical token (`__`, `import`, `lambda`, `open`,
`eval`, `exec`, `os`, `sys`, `subprocess`) is refused before parsing.

## Presentation

```markdown
$$\hat{\beta}_{IV} = (Z'X)^{-1}Z'y$$
*step 2: substituting $y = X\beta + u$* ✓
$$\hat{\beta}_{IV} = \beta + (Z'X)^{-1}Z'u$$
*step 3: assuming $\text{plim}(Z'u/n) = 0$* — **assumption, not derived**
```

- Premises keep their own tier-1 source markers.
- The chain between them is `[beyond course]`.
- The provenance line at the end of the answer states the fraction: *"6 of 7
  derivation steps checked · 1 step assumed, not derived"*.

## When it fails

Two failed attempts ends it. Explain the method without the algebra and say why.
Never show the unchecked version, and never show it with a caveat: a caveat on a
wrong derivation is read as a caveat on a right one.
