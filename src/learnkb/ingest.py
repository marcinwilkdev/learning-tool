"""Convert PDFs in library/ into Markdown under kb/raw/, tracked by kb/manifest.json.

Re-running is incremental: a PDF is only re-converted when its content hash changes.
Each converted document is flagged `wiki_built: false` so the ingest skill knows
which sources still need to be folded into the wiki.
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "library"
KB = ROOT / "kb"
RAW = KB / "raw"
MANIFEST = KB / "manifest.json"


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

    pending = [d["slug"] for d in docs.values() if not d["wiki_built"] and not d.get("removed")]
    print(f"\n{len(pending)} document(s) awaiting wiki ingest: {', '.join(pending) or '-'}")
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-convert every PDF")
    sys.exit(ingest(force=parser.parse_args().force))


if __name__ == "__main__":
    main()
