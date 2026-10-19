# Learning tool

A reusable harness for learning any subject from a set of PDFs. You ingest the documents into
a wiki, the wiki is rendered as a lesson website, the learner takes quizzes, and their
knowledge is tracked over time.

## Branches
- **`main`** holds only the harness: `.claude/skills/`, `src/learnkb/`, `pyproject.toml`,
  `uv.lock`, `.python-version`, `library/.gitkeep`, `Start learning.command` (macOS) and
  `Start learning.bat` (Windows). It has no subject content: no `kb/`, no
  `learner/`, no PDFs.
- **`learn/<subject>`** (for example `learn/git`) is one branch per subject, branched from main.
  It adds that subject's `library/*.pdf`, `kb/` (wiki, lessons, quizzes) and `learner/`
  (knowledge database).

Rules:
- Make harness changes (skills, scripts, styles) **on main**, then merge main into each
  learning branch with `git switch learn/<subject> && git merge main`. If a harness fix
  happens on a learning branch, commit it separately and cherry-pick it onto main.
- Never commit subject content to main.
- `site/` is generated and ignored. `learnkb-serve` rebuilds it at start; after switching branches
  while it runs, restart it (or run `uv run learnkb-site`).

## Starting a new subject
```bash
git switch main
git switch -c learn/<subject>
# copy the PDFs into library/ (or drop them on the admin panel, http://localhost:8000/admin/)
```
To watch the build live, run `uv run learnkb-serve --open --admin` in another terminal first: the
admin panel shows the progress, and the site at http://localhost:8000 fills in as pages are written.
Then run `/ingest`, `/learning-page all` and `/assess <topic>`, and commit `library/`, `kb/`
and `learner/` on the branch.

## Daily loop
1. Double-click `Start learning.command` (macOS) or `Start learning.bat` (Windows), or run
   `uv run learnkb-serve --open`:
   the site on http://localhost:8000, the admin panel on
   http://localhost:8000/admin/. It rebuilds the site whenever `kb/` changes, so leave it running.
   (Safari blocks pages opened from `file://`.)
2. Learn a topic on the site.
3. `/assess <topic>`, then take the quiz on the site. The page saves the results to
   `learner/inbox/` by itself.
4. Run `/assess` in Claude Code: it reviews the saved results and records them in `learner/`.
   (Without `learnkb-serve`, paste "Copy results for Claude" instead.)
5. Ask "what should I study next?" (the track-knowledge skill).
6. Commit the progress on the learning branch.

## Commands
| Command | Does |
|---|---|
| `uv run learnkb-ingest` | parse new PDFs in `library/` into `kb/raw/` |
| `uv run learnkb-ingest --transcribed DOC \| --ocr-ok DOC` | record the verdict on a scanned document's OCR draft (used by /ingest) |
| `uv run learnkb-check` | validate the wiki and regenerate `kb/index.json` |
| `uv run learnkb-site [topic…]` | render `site/` (a full build when no topics are given) |
| `uv run learnkb-learner [record FILE \| rebuild \| status [topic]]` | the learner knowledge database |
| `uv run learnkb-serve [--open [--admin]] [--port N]` | serve the site on http://localhost:8000 (rebuilt whenever `kb/` changes) and the admin panel on /admin/ (build progress, coverage, health); quiz results are saved to `learner/inbox/` |
| `uv run learnkb-admin [--open]` | the same server, opening the admin panel |
| `uv run learnkb-admin step PHASE [MSG] [--doc D --part N\|N-M] [--skip]` | record a build step for the panel (used by /ingest); `read --skip` marks parts left unread on purpose |
