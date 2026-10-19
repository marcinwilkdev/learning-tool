"""Serve the learning site and the admin panel on http://localhost:8000.

`learnkb-serve` is the one server to run while building or learning:

- `/` is the learning site from site/. It's rebuilt at start and again whenever kb/
  changes, so lessons and quizzes appear as they're written. A build that fails (a
  half-written page mid-ingest, say) keeps the last good site.
- `/admin/` is the admin panel (see admin.py): build progress, coverage and health, live.
- `/api/results` takes a quiz page's results and saves them as
  learner/inbox/<topic>--<attempt>.txt, the same text as the "Copy results for Claude"
  export, so `/assess` with no arguments can review them without any pasting. Changing
  the self-grading ticks after submitting re-posts the same attempt, which overwrites its
  file. Opened any other way (file://, http.server), the page falls back to the copy button.
"""

import argparse
import contextlib
import functools
import io
import json
import re
import sys
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from learnkb import admin
from learnkb.learner import LEARNER
from learnkb.site import SITE, build

INBOX = LEARNER / "inbox"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ATTEMPT = re.compile(r"^[0-9T-]{10,25}$")
MAX_BYTES = 256 * 1024
QUIET = 1.5  # seconds without changes before the site is rebuilt

NO_SITE = b"""<!doctype html><html><head><meta charset="utf-8"><title>No site yet</title>
<style>body{font:16px system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem;line-height:1.5}</style>
</head><body><h1>No learning site yet</h1>
<p>The site is built from <code>kb/</code> as soon as it holds a valid wiki: run <code>/ingest</code>
in Claude Code and this page will turn into the site. Meanwhile, watch the build in the
<a href="/admin/">admin panel</a>.</p></body></html>"""


def say(message: str) -> None:
    # Straight to the terminal: a rebuild in another thread may be redirecting stdout.
    print(message, file=sys.__stdout__, flush=True)


def quiet_build() -> tuple[int, str]:
    """Build the site, returning the exit code and the last line it printed."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = build()
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith("ERROR")]
    return code, (f"{len(errors)} error(s), e.g. {errors[0][7:]}" if errors else lines[-1] if lines else "")


class Rebuilder(threading.Thread):
    """Rebuild the site once kb/ has been quiet for a moment after a change."""

    def __init__(self):
        super().__init__(daemon=True)
        self.wake = threading.Event()

    def poke(self) -> None:
        self.wake.set()

    def run(self) -> None:
        while True:
            self.wake.wait()
            while self.wake.wait(timeout=QUIET):  # changes still coming: keep waiting
                self.wake.clear()
            code, last = quiet_build()
            say(f"site rebuilt: {last}" if code == 0 else f"site not rebuilt ({last}); keeping the last good one")


def handler(watcher: admin.Watcher):
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/admin":
                self.send_response(301)
                self.send_header("Location", "/admin/")
                self.end_headers()
            elif path.startswith("/admin/"):
                admin.handle_get(self, path[len("/admin/"):], watcher)
            elif path in ("/", "/index.html") and not (SITE / "index.html").exists():
                admin.send(self, NO_SITE, "text/html; charset=utf-8")
            else:
                super().do_GET()

        def reply(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/api/results":
                return self.reply(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BYTES:
                return self.reply(413, {"error": "empty or too large"})
            try:
                data = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return self.reply(400, {"error": "invalid JSON"})
            topic, attempt, text = data.get("topic", ""), data.get("attempt", ""), data.get("text", "")
            if not (SLUG.match(topic) and ATTEMPT.match(attempt)
                    and isinstance(text, str) and text.startswith("Assessment results:")):
                return self.reply(400, {"error": "expected topic, attempt and an Assessment results text"})
            INBOX.mkdir(parents=True, exist_ok=True)
            path = INBOX / f"{topic}--{attempt}.txt"
            new = not path.exists()
            path.write_text(text + "\n")
            if new:
                say(f"saved {path.relative_to(LEARNER.parent)}: run /assess in Claude Code to review it")
            self.reply(200, {"saved": str(path.relative_to(LEARNER.parent))})

    return Handler


def run(port: int = 8000, open_path: str | None = None, rebuild: bool = True) -> None:
    if rebuild:
        code, last = quiet_build()
        say(f"site built: {last}" if code == 0 else f"site not built yet ({last})")
    watcher = admin.Watcher()
    if rebuild:
        rebuilder = Rebuilder()
        rebuilder.start()
        watcher.on_change.append(rebuilder.poke)
    watcher.start()
    SITE.mkdir(exist_ok=True)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(handler(watcher), directory=str(SITE)))
    except OSError as exc:
        sys.exit(f"can't listen on port {port} ({exc.strerror}); is another server running? "
                 "Stop it or pass --port")
    server.daemon_threads = True
    url = f"http://localhost:{port}/"
    say(f"learning site on {url}, admin panel on {url}admin/; quiz results go to learner/inbox/. Ctrl+C to stop")
    if open_path is not None:
        webbrowser.open(url + open_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="open the site in a browser")
    parser.add_argument("--admin", action="store_true", help="with --open: open the admin panel instead")
    parser.add_argument("--no-build", action="store_true", help="serve site/ as it is: don't build or rebuild it")
    args = parser.parse_args()
    run(args.port, ("admin/" if args.admin else "") if args.open else None, rebuild=not args.no_build)


if __name__ == "__main__":
    main()
