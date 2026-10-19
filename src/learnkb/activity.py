"""The build activity log: what the knowledge-base build is doing right now.

Each step (phase, document, reading part, message) is one JSON line in
.learnkb/activity.jsonl, written by `learnkb-ingest` and by the ingest skill through
`learnkb-admin step`. The admin panel shows the latest step live. The log is local
working state, so it's ignored by git.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

ACTIVITY = Path(__file__).resolve().parents[2] / ".learnkb" / "activity.jsonl"
# The ingest procedure in order; the panel draws them as a stepper.
PHASES = ["parse", "transcribe", "read", "source", "concepts", "topics", "curriculum", "check", "done"]


def record(phase: str, message: str = "", doc: str | None = None, part: int | None = None,
           skipped: bool = False) -> None:
    """Log a step. A read step with skipped=True marks a part left unread on purpose (an index, say)."""
    ACTIVITY.parent.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "phase": phase,
             "message": message, "doc": doc, "part": part, "skipped": skipped or None}
    with ACTIVITY.open("a") as f:
        f.write(json.dumps({k: v for k, v in entry.items() if v not in (None, "")}) + "\n")


def recent(limit: int | None = 200) -> list[dict]:
    """The last `limit` steps, or all of them when limit is None."""
    if not ACTIVITY.exists():
        return []
    out = []
    lines = ACTIVITY.read_text().splitlines()
    for line in lines[-limit:] if limit else lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a half-written line; it'll be complete on the next read
    return out
