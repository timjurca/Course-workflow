#!/usr/bin/env python3
"""Recompute every number before it is written down, and drop what does not check.

A wrong worked solution is the single most damaging thing this skill can
produce. Everything else it writes is either checked by the student against the
notes or simply not used; a worked calculation is *studied*, step by step, and a
student who learns a wrong method learns it well.

So no number reaches a revision file or a mock solution on the model's word. It
is recomputed by a script that is written to `Exams/.work/calc/<run>/q<id>.py`
and actually run, and symbolic steps are checked with `sympy` wherever the step
can be written as an equation. The script is kept, so a disputed answer can be
re-run months later.

Two rules matter more than the mechanics:

  **A mismatch drops the question.** It is never "repaired" by the model, which
  in practice means rewriting the answer until it agrees with the script, and
  that is a coin flip about which of the two was wrong.

  **What cannot be checked says so.** A proof or a verbal argument inside a
  derivation is written with `[not machine-verified]` and counted in the report
  and the file frontmatter. An unmarked unverifiable step is indistinguishable
  from a verified one.

When the mismatch traces back to a formula as the *notes* state it, that is not
a bad question, it is a bad note: it becomes a `suspect` finding for skill D.

Script contract: each `q<id>.py` prints one JSON object on stdout with `id`,
`value` (a number, a list of numbers, or a string sympy expression) and an
optional `steps` list. Data for new-number variants is generated inside the same
script, so the numbers and the solution can never come from different places.

CLI:
    verify_calc.py run      --dir <calc dir> [--claims <json>] [--timeout 20]
    verify_calc.py symbolic --lhs "..." --rhs "..." [--symbols x,y]
    verify_calc.py numeric  --expected 3.14 --actual 3.1400001 [--tol 1e-6]
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

REL_TOL = 1e-6
ABS_TOL = 1e-9
DEFAULT_TIMEOUT = 20


def numeric_equal(expected, actual, tol: float = REL_TOL) -> dict:
    try:
        a, b = float(expected), float(actual)
    except (TypeError, ValueError):
        return {'equal': False, 'why': 'not both numbers'}
    ok = math.isclose(a, b, rel_tol=tol, abs_tol=ABS_TOL)
    return {'equal': ok, 'expected': a, 'actual': b,
            'abs_diff': abs(a - b),
            'why': None if ok else f'differs by {abs(a - b):g}'}


def symbolic_equal(lhs: str, rhs: str, symbols: list[str] | None = None) -> dict:
    """simplify(lhs - rhs) == 0, which is the only check worth making.

    String comparison of two expressions calls `2*x` and `x + x` different, and
    a student rearranging a formula correctly would be marked wrong.
    """
    try:
        import sympy
    except ImportError:
        return {'equal': None, 'why': 'sympy is not installed in this runtime; '
                                      'the step must be marked [not machine-verified]'}
    try:
        local = {s: sympy.Symbol(s) for s in (symbols or [])}
        a = sympy.sympify(lhs, locals=local)
        b = sympy.sympify(rhs, locals=local)
        diff = sympy.simplify(a - b)
        ok = bool(diff == 0)
        return {'equal': ok, 'difference': str(diff),
                'why': None if ok else 'the two expressions are not equivalent'}
    except Exception as e:
        return {'equal': None, 'why': f'could not be expressed symbolically: {e}. '
                                      'Mark the step [not machine-verified].'}


def _compare(claim, value, tol: float) -> dict:
    if claim is None:
        return {'verdict': 'not_machine_verified',
                'why': 'no claimed value was supplied for this question; write it '
                       'with [not machine-verified]'}
    if isinstance(claim, str) or isinstance(value, str):
        r = symbolic_equal(str(claim), str(value))
        if r['equal'] is True:
            return {'verdict': 'verified', 'by': 'sympy'}
        if r['equal'] is None:
            return {'verdict': 'not_machine_verified', 'why': r['why']}
        return {'verdict': 'mismatch', 'by': 'sympy', 'why': r['why'],
                'difference': r.get('difference')}
    if isinstance(claim, (list, tuple)) and isinstance(value, (list, tuple)):
        if len(claim) != len(value):
            return {'verdict': 'mismatch',
                    'why': f'{len(claim)} claimed values, {len(value)} computed'}
        bad = [(i, c, v) for i, (c, v) in enumerate(zip(claim, value))
               if not numeric_equal(c, v, tol)['equal']]
        return {'verdict': 'verified', 'by': 'numeric'} if not bad else \
            {'verdict': 'mismatch', 'by': 'numeric', 'positions': bad}
    r = numeric_equal(claim, value, tol)
    if r['equal']:
        return {'verdict': 'verified', 'by': 'numeric'}
    return {'verdict': 'mismatch', 'by': 'numeric', 'why': r['why'],
            'expected': r.get('expected'), 'actual': r.get('actual')}


def run(directory: Path | str, claims: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT, tol: float = REL_TOL) -> dict:
    directory = Path(directory)
    claims = claims or {}
    if not claims and (directory / 'claims.json').is_file():
        claims = json.loads((directory / 'claims.json').read_text(encoding='utf-8'))
    rows = []
    for script in sorted(directory.glob('q*.py')):
        qid = script.stem
        try:
            proc = subprocess.run([sys.executable, script.name],
                                  cwd=str(directory), capture_output=True,
                                  text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            rows.append({'id': qid, 'verdict': 'error', 'script': script.name,
                         'why': f'the script did not finish within {timeout}s'})
            continue
        if proc.returncode != 0:
            rows.append({'id': qid, 'verdict': 'error', 'script': script.name,
                         'why': (proc.stderr or '').strip()[-800:] or
                                f'exit status {proc.returncode}'})
            continue
        payload = _last_json(proc.stdout)
        if payload is None:
            rows.append({'id': qid, 'verdict': 'error', 'script': script.name,
                         'why': 'the script printed no JSON object. It must print '
                                '{"id": ..., "value": ...} on stdout.'})
            continue
        key = payload.get('id') or qid
        result = _compare(claims.get(key, claims.get(qid)), payload.get('value'), tol)
        rows.append({'id': key, 'script': script.name,
                     'computed': payload.get('value'),
                     'claimed': claims.get(key, claims.get(qid)),
                     'steps': payload.get('steps'), **result})
    by = {}
    for r in rows:
        by.setdefault(r['verdict'], []).append(r['id'])
    drops = by.get('mismatch', []) + by.get('error', [])
    return {'dir': str(directory), 'checked': len(rows), 'results': rows,
            'by_verdict': by,
            'drop': drops,
            'mark_not_machine_verified': by.get('not_machine_verified', []),
            'action': 'nothing to drop' if not drops else
                      'drop these questions and count them in the report. Never '
                      'rewrite the answer to agree with the script. If the formula '
                      'as the notes state it is the cause, log a suspect finding.'}


def _last_json(text: str):
    payload = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('{') and line.endswith('}'):
            try:
                payload = json.loads(line)
            except ValueError:
                continue
    return payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--dir', required=True)
    r.add_argument('--claims')
    r.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT)
    r.add_argument('--tol', type=float, default=REL_TOL)
    s = sub.add_parser('symbolic')
    s.add_argument('--lhs', required=True)
    s.add_argument('--rhs', required=True)
    s.add_argument('--symbols')
    n = sub.add_parser('numeric')
    n.add_argument('--expected', required=True)
    n.add_argument('--actual', required=True)
    n.add_argument('--tol', type=float, default=REL_TOL)
    args = ap.parse_args(argv)
    if args.cmd == 'run':
        claims = None
        if args.claims:
            try:
                p = Path(args.claims)
                raw = p.read_text(encoding='utf-8') if p.is_file() else args.claims
            except OSError:
                raw = args.claims
            claims = json.loads(raw)
        out = run(args.dir, claims, args.timeout, args.tol)
    elif args.cmd == 'symbolic':
        out = symbolic_equal(args.lhs, args.rhs,
                             args.symbols.split(',') if args.symbols else None)
    else:
        out = numeric_equal(args.expected, args.actual, args.tol)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
