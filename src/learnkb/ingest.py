"""Convert PDFs in library/ into Markdown under kb/raw/, tracked by kb/manifest.json.

Re-running is incremental: a PDF is only re-converted when its content hash changes.
Each converted document is flagged `wiki_built: false` so the ingest skill knows
which sources still need to be folded into the wiki.

Next to each kb/raw/<doc>.md goes kb/raw/<doc>.outline.md: a reading plan that splits
long documents into parts at headings, the places where conversion probably lost
content (commands that were images, code flattened onto one line), and every heading
with its line number. Outlines are regenerated whenever they're missing or stale.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from learnkb import activity

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "library"
KB = ROOT / "kb"
RAW = KB / "raw"
MANIFEST = KB / "manifest.json"
PART_CHARS = 60_000  # about 15k tokens: comfortably under one Read call's limit


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "document"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"documents": {}}


def save_manifest(manifest: dict) -> None:
    KB.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def make_converter():
    # Imported lazily: docling pulls in heavy ML deps and loads models on first use.
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = True  # handles scanned PDFs; slower, but sources are few
    options.do_table_structure = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


# ---------------------------------------------------------------- outline


def blocks(lines: list[str]) -> list[tuple[int, str]]:
    """Split Markdown into (first line index, text) blocks: fenced code or blank-line paragraphs."""
    out, i = [], 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        start = i
        if lines[i].startswith("```"):
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                i += 1
            i += 1
        else:
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("```"):
                i += 1
        out.append((start, "\n".join(lines[start:i])))
    return out


def conversion_losses(lines: list[str]) -> dict[str, list[int]]:
    """1-based line numbers where the PDF conversion probably lost or mangled content."""
    lost_image, lost_text, flattened, figures = [], [], [], []
    bs = blocks(lines)
    for (_, text), (start, nxt) in zip(bs, bs[1:]):
        # "Run this command:" followed by an image (or by prose) instead of the code it announces.
        if (text.rstrip().endswith(":") and not text.startswith(("```", "#", "|", "<!--", "$"))
                and not nxt.startswith(("```", "|", "- ", "* ", "#", "$", "Figure "))
                and not re.match(r"\d+\. ", nxt) and not nxt.rstrip().endswith(":")):
            (lost_image if nxt.startswith("<!-- image") else lost_text).append(start + 1)
        if re.match(r"Figure \d+[.:]", text):
            figures.append(start + 1)
    for n, line in enumerate(lines, 1):
        if len(re.findall(r"(?:^|\s)\$ \S", line)) > 1:
            flattened.append(n)
    return {"lost_image": lost_image, "lost_text": lost_text, "flattened": flattened, "figures": figures}


def reading_parts(lines: list[str], heads: list[int]) -> list[tuple[int, int]]:
    """(first, last) 1-based line ranges under PART_CHARS each, split at headings where possible."""
    cuts = sorted({0, *heads, len(lines)})
    sections = [(a, b) for a, b in zip(cuts, cuts[1:]) if b > a]
    size = lambda a, b: sum(len(l) + 1 for l in lines[a:b])
    pieces = []
    for a, b in sections:  # an oversized section is cut at line boundaries
        start = a
        while size(start, b) > PART_CHARS:
            end, total = start, 0
            while end < b and total + len(lines[end]) + 1 <= PART_CHARS:
                total += len(lines[end]) + 1
                end += 1
            end = max(end, start + 1)
            pieces.append((start, end))
            start = end
        pieces.append((start, b))
    parts: list[list[int]] = []
    for a, b in pieces:
        if parts and size(parts[-1][0], b) <= PART_CHARS:
            parts[-1][1] = b
        else:
            parts.append([a, b])
    return [(a + 1, b) for a, b in parts]


def write_outline(raw: Path) -> Path:
    text = raw.read_text()
    lines = text.splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("#")]
    title = lambda i: lines[i].lstrip("#").strip()
    kb = lambda a, b: f"{sum(len(l) + 1 for l in lines[a:b]) / 1000:.0f} KB"
    out = [f"# Outline of kb/raw/{raw.name}", "",
           f"{len(lines):,} lines, {len(text) / 1000:,.0f} KB, about {len(text) // 4000}k tokens. "
           "Generated by `learnkb-ingest`; don't edit.", "",
           "## Reading plan", "",
           "Read the document part by part with `Read` (offset = first line, limit = line count).", "",
           "| Part | Lines | Size | Starts at |", "|---|---|---|---|"]
    for n, (a, b) in enumerate(reading_parts(lines, heads), 1):
        first = next((title(h) for h in heads if a - 1 <= h < b), "(continued)")
        out.append(f"| {n} | {a}–{b} ({b - a + 1} lines) | {kb(a - 1, b)} | {first} |")
    loss = conversion_losses(lines)
    fmt = lambda xs: ", ".join(map(str, xs)) or "none"
    out += ["", "## Possible conversion losses", "",
            "Check the raw text at these lines before quoting commands or output near them, and "
            "never fill a gap from outside knowledge: leave it out or say it's missing.", "",
            f"- **Block lost as an image** ({len(loss['lost_image'])}): text announcing a command or "
            f"output (ending in \":\") is followed by an image placeholder instead. Lines: {fmt(loss['lost_image'])}",
            f"- **Block possibly missing** ({len(loss['lost_text'])}): the same, followed by ordinary "
            f"prose. Lines: {fmt(loss['lost_text'])}",
            f"- **Flattened code** ({len(loss['flattened'])}): several commands, or a command and its "
            f"output, joined onto one line; split them at `$ ` when quoting. Lines: {fmt(loss['flattened'])}",
            f"- **Figures** ({len(loss['figures'])}): only the caption survives. Describe a figure "
            "from its caption and the surrounding text, never from memory.",
            "", "## Headings", "", "| Line | Size | Heading |", "|---|---|---|"]
    for h, nxt in zip(heads, heads[1:] + [len(lines)]):
        out.append(f"| {h + 1} | {kb(h, nxt)} | {title(h).replace('|', '/')} |")
    path = raw.with_suffix(".outline.md")
    path.write_text("\n".join(out) + "\n")
    return path


def refresh_outlines() -> None:
    for raw in sorted(RAW.glob("*.md")):
        if raw.name.endswith(".outline.md"):
            if not raw.with_name(raw.name.removesuffix(".outline.md") + ".md").exists():
                raw.unlink()  # its document is gone
            continue
        outline = raw.with_suffix(".outline.md")
        if not outline.exists() or outline.stat().st_mtime < raw.stat().st_mtime:
            print(f"outline  kb/raw/{write_outline(raw).name}")


# ---------------------------------------------------------------- convert


def ingest(force: bool = False) -> int:
    pdfs = sorted(LIBRARY.glob("**/*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {LIBRARY}")
        return 0

    manifest = load_manifest()
    docs = manifest["documents"]
    RAW.mkdir(parents=True, exist_ok=True)
    converter = None
    failures = 0

    for pdf in pdfs:
        rel = str(pdf.relative_to(LIBRARY))
        digest = sha256(pdf)
        entry = docs.get(rel)
        if entry and entry["sha256"] == digest and not force:
            print(f"skip     {rel} (unchanged)")
            continue

        slug = entry["slug"] if entry else slugify(pdf.stem)
        taken = {d["slug"] for k, d in docs.items() if k != rel}
        base, n = slug, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1

        print(f"convert  {rel} -> kb/raw/{slug}.md")
        activity.record("parse", f"Converting {rel}", doc=slug)
        converter = converter or make_converter()
        try:
            result = converter.convert(pdf)
        except Exception as exc:  # keep going; one bad PDF shouldn't stop the batch
            print(f"FAILED   {rel}: {exc}", file=sys.stderr)
            failures += 1
            continue

        doc = result.document
        (RAW / f"{slug}.md").write_text(doc.export_to_markdown())
        docs[rel] = {
            "slug": slug,
            "title": getattr(doc, "name", None) or pdf.stem,
            "sha256": digest,
            "pages": doc.num_pages() if hasattr(doc, "num_pages") else None,
            "converted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "wiki_built": False,
        }
        save_manifest(manifest)  # save after each doc so a crash loses little work

    # Drop manifest entries whose PDF was removed from the library.
    present = {str(p.relative_to(LIBRARY)) for p in pdfs}
    for rel in [k for k in docs if k not in present]:
        print(f"removed  {rel}")
        docs[rel]["removed"] = True
    save_manifest(manifest)
    refresh_outlines()

    pending = [d["slug"] for d in docs.values() if not d["wiki_built"] and not d.get("removed")]
    activity.record("parse", f"{len(pending)} document(s) awaiting wiki ingest")
    print(f"\n{len(pending)} document(s) awaiting wiki ingest: {', '.join(pending) or '-'}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-convert every PDF")
    sys.exit(ingest(force=parser.parse_args().force))


if __name__ == "__main__":
    main()
