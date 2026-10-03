#!/usr/bin/env python3
"""Assigned videos and assigned links: three tiers of acquisition, never a block.

An assigned video is course *material*, not a recording of the lecture, so it
sits in the priority ladder beside articles rather than in a metadata field. The
same is true of an assigned link. What makes both awkward is that they live on
the network, and the network is the one input this plugin cannot guarantee.

So acquisition degrades in three stated tiers, and the **third tier always
succeeds**:

  1. content — captions via `yt-dlp --write-auto-sub --skip-download`, or the
     page text for a link
  2. metadata only — title, channel, duration; the note says
     `content not processed`
  3. link only — listed, flagged, run continues

A failure at tier 1 or 2 is never an error, because a missing caption track must
not stop a lesson whose slides and transcript are sitting right there. What
*would* be an error is silence: every degraded item is flagged in the note and
in the run report, so "this video contributed nothing" is visible rather than
inferred from a thin section.

Two refusals are deliberate. **No credentials, ever**, and no paywall is
followed. And a link that resolves to a PDF over roughly 40 pages is not
fetched inline — it is reported as something to file as an article or a book
through course-setup, because a 200-page PDF pulled in silently would dominate
the lesson's extraction and nothing in the coverage arithmetic would show it.

Keyframe extraction is deliberately absent: it needs the whole video file, and
course videos are almost never silent visual demonstrations. Captions carry the
content.

CLI:
    fetch_video_captions.py parse --file Content/videos.md
    fetch_video_captions.py captions --url <u> --index 1 --out-dir <.work>
    fetch_video_captions.py vtt --path <f.vtt> --index 1
    fetch_video_captions.py link --url <u> --index 1
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))

URL_RE = re.compile(r'https?://[^\s<>()\[\]]+')
TS_RE = re.compile(r'^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->')
SEGMENT_WORDS = 90
PDF_PAGE_LIMIT = 40
TIMEOUT = 45


def parse_list(path: Path | str) -> dict:
    """One link per line, optional label and free text after a dash.

    The free text is the student's own commentary and becomes an `N` item
    attached to that video or link — it is their note, not the source's.
    """
    path = Path(path)
    entries = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        m = URL_RE.search(line)
        if not m:
            continue
        url = m.group(0).rstrip('.,;')
        rest = line[m.end():].strip(' -–—\t')
        before = line[:m.start()].strip(' -*\t')
        entries.append({'index': len(entries) + 1, 'url': url,
                        'label': before or None,
                        'comment': rest or None})
    return {'file': str(path), 'entries': entries, 'count': len(entries)}


def _segments(text: str, prefix: str, size: int = SEGMENT_WORDS) -> list[dict]:
    words = re.sub(r'\s+', ' ', text).strip().split()
    out = []
    for i in range(0, len(words), size):
        out.append({'id': f'{prefix}.{len(out) + 1}', 'tags': [],
                    'text': ' '.join(words[i:i + size])})
    return out


def parse_vtt(path: Path | str, index: int, prefix: str = 'V') -> dict:
    """A caption file to segments. Cue timings and cue numbers are dropped; the
    IDs this skill uses are its own, and a cue is far too small to be one."""
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    lines, seen = [], set()
    for line in raw.splitlines():
        s = line.strip()
        if not s or s in ('WEBVTT',) or TS_RE.match(s) or s.isdigit():
            continue
        if s.startswith(('NOTE', 'Kind:', 'Language:', 'STYLE')):
            continue
        s = re.sub(r'<[^>]+>', '', s)
        # auto-captions repeat each line as the rolling window advances
        if s in seen:
            continue
        seen.add(s)
        lines.append(s)
    text = ' '.join(lines)
    return {'path': str(path), 'words': len(text.split()),
            'items': _segments(text, f'{prefix}{index}'), 'text': text}


def captions(url: str, index: int, out_dir: Path | str | None = None,
             lang: str = 'en') -> dict:
    """Tier 1, then tier 2, then tier 3. Each fall-through is reported."""
    if not shutil.which('yt-dlp'):
        return {'url': url, 'tier': 'link-only', 'captions': 'none',
                'reason': 'yt-dlp is not installed. Offer the install; this '
                          'never blocks the run.',
                'install': 'pip install yt-dlp', 'items': []}
    out_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp())
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = _metadata(url)
    stem = out_dir / f'video_{index}'
    cmd = ['yt-dlp', '--skip-download', '--write-auto-sub', '--write-sub',
           '--sub-lang', lang, '--sub-format', 'vtt', '-o', str(stem), url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
        err = proc.stderr
    except (subprocess.TimeoutExpired, OSError) as e:
        err = str(e)
    found = sorted(out_dir.glob(f'video_{index}*.vtt'))
    if found:
        data = parse_vtt(found[0], index)
        kind = 'manual' if '.orig' in found[0].name else 'auto'
        return {'url': url, 'tier': 'captions', 'captions': kind,
                'file': str(found[0]), 'metadata': meta,
                'words': data['words'], 'items': data['items']}
    if meta.get('title'):
        return {'url': url, 'tier': 'metadata', 'captions': 'none',
                'metadata': meta, 'items': [],
                'reason': 'no caption track; the note is written with metadata '
                          'only and marked "content not processed"',
                'stderr': (err or '')[-300:]}
    return {'url': url, 'tier': 'link-only', 'captions': 'none', 'items': [],
            'reason': 'not fetchable (no network, another platform, or a login '
                      'wall). The link is listed and flagged; credentials are '
                      'never attempted.',
            'stderr': (err or '')[-300:]}


def _metadata(url: str) -> dict:
    if not shutil.which('yt-dlp'):
        return {}
    try:
        proc = subprocess.run(['yt-dlp', '-J', '--skip-download', url],
                              capture_output=True, text=True, timeout=TIMEOUT)
        data = json.loads(proc.stdout or '{}')
    except Exception:
        return {}
    dur = data.get('duration')
    return {'title': data.get('title'), 'channel': data.get('uploader'),
            'duration': f'{dur // 60}:{dur % 60:02d}' if isinstance(dur, int) else None,
            'description': (data.get('description') or '')[:1200]}


def fetch_link(url: str, index: int) -> dict:
    """Tier 1 for an assigned link: page text with navigation stripped."""
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={'User-Agent': 'course-notes/1'})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ctype = (resp.headers.get('Content-Type') or '').lower()
            body = resp.read(8_000_000)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {'url': url, 'tier': 'link-only', 'items': [],
                'reason': f'not fetchable ({e}). Listed and flagged; the run '
                          'continues and credentials are never attempted.'}
    if 'pdf' in ctype or url.lower().endswith('.pdf'):
        pages = _pdf_pages(body)
        if pages is None or pages > PDF_PAGE_LIMIT:
            return {'url': url, 'tier': 'refused', 'items': [], 'pages': pages,
                    'reason': f'resolves to a PDF of {pages} pages. Download it '
                              'and file it as an article or a book through '
                              'course-setup; fetching it inline would let one '
                              'link dominate the lesson.'}
    try:
        from bs4 import BeautifulSoup                    # noqa: E402
        soup = BeautifulSoup(body.decode('utf-8', 'replace'), 'html.parser')
    except Exception as e:
        return {'url': url, 'tier': 'metadata', 'items': [],
                'reason': f'not parseable as an article ({e}); title and URL '
                          'only, marked "content not processed"'}
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside',
                     'form', 'noscript']):
        tag.decompose()
    title = (soup.title.get_text(strip=True) if soup.title else '') or url
    text = re.sub(r'\n{2,}', '\n', soup.get_text('\n', strip=True))
    if len(text.split()) < 80:
        return {'url': url, 'tier': 'metadata', 'title': title, 'items': [],
                'reason': 'a landing page or a dynamic app rather than an '
                          'article; title and URL only, marked "content not '
                          'processed"'}
    return {'url': url, 'tier': 'content', 'title': title,
            'words': len(text.split()),
            'items': _segments(text, f'K{index}')}


def _pdf_pages(body: bytes) -> int | None:
    try:
        import io

        from pypdf import PdfReader                      # noqa: E402
        return len(PdfReader(io.BytesIO(body)).pages)
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('parse'); p.add_argument('--file', required=True)
    p = sub.add_parser('captions')
    p.add_argument('--url', required=True); p.add_argument('--index', type=int, default=1)
    p.add_argument('--out-dir'); p.add_argument('--lang', default='en')
    p = sub.add_parser('vtt')
    p.add_argument('--path', required=True); p.add_argument('--index', type=int, default=1)
    p.add_argument('--prefix', default='V')
    p = sub.add_parser('link')
    p.add_argument('--url', required=True); p.add_argument('--index', type=int, default=1)
    args = ap.parse_args(argv)

    if args.cmd == 'parse':
        out = parse_list(args.file)
    elif args.cmd == 'captions':
        out = captions(args.url, args.index, args.out_dir, args.lang)
    elif args.cmd == 'vtt':
        out = parse_vtt(args.path, args.index, args.prefix)
        out.pop('text', None)
    else:
        out = fetch_link(args.url, args.index)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
