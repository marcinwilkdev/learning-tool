"""Admin panel: watch the knowledge base being built, live.

The dashboard is served at http://localhost:8000/admin/ by `learnkb-serve`, next to the
learning site (`learnkb-admin` starts the same server and opens the panel). A watcher thread polls kb/,
library/ and the activity log once a second; when anything changes it recomputes a
snapshot and pushes it to open pages over Server-Sent Events. Everything is derived
from disk, so the panel can be started or restarted at any point of a build:

- per document: converted, outlined, wiki built, and its reading plan with the share
  of headings in each part that wiki pages already cite
- the wiki: page counts, the curriculum with each topic's lesson and quiz status
- health: the same errors and warnings as `learnkb-check`
- activity: build steps (see `learnkb-admin step`) and recently written files

`learnkb-admin step <phase> [message] [--doc SLUG] [--part N|N-M] [--skip]` records a
build step for the panel; the ingest skill calls it as it works. `read --skip` marks
parts deliberately left unread, such as a book's index, which the coverage figure then
leaves out.
"""

import argparse
import html
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from learnkb import activity
from learnkb.check import CURRICULUM, SECTIONS, Report, as_list, check, load_pages, read_json
from learnkb.ingest import KB, LIBRARY, MANIFEST, RAW, ROOT, library_key, load_manifest, reading_parts
from learnkb.site import load_extras

PAGE = Path(__file__).parent / "admin.html"
WATCHED = [KB, LIBRARY, activity.ACTIVITY.parent]
RECENT_FILES = 40
HEALTH_LIMIT = 200


# ---------------------------------------------------------------- snapshot


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def norm(section) -> str:
    # Same normalisation as check_sections: entities and spacing don't matter.
    return " ".join(html.unescape(str(section)).split()).casefold()


def git_branch() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def document_plan(slug: str, cited: set[str], steps: list[dict]) -> dict | None:
    """The reading plan of kb/raw/<slug>.md with citation coverage and reading progress per part."""
    raw = RAW / f"{slug}.md"
    if not raw.exists():
        return None
    lines = raw.read_text().splitlines()
    heads = [i for i, l in enumerate(lines) if l.startswith("#")]
    # The latest step for a part wins, so a skipped part that's read later counts as read.
    status: dict[int, str] = {}
    for s in steps:
        if s.get("doc") == slug and s.get("phase") == "read" and isinstance(s.get("part"), int):
            status[s["part"]] = "skipped" if s.get("skipped") else "read"
    parts, counted = [], set()
    for n, (a, b) in enumerate(reading_parts(lines, heads), 1):
        inside = [norm(lines[h].lstrip("#")) for h in heads if a - 1 <= h < b]
        if status.get(n) != "skipped":
            counted.update(inside)
        parts.append({"n": n, "lines": [a, b], "headings": len(inside),
                      "cited": sum(h in cited for h in inside), "status": status.get(n),
                      "starts": next((lines[h].lstrip("#").strip() for h in heads if a - 1 <= h < b), "")})
    # Coverage leaves out skipped parts (an index, say): their headings are never meant to be cited.
    return {"lines": len(lines), "kb": round(raw.stat().st_size / 1000), "parts": parts,
            "headings": len(counted), "cited": len(counted & cited),
            "skipped": sum(p["status"] == "skipped" for p in parts),
            "outline": raw.with_suffix(".outline.md").exists()}


def documents(pages: dict, steps: list[dict]) -> list[dict]:
    manifest = load_manifest()["documents"] if KB.exists() else {}
    cited: dict[str, set[str]] = {}
    for page in pages.values():
        for src in as_list(page.meta.get("sources")):
            if isinstance(src, dict) and src.get("section"):
                cited.setdefault(src.get("doc"), set()).add(norm(src["section"]))
    source_docs = {p.meta.get("doc") for p in pages.values() if p.kind == "source"}

    out = []
    for rel, d in manifest.items():
        out.append({"file": rel, "slug": d["slug"], "title": d.get("title") or d["slug"],
                    "pages": d.get("pages"), "converted_at": d.get("converted_at"),
                    "wiki_built": bool(d.get("wiki_built")), "removed": bool(d.get("removed")),
                    "source_page": d["slug"] in source_docs,
                    "scanned_pages": len(d.get("scanned_pages") or []), "transcription": d.get("transcription"),
                    "plan": document_plan(d["slug"], cited.get(d["slug"], set()), steps)})
    for pdf in sorted(LIBRARY.glob("**/*.pdf")):
        rel = library_key(pdf)
        if rel not in manifest:
            out.append({"file": rel, "slug": None, "title": pdf.stem, "wiki_built": False,
                        "removed": False, "source_page": False, "plan": None, "unconverted": True})
    return out


def curriculum_view(pages: dict, lessons: dict, quizzes: dict) -> dict:
    curriculum = read_json(CURRICULUM)
    topics = {s: p for s, p in pages.items() if p.kind == "topic"}

    def topic(slug: str) -> dict:
        page = topics.get(slug)
        return {"slug": slug, "title": page.meta.get("title", slug) if page else slug,
                "page": page is not None, "lesson": slug in lessons, "quiz": slug in quizzes,
                "concepts": len(as_list(page.meta.get("concepts"))) if page else 0}

    modules = [{"slug": m.get("slug"), "title": m.get("title") or m.get("slug"),
                "topics": [topic(t) for t in m.get("topics", [])]}
               for m in curriculum.get("modules", [])]
    placed = {t["slug"] for m in modules for t in m["topics"]}
    unplaced = [topic(s) for s in sorted(topics) if s not in placed]
    return {"modules": modules, "unplaced": unplaced}


def recent_files(limit: int = RECENT_FILES) -> tuple[list[dict], dict]:
    files, counts = [], {"10m": 0, "60m": 0}
    now = time.time()
    for path in KB.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        st = path.stat()
        born = getattr(st, "st_birthtime", None)
        files.append({"path": str(path.relative_to(KB)), "at": st.st_mtime,
                      "created": born is not None and st.st_mtime - born < 2})
        counts["10m"] += now - st.st_mtime < 600
        counts["60m"] += now - st.st_mtime < 3600
    files.sort(key=lambda f: f["at"], reverse=True)
    return [{**f, "at": iso(f["at"])} for f in files[:limit]], counts


def snapshot() -> dict:
    steps = activity.recent()
    snap = {"generated_at": iso(time.time()), "branch": git_branch(), "kb": KB.exists(),
            "steps": steps[-60:], "phases": activity.PHASES}
    if not KB.exists():
        return snap

    report = Report()
    pages = load_pages(report)
    curriculum = read_json(CURRICULUM)
    check(pages, read_json(MANIFEST), curriculum, report)
    order = [t for m in curriculum.get("modules", []) for t in m.get("topics", [])]
    lessons, quizzes = load_extras(pages, order, report)

    files, written = recent_files()
    snap.update({
        "documents": documents(pages, activity.recent(limit=None)),  # reading progress needs every step
        "counts": {**{folder: sum(p.kind == kind for p in pages.values()) for kind, folder in SECTIONS.items()},
                   "modules": len(curriculum.get("modules", [])), "placed": len(order),
                   "lessons": len(lessons), "quizzes": len(quizzes)},
        "curriculum": curriculum_view(pages, lessons, quizzes),
        "health": {"errors": report.errors[:HEALTH_LIMIT], "warnings": report.warnings[:HEALTH_LIMIT],
                   "n_errors": len(report.errors), "n_warnings": len(report.warnings)},
        "files": files, "written": written,
    })
    return snap


def safe_snapshot() -> dict:
    # Mid-build, files can be half-written; report that instead of killing the watcher.
    try:
        return snapshot()
    except Exception:
        return {"generated_at": iso(time.time()), "kb": KB.exists(), "branch": git_branch(),
                "steps": activity.recent()[-60:], "phases": activity.PHASES,
                "failure": traceback.format_exc(limit=3)}


# ---------------------------------------------------------------- watcher


def fingerprint() -> tuple:
    count, newest, size = 0, 0, 0
    for root in WATCHED:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") or d == ".learnkb"]
            for name in filenames:
                try:
                    st = os.stat(os.path.join(dirpath, name))
                except FileNotFoundError:
                    continue  # deleted between listing and stat
                count += 1
                newest = max(newest, st.st_mtime_ns)
                size += st.st_size
    return count, newest, size


class Watcher(threading.Thread):
    """Recompute the snapshot whenever the watched files change, and wake up listeners.

    `on_change` callbacks run in the watcher thread after each new snapshot."""

    def __init__(self, interval: float = 1.0):
        super().__init__(daemon=True)
        self.interval = interval
        self.on_change: list = []
        self.changed = threading.Condition()
        self.version = 0
        self.data = json.dumps(safe_snapshot())
        self.last = fingerprint()

    def run(self) -> None:
        while True:
            time.sleep(self.interval)
            current = fingerprint()
            if current == self.last:
                continue
            self.last = current
            data = json.dumps(safe_snapshot())
            with self.changed:
                self.data, self.version = data, self.version + 1
                self.changed.notify_all()
            for callback in self.on_change:
                callback()


# ---------------------------------------------------------------- server


def send(request: BaseHTTPRequestHandler, body: bytes, ctype: str) -> None:
    request.send_response(200)
    request.send_header("Content-Type", ctype)
    request.send_header("Cache-Control", "no-store")
    request.send_header("Content-Length", str(len(body)))
    request.end_headers()
    request.wfile.write(body)


def handle_get(request: BaseHTTPRequestHandler, path: str, watcher: Watcher) -> None:
    """Answer a GET for the panel; `path` is relative to where the panel is mounted."""
    if path in ("", "index.html"):
        send(request, PAGE.read_bytes(), "text/html; charset=utf-8")
    elif path == "api/status":
        send(request, watcher.data.encode(), "application/json")
    elif path == "api/events":
        events(request, watcher)
    else:
        request.send_error(404)


def events(request: BaseHTTPRequestHandler, watcher: Watcher) -> None:
    request.send_response(200)
    request.send_header("Content-Type", "text/event-stream")
    request.send_header("Cache-Control", "no-store")
    request.end_headers()
    seen = -1
    try:
        while True:
            with watcher.changed:
                if watcher.version == seen:
                    watcher.changed.wait(timeout=15)
                version, data = watcher.version, watcher.data
            if version != seen:
                request.wfile.write(f"data: {data}\n\n".encode())
                seen = version
            else:
                request.wfile.write(b": keep-alive\n\n")
            request.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass  # the page was closed


def parts_arg(value: str) -> list[int]:
    """--part accepts one part number or an inclusive range such as 25-30."""
    first, _, last = value.partition("-")
    try:
        a, b = int(first), int(last or first)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected N or N-M, got {value!r}")
    if not 1 <= a <= b:
        raise argparse.ArgumentTypeError(f"invalid part range {value!r}")
    return list(range(a, b + 1))


def main() -> None:
    serving = argparse.ArgumentParser(add_help=False)
    serving.add_argument("--port", type=int, default=8000)
    serving.add_argument("--open", action="store_true", help="open the panel in a browser")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     parents=[serving])
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", parents=[serving], help="serve the site and the panel, like learnkb-serve (the default)")
    step = sub.add_parser("step", help="record a build step for the panel")
    step.add_argument("phase", choices=activity.PHASES)
    step.add_argument("message", nargs="?", default="")
    step.add_argument("--doc", help="document slug the step is about")
    step.add_argument("--part", type=parts_arg, help="reading-plan part being read, or a range N-M (with --doc)")
    step.add_argument("--skip", action="store_true", help="with read: the part(s) are deliberately not read")
    sub.add_parser("status", help="print the current snapshot as JSON")
    args = parser.parse_args()

    if args.command == "step":
        if args.skip and (args.phase != "read" or not args.part or not args.doc):
            parser.error("--skip needs the read phase, --doc and --part")
        for part in args.part or [None]:
            activity.record(args.phase, args.message, args.doc, part, skipped=args.skip)
    elif args.command == "status":
        print(json.dumps(snapshot(), indent=2))
    else:
        from learnkb import serve  # serve imports this module
        serve.run(args.port, open_path="admin/" if args.open else None)
    sys.exit(0)


if __name__ == "__main__":
    main()
