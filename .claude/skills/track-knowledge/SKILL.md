---
name: track-knowledge
description: Record what the learner knows in the on-disk knowledge database (learner/knowledge.json), from quiz results or evidence gathered in chat, and report their current state across all topics. Use after reviewing pasted "Assessment results", when the user asks to save, record or update their progress or knowledge, or asks what they know, what to review or where they stand.
---

# Track knowledge

`learner/` holds the learner's knowledge database. It sits next to `kb/`, which holds the
material.

```
learner/assessments/<date>-<topic>.json   one record per graded assessment (the evidence)
learner/knowledge.json                    current state of every curriculum topic (derived)
learner/knowledge.md                      readable view of the same (derived)
```

Records are the source of truth. `uv run learnkb-learner` rebuilds the two derived files
from scratch by replaying every record in date order. Never edit `knowledge.json` or
`knowledge.md` by hand. To correct something, fix the record and run `uv run learnkb-learner rebuild`.

How the script turns records into state:
- **Objective level** comes from the mean question score in the *latest* record that tests
  that objective: solid (80% or more), shaky (50% or more) or review. Objectives that a record
  doesn't test keep their earlier state.
- **Re-check dates**: a review objective is due at once, and a shaky one after 2 days. A solid
  one waits 3, 7, 21 and then 60 days as its streak of consecutive solid results grows.
- **Misconceptions** are keyed by `id` within a topic. Reporting the same `id` again makes it
  recur (`times` goes up). Listing it in `resolved` closes it.
- **Topic status**: *needs review* if any objective is at review level or any misconception
  is active. *In progress* if any objective is shaky or untested. *Mastered* if every
  objective is solid. Otherwise *not assessed*.

## Arguments
- Pasted `Assessment results:` text, or nothing right after an `/assess` review: record it.
- `status` or a topic: show the current state (`uv run learnkb-learner status [topic]`) and
  recommend what to do next.

## Recording an assessment

1. **Get honest scores.** If you already reviewed these results in this conversation (the
   assess skill, mode B), reuse those grades exactly. Otherwise grade them now, following
   *Mode B* in `.claude/skills/assess/SKILL.md`. Never record the learner's own ticks as the
   score of an open question: the learner may have skipped grading or been generous.
   - Choice question: 1 if correct, otherwise 0.
   - Open question: the share of its `points` the answer really covers. A half-covered point
     counts 0.5.
   - Get each question's objective from the export (`[objective N, …]`) or from
     `kb/quizzes/<slug>.yaml`.
2. **Read the current state.** Run `uv run learnkb-learner status <slug>` and look at the
   topic's active misconceptions.
   - When a mistake matches one that's already recorded, **reuse its `id`**, so it's counted
     as recurring instead of duplicated.
   - Put an active misconception in `resolved` only if this attempt shows it's fixed. That
     means a question on it answered correctly *with sound reasoning*. Leave it active if
     nothing in this attempt tested it.
3. **Name the misconceptions.** Record one entry for each distinct wrong mental model, not one
   for each wrong question. Use a short kebab-case `id` that states the error, such as
   `stash-as-queue` or `merge-direction`. Don't record slips that the learner clearly got right
   elsewhere as misconceptions. Mention them in `summary` instead.
4. **Write the record** to a file in your scratchpad (`learner/assessments/` may not exist
   yet), then run `uv run learnkb-learner record <that file>`. It validates the record,
   stores it as `learner/assessments/<date>-<topic>.json` (adding `-2`, `-3` for a retake on
   the same day), rebuilds the state and prints the topic. Fix any `ERROR` and run it again.
   To correct a stored record, edit it in place and run `uv run learnkb-learner rebuild`.
5. **Report** briefly:
   - what changed, such as objective levels before → after and misconceptions added or
     resolved
   - the topic's new status and when it's due for a re-check
   - one recommended next step

   Point to `learner/knowledge.md` for the full picture.

### Evidence from chat
When the learner answers follow-up questions in chat, for example probes from an
assessment review, record those answers as a separate record with `"source": "chat"`. Give
each probe one entry in `questions`, scored the same way. Record only evidence you actually
saw. Never infer knowledge of an objective that nothing tested.

## Record format

```json
{
  "topic": "branches-and-merging",
  "date": "2026-10-16",
  "source": "quiz",
  "self_score": 64,
  "summary": "Merge direction understood; Q6 wrote checkout for merge (slip). Stash order reversed; out-of-sync seen as 'behind'.",
  "questions": [
    {"n": 1, "objective": 1, "type": "choice", "score": 1},
    {"n": 2, "objective": 1, "type": "open", "score": 0.5, "note": "Manual extraction yes; no automatic merge, no disk space"}
  ],
  "misconceptions": [
    {"id": "stash-as-queue", "objective": 4, "concepts": ["git-stash"],
     "description": "Thinks stash removes the oldest entry first (queue), not the newest (stack)",
     "evidence": "Q8: after A, B, C then drop, chose 'B and C'"}
  ],
  "resolved": [],
  "raw": "Assessment results: Branches and merging …"
}
```

- `score` is from 0 to 1. `self_score` is the page's percentage, kept so you can compare.
- `objective` numbers are 1-based, as on the topic page. `concepts` must be concept slugs from
  `kb/concepts/`.
- `raw` holds the pasted export unchanged, so the record can be re-graded later.

## Showing the state
For "what do I know?" or "what should I study?", run `uv run learnkb-learner status`. It
covers every topic in the curriculum. Then recommend next steps, in this order:
1. objectives that are due for a re-check
2. topics that need review, especially ones with recurring misconceptions (`times` above 1)
3. the next topic in the curriculum that isn't assessed yet

Link the review material, such as `site/topics/<slug>.html` and `site/concepts/<concept>.html`.
