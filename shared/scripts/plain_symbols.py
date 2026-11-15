#!/usr/bin/env python3
"""Find mathematical symbols written as plain text in running prose.

Display formulas were always written as `$$...$$`, but symbols in sentences,
tables, callouts and definitions kept coming out as `e_P`, `MU_X`, `q_11` or
`X^(−1/2)`. Obsidian shows those literally, and two underscores on one line can
be read as italic markers that garble the sentence between them. One lesson
carried 71 of them, each fixed afterwards by a logged correction. The rule is
note-invariants §2d; this module is the check, shared by course-notes Pass D
(`Plain symbols` in `D_verification.md`) and course-condense `verify.py`, so the
two can never disagree about what counts.

What is flagged, in the body only:

    <1-3 letters>_<1-4 alphanumerics>      e_P  e_XZ  MU_X  q_11  Div_1  Y_OLD
    <letter>^(...)                         X^(−1/2)  P_0^(2)

What is never flagged, because it is not prose:

  * anything inside `$...$`, `$$...$$`, a code span or a fenced block
  * wikilinks and embeds, markdown links, HTML tags and comments, URLs
  * source, correction, tier and judgement markers (`[S3.1]`, `[B1.4.2]`)
  * file-name-like tokens: a word with an `L<NN>`/`T<NN>` part
    (`EF_L02_Final_notes`, `FM_T06`), an attachment or file name, a path
  * the student's protected blocks (`## My additions`, `## My notes`, the
    `ranking:yours` pair): nobody but the student writes there

A currency amount is not maths: `$530 billion` does not open a span when the
text up to the next `$` contains whitespace, so a sentence after it is still
scanned. `\\$530` is always literal.

It reports and never blocks, like every other writing gate.

CLI:
    plain_symbols.py scan --file <note.md>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

FM_RE = re.compile(r'\A---\r?\n.*?\r?\n---\r?\n?', re.DOTALL)

SUP_RE = re.compile(
    r'(?<![A-Za-z0-9_\\])'
    r'(?P<tok>(?P<base>[A-Za-z]{1,3}(?:_[A-Za-z0-9]{1,4})?)\^\((?P<exp>[^()\n]{1,24})\))')
SUB_RE = re.compile(
    r'(?<![A-Za-z0-9_\\])'
    r'(?P<tok>(?P<base>[A-Za-z]{1,3})_(?P<sub>[A-Za-z0-9]{1,4}))'
    r'(?![A-Za-z0-9_])')

FENCE_RE = re.compile(r'^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$', re.MULTILINE | re.DOTALL)
DISPLAY_RE = re.compile(r'\$\$.*?\$\$', re.DOTALL)
COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
CODE_RE = re.compile(r'`[^`\n]*`')
WIKILINK_RE = re.compile(r'!?\[\[[^\]\n]*\]\]')
MDLINK_RE = re.compile(r'!?\[[^\]\n]*\]\([^)\n]*\)')
URL_RE = re.compile(r'(?:\b(?:https?|ftp)://|\bwww\.)[^\s)>\]]+')
HTML_RE = re.compile(r'</?[A-Za-z][^>\n]*>')
MARKER_RE = re.compile(
    r'\[(?:[SBTAHNCVKG]\d[^\[\]\n]*'
    r'|(?:source error|student, sources differ|unverified|differs from course):[^\[\]\n]*'
    r'|W\d+|beyond course|your note|judgement)\]')
RANKING_RE = re.compile(r'<!--\s*ranking:yours:start\s*-->.*?<!--\s*ranking:yours:end\s*-->',
                        re.DOTALL)
PROTECTED_H2 = ('my additions', 'my notes')

WORD_CHARS = re.compile(r'[A-Za-z0-9_.\-/]')
LESSON_PART_RE = re.compile(r'(?<![A-Za-z0-9])[LT]\d{2}(?![0-9])')
FILE_EXT_RE = re.compile(
    r'\.(?:png|jpe?g|gif|svg|webp|bmp|tiff?|pdf|md|txt|pptx?|docx?|xlsx?|csv|'
    r'epub|vtt|srt|json|ya?ml|py|html?)$', re.IGNORECASE)
MINUS = {'−': '-', '–': '-', '‒': '-', '‐': '-', '‑': '-'}


def _blank(text: str, start: int, end: int) -> str:
    """Overwrite a span with spaces, newlines kept, so line numbers survive."""
    chunk = ''.join('\n' if c == '\n' else ' ' for c in text[start:end])
    return text[:start] + chunk + text[end:]


def _blank_all(text: str, pattern: re.Pattern) -> str:
    for m in reversed(list(pattern.finditer(text))):
        text = _blank(text, m.start(), m.end())
    return text


def _blank_protected(text: str) -> str:
    """The student's own blocks: an H2 up to the next H2, and the ranking pair."""
    text = _blank_all(text, RANKING_RE)
    lines = text.split('\n')
    out, skipping = [], False
    for line in lines:
        if line.startswith('## '):
            skipping = line[3:].strip().lower() in PROTECTED_H2
        out.append(' ' * len(line) if skipping else line)
    return '\n'.join(out)


def _inline_math_spans(line: str) -> list[tuple[int, int]]:
    """`$...$` spans as Obsidian draws them, with currency left alone.

    An opener is a `$` not escaped and not followed by whitespace; a closer is
    a `$` not escaped, not preceded by whitespace and not followed by a digit.
    A span whose opener is followed by a digit and whose content holds
    whitespace is a currency amount (`$530 billion ... $x$`), not maths.
    """
    spans, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == '$' and (i == 0 or line[i - 1] != '\\') \
                and line[i + 1:i + 2] not in ('', ' ', '\t', '$'):
            close = None
            for j in range(i + 1, n):
                if line[j] == '$' and line[j - 1] not in (' ', '\t', '\\') \
                        and not line[j + 1:j + 2].isdigit():
                    close = j
                    break
            if close is not None:
                content = line[i + 1:close]
                if line[i + 1].isdigit() and re.search(r'\s', content):
                    i += 1
                    continue
                spans.append((i, close + 1))
                i = close + 1
                continue
        i += 1
    return spans


def scrub(body: str) -> str:
    """The body with everything that is not prose blanked out."""
    text = _blank_protected(body)
    for pat in (FENCE_RE, DISPLAY_RE, COMMENT_RE, CODE_RE, WIKILINK_RE,
                MDLINK_RE, URL_RE, HTML_RE, MARKER_RE):
        text = _blank_all(text, pat)
    lines = text.split('\n')
    for k, line in enumerate(lines):
        for a, b in reversed(_inline_math_spans(line)):
            line = line[:a] + ' ' * (b - a) + line[b:]
        lines[k] = line
    return '\n'.join(lines)


def _file_like(text: str, start: int, end: int) -> bool:
    """Is the token part of a file name, an attachment name or a path?

    The surrounding word is what decides: `FM_T06` and `EF_L02_Final_notes`
    carry a lesson part, `x_fig.png` an extension, `a/b_c` a path. A slash
    inside the token itself is maths (`X^(-1/2)`), so only the characters
    around the token count for that test.
    """
    a, b = start, end
    while a > 0 and WORD_CHARS.match(text[a - 1]):
        a -= 1
    while b < len(text) and WORD_CHARS.match(text[b]):
        b += 1
    word = text[a:b].rstrip('.')
    around = text[a:start] + text[end:b]
    return bool(LESSON_PART_RE.search(word) or FILE_EXT_RE.search(word)
                or '/' in around)


def _tex_base(base: str) -> str:
    if '_' in base:
        head, sub = base.split('_', 1)
        return f'{head}_{{{sub}}}' if len(sub) > 1 else f'{head}_{sub}'
    return base


def suggestion(token: str) -> str:
    """The inline-math form to write instead, ASCII minus inside the maths."""
    m = SUP_RE.fullmatch(token)
    if m:
        exp = ''.join(MINUS.get(c, c) for c in m.group('exp')).strip()
        return f"${_tex_base(m.group('base'))}^{{{exp}}}$"
    return f'${_tex_base(token)}$'


def scan(body: str) -> list[dict]:
    """Plain-text symbols in a note body (frontmatter already removed)."""
    text = scrub(body)
    src_lines = body.split('\n')
    hits = []
    for pat in (SUP_RE, SUB_RE):
        for m in pat.finditer(text):
            tok = m.group('tok')
            if _file_like(text, m.start('tok'), m.end('tok')):
                continue
            hits.append((m.start('tok'), m.end('tok'), tok))
        # A superscript token contains a subscript one (`P_0^(2)`): blank it
        # before the subscript pass so it is reported once.
        for a, b, _ in hits:
            text = _blank(text, a, b)
    out = []
    for a, _b, tok in sorted(hits):
        line = text.count('\n', 0, a) + 1
        out.append({'token': tok, 'line': line, 'fix': suggestion(tok),
                    'text': src_lines[line - 1].strip()[:120]})
    return out


def scan_file(path: Path | str) -> list[dict]:
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    m = FM_RE.match(raw)
    return scan(raw[m.end():] if m else raw)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('scan')
    p.add_argument('--file', required=True)
    args = ap.parse_args(argv)
    rows = scan_file(args.file)
    json.dump({'file': args.file, 'count': len(rows), 'plain_symbols': rows},
              sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
