#!/usr/bin/env python3
"""Repair ASR damage against the lecture's own vocabulary, then segment.

Automatic transcription destroys exactly the words that matter. It renders
ordinary English fluently and turns "heteroskedasticity" into "hetero
elasticity", surnames into noise, and Slovenian technical terms into whatever
was nearest. The damage is concentrated in the terms the notes are *about*.

This runs **before** segmentation, and that order is the point. A garbled term
poisons twice over: once in the concept sections, and once in the term ledger,
where it becomes a permanent entry that every later lesson is compared against.
By the time anyone notices, three lessons have "refined" a definition of a word
that does not exist.

The vocabulary is built from the slides and the book **first**, so corrections
are only ever towards words the lecturer actually used. A general-purpose
spellchecker here would be worse than nothing: it would confidently normalise
real technical terms into common English.

Every correction is logged to `.work/transcript_corrections_<entry slug>.md` with its
context, because fuzzy matching gets some wrong and an unlogged wrong correction
is indistinguishable from what the lecturer said. That file deliberately carries
**no `A_` prefix**: `A_*` is the extraction namespace four skills read, and a
correction log is not an extraction.

The four classifications this emits — recap, announcement, non-content, exam
signal — are **candidates**, not verdicts. Cue phrases find the segments worth
looking at; deciding that an aside is genuinely non-content is model work, and
§6.3 requires the discarded ones to be counted so the coverage arithmetic still
balances rather than quietly losing IDs.

CLI:
    normalize_transcript.py run --path <transcript.md> --entry Content/t.md \\
        --work <.work> --vocab-from <A_slides.md> [<A_book.md> ...] \\
        --run <ts> --hash <h> [--apply]
    normalize_transcript.py vocab --from <A_x.md> [...]
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'shared' / 'scripts'))
sys.path.insert(0, str(HERE))
import extraction                                                  # noqa: E402

SEGMENT_WORDS = 110
MIN_TERM = 7            # shorter words are common vocabulary, not jargon
CUTOFF = 0.86           # with a lexicon to veto real words
CUTOFF_NO_LEXICON = 0.92
JOIN_CUTOFF = 0.85
LOG_NAME = 'transcript_corrections.md'

# A general word list is the veto, not the source of corrections. Without it the
# matcher happily "repairs" correlation into creation and theorem into theories:
# both are close, both are wrong, and the log fills with noise nobody will read.
LEXICON_PATHS = ['/usr/share/dict/words', '/usr/share/hunspell/en_US.dic',
                 '/usr/share/dict/american-english', '/usr/share/myspell/en_US.dic']

WORD_RE = re.compile(r"[A-Za-zÀ-ž][A-Za-zÀ-ž'\-]+")

RECAP_RE = re.compile(
    r'\b(last (week|time|lecture)|previous(ly| lecture| week)|recap|'
    r'to remind you|as we saw|where we (left off|stopped)|'
    r'prej[sš]nji[cč]? (teden|uri)|ponovimo)\b', re.I)
ANNOUNCE_RE = re.compile(
    r'\b(exam .{0,20}(moved|postponed|is on|will be on)|deadline|due (date|on)|'
    r'no lecture|cancell?ed|rescheduled|hand ?in|submission .{0,15}(date|by)|'
    r'office hours|izpit .{0,20}(prestavljen|je))\b', re.I)
NONCONTENT_RE = re.compile(
    r'\b(can you hear me|is the mic|microphone|sound is|technical (issue|problem)|'
    r'\[laughter\]|sorry about|let me just|my slides are not|coffee break|'
    r'five minute break)\b', re.I)
EXAM_RE = re.compile(
    r'\b(on the exam|in the exam|will be examined|examinable|i always ask|'
    r'you will be asked|this comes up every year|do not worry about|'
    r"don't worry about|not examinable|učni izpit|to pride na izpit)\b", re.I)
SLIDE_FIX_RE = re.compile(
    r'\b(ignore|forget|disregard) the (typo|mistake|error)[^.]{0,40}'
    r'slide\s+(?P<slide>\d+)|slide\s+(?P<slide2>\d+)[^.]{0,40}\b'
    r'(is wrong|should (say|be)|has a typo)', re.I)


FRONTMATTER_RE = re.compile(r'\A---\r?\n(.*?)\r?\n---\r?\n', re.S)


def split_frontmatter(raw: str) -> tuple[dict, str]:
    """Recorder metadata is not a transcript segment.

    It used to become item T*.01, so every lesson's first "transcript segment"
    was the mic model and the diarization threshold. The metadata itself is
    worth keeping though: `recording_date` is the only mechanical evidence that
    `transcript_lesson_2.md` is lesson 1's second half, which its file name
    flatly contradicts.
    """
    m = FRONTMATTER_RE.match(raw)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ':' not in line or line.lstrip().startswith('#'):
            continue
        k, _, v = line.partition(':')
        meta[k.strip()] = v.strip()
    keep = {k: meta[k] for k in ('duration', 'recording_date', 'speakers',
                                 'language', 'model') if k in meta}
    return keep, raw[m.end():]


def variant_groups(counts: dict, lexicon: set) -> list[dict]:
    """Near-duplicate proper nouns inside one source set, with a majority form.

    Both sides must be outside the general word list, or every singular/plural
    pair in a deck is reported and the real finding drowns.
    """
    keys = sorted(counts)
    seen, out = set(), []
    for w in keys:
        for m in difflib.get_close_matches(w, keys, n=4, cutoff=0.88):
            if m == w or m.lower() == w.lower():
                continue
            pair = tuple(sorted((w, m)))
            if pair in seen:
                continue
            seen.add(pair)
            a, b = pair
            if _known(a, lexicon) or _known(b, lexicon):
                continue
            out.append({'a': a, 'a_count': counts[a], 'b': b, 'b_count': counts[b],
                        'majority': a if counts[a] >= counts[b] else b})
    return out


def build_name_vocab(paths: list[str]) -> set:
    """Capitalised tokens from the priority-1 extractions, with no length floor.

    MIN_TERM = 7 keeps short common words out of the general matcher, and must
    stay. But it also means a four-letter surname can never be repaired, so the
    lecturer's own name survived as Hort, Ord and Ward through both transcripts.
    Names get their own channel instead of lowering the global floor.
    """
    names: dict[str, int] = {}
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        if path.name.startswith('A_') and path.suffix == '.md':
            text = '\n'.join(i['text'] for i in extraction.read(path)['items'])
        else:
            continue
        for w in re.findall(r"\b[A-Z][A-Za-z'\-]{2,}\b", text):
            names[w] = names.get(w, 0) + 1
    # The sources sometimes spell one name two ways. Correcting toward whichever
    # variant happens to be the closer string match writes the *minority* form
    # into the extraction, while the notes are told to use the majority -- so
    # the extraction and the notes disagree, and two other skills read the
    # extraction. Drop the minority variants before anything can match them.
    lexicon = load_lexicon()
    for g in variant_groups(names, lexicon):
        loser = g['b'] if g['majority'] == g['a'] else g['a']
        names.pop(loser, None)
    return set(names)


def build_vocab(paths: list[str]) -> dict:
    """Terms the lecturer actually used, from the slide and book extractions.

    Capitalised words and long lowercase words both qualify: surnames and
    technical nouns are the two things ASR reliably ruins.
    """
    terms: dict[str, int] = {}
    for p in paths:
        path = Path(p)
        if not path.is_file():
            continue
        if path.name.startswith('A_') and path.suffix == '.md':
            text = '\n'.join(i['text'] for i in extraction.read(path)['items'])
        else:
            text = path.read_text(encoding='utf-8', errors='replace')
        for w in WORD_RE.findall(text):
            if len(w) < MIN_TERM:
                continue
            key = w.lower()
            terms[key] = terms.get(key, 0) + 1
    return terms


def load_lexicon(paths: list[str] | None = None) -> set[str]:
    """The first general word list on disk, as a plain set. Never fatal."""
    for candidate in (paths or LEXICON_PATHS):
        path = Path(candidate)
        if not path.is_file():
            continue
        words = set()
        try:
            with path.open(encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    w = line.split('/')[0].strip().lower()
                    if w and w.isalpha():
                        words.add(w)
        except OSError:
            continue
        if len(words) > 5000:
            return words
    return set()


def _known(word: str, lexicon: set[str]) -> bool:
    """A word, or a plural of one. Hunspell keeps plurals behind affix flags, so
    a bare membership test calls half the nouns in a lecture unknown."""
    if not lexicon:
        return False
    w = word.lower()
    if w in lexicon:
        return True
    if w.endswith('ies') and w[:-3] + 'y' in lexicon:
        return True
    if w.endswith('es') and (w[:-2] in lexicon or w[:-1] in lexicon):
        return True
    if w.endswith('s') and w[:-1] in lexicon:
        return True
    # Plurals alone are not enough. A base word list stores lemmas, so every
    # ordinary inflected form ("competing", "solving", "innovative",
    # "redesigned") came back unknown and lost the veto -- and the matcher then
    # "repaired" correct English into a different word: competing -> computing.
    if w.endswith('ied') and len(w) > 4 and w[:-3] + 'y' in lexicon:
        return True
    for suf, adds in (('ing', ('', 'e')), ('ed', ('', 'e')), ('er', ('', 'e')),
                      ('est', ('', 'e')), ('ly', ('', 'e')), ('ive', ('', 'e')),
                      ('ion', ('', 'e')), ('ions', ('', 'e')), ('ment', ('',)),
                      ('ness', ('',)), ('able', ('', 'e')), ('al', ('', 'e'))):
        if w.endswith(suf) and len(w) > len(suf) + 2:
            stem = w[: -len(suf)]
            for add in adds:
                if stem + add in lexicon:
                    return True
            # running -> run, bigger -> big (doubled final consonant)
            if len(stem) > 2 and stem[-1] == stem[-2] and stem[:-1] in lexicon:
                return True
    for pre in ('re', 'un', 'in', 'im', 'dis', 'non', 'over', 'under', 'mis',
                'pre', 'sub', 'inter', 'multi'):
        if w.startswith(pre) and len(w) > len(pre) + 3:
            if _known(w[len(pre):], lexicon):
                return True
    return False


def _candidates(tokens: list[str], i: int) -> list[tuple[str, int]]:
    """Surface forms to test at position i: the word, and the word joined with
    the next one. "hetero elasticity" is one ruined term, not two words."""
    out = [(tokens[i].lower(), 1)]
    if i + 1 < len(tokens):
        out.append((tokens[i].lower() + tokens[i + 1].lower(), 2))
    return out


NAME_CUTOFF = 0.80      # names only, and only against priority-1 names
NAME_MIN = 5            # below this a 'name' is an abbreviation


def normalise(text: str, vocab: dict, cutoff: float | None = None,
              lexicon: set[str] | None = None, names: set | None = None) -> dict:
    lexicon = load_lexicon() if lexicon is None else lexicon
    if cutoff is None:
        cutoff = CUTOFF if lexicon else CUTOFF_NO_LEXICON
    keys = [k for k in vocab if len(k) >= MIN_TERM]
    tokens = re.split(r'(\W+)', text)
    words = [(i, t) for i, t in enumerate(tokens) if WORD_RE.fullmatch(t)]
    corrections = []
    idx = 0
    word_positions = [i for i, _ in words]
    word_values = [t for _, t in words]

    names = names or set()
    name_keys = sorted(names)
    unmatched_names = []
    while idx < len(word_values):
        applied = False
        # The name channel, first and separate: a capitalised token that is not
        # a word and is not already a known name. Single tokens only -- joining
        # two words into a name is how a surname eats the word after it.
        raw_tok = word_values[idx]
        if (name_keys and raw_tok[:1].isupper() and len(raw_tok) >= NAME_MIN
                and not raw_tok.isupper()          # an acronym is not a surname
                and raw_tok not in names and not _known(raw_tok, lexicon)):
            hit = difflib.get_close_matches(raw_tok, name_keys, n=1,
                                            cutoff=NAME_CUTOFF)
            # The target must not be a dictionary word either. Without this the
            # channel "repairs" Uni -> Unit and Universitat -> University: both
            # score well and both are wrong, because a name channel whose target
            # is a common noun is just the F3 bug again in a smaller font.
            if hit and hit[0] != raw_tok and not _known(hit[0], lexicon) \
                    and abs(len(hit[0]) - len(raw_tok)) <= 3:
                ratio = difflib.SequenceMatcher(None, raw_tok, hit[0]).ratio()
                before = ' '.join(word_values[max(0, idx - 5):idx])
                after = ' '.join(word_values[idx + 1:idx + 6])
                tokens[word_positions[idx]] = hit[0]
                corrections.append({'from': raw_tok, 'to': hit[0],
                                    'score': round(ratio, 3), 'kind': 'name',
                                    'context': f'...{before} [{raw_tok}] {after}...'})
                idx += 1
                continue
            if not raw_tok.isupper():
                unmatched_names.append(raw_tok)
        for surface, span in _candidates(word_values, idx):
            if len(surface) < MIN_TERM or surface in vocab:
                continue
            # The veto: a word the language already has is not an ASR error,
            # however close some lecture term happens to be to it.
            if _known(surface, lexicon):
                continue
            floor = cutoff if span == 1 else min(cutoff, JOIN_CUTOFF)
            match = difflib.get_close_matches(surface, keys, n=1, cutoff=floor)
            if not match:
                continue
            best = match[0]
            if best == surface or abs(len(best) - len(surface)) > 4:
                continue
            # A join must look like one ruined long term, not two ordinary words
            # that happen to concatenate near something in the vocabulary.
            if span == 2 and (len(best) < 10 or best[:4] != surface[:4]):
                continue
            # A join is only a repair when one of the two tokens is itself not a
            # word. Two ordinary words that happen to concatenate near a vocab
            # term ("University"+"of") are not one ruined term, and the match is
            # then explained purely by dropping the second token.
            if span == 2:
                a, b = word_values[idx].lower(), word_values[idx + 1].lower()
                if _known(a, lexicon) and _known(b, lexicon):
                    continue
                # best being a prefix of the surface means "delete the tail",
                # never "repair a misheard term".
                if surface.startswith(best) or best.startswith(surface):
                    continue
            ratio = difflib.SequenceMatcher(None, surface, best).ratio()
            before = ' '.join(word_values[max(0, idx - 5):idx])
            after = ' '.join(word_values[idx + span:idx + span + 5])
            original = ' '.join(word_values[idx:idx + span])
            # keep the original capitalisation shape of the first token
            replacement = best.capitalize() if original[:1].isupper() else best
            tokens[word_positions[idx]] = replacement
            for k in range(1, span):
                tokens[word_positions[idx + k]] = ''
                # drop the space that joined them
                sep = word_positions[idx + k] - 1
                if 0 <= sep < len(tokens) and tokens[sep].strip() == '':
                    tokens[sep] = ''
            corrections.append({'from': original, 'to': replacement,
                                'score': round(ratio, 3),
                                'context': f'...{before} [{original}] {after}...'})
            idx += span
            applied = True
            break
        if not applied:
            idx += 1
    return {'text': ''.join(tokens), 'corrections': corrections,
            'unmatched_names': sorted(set(unmatched_names))}


def segment(text: str, prefix: str = 'T', size: int = SEGMENT_WORDS) -> list[dict]:
    """Paragraph first, then a word budget inside a long paragraph.

    Segment size is the one number here with no principled value; §17 item 7
    says to fix it against a real transcript rather than in the abstract, so it
    is a flag rather than a constant hard-coded in three places.
    """
    paras = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    items, buf = [], []

    def _flush():
        if buf:
            items.append({'id': f'{prefix}{len(items) + 1:02d}', 'tags': [],
                          'text': ' '.join(buf).strip()})
            buf.clear()

    for para in paras:
        words = para.split()
        if len(' '.join(buf).split()) + len(words) > size and buf:
            _flush()
        if len(words) > size * 2:
            _flush()
            for i in range(0, len(words), size):
                items.append({'id': f'{prefix}{len(items) + 1:02d}', 'tags': [],
                              'text': ' '.join(words[i:i + size])})
            continue
        buf.append(para)
    _flush()
    return items


def classify_segments(items: list[dict]) -> dict:
    recap, announce, noncontent, signals, slide_fixes = [], [], [], [], []
    for n, item in enumerate(items):
        text = item['text']
        if RECAP_RE.search(text) and n < max(2, len(items) // 5):
            recap.append(item['id'])
        if ANNOUNCE_RE.search(text):
            announce.append({'id': item['id'],
                             'text': text[:240]})
        if NONCONTENT_RE.search(text):
            noncontent.append(item['id'])
        if EXAM_RE.search(text):
            item['tags'] = sorted(set(item['tags']) | {'exam_signal'})
            signals.append({'id': item['id'], 'text': text[:200]})
        m = SLIDE_FIX_RE.search(text)
        if m:
            slide = m.group('slide') or m.group('slide2')
            slide_fixes.append({'id': item['id'], 'slide': f'S{slide}',
                                'marker': f'[S{slide} corrected by {item["id"]}]',
                                'text': text[:240]})
    return {'recap': recap, 'announcements': announce,
            'non_content': noncontent, 'exam_signals': signals,
            'slide_corrections': slide_fixes}


def write_log(work: Path | str, source: str, corrections: list[dict],
              apply_it: bool = True) -> str:
    stem = extraction.extraction_name(source)[2:-3] if source else ''
    path = Path(work) / (LOG_NAME.replace('.md', f'_{stem}.md') if stem
                         else LOG_NAME)
    lines = ['# Transcript corrections',
             '',
             f'Source: `{source}`  ·  {len(corrections)} corrections',
             '',
             'Fuzzy matching against the slide and book vocabulary gets some of '
             'these wrong. Each row carries its context so a wrong correction '
             'is visible rather than indistinguishable from what was said.',
             '',
             '| From | To | Score | Context |', '|---|---|---|---|']
    for c in corrections:
        ctx = c['context'].replace('|', '\\|')
        lines.append(f"| {c['from']} | {c['to']} | {c['score']} | {ctx} |")
    text = '\n'.join(lines) + '\n'
    if apply_it:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + '.tmp')
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)
    return str(path)


def _assert_prefix_free(work: Path | str, entry: str, prefix: str) -> None:
    """Refuse to give two recordings in one lesson the same id prefix.

    `--index` defaults to 1, so normalising a lesson's second transcript
    without passing it produced a second set of `T1.` ids. Nothing downstream
    could see it: `extraction.validate_id` accepts them, and Pass D subtracts
    *sets*, so the two files' items merge and the coverage arithmetic reports
    complete while half of one recording is unaccounted for. note-invariants
    \u00a72 requires the file index precisely so this cannot happen, so the
    guarantee belongs here rather than in the caller's memory.
    """
    work = Path(work)
    if not work.is_dir():
        return
    mine = extraction.extraction_name(entry)
    for other in sorted(work.glob('A_*.md')):
        if other.name == mine:
            continue
        try:
            data = extraction.read(other)
        except Exception:
            continue
        if (data.get('header', {}) or {}).get('kind') != 'transcript':
            continue
        ids = [i['id'] for i in data.get('items', [])]
        if not ids:
            continue
        theirs = ids[0].split('.')[0] + '.'
        if theirs == prefix:
            raise extraction.ExtractionError(
                f'{other.name} already uses the id prefix `{prefix}` for source '
                f"`{(data.get('header', {}) or {}).get('source', '?')}`. Giving "
                f'`{entry}` the same prefix would make the two recordings\' ids '
                'indistinguishable, and Pass D would report complete coverage '
                'while missing half of one of them. Pass a distinct --index '
                '(the second recording in a lesson is --index 2).')


def run(path: Path | str, entry: str, work: Path | str, vocab_from: list[str],
        run_id: str, sources_hash: str, prefix: str = 'T',
        size: int = SEGMENT_WORDS, apply_it: bool = False,
        index: int = 1) -> dict:
    raw = Path(path).read_text(encoding='utf-8', errors='replace')
    meta, raw = split_frontmatter(raw)
    # Transcript ids are always indexed, like A2.4 and V1.6. The conditional
    # form renumbers lesson 1's ids the day a second recording is added, which
    # detaches every correction anchored to one.
    if prefix == 'T':
        prefix = f'T{index}.'
    _assert_prefix_free(work, entry, prefix)
    vocab = build_vocab(vocab_from)
    names = build_name_vocab(vocab_from)
    lexicon = load_lexicon()
    norm = normalise(raw, vocab, lexicon=lexicon, names=names)
    items = segment(norm['text'], prefix, size)
    marks = classify_segments(items)
    log = write_log(work, entry, norm['corrections'], apply_it)
    written = extraction.write(work, entry, run_id, sources_hash, 'transcript',
                               items, _chunks(items), apply_it=apply_it)
    return {'path': str(path), 'entry': entry, 'vocabulary': len(vocab),
            'names': len(names), 'prefix': prefix, 'metadata': meta,
            'unmatched_names': norm.get('unmatched_names', []),
            'lexicon': len(lexicon),
            'lexicon_note': None if lexicon else
            ('no general word list on this machine, so the only guard against '
             'correcting a real word is the similarity threshold. It is raised '
             'to compensate, which means fewer genuine ASR errors are repaired. '
             'Say so in the run report.'),
            'corrections': norm['corrections'], 'segments': len(items),
            'log': log, 'written': written, **marks}


def _chunks(items: list[dict], limit: int = 8000) -> list[str]:
    out, words = [], 0
    for item in items:
        n = len(item['text'].split())
        if words and words + n > limit:
            out.append(item['id'])
            words = 0
        words += n
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('vocab'); p.add_argument('--from', dest='src', nargs='+',
                                                required=True)
    p = sub.add_parser('run')
    p.add_argument('--path', required=True); p.add_argument('--entry', required=True)
    p.add_argument('--work', required=True)
    p.add_argument('--vocab-from', nargs='*', default=[])
    p.add_argument('--run', dest='run_id', default='')
    p.add_argument('--hash', default=''); p.add_argument('--prefix', default='T')
    p.add_argument('--index', type=int, default=1)
    p.add_argument('--segment-words', type=int, default=SEGMENT_WORDS)
    p.add_argument('--apply', action='store_true')
    args = ap.parse_args(argv)

    if args.cmd == 'vocab':
        v = build_vocab(args.src)
        out = {'terms': len(v),
               'sample': sorted(v, key=lambda k: -v[k])[:40]}
    else:
        out = run(args.path, args.entry, args.work, args.vocab_from,
                  args.run_id, args.hash, args.prefix, args.segment_words,
                  args.apply, args.index)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
