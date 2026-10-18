---
name: lint-kb
description: Health-check the knowledge-base wiki in kb/: broken links, orphan or duplicate concepts, contradictions between sources, gaps and thin pages. Use when the user asks to check, lint, audit, clean up or improve the knowledge base.
---

# Lint the knowledge base

Page formats and conventions are defined in `.claude/skills/ingest/SKILL.md`.
Read it first if you haven't this session.

## 1. Mechanical checks
Run `uv run learnkb-check`. It reports structural errors (broken links, unknown
references, curriculum mismatches, prerequisite cycles) and warnings (orphans,
uncovered concepts, unlinked concepts, documents not yet ingested).

## 2. Judgement checks
Use `kb/index.json` to survey the wiki, then read pages as needed to look for:

- **Duplicates**: two concepts that are really the same idea under different
  names. Merge them into one page, keep the other name in `aliases`, and
  update all links.
- **Contradictions**: pages that disagree, or a concept page that states
  something one of its sources contradicts and has no `## Source disagreements`
  section.
- **Thin pages**: concepts that are only a definition, or topics whose
  walkthrough doesn't actually connect their concepts. Enrich them from
  `kb/raw/`; never from outside knowledge.
- **Missing concepts**: terms used repeatedly across pages that have no page.
- **Topic sizing**: topics with too many concepts (split them), or too few
  (merge them). Check that learning objectives are concrete and testable.
- **Curriculum order**: whether a newcomer could follow the modules in order.
- **Drift**: claims on a page that its cited sections in `kb/raw/` don't support.
  Spot-check a few pages per run instead of reading everything.

## 3. Report, then fix
Show the user a short list of findings grouped by severity. Fix mechanical
errors and clear-cut issues (broken links, obvious duplicates) right away.
Ask before structural changes such as merging or splitting topics or reordering
modules. Run `uv run learnkb-check` again until it passes, then append a
`## <date> lint` entry to `kb/log.md` listing what changed.
