"""Track what the learner knows, topic by topic.

Each graded assessment is saved as a record in learner/assessments/<date>-<topic>.json
(written by the track-knowledge skill). learner/knowledge.json is derived from them: every
record is replayed in date order, so the state is reproducible and a corrected record
just needs a rebuild. learner/knowledge.md is a readable view of the same data.

Per learning objective the state keeps the latest score and level (solid / shaky /
review), a streak of consecutive solid results, and a date after which it's worth
checking again (spaced out further with each solid result). Per topic it keeps the
attempts and the learner's misconceptions, active or resolved.
"""

import argparse
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from learnkb.check import CURRICULUM, NO_KB, Report, load_pages, read_json
from learnkb.ingest import ROOT
from learnkb.site import objectives

LEARNER = ROOT / "learner"
RECORDS = LEARNER / "assessments"
STATE = LEARNER / "knowledge.json"
VIEW = LEARNER / "knowledge.md"
SOLID, SHAKY = 0.8, 0.5
INTERVALS = [3, 7, 21, 60]  # days until a solid objective is re-checked, by streak length
STATUS_ORDER = ["needs review", "in progress", "mastered", "not assessed"]


def level(score: float) -> str:
    return "solid" if score >= SOLID else "shaky" if score >= SHAKY else "review"


def review_after(day: date, lvl: str, streak: int) -> date:
    if lvl == "solid":
        return day + timedelta(days=INTERVALS[min(streak, len(INTERVALS)) - 1])
    return day + timedelta(days=2 if lvl == "shaky" else 0)


# ---------------------------------------------------------------- records


def validate(rec: dict, pages, order: list[str]) -> list[str]:
    errs = []
    slug = rec.get("topic")
    if slug not in order:
        return [f"unknown topic '{slug}'"]
    try:
        date.fromisoformat(str(rec.get("date", "")))
    except ValueError:
        errs.append("'date' must be YYYY-MM-DD")
    if rec.get("source", "quiz") not in ("quiz", "chat"):
        errs.append("'source' must be quiz or chat")
    n = len(objectives(pages[slug]))
    questions = rec.get("questions") or []
    if not questions:
        errs.append("no questions")
    for i, q in enumerate(questions, 1):
        if not isinstance(q.get("objective"), int) or not 1 <= q["objective"] <= n:
            errs.append(f"question {i}: 'objective' must be a number from 1 to {n}")
        score = q.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 1:
            errs.append(f"question {i}: 'score' must be between 0 and 1")
    for m in rec.get("misconceptions") or []:
        if not m.get("id") or not m.get("description"):
            errs.append("each misconception needs 'id' and 'description'")
        if m.get("objective") is not None and not (isinstance(m["objective"], int) and 1 <= m["objective"] <= n):
            errs.append(f"misconception '{m.get('id')}': 'objective' must be a number from 1 to {n}")
        for c in m.get("concepts") or []:
            if c not in pages or pages[c].kind != "concept":
                errs.append(f"misconception '{m.get('id')}': unknown concept '{c}'")
    return errs


def load_records(pages, order) -> tuple[list[tuple[Path, dict]], list[str]]:
    records, errs = [], []
    for path in sorted(RECORDS.glob("*.json")):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errs.append(f"{path.name}: invalid JSON: {exc}")
            continue
        errs += [f"{path.name}: {e}" for e in validate(rec, pages, order)]
        records.append((path, rec))
    records.sort(key=lambda r: (str(r[1].get("date", "")), sequence(r[0], r[1])))
    return records, errs


def sequence(path: Path, rec: dict) -> int:
    """Order of same-day records: <date>-<topic>.json is 1, then -2, -3 for retakes."""
    suffix = path.stem.removeprefix(f"{rec.get('date')}-{rec.get('topic')}").lstrip("-")
    return int(suffix) if suffix.isdigit() else 1


# ---------------------------------------------------------------- state


def apply(topic: dict, rec: dict, texts: list[str], name: str, warnings: list[str]) -> None:
    day = rec["date"]
    by_obj: dict[int, list[float]] = {}
    for q in rec["questions"]:
        by_obj.setdefault(q["objective"], []).append(q["score"])
    for n, scores in sorted(by_obj.items()):
        s = sum(scores) / len(scores)
        lvl = level(s)
        o = topic["objectives"].setdefault(str(n), {"history": [], "streak": 0})
        o["streak"] = o["streak"] + 1 if lvl == "solid" else 0
        o.update(text=texts[n - 1], score=round(s * 100), level=lvl, assessed=day,
                 review_after=review_after(date.fromisoformat(day), lvl, o["streak"]).isoformat())
        o["history"].append({"date": day, "score": round(s * 100)})
    total = sum(q["score"] for q in rec["questions"]) / len(rec["questions"])
    attempt = {"date": day, "record": name, "source": rec.get("source", "quiz"),
               "score": round(total * 100), "objectives": sorted(by_obj)}
    if rec.get("self_score") is not None:
        attempt["self_score"] = rec["self_score"]
    if rec.get("summary"):
        attempt["summary"] = rec["summary"]
    topic["attempts"].append(attempt)

    for m in rec.get("misconceptions") or []:
        cur = topic["misconceptions"].get(m["id"])
        if cur:
            cur.update(description=m["description"], last_seen=day, times=cur["times"] + 1, status="active")
            cur.pop("resolved", None)
            if m.get("evidence"):
                cur["evidence"] = m["evidence"]
        else:
            topic["misconceptions"][m["id"]] = {
                "description": m["description"], "objective": m.get("objective"),
                "concepts": m.get("concepts") or [], "evidence": m.get("evidence", ""),
                "first_seen": day, "last_seen": day, "times": 1, "status": "active"}
    for mid in rec.get("resolved") or []:
        if mid in topic["misconceptions"]:
            topic["misconceptions"][mid].update(status="resolved", resolved=day)
        else:
            warnings.append(f"{name}: resolved misconception '{mid}' was never recorded")


def topic_status(topic: dict, n_objectives: int) -> str:
    objs = topic["objectives"]
    if not objs:
        return "not assessed"
    levels = [o["level"] for o in objs.values()]
    if "review" in levels or any(m["status"] == "active" for m in topic["misconceptions"].values()):
        return "needs review"
    if "shaky" in levels or len(objs) < n_objectives:
        return "in progress"
    return "mastered"


def build_state(pages, curriculum, records, warnings: list[str]) -> dict:
    topics = {}
    for module in curriculum["modules"]:
        for slug in module["topics"]:
            topics[slug] = {"title": pages[slug].meta["title"], "module": module["title"],
                            "objectives": {}, "misconceptions": {}, "attempts": []}
    for path, rec in records:
        slug = rec["topic"]
        apply(topics[slug], rec, objectives(pages[slug]), path.name, warnings)
    for slug, t in topics.items():
        n = len(objectives(pages[slug]))
        t["objective_count"] = n
        t["status"] = topic_status(t, n)
        t["last_assessed"] = t["attempts"][-1]["date"] if t["attempts"] else None
        # Current knowledge, not the last attempt's score: a retake may test only some objectives.
        scores = [o["score"] for o in t["objectives"].values()]
        t["score"] = round(sum(scores) / len(scores)) if scores else None
    dates = [rec["date"] for _, rec in records]
    return {"updated": max(dates) if dates else None,
            "summary": {s: sum(t["status"] == s for t in topics.values()) for s in STATUS_ORDER},
            "topics": topics}


# ---------------------------------------------------------------- view


def due(t: dict, today: date) -> list[str]:
    return [n for n, o in sorted(t["objectives"].items(), key=lambda x: int(x[0]))
            if date.fromisoformat(o["review_after"]) <= today]


def topic_md(slug: str, t: dict, today: date) -> str:
    out = [f"## {t['title']} (`{slug}`)",
           f"**{t['status']}**. Last assessed {t['last_assessed']}, score {t['score']}%, "
           f"{len(t['attempts'])} attempt(s).", "",
           "| # | Objective | Level | Score | Trend | Re-check after |", "|---|---|---|---|---|---|"]
    for n in range(1, t["objective_count"] + 1):
        o = t["objectives"].get(str(n))
        if not o:
            out.append(f"| {n} | (not yet tested) | – | – | – | – |")
            continue
        trend = " → ".join(str(h["score"]) for h in o["history"][-4:])
        when = o["review_after"] + (" **(due)**" if date.fromisoformat(o["review_after"]) <= today else "")
        out.append(f"| {n} | {o['text']} | {o['level']} | {o['score']}% | {trend} | {when} |")
    active = {k: m for k, m in t["misconceptions"].items() if m["status"] == "active"}
    resolved = {k: m for k, m in t["misconceptions"].items() if m["status"] == "resolved"}
    if active:
        out += ["", "**Active misconceptions**"]
        for k, m in active.items():
            obj = f" (objective {m['objective']})" if m.get("objective") else ""
            seen = f", seen {m['times']}×" if m["times"] > 1 else ""
            concepts = f" Review: {', '.join(m['concepts'])}." if m["concepts"] else ""
            out.append(f"- `{k}`{obj}: {m['description']}{seen}.{concepts}")
    if resolved:
        out += ["", "Resolved: " + ", ".join(f"`{k}` ({m['resolved']})" for k, m in resolved.items())]
    return "\n".join(out)


def render_md(state: dict, curriculum: dict, today: date) -> str:
    topics = state["topics"]
    s = state["summary"]
    out = ["# Learner knowledge", "",
           "Generated by `uv run learnkb-learner` from the records in `learner/assessments/`. "
           "Don't edit by hand; fix a record and rebuild instead. Due dates are as of the last rebuild.", "",
           f"{s['mastered']} mastered · {s['in progress']} in progress · {s['needs review']} needs review · "
           f"{s['not assessed']} not assessed", "",
           "| Module | Topic | Status | Score | Last assessed | Due objectives |", "|---|---|---|---|---|---|"]
    for module in curriculum["modules"]:
        for slug in module["topics"]:
            t = topics[slug]
            d = ", ".join(due(t, today)) or "–"
            out.append(f"| {module['title']} | {t['title']} | {t['status']} | "
                       f"{str(t['score']) + '%' if t['score'] is not None else '–'} | "
                       f"{t['last_assessed'] or '–'} | {d if t['attempts'] else '–'} |")
    for slug, t in topics.items():
        if t["attempts"]:
            out += ["", topic_md(slug, t, today)]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- commands


def load_kb():
    report = Report()
    pages = load_pages(report)
    curriculum = read_json(CURRICULUM)
    return pages, curriculum, [t for m in curriculum.get("modules", []) for t in m["topics"]]


def rebuild(pages, curriculum, order) -> dict | None:
    records, errs = load_records(pages, order)
    if errs:
        for e in errs:
            print(f"ERROR  {e}")
        print("knowledge not updated; fix the records above")
        return None
    warnings: list[str] = []
    state = build_state(pages, curriculum, records, warnings)
    for w in warnings:
        print(f"WARN   {w}")
    LEARNER.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    VIEW.write_text(render_md(state, curriculum, date.today()), encoding="utf-8")
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    rec = sub.add_parser("record", help="validate an assessment record, store it, and rebuild")
    rec.add_argument("file", type=Path)
    sub.add_parser("rebuild", help="rebuild knowledge.json and knowledge.md from all records")
    st = sub.add_parser("status", help="print the current state (all topics, or one)")
    st.add_argument("topic", nargs="?")
    args = parser.parse_args()
    if not CURRICULUM.exists():
        sys.exit(NO_KB)
    pages, curriculum, order = load_kb()

    if args.cmd == "record":
        data = json.loads(args.file.read_text(encoding="utf-8"))
        errs = validate(data, pages, order)
        if errs:
            for e in errs:
                print(f"ERROR  {e}")
            sys.exit(1)
        RECORDS.mkdir(parents=True, exist_ok=True)
        if args.file.resolve().parent != RECORDS.resolve():
            base, n = f"{data['date']}-{data['topic']}", 1
            dest = RECORDS / f"{base}.json"
            while dest.exists():
                n += 1
                dest = RECORDS / f"{base}-{n}.json"
            shutil.copy(args.file, dest)
            print(f"stored {dest.relative_to(ROOT)}")
        state = rebuild(pages, curriculum, order)
        if not state:
            sys.exit(1)
        print(topic_md(data["topic"], state["topics"][data["topic"]], date.today()))
    elif args.cmd == "status":
        state = rebuild(pages, curriculum, order)
        if not state:
            sys.exit(1)
        if args.topic:
            if args.topic not in state["topics"]:
                sys.exit(f"unknown topic '{args.topic}'")
            t = state["topics"][args.topic]
            print(topic_md(args.topic, t, date.today()) if t["attempts"] else f"{t['title']}: not assessed yet")
        else:
            print(VIEW.read_text(encoding="utf-8"))
    else:
        if rebuild(pages, curriculum, order):
            print(f"rebuilt {STATE.relative_to(ROOT)} and {VIEW.relative_to(ROOT)}")
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
