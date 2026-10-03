#!/usr/bin/env python3
"""Check E's own arithmetic, formulas and derivations before the student sees them.

Every other skill mechanically checks its own output. E is the most exposed,
because a worked example with an arithmetic slip does not merely fail to teach:
it teaches the wrong method, confidently, in the student's own notation, and the
student will reproduce it in the exam.

The `derivation` mode is the one that matters most, and it exists because a
derivation is the single output where **the answer can be right and the path
wrong**. The student is not learning the answer, they are learning the path, so
checking only the endpoint certifies precisely the failure that matters least.
Three rules follow from that:

  * each step is checked against its predecessor, not against the conclusion;
  * a step that introduces an assumption, a substitution or a limit is
    **labelled and exempted**, never silently skipped - a derivation that
    quietly assumes its conclusion is the most persuasive wrong answer there is;
  * an unparseable step is marked at the step, not at the end, and when more
    than half the steps went unchecked the derivation as a whole is declared
    not machine-verified.

What this cannot check is most of what E writes: an analogy, a framing, a
"where students go wrong". Nothing here touches those, and nothing here should
be read as covering them.

A tier-1 formula quoted from the course is **not** re-derived here. It is quoted
with its source ID, and a disagreement with it is a tier-3 claim, not a repair.

CLI:
    verify_calc.py number     --expr "3*4+2" [--claimed 14]
    verify_calc.py formula    --expr "a**2-b**2" --equals "(a-b)*(a+b)"
    verify_calc.py derivation --steps <file.json>   (or --json '<inline>')
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import sympy
    from sympy.parsing.sympy_parser import (parse_expr, standard_transformations,
                                            convert_xor)
except ImportError:                                                  # pragma: no cover
    sympy = None

TRANSFORMS = None if sympy is None else (standard_transformations + (convert_xor,))

NOT_VERIFIED = '[not machine-verified]'

# parse_expr evaluates the string it is given. The steps normally come from E
# itself, but a student can paste one, so anything that could reach the
# interpreter rather than the algebra is refused before parsing.
UNSAFE_RE = re.compile(r'__|\bimport\b|\blambda\b|\bopen\b|\beval\b|\bexec\b|'
                       r'\bos\b|\bsys\b|\bsubprocess\b')

ASSUMPTION_WORDS = ('assum', 'substitut', 'let ', 'set ', 'limit', 'plim',
                    'define', 'by definition', 'suppose', 'impose')


def _available() -> dict | None:
    if sympy is None:
        return {'error': 'sympy is not importable in this runtime',
                'consequence': ('nothing can be machine-checked: say so, and mark '
                                'every computed value ' + NOT_VERIFIED)}
    return None


IDENT_RE = re.compile(r'(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?P<call>\()?')

# Names that keep their sympy meaning. Everything else in a step is read as a
# symbol, which is the opposite of sympy's default and is deliberate: in course
# algebra `beta` is a coefficient, not the beta function, and sympy's own
# namespace turns half a real econometrics derivation into a TypeError. Open
# item 4 of the spec asks how often a real step parses at all; this is most of
# the answer, and the identifiers that were bound come back in the result so the
# reading is visible rather than assumed.
KNOWN_FUNCTIONS = {
    'sin', 'cos', 'tan', 'asin', 'acos', 'atan', 'sinh', 'cosh', 'tanh',
    'exp', 'log', 'ln', 'sqrt', 'Abs', 'abs', 'Max', 'Min', 'sign',
    'factorial', 'binomial', 'erf', 'Sum', 'Product', 'Integral', 'Derivative',
    'diff', 'integrate', 'limit', 'simplify', 'expand', 'factor', 'Piecewise',
    'Matrix', 'transpose', 'det', 'trace', 'inv',
}
KNOWN_CONSTANTS = {'pi', 'oo', 'zoo', 'nan'}


def _local_dict(text: str) -> dict:
    """Bind every bare identifier: a function where it is called, a symbol otherwise."""
    local = {}
    for m in IDENT_RE.finditer(text):
        name = m.group('name')
        if name in KNOWN_CONSTANTS or name in local:
            continue
        if m.group('call'):
            if name not in KNOWN_FUNCTIONS:
                local[name] = sympy.Function(name)
        else:
            local[name] = sympy.Symbol(name)
    return local


def parse(text: str):
    """Parse one expression or equation. Returns (expr, error)."""
    if not text or not text.strip():
        return None, 'empty'
    if UNSAFE_RE.search(text):
        return None, 'refused: the string contains a non-mathematical token'
    try:
        local = _local_dict(text)
        if '=' in text and '==' not in text:
            lhs, rhs = text.split('=', 1)
            return sympy.Eq(
                parse_expr(lhs, local_dict=local, transformations=TRANSFORMS),
                parse_expr(rhs, local_dict=local, transformations=TRANSFORMS)), None
        return parse_expr(text, local_dict=local, transformations=TRANSFORMS), None
    except Exception as exc:
        return None, '{}: {}'.format(type(exc).__name__, exc)


def _difference(a, b):
    """The quantity that must vanish for two steps to be equivalent."""
    ae = (a.lhs - a.rhs) if isinstance(a, sympy.Eq) else a
    be = (b.lhs - b.rhs) if isinstance(b, sympy.Eq) else b
    return sympy.simplify(ae - be)


def _equivalence(a, b) -> dict:
    """ok, contradicted, or undecidable - and the third is not a failure.

    A step containing `Var(x)` or `E(y)` carries a function sympy has no axioms
    for, so the difference will not simplify away however correct the algebra
    is. Reporting that as a failure would make E discard a correct line and
    re-derive it, twice, and then refuse to show a worked example. So an
    undecidable comparison is marked `[not machine-verified]` and counted as
    unchecked, which is what it is, while a numeric counterexample is a real
    failure and is reported as one.
    """
    try:
        diff = _difference(a, b)
    except Exception as exc:
        return {'status': 'undecidable', 'reason': str(exc), 'difference': None}
    if diff == 0:
        return {'status': 'ok', 'difference': '0'}
    opaque = bool(diff.atoms(sympy.core.function.AppliedUndef))
    free = sorted(diff.free_symbols, key=str)
    if not opaque and free:
        # Distinct small rationals, chosen so that a genuine identity cannot
        # vanish by coincidence on one lucky substitution.
        values = [sympy.Rational(p, 7) for p in (2, 3, 5, 11, 13, 17, 19, 23)]
        for offset in (0, 1):
            sub = {s: values[(i + offset) % len(values)] for i, s in enumerate(free)}
            try:
                val = sympy.N(diff.subs(sub))
            except Exception:
                return {'status': 'undecidable', 'difference': str(diff),
                        'reason': 'the difference could not be evaluated numerically'}
            if val.is_number and abs(val) > 1e-9:
                return {'status': 'contradicted', 'difference': str(diff),
                        'counterexample': {str(k): str(v) for k, v in sub.items()},
                        'value': str(val)}
        return {'status': 'undecidable', 'difference': str(diff),
                'reason': 'the difference is not zero symbolically but vanishes '
                          'on every value tried'}
    if not opaque and not free:
        return {'status': 'contradicted', 'difference': str(diff),
                'value': str(sympy.N(diff))}
    return {'status': 'undecidable', 'difference': str(diff),
            'reason': 'the expression contains functions sympy has no axioms for '
                      '(for example E, Var, plim), so equivalence is not decidable'}


def number(expr: str, claimed: str | None = None) -> dict:
    """Recompute a value and compare it with what E was about to write."""
    err = _available()
    if err:
        return err
    parsed, perr = parse(expr)
    if perr:
        return {'expr': expr, 'ok': False, 'parsed': False, 'reason': perr,
                'mark': NOT_VERIFIED}
    try:
        value = sympy.N(parsed)
    except Exception as exc:
        return {'expr': expr, 'ok': False, 'parsed': True, 'reason': str(exc),
                'mark': NOT_VERIFIED}
    out = {'expr': expr, 'parsed': True, 'value': str(value),
           'exact': str(sympy.simplify(parsed))}
    if claimed is None:
        out['ok'] = True
        return out
    want, werr = parse(str(claimed))
    if werr:
        out.update({'ok': False, 'reason': f'the claimed value does not parse: {werr}'})
        return out
    try:
        out['ok'] = bool(sympy.simplify(parsed - want) == 0)
    except Exception as exc:
        out.update({'ok': False, 'reason': str(exc), 'mark': NOT_VERIFIED})
        return out
    out['claimed'] = str(claimed)
    if not out['ok']:
        out['action'] = ('fix the number and re-check. Never show the unchecked '
                         'version; after two failures, explain the method without '
                         'numbers and say why.')
    return out


def formula(expr: str, equals: str) -> dict:
    """Symbolic equivalence of two forms of the same formula."""
    err = _available()
    if err:
        return err
    a, aerr = parse(expr)
    b, berr = parse(equals)
    if aerr or berr:
        return {'ok': False, 'parsed': False, 'mark': NOT_VERIFIED,
                'reason': aerr or berr, 'expr': expr, 'equals': equals}
    res = _equivalence(a, b)
    out = {'parsed': True, 'expr': expr, 'equals': equals,
           'ok': res['status'] == 'ok', 'status': res['status'],
           'difference': res.get('difference')}
    if res['status'] == 'undecidable':
        out['mark'] = NOT_VERIFIED
        out['reason'] = res.get('reason')
    if res['status'] == 'contradicted':
        out['counterexample'] = res.get('counterexample')
        out['action'] = 'fix the formula and re-check; never show it unchecked'
    return out


def _is_assumption(step: dict) -> bool:
    if step.get('assumption') is True:
        return True
    label = (step.get('label') or '').lower()
    return any(w in label for w in ASSUMPTION_WORDS)


def derivation(steps: list) -> dict:
    """Step against predecessor, assumptions exempted and labelled, aggregate rule.

    "Unchecked" means no equivalence check ran on that step: an unparseable step
    and an exempted assumption both count, because both leave the reader with a
    line nothing verified. Reporting only the unparseable ones would let a chain
    of five assumptions come back as fully checked.
    """
    err = _available()
    if err:
        return err
    rows, parsed = [], []
    for i, raw in enumerate(steps):
        step = raw if isinstance(raw, dict) else {'expr': str(raw)}
        expr, perr = parse(step.get('expr', ''))
        parsed.append(expr)
        row = {'n': i + 1, 'expr': step.get('expr'), 'label': step.get('label'),
               'status': None, 'mark': None}
        if perr:
            row['status'] = 'unparseable'
            row['reason'] = perr
            row['mark'] = NOT_VERIFIED
        elif i == 0:
            row['status'] = 'premise'
            row['note'] = 'the starting point; it carries its own tier-1 marker'
        elif _is_assumption(step):
            row['status'] = 'assumption'
            row['mark'] = 'assumption, not derived'
            row['note'] = ('exempt from the equivalence check, and the label is '
                           'part of the output')
        elif parsed[i - 1] is None:
            row['status'] = 'unchecked'
            row['reason'] = 'the previous step did not parse'
            row['mark'] = NOT_VERIFIED
        else:
            res = _equivalence(parsed[i - 1], expr)
            row['difference'] = res.get('difference')
            if res['status'] == 'ok':
                row['status'] = 'ok'
            elif res['status'] == 'contradicted':
                row['status'] = 'failed'
                row['counterexample'] = res.get('counterexample')
            else:
                row['status'] = 'unchecked'
                row['reason'] = res.get('reason')
                row['mark'] = NOT_VERIFIED
        rows.append(row)

    total = len(rows)
    checkable = [r for r in rows if r['status'] in ('ok', 'failed')]
    unchecked = [r for r in rows
                 if r['status'] in ('unparseable', 'unchecked', 'assumption')]
    failed = [r for r in rows if r['status'] == 'failed']
    # The first step is a premise, not a transition: the aggregate rule is about
    # the transitions between steps, so the premise is out of the denominator.
    transitions = max(total - 1, 0)
    aggregate = bool(transitions and len(unchecked) > transitions / 2)
    out = {'steps': rows, 'total': total, 'transitions': transitions,
           'checked': len(checkable), 'verified': len(checkable) - len(failed),
           'failed': [r['n'] for r in failed],
           'unchecked': [r['n'] for r in unchecked],
           'assumptions': [r['n'] for r in rows if r['status'] == 'assumption'],
           'aggregate_not_machine_verified': aggregate,
           'tier': 'tier 2 unless the course itself shows this derivation'}
    if failed:
        out['action'] = ('a failed step is fixed and re-checked, never shown. After '
                         'two attempts, explain the method without the algebra and '
                         'say why.')
    if aggregate:
        out['say'] = ('more than half the steps went unchecked: state that the '
                      'derivation as a whole is not machine-verified')
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('number'); p.add_argument('--expr', required=True)
    p.add_argument('--claimed')
    p = sub.add_parser('formula'); p.add_argument('--expr', required=True)
    p.add_argument('--equals', required=True)
    p = sub.add_parser('derivation')
    p.add_argument('--steps', help='path to a JSON file: [{"expr": ..., "label": ...}]')
    p.add_argument('--json', dest='inline', help='the same JSON, inline')
    args = ap.parse_args(argv)
    if args.cmd == 'number':
        out = number(args.expr, args.claimed)
    elif args.cmd == 'formula':
        out = formula(args.expr, args.equals)
    else:
        raw = args.inline or (Path(args.steps).read_text(encoding='utf-8')
                              if args.steps else '[]')
        data = json.loads(raw)
        out = derivation(data.get('steps') if isinstance(data, dict) else data)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0 if out.get('ok', True) is not False else 1


if __name__ == '__main__':
    raise SystemExit(main())
