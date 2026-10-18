"""Validate the wiki under kb/ (pages, lessons and quizzes) and regenerate kb/index.json.

Checks are mechanical only (structure, links, references); judgement calls such as
contradictions between sources are left to the lint-kb skill.

Errors break the wiki for the viewer or quizzes and make the command exit non-zero.
Warnings are things worth fixing but safe to ship. index.json is written only when
there are no errors, so consumers never see a broken index.
"""

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from learnkb.ingest import KB, MANIFEST, RAW

INDEX = KB / "index.json"
CURRICULUM = KB / "curriculum.json"
SECTIONS = {"source": "sources", "concept": "concepts", "topic": "topics"}
REQUIRED = {
    "source": ["title", "doc"],
    "concept": ["title", "definition", "sources"],
    "topic": ["title", "module", "summary", "difficulty", "concepts", "sources"],
}
NO_KB = ("No knowledge base yet (kb/ is missing). Add PDFs to library/ and run /ingest. "
         "On main, switch to a learning branch first (git branch --list 'learn/*').")
DIFFICULTIES = {"beginner", "intermediate", "advanced"}
LINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)
# Substrings of PyYAML errors, and the usual cause when writing kb/ files by hand.
YAML_HINTS = [
    ("mapping values are not allowed", "a one-line value contains ': '; quote it or use a | block"),
    ("while parsing a flow", "a value inside [...] or {...} contains @ { } ? : or a comma; double-quote it"),
    ("found character '@'", "a value starts with @; double-quote it"),
    ("found character '`'", "a value starts with a backtick; double-quote it"),
    ("while parsing a block mapping", "if a | block starts with spaces (terminal output), write |2 so YAML "
                                      "knows its indent; otherwise check the indentation"),
]


@dataclass
class Page:
    kind: str
    slug: str
    path: Path
    meta: dict
    body: str
    links: set[str] = field(default_factory=set)


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def yaml_error(exc: yaml.YAMLError, line_offset: int = 0) -> str:
    """One-line YAML error with the file line number and a hint for the common causes."""
    mark = getattr(exc, "problem_mark", None)
    where = f" at line {mark.line + 1 + line_offset}" if mark else ""
    problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
    hint = next((h for key, h in YAML_HINTS if key in str(exc)), "")
    return f"invalid YAML{where}: {problem}" + (f" (hint: {hint})" if hint else "")


def malformed_links(text: str) -> list[str]:
    """Openings of [[links]] that never close, such as [[slug|Label], outside code."""
    return re.findall(r"\[\[[^\n]{0,40}", LINK.sub("", CODE.sub("", text)))


def check_links(rel: str, text: str, pages: dict, report: Report) -> set[str]:
    """Report unclosed and broken [[links]] in text; return the link targets."""
    for bad in malformed_links(text):
        report.error(f"{rel}: unclosed link '{bad}' (needs ]])")
    links = {m.strip() for m in LINK.findall(text)}
    for target in sorted(links - pages.keys()):
        report.error(f"{rel}: broken link [[{target}]]")
    return links


def load_pages(report: Report) -> dict[str, Page]:
    pages: dict[str, Page] = {}
    for kind, folder in SECTIONS.items():
        for path in sorted((KB / folder).glob("*.md")):
            rel = path.relative_to(KB)
            match = FRONTMATTER.match(path.read_text())
            if not match:
                report.error(f"{rel}: missing YAML frontmatter")
                continue
            try:
                meta = yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError as exc:
                report.error(f"{rel}: {yaml_error(exc, line_offset=1)}")
                continue
            slug = path.stem
            if meta.get("type") != kind:
                report.error(f"{rel}: type should be '{kind}', got {meta.get('type')!r}")
            for key in REQUIRED[kind]:
                if not meta.get(key):
                    report.error(f"{rel}: missing '{key}'")
            if slug in pages:
                report.error(f"{rel}: slug '{slug}' already used by {pages[slug].path.relative_to(KB)}")
                continue
            body = match.group(2)
            links = {m.strip() for m in LINK.findall(body)}
            pages[slug] = Page(kind, slug, path, meta, body, links)
    return pages


def as_list(value) -> list:
    return value if isinstance(value, list) else [] if value is None else [value]


def source_docs(page: Page) -> list[str]:
    return [s["doc"] if isinstance(s, dict) else s for s in as_list(page.meta.get("sources"))]


def check(pages: dict[str, Page], manifest: dict, curriculum: dict, report: Report) -> None:
    docs = {d["slug"]: d for d in manifest.get("documents", {}).values() if not d.get("removed")}
    by_kind = {k: {s: p for s, p in pages.items() if p.kind == k} for k in SECTIONS}
    concepts, topics, sources = by_kind["concept"], by_kind["topic"], by_kind["source"]
    inbound: dict[str, set[str]] = {s: set() for s in pages}

    for page in pages.values():
        rel = page.path.relative_to(KB)
        check_links(str(rel), page.body, pages, report)
        for target in page.links & pages.keys() - {page.slug}:
            inbound[target].add(page.slug)
        for doc in source_docs(page):
            if doc not in docs:
                report.error(f"{rel}: cites unknown document '{doc}'")

    for slug, page in sources.items():
        if page.meta.get("doc") not in docs:
            report.error(f"sources/{slug}.md: doc '{page.meta.get('doc')}' not in manifest")
    for slug, doc in docs.items():
        if doc.get("wiki_built") and slug not in {p.meta.get("doc") for p in sources.values()}:
            report.warn(f"document '{slug}' is marked wiki_built but has no source page")
        if not doc.get("wiki_built"):
            report.warn(f"document '{slug}' not yet ingested into the wiki")

    for slug, page in topics.items():
        rel = f"topics/{slug}.md"
        if page.meta.get("difficulty") not in DIFFICULTIES:
            report.error(f"{rel}: difficulty must be one of {sorted(DIFFICULTIES)}")
        for c in as_list(page.meta.get("concepts")):
            if c not in concepts:
                report.error(f"{rel}: concept '{c}' has no page")
        for p in as_list(page.meta.get("prerequisites")):
            if p not in topics:
                report.error(f"{rel}: prerequisite '{p}' is not a topic")
        missing = set(as_list(page.meta.get("concepts"))) - page.links
        if missing:
            report.warn(f"{rel}: concepts listed but never linked in text: {', '.join(sorted(missing))}")

    covered = {c for t in topics.values() for c in as_list(t.meta.get("concepts"))}
    for slug in concepts:
        if slug not in covered:
            report.warn(f"concepts/{slug}.md: not covered by any topic")
        if not inbound[slug]:
            report.warn(f"concepts/{slug}.md: orphan (no page links to it)")

    check_sections(pages, report)
    check_prerequisite_cycles(topics, report)
    check_curriculum(topics, curriculum, report)


def check_sections(pages: dict[str, Page], report: Report) -> None:
    """Warn when a cited section isn't a heading in the document's raw text."""
    # The PDF converter writes some characters as HTML entities ("SETUP &amp; INIT").
    norm = lambda s: " ".join(html.unescape(str(s)).split()).casefold()
    headings: dict[str, set[str] | None] = {}
    for page in pages.values():
        for src in as_list(page.meta.get("sources")):
            if not isinstance(src, dict) or not src.get("section"):
                continue
            doc = src.get("doc")
            if doc not in headings:
                raw = RAW / f"{doc}.md"
                headings[doc] = ({norm(l.lstrip("#")) for l in raw.read_text().splitlines() if l.startswith("#")}
                                 if raw.exists() else None)
            if headings[doc] is not None and norm(src["section"]) not in headings[doc]:
                report.warn(f"{page.path.relative_to(KB)}: section '{src['section']}' is not a heading in raw/{doc}.md")


def check_prerequisite_cycles(topics: dict[str, Page], report: Report) -> None:
    state: dict[str, int] = {}  # 1 = visiting, 2 = done

    def visit(slug: str, path: list[str]) -> None:
        if state.get(slug) == 2 or slug not in topics:
            return
        if state.get(slug) == 1:
            cycle = path[path.index(slug):] + [slug]
            report.error(f"prerequisite cycle: {' -> '.join(cycle)}")
            return
        state[slug] = 1
        for p in as_list(topics[slug].meta.get("prerequisites")):
            visit(p, path + [slug])
        state[slug] = 2

    for slug in topics:
        visit(slug, [])


def check_curriculum(topics: dict[str, Page], curriculum: dict, report: Report) -> None:
    if not topics:
        return
    if not curriculum:
        report.error("curriculum.json missing; every topic must belong to a module")
        return
    placed: dict[str, str] = {}
    for module in curriculum.get("modules", []):
        order = module.get("topics", [])
        for i, slug in enumerate(order):
            if slug not in topics:
                report.error(f"curriculum.json: module '{module.get('slug')}' lists unknown topic '{slug}'")
                continue
            if slug in placed:
                report.error(f"curriculum.json: topic '{slug}' in modules '{placed[slug]}' and '{module.get('slug')}'")
            placed[slug] = module.get("slug")
            if topics[slug].meta.get("module") != module.get("slug"):
                report.error(f"topics/{slug}.md: module is '{topics[slug].meta.get('module')}' but curriculum puts it in '{module.get('slug')}'")
            later = set(order[i + 1:])
            for p in as_list(topics[slug].meta.get("prerequisites")):
                if p in later:
                    report.warn(f"curriculum.json: '{slug}' comes before its prerequisite '{p}'")
    for slug in topics:
        if slug not in placed:
            report.error(f"topics/{slug}.md: not placed in any curriculum module")


def build_index(pages: dict[str, Page], curriculum: dict) -> dict:
    inbound: dict[str, list[str]] = {s: [] for s in pages}
    for page in pages.values():
        for target in page.links:
            if target in inbound and target != page.slug:
                inbound[target].append(page.slug)

    def entry(page: Page) -> dict:
        meta = {k: v for k, v in page.meta.items() if k != "type"}
        return {**meta, "path": str(page.path.relative_to(KB)),
                "links": sorted(page.links), "backlinks": sorted(inbound[page.slug])}

    return {
        "modules": curriculum.get("modules", []),
        **{folder: {s: entry(p) for s, p in pages.items() if p.kind == kind}
           for kind, folder in SECTIONS.items()},
    }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="print errors only")
    args = parser.parse_args()

    if not KB.exists():
        sys.exit(NO_KB)
    report = Report()
    pages = load_pages(report)
    curriculum = read_json(CURRICULUM)
    check(pages, read_json(MANIFEST), curriculum, report)
    from learnkb.site import load_extras  # site imports this module, so import late
    load_extras(pages, [t for m in curriculum.get("modules", []) for t in m.get("topics", [])], report)

    for msg in report.errors:
        print(f"ERROR  {msg}")
    if not args.quiet:
        for msg in report.warnings:
            print(f"warn   {msg}")
    counts = {f: sum(p.kind == k for p in pages.values()) for k, f in SECTIONS.items()}
    print(f"\n{counts['sources']} sources, {counts['concepts']} concepts, {counts['topics']} topics: "
          f"{len(report.errors)} error(s), {len(report.warnings)} warning(s)")

    if report.errors:
        print("index.json not updated")
        sys.exit(1)
    KB.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(build_index(pages, curriculum), indent=2, ensure_ascii=False) + "\n")
    print("index.json updated")


if __name__ == "__main__":
    main()
