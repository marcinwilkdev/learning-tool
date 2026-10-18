---
name: learning-page
description: Build an engaging learning web page for a knowledge-base topic by writing its lesson file (hook, diagram, step-by-step walkthrough, self-check questions) and rendering the site. Use when the user wants to learn a topic, asks for a page, lesson or website for a topic, or wants the learning site built or refreshed.
---

# Learning page

The site under `site/` is rendered from the wiki in `kb/` by `uv run learnkb-site`.
A topic page always shows the topic's own content:
- learning objectives (as a checklist)
- overview, walkthrough, pitfalls and summary
- concept flashcards
- progress tracking

Your job is the **lesson layer**: `kb/lessons/<topic>.yaml`. It turns a reference page
into a guided lesson. The generator places each piece into the page.

## Arguments
- A topic slug or title: build that topic's lesson.
- `all`: every topic without a lesson file. Ask before overwriting existing ones.
- Nothing: list topics from `kb/curriculum.json` with whether each has a lesson,
  and ask which to build.

## Procedure

1. **Check the wiki.** Run `uv run learnkb-check`. If it fails, stop and suggest
   `/lint-kb`. The page can't be built from a broken wiki.
2. **Read the material.** Read `kb/topics/<slug>.md`, every concept page in its
   `concepts` list, and its prerequisite topics' summaries. Open the cited sections
   in `kb/raw/` when you need exact commands or output.
3. **Design the lesson.** Ask yourself:
   - What concrete situation makes this topic matter to a learner? That's the hook.
   - Is there a process or pipeline with stages? That's the flow diagram. Skip it if
     the topic isn't a sequence.
   - What hands-on sequence lets the learner *see* the ideas work? That's the
     step-through. Each step should show one idea and build on the previous one.
   - What would show the learner they've met each learning objective? That's the
     self-check.
4. **Write `kb/lessons/<slug>.yaml`** using the format below.
5. **Render.** Run `uv run learnkb-site <slug>` (any lesson errors are reported),
   then `uv run learnkb-site` once to refresh progress counts and navigation.
6. **Look at it.** Screenshot the page to check the layout:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
     --screenshot=<scratchpad>/<slug>.png --window-size=1280,3000 \
     "file://$PWD/site/topics/<slug>.html"
   ```
   Read the PNG. Look for broken layout, overflowing terminals, empty sections, and
   steps that are too long to read comfortably. Fix them, then re-render.
7. **Report.** Give the path `site/topics/<slug>.html`, and offer to open it
   (`uv run learnkb-site <slug> --open`). Mention any gaps in the sources that
   limited the lesson. If the topic has no quiz yet (`kb/quizzes/<slug>.yaml`), offer
   `/assess <slug>` so the learner can test themselves afterwards.

## Content rules
- **Grounded.** Every fact must come from the wiki or the cited raw sections.
  Don't add commands, flags or behaviour the sources don't describe.
- **Terminal output.** Use output from the sources when they show it (reformatted
  so it's readable). When they don't, leave `output` out. Never invent output.
  Illustrative file names and messages in commands are fine.
- **Voice.** Address the learner as "you". Keep sentences short, introduce one new
  idea per step, and explain *why* as well as *what*.
- **Links.** Link concepts in `explain`, `note`, `a` and `hook` with `[[slug]]`. On
  hover the page shows each concept's definition.
- **Doesn't duplicate the topic.** The walkthrough section already tells the story.
  The step-through is the hands-on version of it.

## Lesson format: `kb/lessons/<slug>.yaml`

```yaml
topic: the-commit-cycle          # must match the file name

hook: |                          # 2–4 sentences: a relatable problem, in the second person
  It's the night before your deadline and the script that worked yesterday is broken.
  Which of `analysis_02.sh` and `analysis_final_v3.sh` produced your figure?

flow:                            # optional; shown after Overview. 2–5 nodes
  nodes:
    - {label: Working directory, note: "where you edit"}
    - {label: Staging area, note: "what goes in the next commit"}
    - {label: Repository, note: "permanent snapshots"}
  arrows: ["git add", "git commit"]   # one label per gap between nodes
  loop: "Edit again and repeat"       # optional line under the diagram
  caption: "How a change travels into history."

walkthrough:                     # optional; shown after Walkthrough. 4–8 steps
  title: Your first commits, step by step
  intro: Follow along in an empty folder.
  steps:
    - title: Create the repository
      command: |                 # one command per line; omit for a thinking-only step
        cd ~/thesis
        git init
      output: |                  # only if the sources show it
        Initialized empty Git repository in ~/thesis/.git/
      explain: |                 # markdown, 1–3 short paragraphs
        [[git-init]] creates a hidden `.git` folder. That's where the history will live.

checks:                          # 4–6 questions covering the learning objectives
  - q: You edited a file after running `git add`. What gets committed?
    a: |
      The version from when you ran `git add`. Staging captures the file *as it was then*,
      so stage it again to include the new edits.
```

**YAML gotchas** (each of these broke a build before):
- A one-line value that contains `": "` (such as a question with a colon), or that starts
  with a backtick, `[`, `{`, `*`, `@` or `?`, must be double-quoted or written as a `|` block.
- Inside `{...}` and `[...]`, double-quote any value containing `?`, `:`, `@`, `{`, `}` or a
  comma: `- {label: "Where is it?", note: "git grep"}`.
- If the first line of a `|` block starts with spaces, as terminal output often does
  (` M README`), write `|2` so YAML takes the indent from the key, not from that line.
- Bare `<placeholders>` in prose are fine (the renderer escapes them); in commands, use
  the `command` field or backticks as usual.

### Writing good checks
- Mix question types: recall ("What does…"), prediction ("What happens if…"),
  diagnosis ("Your colleague sees… why?") and choice ("Which command…").
- Each answer explains the reason, not just the fact.
- Together the checks should cover every learning objective at least once.
