---
name: assess
description: Assess the learner's knowledge of a knowledge-base topic. Writes a graded quiz (kb/quizzes/<topic>.yaml) tied to the topic's learning objectives and renders it as a page linked from the lesson. When the learner pastes their quiz results, grades their written answers and says what to review. Use when the user wants to be tested, quizzed or assessed on a topic, asks for a quiz or exam, wants to know how well they understand something, or pastes "Assessment results".
---

# Assess

A topic page (built by the learning-page skill) teaches. A quiz page tests what the learner
can do afterwards. `uv run learnkb-site` renders `kb/quizzes/<topic>.yaml` as
`site/quizzes/<topic>.html` and adds a "Test yourself" button to the topic page.

The page grades itself in the browser:
- **Choice questions** are all-or-nothing. After submitting, the learner sees which options
  were right and the `why` for each option they picked, and for every correct option.
- **Open questions** show the model answer and its key `points`. The learner ticks the
  points their answer covered.
- **Results** give a score per learning objective: Solid (80% or more), Shaky (50% or
  more) or Review. Solid objectives are ticked off on the topic page. The page also has a
  **Copy results for Claude** button, which exports every answer as text. When the site is
  served by `uv run learnkb-serve`, the page also saves that text by itself to
  `learner/inbox/<topic>--<attempt>.txt`, so the learner doesn't need to paste it.

So this skill has two modes. Pick one from the arguments.

## Arguments
- A topic slug or title: **write** that topic's quiz (mode A).
- Pasted text starting with `Assessment results:`: **review** it (mode B).
- `all`: write quizzes for every topic that doesn't have one. Ask before overwriting
  existing ones.
- Nothing: if `learner/inbox/` holds result files, **review** them (mode B), oldest first.
  Otherwise list the topics from `kb/curriculum.json`, showing whether each one has a lesson
  and a quiz, and ask which one to assess.

## Mode A: write a quiz

1. **Check the wiki.** Run `uv run learnkb-check`. If it fails, stop and suggest `/lint-kb`.
2. **Read the material.** Read `kb/topics/<slug>.md` and number its learning objectives
   from 1. Read every concept page in its `concepts` list, and `kb/lessons/<slug>.yaml` if
   it exists. Open the cited sections in `kb/raw/` when you need exact commands or output,
   and check `kb/raw/<doc>.outline.md` for conversion losses near them.
3. **Plan the coverage.** Write 8–12 questions in total, with 1–3 per objective. Give more
   questions to objectives the topic's *Common pitfalls* section touches.

   Order the questions from recall up to application. Make about a quarter of them `open`.

   If `uv run learnkb-learner status <slug>` shows earlier attempts, aim at the learner's
   gaps. Make sure each active misconception is tested by at least one question in a new
   situation, so the next record can resolve it or confirm it.
4. **Don't repeat the lesson.** The `checks` in the lesson file are already on the topic
   page with their answers. Don't reuse them or reword them slightly. Test the same idea in
   a new situation instead.
5. **Write `kb/quizzes/<slug>.yaml`** in the format below.
6. **Render.** Run `uv run learnkb-site <slug>`, then `uv run learnkb-site` once so the home
   page shows the score chip. Fix every `ERROR`. A `WARN` about an untested objective
   means a question is missing, so add one.
7. **Look at it.** Take a screenshot to check the layout:
   ```bash
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
     --screenshot=<scratchpad>/quiz-<slug>.png --window-size=1280,4000 \
     "file://$PWD/site/quizzes/<slug>.html"
   ```
   On Windows, Chrome is `"C:/Program Files/Google/Chrome/Application/chrome.exe"`.
   Read the PNG. Look for overflowing code, very long options, and options whose length
   gives the answer away.
8. **Report.** Give the path `site/quizzes/<slug>.html` and offer to open it with
   http://localhost:8000/quizzes/<slug>.html (with `learnkb-serve` running). Tell the learner that after the quiz they can paste
   their copied results back into `/assess` for feedback.

## Mode B: review pasted results

The results come pasted, or as files in `learner/inbox/` (one per attempt; a later save of
the same attempt has overwritten the earlier one, so each file is final). The text lists the score, each objective's status and every question: what the
learner chose, or what they wrote and which key points they ticked.

1. Read `kb/quizzes/<slug>.yaml`, the topic page and the relevant concept pages. Grade
   against those, not against outside knowledge.
2. **Re-grade the open answers.** Learners often mark themselves too high or too low, or
   skip it: an answer marked "Not graded yet" was left out of the page's score, so the
   pasted score and objective statuses are only provisional.
   Compare each written answer with the model answer and its points. Say which points it
   really covers, and quote the learner's own words when a point is missing or wrong.
3. **Diagnose, don't just list.** Group the mistakes into misconceptions, for example
   "treats staging as automatic". Tie each one to the objective it breaks, and use the `why`
   of the option the learner picked.
4. **Prescribe review.** For each weak objective, point to the exact place to revisit:
   the topic page section (`site/topics/<slug>.html#walkthrough`), the lesson step or the
   concept page (`site/concepts/<concept>.html`). Explain the misconception again briefly,
   in different words from the page.
5. **Probe if useful.** If an answer is ambiguous, for example right but for an unclear
   reason, ask one or two follow-up questions in chat before you conclude.
6. **Recommend next steps.** Either move on to the next topic in the curriculum, or
   revisit specific sections and retake the quiz. The page reshuffles the options on
   every attempt.
7. **Record it.** Save your re-graded result to the learner's knowledge database by
   following `.claude/skills/track-knowledge/SKILL.md`, and mention it in one line of the
   review. Once it's recorded, delete the inbox file it came from: the record keeps the
   text in `raw`.

Keep the review short: an overall verdict, then misconceptions with links to review, then
the next step. Don't repeat questions the learner got right unless their reasoning was
shaky.

## Content rules
- **Language.** Write questions, options and answers in the wiki's language (`lang` in
  `kb/site.json`, English if absent). Keep the YAML keys in English. Pasted results always
  arrive in English labels (`Assessment results:`, `Solid`, `Shaky`, `Review`), whatever the
  site's language.
- **Grounded.** Every correct answer, `why` and model answer must come from the wiki or the
  cited raw sections. Don't test commands, flags or behaviour the sources don't describe.
- **Test understanding, not wording.** Prefer prediction ("What happens if…"), diagnosis
  ("Your colleague sees… why?") and choice of approach ("Which command…") over recalling
  definitions. Use at most two pure-recall questions per quiz.
- **Plausible distractors.** Each wrong option should be a real misconception, ideally one
  from *Common pitfalls* or a `> Note:` on a concept page. Every wrong option needs a `why`
  that corrects that specific misconception. Avoid "all of the above" and joke options.
  Keep the options a similar length, because the longest option shouldn't give the
  answer away.
- **No giveaways.** Don't use `[[links]]` in `q` or option `text`, because their hover
  tooltips reveal definitions. Use links freely in `why`, `explain`, `answer` and `points`,
  where they lead the learner to review material.
- **Open questions** ask the learner to explain why, compare two things, or describe the
  steps to fix a situation. Give 2–4 `points`. Each point is one checkable idea that a
  learner can honestly tick or not tick.
- **Multiple correct options** turn the question into "select all that apply". Use this
  sparingly, because the question is graded all-or-nothing.
- Address the learner as "you". Keep questions short. Put illustrative commands or output
  in fenced code blocks inside `q`.

## Quiz format: `kb/quizzes/<slug>.yaml`

```yaml
topic: the-commit-cycle          # must match the file name
intro: |                         # optional; replaces the default lead sentence
  Ten questions on the commit cycle. Answer from memory first.

questions:
  - objective: 5                 # 1-based index into the topic's learning objectives
    q: You run `git add clean.py`, then edit `clean.py` again and run `git commit`. What is committed?
    options:                     # type defaults to choice; the page shuffles the options
      - text: The version of `clean.py` from when you ran `git add`
        correct: true
        why: Staging captures the file as it was at that moment ([[staging-area]]).
      - text: The latest version on disk, including the new edit
        why: Git doesn't re-read the file at commit time. Only staged content is committed.
      - text: Nothing, because Git refuses to commit a file that changed after staging
        why: Git commits what's staged without complaint. `git status` would list the file under both staged and unstaged changes.
    explain: |                   # optional; shown after submitting, for any outcome
      Run `git add clean.py` again to include the new edit.

  - objective: 3
    type: open
    q: Describe the three places a change can be in Git, and how a change moves between them.
    answer: |                    # model answer, markdown
      A change starts in the [[working-directory]]. `git add` copies it to the
      [[staging-area]], and `git commit` records everything staged as a [[commit]].
    points:                      # 2–4 rubric points the learner ticks
      - Names the working directory, the staging area and the commit history
      - "`git add` moves a change from the working directory to the staging area"
      - "`git commit` records the staged changes permanently"
```

**YAML gotchas:**
- A one-line value that contains `": "`, or that starts with a backtick, `[`, `{`, `*`, `@`
  or `?`, must be double-quoted or written as a `|` block, or the build fails.
- Bare `yes`, `no`, `on`, `off` and numbers become booleans or numbers. Quote option
  text like `"No"`.
