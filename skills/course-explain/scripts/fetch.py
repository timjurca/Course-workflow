#!/usr/bin/env python3
"""Reach outside the course material, under rails, and bring back a snapshot.

E is the only skill in this plugin with network access. Every other skill is
local by construction, and the asymmetry is deliberate: the material is often
thin, and a tutor that cannot reach past a bad slide is a tutor with a bad
slide. The cost of that privilege is that every fetch is announced, bounded and
recorded, because an unannounced fetch turns a tutor into an unsourced one.

Three rails are enforced here rather than left to judgement:

**The snapshot.** A link with no snapshot rots: the page moves, the student
opens the explanation in June and finds a 404 where the evidence was. So every
fetched claim is stored with its URL, its retrieval date and a verbatim quote of
at most 50 words. The snapshot survives the page.

**The budget.** Three fetched sources in one answer, two more across the
follow-ups on one concept in a session. Not because reading is bad, but because
an unbounded fetch loop quietly replaces the course material with the internet,
which is the failure the authority ladder exists to prevent. The counter lives
in a scratch file **outside the vault**: it is session state, not a record of
the student's work, and `explain_state.json` holds neither.

**Assessment material is discarded, not cited.** If a fetched page turns out to
be this course's solutions, a marking scheme or a solved past paper, it is
dropped and the fact is stated. This module can only flag the obvious cases; the
rule itself is absolute and belongs to the model.

Authority classification is a heuristic and says so. It ranks a domain, and a
rung-4 general-web page is usable for orientation, cited alone only when nothing
higher exists, and always with that fact stated.

CLI:
    fetch.py get    --url <u> [--match "<text>"] [--budget-file <scratch.json>]
                    [--concept <id>] [--assignment-context]
    fetch.py budget --budget-file <scratch.json> [--concept <id>] [--reset]
    fetch.py block  --refs <refs.json>        (render the reference block)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:                                                  # pragma: no cover
    BeautifulSoup = None

SNAPSHOT_WORDS = 50
PER_ANSWER = 3
PER_SESSION_FOLLOWUP = 2
TIMEOUT = 20
UA = 'course-explain/1 (Obsidian study plugin; single-page fetch)'

# Authority ladder, rungs 2 to 4. Rung 1 is the course's own material and is
# never fetched. These are hints for the model's judgement, not a verdict.
RUNG2_HINTS = ('arxiv.org', 'doi.org', 'jstor.org', 'nber.org', 'springer',
               'sciencedirect', 'ieee.org', 'acm.org', 'nature.com',
               'science.org', 'oup.com', 'cambridge.org', 'wiley.com',
               'jmlr.org', 'iso.org', 'ietf.org', 'w3.org', 'nist.gov',
               'docs.python.org', 'cran.r-project.org', 'statsmodels.org')
RUNG3_HINTS = ('.edu', '.ac.uk', '.ac.', 'uni-', 'univ', 'mit.edu', 'stanford.edu')

ASSESSMENT_RE = re.compile(
    r'\b(marking scheme|mark scheme|model answer|model solution|solutions? manual|'
    r'answer key|worked solutions?|exam solutions?|past paper solutions?|'
    r'assignment solutions?|graded answer)\b', re.I)


def classify(url: str) -> dict:
    host = (urlparse(url).netloc or '').lower()
    if any(h in host for h in RUNG2_HINTS):
        rung, label = 2, 'standard reference'
    elif any(h in host for h in RUNG3_HINTS):
        rung, label = 3, 'institutional teaching material'
    else:
        rung, label = 4, 'general web'
    return {'host': host, 'authority_rung': rung, 'authority': label,
            'heuristic': True,
            'note': ('rung 4 is used for orientation and cited on its own only '
                     'when nothing higher exists, with that fact stated')}


# ------------------------------------------------------------------- budget

def _budget_load(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'answer': 0, 'followups': {}, 'fetches': []}


def budget(budget_file: str | None, concept: str | None = None,
           reset: bool = False, new_answer: bool = False) -> dict:
    """What is left. A missing budget file means the budget is unenforceable."""
    if not budget_file:
        return {'enforced': False,
                'note': ('no budget file given, so the counters are not enforced; '
                         'keep to 3 per answer and 2 more per concept by hand')}
    path = Path(budget_file)
    if path.parts and 'mnt' in path.parts:
        return {'enforced': False,
                'error': ('the budget file must live outside the vault: it is '
                          'session state, not part of the student\'s notes')}
    data = {'answer': 0, 'followups': {}, 'fetches': []} if reset else _budget_load(path)
    if new_answer:
        data['answer'] = 0
    used_answer = data.get('answer', 0)
    used_followup = (data.get('followups') or {}).get(concept or '', 0)
    return {'enforced': True, 'file': str(path), 'concept': concept,
            'used_this_answer': used_answer, 'per_answer': PER_ANSWER,
            'used_followups': used_followup, 'per_session_followup': PER_SESSION_FOLLOWUP,
            'answer_remaining': max(PER_ANSWER - used_answer, 0),
            'followup_remaining': max(PER_SESSION_FOLLOWUP - used_followup, 0),
            'exhausted': used_answer >= PER_ANSWER
                         and used_followup >= PER_SESSION_FOLLOWUP,
            '_data': data, '_path': path}


def _budget_spend(state: dict, url: str, concept: str | None) -> None:
    data, path = state['_data'], state['_path']
    if data.get('answer', 0) < PER_ANSWER:
        data['answer'] = data.get('answer', 0) + 1
    else:
        fu = data.setdefault('followups', {})
        fu[concept or ''] = fu.get(concept or '', 0) + 1
    data.setdefault('fetches', []).append({'url': url, 'date': date.today().isoformat(),
                                           'concept': concept})
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


# -------------------------------------------------------------------- fetch

def _text_of(html: str) -> tuple:
    if BeautifulSoup is None:
        text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html,
                      flags=re.S | re.I)
        text = re.sub(r'<[^>]+>', ' ', text)
        title = re.search(r'<title[^>]*>(.*?)</title>', html, re.S | re.I)
        return (title.group(1).strip() if title else None,
                re.sub(r'\s+', ' ', text).strip())
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'noscript']):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else None
    return title, re.sub(r'\s+', ' ', soup.get_text(' ')).strip()


def snapshot(text: str, match: str | None = None, words: int = SNAPSHOT_WORDS) -> str:
    """At most 50 words, verbatim, around the passage actually used."""
    if not text:
        return ''
    start = 0
    if match:
        keys = [w for w in re.split(r'\W+', match.lower()) if len(w) > 3]
        low = text.lower()
        best, best_hits = 0, 0
        for m in re.finditer(r'\S+', low):
            window = low[m.start():m.start() + 600]
            hits = sum(1 for k in keys if k in window)
            if hits > best_hits:
                best, best_hits = m.start(), hits
        start = best
    return ' '.join(text[start:start + 1200].split()[:words])


def get(url: str, match: str | None = None, budget_file: str | None = None,
        concept: str | None = None, assignment_context: bool = False) -> dict:
    """One page, one snapshot, one budget slot."""
    if assignment_context:
        return {'url': url, 'fetched': False, 'refused': 'assignment context',
                'reason': ('while the current question is under the assignment '
                           'boundary E does not fetch at all')}
    state = budget(budget_file, concept)
    if state.get('enforced') and state.get('exhausted'):
        return {'url': url, 'fetched': False, 'refused': 'budget exhausted',
                'budget': {k: v for k, v in state.items() if not k.startswith('_')},
                'reason': 'say the budget is spent and explain from what was read'}
    if state.get('error'):
        return {'url': url, 'fetched': False, 'refused': 'bad budget file',
                'reason': state['error']}

    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read(2_000_000)
            final_url = resp.geturl()
            ctype = resp.headers.get('Content-Type', '')
    except Exception as exc:
        return {'url': url, 'fetched': False,
                'error': f'{type(exc).__name__}: {exc}',
                'reason': ('say the fetch failed, explain from tiers 1 and 2, and '
                           'never invent a citation')}

    html = raw.decode('utf-8', errors='replace')
    title, text = _text_of(html)
    out = {'url': final_url, 'requested_url': url, 'fetched': True,
           'retrieved': date.today().isoformat(), 'title': title,
           'content_type': ctype, 'chars': len(text)}
    out.update(classify(final_url))

    hit = ASSESSMENT_RE.search(text[:20000])
    if hit:
        out.update({'assessment_material': True, 'matched': hit.group(0),
                    'cite': False,
                    'action': ('this looks like assessment material. If it is this '
                               'course\'s, discard it, say so, and do not cite it.')})
    else:
        out['assessment_material'] = False
        out['cite'] = True
    out['snapshot'] = snapshot(text, match)
    out['snapshot_words'] = len(out['snapshot'].split())
    if state.get('enforced'):
        _budget_spend(state, final_url, concept)
        after = budget(budget_file, concept)
        out['budget'] = {k: v for k, v in after.items() if not k.startswith('_')}
    else:
        out['budget'] = {'enforced': False}
    out['announce'] = ('say that you went outside the course material, before the '
                       'fetched content, every time')
    return out


def block(refs: list) -> dict:
    """Render `## External references` exactly as note-invariants pins it.

    One helper rather than a shape the model retypes each time: the block is
    matched as a literal structure by the staleness check and by a reader
    looking for the snapshot, and four hand-written variants of it would agree
    on nothing.
    """
    lines = ['## External references', '']
    for i, r in enumerate(refs, start=1):
        wid = r.get('id') or 'W{}'.format(i)
        cite = r.get('citation') or r.get('title') or r.get('url')
        lines.append('**[{}]** {}'.format(wid, cite))
        lines.append('{} · retrieved {} · authority: {}'.format(
            r.get('url'), r.get('retrieved'), r.get('authority', 'general web')))
        words = (r.get('snapshot') or '').split()[:SNAPSHOT_WORDS]
        wrapped, current = [], ''
        for w in words:
            if len(current) + len(w) + 1 > 70:
                wrapped.append(current)
                current = w
            else:
                current = (current + ' ' + w).strip()
        if current:
            wrapped.append(current)
        for n, chunk in enumerate(wrapped):
            prefix = '> "' if n == 0 else '> '
            suffix = '"' if n == len(wrapped) - 1 else ''
            lines.append(prefix + chunk + suffix)
        lines.append('')
    return {'markdown': '\n'.join(lines).rstrip() + '\n', 'count': len(refs),
            'snapshot_cap': SNAPSHOT_WORDS}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('get'); p.add_argument('--url', required=True)
    p.add_argument('--match'); p.add_argument('--budget-file', dest='budget_file')
    p.add_argument('--concept'); p.add_argument('--assignment-context', action='store_true')
    p = sub.add_parser('budget'); p.add_argument('--budget-file', dest='budget_file')
    p.add_argument('--concept'); p.add_argument('--reset', action='store_true')
    p.add_argument('--new-answer', dest='new_answer', action='store_true')
    p = sub.add_parser('block'); p.add_argument('--refs', required=True)
    args = ap.parse_args(argv)
    if args.cmd == 'get':
        out = get(args.url, args.match, args.budget_file, args.concept,
                  args.assignment_context)
    elif args.cmd == 'budget':
        state = budget(args.budget_file, args.concept, args.reset, args.new_answer)
        if state.get('enforced') and (args.reset or args.new_answer):
            _budget_spend_path = state['_path']
            _budget_spend_path.parent.mkdir(parents=True, exist_ok=True)
            _budget_spend_path.write_text(
                json.dumps(state['_data'], ensure_ascii=False, indent=2),
                encoding='utf-8')
        out = {k: v for k, v in state.items() if not k.startswith('_')}
    else:
        data = json.loads(Path(args.refs).read_text(encoding='utf-8'))
        out = block(data.get('references') if isinstance(data, dict) else data)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
