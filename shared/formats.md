# File formats: extension to handler

Extended **only on approval**. When a skill meets an extension that is not here, it leaves the file
where it is, says what it found, and proposes a row for this table. It never guesses a handler, because
a wrong handler produces an empty or garbled extraction that looks like a thin source rather than a
failure.

## Sources

| Extension | Handler | Notes |
|---|---|---|
| `.pdf` | `shared/scripts/extract_pdf.py` | Text and page ranges via `pdfplumber`, with `pdftotext` as a cross-check. Annotation layer read separately by B's `extract_annotations.py`. Falls back to `shared/scripts/ocr.py` when there is no text layer. |
| `.pptx` | B `scripts/extract_pptx.py` | Text, speaker notes, images, per-slide IDs (`python-pptx`) |
| `.docx` | B `scripts/extract_docx.py` | `python-docx` |
| `.epub` | B `scripts/extract_epub.py` | Structure from the spine and nav document; page ranges become section anchors |
| `.md`, `.txt` | read directly | Transcripts, student notes, handouts written as text |
| `.vtt`, `.srt` | B `scripts/fetch_video_captions.py` | Also the on-disk form of downloaded captions |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.webp` | `shared/scripts/ocr.py` | OCR plus a vision fallback; every uncertain reading is flagged |
| `.html`, `.htm` | `bs4` | Saved lecture pages; assigned links are fetched by B, not by A |
| `.xlsx`, `.xlsm` | B `scripts/extract_xlsx.py` (`openpyxl`) | Workshop and tutorial workbooks. Sheet names, labels, values **and formulas** are all extracted: in a finance or engineering workshop `=B12/B30` *is* the content, and a workbook read for its values alone loses the method the tutorial is teaching. A lecturer's workbook is priority 1 with the `handout_` prefix; a filled-in copy by a student is priority 3 with `notes_`, and is never a standalone claim. |

## Deliberately unhandled

| Extension | Why |
|---|---|
| `.doc`, `.ppt` (legacy binary) | Convert to the modern format first. `pandoc` and LibreOffice are available and A proposes the conversion; nothing converts silently. The original is always kept. |
| `.pages`, `.key`, `.numbers` | Apple formats with no reliable text extraction. Export to PDF first. |
| `.zip`, `.rar`, `.7z` | Archives are never expanded automatically. A asks the student to unpack into `_Inbox/`. |
| `.mp4`, `.mov`, `.m4a`, `.mp3` | No local transcription in this plugin. A transcript is a source; a recording is not. Assigned online videos go through `videos.md` and captions. |

## Python dependencies

Checked by B's pre-flight check 7, and never installed without asking.

| Package | Used by | Present in the current runtime |
|---|---|---|
| `pdfplumber`, `pypdf` | `extract_pdf.py` | yes |
| `python-pptx` | `extract_pptx.py` | yes |
| `python-docx` | `extract_docx.py` | yes |
| `Pillow`, `numpy` | `detect_marks.py`, `ocr.py` | yes |
| `sympy` | `verify_calc.py`, `verify_fix.py` | yes |
| `beautifulsoup4` | link extraction, E's `fetch.py` | yes |
| `pytesseract` / `tesseract` binary | `ocr.py` | binary yes |
| `ebooklib` | `extract_epub.py` | **no** — install on first use, after asking |
| `yt-dlp` | `fetch_video_captions.py` | **no** — install on first use, after asking |

Command-line tools already present: `pdftotext`, `tesseract`, `pandoc`, `git`, `jq`, `node`.

## Scanned PDFs and the repair policy

A PDF with no text layer is OCR'd into a **new searchable PDF beside the original**
(`ocrmypdf`, oversampled; the original is never modified). Measured on a real
490-page scan: about 1 line in 10 comes back uncertain, and some of the rest is
wrong without being flagged.

Repairs to that text are allowed, and every one of them is recorded in
`source_errata.json` with a `basis`:

| `basis` | Meaning | Applied? |
|---|---|---|
| `vocabulary` | The garbled token maps onto a term the slides or book already use. `Tatrinsictack` → `intrinsic task`. | Yes, tagged `errata` |
| `external` | The reading came from outside the book. Carries the URL and a quoted snapshot. | Yes for prose, tagged `errata_external`, and the notes cite `[B4.2, repaired: external W1]` so the provenance survives into the notes and into revision questions |
| `external`, on a **number, formula, threshold or date** | Same, but the repair changes a value | **No. Proposed only**, left as OCR read it and marked `[OCR, verify]`, with the candidate reading and its source held in the log as pending. |

**Why numbers are carved out.** An outside source can be authoritative, genuinely
about the topic, and wrong *for this edition*. This course's own Solutions Manual
is the proof: it is the 2nd edition of the set textbook and its numbers differ.
A value repaired that way is confidently wrong, carries a marker that reads as
verified, and the revision skill will build exam questions from it. Prose has
redundancy to recover from; a threshold does not.

---

## Files that are never sources

A file manager's leftovers and an editor's lock files are not course material,
and handing one to an extractor by its extension fails mid-run for no reason: a
165-byte `~$Chapter_1.docx` is an Office owner file, not a document.

| Pattern | What it is |
|---|---|
| `.DS_Store`, `Thumbs.db`, `desktop.ini`, `Icon\r` | file-manager metadata |
| any name starting with `.` | dotfile, including `._` AppleDouble forks |
| `~$*` | Word, Excel and PowerPoint lock and owner files |
| `*.tmp`, `*.temp`, `*.swp` | editor and system scratch |
| `*.crdownload`, `*.part` | a download still in flight |

**One implementation:** `shared/scripts/classify.py` → `is_ignored(path)`, which
both course-setup and course-notes call. The table above is the human-readable
contract; the function is what runs. Two ignore lists would drift, and only one
of them would be wrong.

Excluded at **scope construction**, before any check runs, so these files never
reach the iCloud scan, the extension check or an extractor.
