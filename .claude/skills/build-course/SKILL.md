---
name: build-course
description: Build the whole learning site from the PDFs in library/ in one run: ingest them into the wiki, write a lesson for every topic, write a quiz for every topic, and render and check the site. Use when the user wants to go from raw PDFs to a finished course, asks to build or rebuild everything, set up a new subject end to end, or run ingest, learning pages and quizzes together.
---

# Build course

This skill chains three skills into one pipeline. It doesn't repeat their rules: at each
stage, read that skill's `SKILL.md` and follow it, with the overrides listed here.

| Stage | Skill | Produces |
|---|---|---|
| 1. Ingest | `.claude/skills/ingest/SKILL.md` | `kb/raw/`, `kb/sources/`, `kb/concepts/`, `kb/topics/`, `kb/curriculum.json` |
| 2. Lessons | `.claude/skills/learning-page/SKILL.md` | `kb/lessons/<topic>.yaml` for every topic |
| 3. Quizzes | `.claude/skills/assess/SKILL.md` (mode A) | `kb/quizzes/<topic>.yaml` for every topic |
| 4. Finish | (this skill) | a clean full site build and a report |

Paths are relative to the project root.

## Arguments
- Nothing: run the whole pipeline without stopping. The outline goes in the final
  report, so the user can ask for changes afterwards.
- `from lessons` or `from quizzes`: start at that stage, for example to resume an
  interrupted run. Earlier stages must already be done (`uv run learnkb-check` passes).
- `rebuild`: also overwrite existing lessons and quizzes. Ask once to confirm before
  starting, because this throws away hand-tuned files.

## Before you start
1. **Inputs.** `library/` must hold at least one PDF. If it is empty, stop and say
   where to put them (`library/`, or drop them on http://localhost:8000/admin/).
2. **Language.** If the user asked for a language other than English, or the PDFs are
   in another language, settle it now (ask if unclear): ingest sets `kb/site.json`, and
   the lesson and quiz stages write in the language it sets.
3. Tell the user they can watch progress live with `uv run learnkb-serve --open --admin`.

## 1. Ingest
Follow the ingest skill end to end, including progress steps for the admin panel and
transcribing scanned pages.

- **No stop at the outline.** Go straight on to stages 2 and 3 with the outline you
  proposed. Keep it for the final report.
- If no documents are pending and the wiki already passes `uv run learnkb-check`, skip
  to stage 2.
- Don't give the ingest report yet. Keep its points for the final report.

Stage 1 is done when `uv run learnkb-check` passes.

## 2 and 3. Lessons and quizzes
List the topics in curriculum order from `kb/curriculum.json`. A topic needs a lesson
if `kb/lessons/<slug>.yaml` doesn't exist, and a quiz if `kb/quizzes/<slug>.yaml`
doesn't exist. Without `rebuild`, leave existing files as they are.

The topics are independent, so build them in parallel.
- **Up to 3 topics:** do them yourself. For each one, write the lesson first, then the quiz.
- **More:** split the topics into batches of 2–4, keeping topics from the same module
  together, and give each batch to a subagent. Run up to 5 at once. Give each one this brief:

  > You are building learning material for these topics: `<slug>`, `<slug>`, … in
  > `<project root>`. Do not touch any other topic's files.
  > For each topic, in order:
  > 1. Read `.claude/skills/learning-page/SKILL.md` and follow its procedure to write
  >    `kb/lessons/<slug>.yaml` (skip if it exists: `<yes/no>`).
  > 2. Read `.claude/skills/assess/SKILL.md` and follow mode A to write
  >    `kb/quizzes/<slug>.yaml` (skip if it exists: `<yes/no>`). The quiz must not reuse
  >    the lesson's `checks`.
  > Render only your topic (`uv run learnkb-site <slug>`). Don't run the full build
  > (`uv run learnkb-site` with no topic), and don't edit wiki pages under `kb/topics/`,
  > `kb/concepts/` or `kb/sources/`: if one is wrong, report it instead. Other agents are
  > rendering at the same time, so shared pages like the home page may be briefly out
  > of date, which is fine. Screenshot each page as those
  > skills describe and fix what you see. Save screenshots to `<scratchpad>`.
  > Reply with one line per topic: lesson written/skipped, quiz written/skipped, number
  > of questions, and any gap in the sources that limited the lesson or quiz. Don't
  > offer to open pages or suggest next steps.

  The skills' own "report" and "offer to open" steps don't apply inside the pipeline.

When all batches are back, check every topic has both files. Retry any missing topic
once, yourself. If it fails again, list it in the report and continue.

## 4. Finish
1. Run `uv run learnkb-check`, then `uv run learnkb-site` (a full build: it starts clean
   and refreshes the home page, navigation and score chips). Fix every `ERROR` and every
   `WARN` about an untested objective or a lesson or quiz file, then build again.
2. Screenshot the home page (`site/index.html`) as the learning-page skill describes, and
   check that every topic shows a lesson and a quiz.
3. Log `uv run learnkb-admin step done "Course built: N topics"`.

## Report
Keep it short:
- documents ingested, and anything from the ingest report worth knowing: contradictions,
  badly parsed content, scanned documents and `[illegible]` passages
- the outline (modules → topics), and that the user can ask to merge, split, rename or
  reorder topics
- topics built: lessons and quizzes written, skipped (already existed) or failed
- gaps in the sources that limited lessons or quizzes, grouped by topic
- how to start: http://localhost:8000 with `learnkb-serve` running (or double-click
  `Start learning.command` / `Start learning.bat`), and suggest the first topic in the
  curriculum
