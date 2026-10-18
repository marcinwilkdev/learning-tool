# Learning tool

A reusable harness for learning any subject from a set of PDFs. You ingest the documents into
a wiki, the wiki is rendered as a lesson website, the learner takes quizzes, and their
knowledge is tracked over time.

## Branches
- **`main`** holds only the harness: `.claude/skills/`, `src/learnkb/`, `pyproject.toml`,
  `uv.lock`, `.python-version`, `library/.gitkeep`. It has no subject content: no `kb/`, no
  `learner/`, no PDFs.
- **`learn/<subject>`** (for example `learn/git`) is one branch per subject, branched from main.
  It adds that subject's `library/*.pdf`, `kb/` (wiki, lessons, quizzes) and `learner/`
  (knowledge database).

Rules:
- Make harness changes (skills, scripts, styles) **on main**, then merge main into each
  learning branch with `git switch learn/<subject> && git merge main`. If a harness fix
  happens on a learning branch, commit it separately and cherry-pick it onto main.
- Never commit subject content to main.
- `site/` is generated and ignored. After switching branches, run `uv run learnkb-site`.

## Starting a new subject
```bash
git switch main
git switch -c learn/<subject>
# copy the PDFs into library/
```
To watch the build live, run `uv run learnkb-admin --open` in another terminal first.
Then run `/ingest`, `/learning-page all` and `/assess <topic>`, and commit `library/`, `kb/`
and `learner/` on the branch.

## Daily loop
1. `uv run learnkb-site`, then `python3 -m http.server 8000 -d site` and open
   http://localhost:8000. Safari blocks pages opened from `file://`.
2. Learn a topic on the site.
3. `/assess <topic>`, then take the quiz on the site.
4. Paste "Copy results for Claude" into Claude Code. It's reviewed and recorded in `learner/`.
5. Ask "what should I study next?" (the track-knowledge skill).
6. Commit the progress on the learning branch.

## Commands
| Command | Does |
|---|---|
| `uv run learnkb-ingest` | parse new PDFs in `library/` into `kb/raw/` |
| `uv run learnkb-check` | validate the wiki and regenerate `kb/index.json` |
| `uv run learnkb-site [topic…]` | render `site/` (a full build when no topics are given) |
| `uv run learnkb-learner [record FILE \| rebuild \| status [topic]]` | the learner knowledge database |
| `uv run learnkb-admin [--open]` | live admin panel on http://localhost:8001: build progress, coverage, health |
| `uv run learnkb-admin step PHASE [MSG] [--doc D --part N]` | record a build step for the panel (used by /ingest) |
