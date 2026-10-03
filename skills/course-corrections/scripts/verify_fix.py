#!/usr/bin/env python3
"""Check a fix before it is written, and say plainly when it cannot be checked.

A correction replaces a flagged problem with a confident statement. The flag was
the one thing telling the reader to be careful, so removing it without a check
is strictly worse than leaving the error in place. This module is the check, and
its most important output is the honest one: `not machine-verified`, printed in
the plan, so the student knows their confirmation is the only thing holding the
fix up (spec section 13).

Four kinds, from the spec's table:

    formula   the old and the new LaTeX are parsed and compared, and the new one
              is matched against expressions found in the evidence text
    numeric   the arithmetic is recomputed and compared with the claim
    marker    a filled gap must carry a source marker whose ID really exists in
              the extraction — that is what keeps D from writing its own prose
              into the notes under a borrowed ID
    text      no machine check exists; the quote and its ID go in the plan and
              the student's confirmation is the check

A failing check **drops that fix**. It is never repaired by the model and never
weakened into a warning (D-18): a formula that failed its check and got written
anyway is the exact artefact this plugin must not produce.

LaTeX is normalised by hand rather than through `sympy.parsing.latex`, which
needs an antlr runtime that is not in this environment. The cleanup covers what
lecture notes actually contain; anything it cannot handle returns
`not machine-verified` rather than a guess.

CLI:
    verify_fix.py formula --old <latex> --new <latex> [--evidence <text>]
    verify_fix.py numeric --claim <expr> [--expected <value>] [--tolerance 1e-9]
    verify_fix.py marker  --text <str> --extraction <file> [<file> ...]
    verify_fix.py plan    --plan <plan.json> --course <path>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
from anchor import SOURCE_ID_RE                                   # noqa: E402

MATH_RE = re.compile(r'\$\$(?P<d>.+?)\$\$|\$(?P<i>.+?)\$', re.DOTALL)
ITEM_RE = re.compile(r'^###\s+(?P<id>\S+)\s*$', re.MULTILINE)

GREEK = ('alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu '
         'xi rho sigma tau phi chi psi omega Gamma Delta Theta Lambda Sigma Phi '
         'Omega').split()

# Ordered: \frac must be expanded before the backslash strip, and \left(/\right)
# before the parentheses matter.
REPLACEMENTS = [
    (re.compile(r'\\left|\\right'), ''),
    (re.compile(r'\\cdot|\\times'), '*'),
    (re.compile(r'\\div'), '/'),
    (re.compile(r'\\geq|\\ge\b'), '>='),
    (re.compile(r'\\leq|\\le\b'), '<='),
    (re.compile(r'\\neq|\\ne\b'), '!='),
    (re.compile(r'\\approx|\\sim'), '=='),
    (re.compile(r'\\sqrt\s*\{([^{}]*)\}'), r'sqrt(\1)'),
    (re.compile(r'\\(?:hat|bar|tilde|vec|mathrm|mathbf|text|operatorname)\s*\{([^{}]*)\}'),
     r'\1'),
    (re.compile(r'\\,|\\;|\\!|\\quad|\\qquad'), ' '),
    (re.compile(r'\\%'), ''),
]
FRAC_RE = re.compile(r'\\(?:frac|dfrac|tfrac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}')


RELATION_RE = re.compile(r'(?P<op>>=|<=|!=|==|>|<|=)')
# A relation written inside prose: "the first-stage F > 10 as a rule of thumb".
# Deliberately narrow — a name, an operator, a number or name — because a wider
# pattern starts "finding" relations in ordinary sentences.
PROSE_RELATION_RE = re.compile(
    r'(?<![\w.])(?P<lhs>[A-Za-z][A-Za-z0-9_\\^{}\-]{0,20})\s*'
    r'(?P<op>>=|<=|!=|>|<|=)\s*'
    r'(?P<rhs>-?\d+(?:\.\d+)?|[A-Za-z][A-Za-z0-9_]{0,20})(?![\w.])')

RELATIONS = {'>': 'Gt', '<': 'Lt', '>=': 'Ge', '<=': 'Le', '!=': 'Ne',
             '=': 'Eq', '==': 'Eq'}


def latex_to_sympy(text: str) -> tuple[str, list[str]]:
    """Enough LaTeX for lecture notes, plus the commands it did not understand.

    The list of leftovers is the point: a command this cleanup does not know
    could mean anything, and guessing at it would produce a "verified" verdict
    on an expression nobody parsed.
    """
    s = text.strip().strip('$').strip()
    for _ in range(4):                      # nested fractions, innermost first
        new = FRAC_RE.sub(r'((\1)/(\2))', s)
        if new == s:
            break
        s = new
    for pattern, repl in REPLACEMENTS:
        s = pattern.sub(repl, s)
    s = s.replace('\\lambda', 'lamda')      # sympy's own spelling; `lambda` is a keyword
    for name in GREEK:
        s = s.replace('\\' + name, name)
    s = s.replace('^', '**').replace('{', '(').replace('}', ')')
    unknown = sorted(set(re.findall(r'\\[A-Za-z]+', s)))
    return s.strip(), unknown


def _locals() -> dict:
    """Force the names lecture notes use to be plain symbols.

    Without this, `beta` resolves to sympy's Beta **function**, `E` to Euler's
    number and `I` to the imaginary unit, and an expectation or a slope
    coefficient stops being comparable with itself. Every one of those is a
    silently wrong verdict rather than an error.
    """
    from sympy import Symbol
    import string
    names = list(GREEK) + ['lamda'] + list(string.ascii_uppercase)
    names += ['beta', 'gamma', 'zeta', 'chi', 'psi', 'phi', 'pi', 'sigma', 'nu']
    return {n: Symbol(n) for n in names}


def _expr(cleaned: str):
    """One expression, no relation. Returns None rather than raising.

    Two passes, and the order matters. `implicit_multiplication_application`
    is what makes `2x` parse, but it reads `Cov(z,y)` as a product with a tuple
    and fails on every covariance in an econometrics note. So the strict parse
    goes first and the implicit one is the fallback.
    """
    import warnings
    from sympy.parsing.sympy_parser import (parse_expr, standard_transformations,
                                            implicit_multiplication_application,
                                            convert_xor)
    strict = standard_transformations + (convert_xor,)
    loose = strict + (implicit_multiplication_application,)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for transformations in (strict, loose):
            try:
                return parse_expr(cleaned, transformations=transformations,
                                  local_dict=_locals())
            except Exception:
                continue
    return None


def _parse(text: str):
    """Parse an expression or a relation. Relations are built explicitly.

    Sympy's parser turns `a = b` into an assignment error and `a == b` into a
    Python bool, so splitting on the operator and constructing `Gt`/`Eq`/... by
    hand is the only way a threshold like `F > 10` survives as something
    comparable.
    """
    import sympy
    cleaned, unknown = latex_to_sympy(text)
    if not cleaned:
        return None, 'there is nothing to parse'
    if unknown:
        return None, ('the expression uses ' + ', '.join(unknown)
                      + ', which this checker does not understand')
    m = RELATION_RE.search(cleaned)
    if m:
        lhs, rhs = cleaned[:m.start()], cleaned[m.end():]
        a, b = _expr(lhs.strip()), _expr(rhs.strip())
        if a is None or b is None:
            return None, 'sympy could not parse one side of the relation'
        try:
            return getattr(sympy, RELATIONS[m.group('op')])(a, b, evaluate=False), None
        except Exception as exc:
            return None, f'sympy could not build the relation: {type(exc).__name__}'
    expr = _expr(cleaned)
    if expr is None:
        return None, 'sympy could not parse it'
    return expr, None


def _show(expr) -> str | None:
    try:
        return str(expr)
    except Exception:
        return None


def _equivalent(a, b) -> bool:
    import warnings
    from sympy import simplify
    from sympy.core.relational import Relational
    if a is None or b is None:
        return False
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            if isinstance(a, Relational) or isinstance(b, Relational):
                if not (isinstance(a, Relational) and isinstance(b, Relational)):
                    return False
                return (type(a) is type(b) and simplify(a.lhs - b.lhs) == 0
                        and simplify(a.rhs - b.rhs) == 0)
            return bool(simplify(a - b) == 0)
        except Exception:
            return False


def _evidence_expressions(evidence: str):
    """Every expression in the evidence worth comparing with: math spans, then prose."""
    for m in MATH_RE.finditer(evidence):
        yield (m.group('d') or m.group('i')).strip()
    for m in PROSE_RELATION_RE.finditer(evidence):
        yield m.group(0).strip()


def formula(old: str, new: str, evidence: str | None = None) -> dict:
    old_expr, old_why = _parse(old)
    new_expr, new_why = _parse(new)
    out = {'kind': 'formula', 'old': old, 'new': new,
           'old_parsed': _show(old_expr), 'new_parsed': _show(new_expr)}
    if new_expr is None:
        return {**out, 'verified': 'not machine-verified', 'ok': True,
                'reason': new_why,
                'note': 'shown in the plan as [not machine-verified]; your '
                        'confirmation is the only check'}
    if old_expr is not None and _equivalent(old_expr, new_expr):
        return {**out, 'verified': 'not machine-verified', 'ok': False,
                'reason': 'the corrected formula is equivalent to the one already in '
                          'the notes, so this correction changes nothing'}

    matched = []
    if evidence:
        for candidate in _evidence_expressions(evidence):
            expr, _ = _parse(candidate)
            if expr is not None and _equivalent(expr, new_expr):
                matched.append(candidate)
    if matched:
        return {**out, 'verified': 'sympy', 'ok': True, 'matched_in_evidence': matched}
    return {**out, 'verified': 'not machine-verified', 'ok': True,
            'reason': 'the new formula parses, but nothing equivalent to it was found '
                      'in the evidence text',
            'note': 'shown in the plan as [not machine-verified]'}


def numeric(claim: str, expected=None, tolerance: float = 1e-9) -> dict:
    expr, why = _parse(claim)
    out = {'kind': 'numeric', 'claim': claim}
    if expr is None:
        return {**out, 'verified': 'not machine-verified', 'ok': True, 'reason': why}
    try:
        value = expr.doit() if hasattr(expr, 'doit') else expr
        value = value.evalf()
        float(value)
    except Exception as exc:
        return {**out, 'verified': 'not machine-verified', 'ok': True,
                'reason': f'it parses but does not evaluate: {type(exc).__name__}'}
    if expected is None:
        return {**out, 'verified': 'numeric', 'ok': True, 'value': str(value)}
    want, why = _parse(str(expected))
    try:
        ok = abs(float(value) - float(want.evalf())) <= tolerance
    except Exception:
        ok = str(value) == str(want)
    return {**out, 'verified': 'numeric' if ok else 'not machine-verified',
            'ok': ok, 'value': str(value), 'expected': str(expected),
            'reason': None if ok else 'the recomputed value does not match the claim; '
                                      'this fix is dropped, not repaired'}


def marker(text: str, extractions: list[str]) -> dict:
    """A filled gap must cite an ID that really exists, or D is writing its own prose."""
    known = set()
    for raw in extractions:
        p = Path(raw)
        if p.is_file():
            known |= set(ITEM_RE.findall(p.read_text(encoding='utf-8')))
    cited = SOURCE_ID_RE.findall(text)
    unknown = sorted({c for c in cited if c.rstrip('!') not in known
                      and c not in known})
    if not cited:
        return {'kind': 'marker', 'verified': 'not machine-verified', 'ok': False,
                'cited': [], 'reason': 'the inserted text carries no source marker; '
                                       'content comes only from extraction items with '
                                       'an ID, and your own material belongs in '
                                       '## My additions'}
    if unknown:
        return {'kind': 'marker', 'verified': 'not machine-verified', 'ok': False,
                'cited': cited, 'unknown': unknown,
                'reason': f'{", ".join(unknown)} is not an item in this run\'s '
                          'extractions'}
    return {'kind': 'marker', 'verified': 'marker', 'ok': True, 'cited': cited}


def for_plan(course: Path | str, plan: dict) -> dict:
    """Run the right check for every edit and hand back the `verified:` values."""
    course = Path(course)
    rows = []
    for edit in plan.get('edits') or []:
        kind = edit.get('verify') or ('marker' if edit.get('gap') else 'text')
        evidence = edit.get('evidence_text') or edit.get('evidence') or ''
        if kind == 'formula':
            row = formula(edit.get('before', ''), edit.get('after', ''), evidence)
        elif kind == 'numeric':
            row = numeric(edit.get('claim') or edit.get('after', ''),
                          edit.get('expected'))
        elif kind == 'marker':
            files = [str(course / f) for f in (edit.get('extractions') or [])]
            row = marker(edit.get('after', ''), files)
        else:
            row = {'kind': 'text', 'verified': 'not machine-verified', 'ok': True,
                   'reason': 'no machine check exists for a text claim; the quote and '
                             'its ID go in the plan and your confirmation is the check',
                   'evidence': evidence}
        rows.append({'id': edit.get('id'), **row})
    return {'checks': rows,
            'dropped': [r['id'] for r in rows if not r['ok']],
            'all_ok': all(r['ok'] for r in rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('formula')
    p.add_argument('--old', required=True); p.add_argument('--new', required=True)
    p.add_argument('--evidence')
    p = sub.add_parser('numeric')
    p.add_argument('--claim', required=True); p.add_argument('--expected')
    p.add_argument('--tolerance', type=float, default=1e-9)
    p = sub.add_parser('marker')
    p.add_argument('--text', required=True)
    p.add_argument('--extraction', nargs='+', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--plan', required=True); p.add_argument('--course', required=True)
    args = ap.parse_args(argv)

    if args.cmd == 'formula':
        out = formula(args.old, args.new, args.evidence)
    elif args.cmd == 'numeric':
        out = numeric(args.claim, args.expected, args.tolerance)
    elif args.cmd == 'marker':
        out = marker(args.text, args.extraction)
    else:
        out = for_plan(args.course,
                       json.loads(Path(args.plan).read_text(encoding='utf-8')))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
