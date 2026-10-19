"""Serve the learning site on http://localhost:8000 and collect quiz results.

`learnkb-serve` rebuilds site/ and serves it like `python3 -m http.server`, with one
addition: a quiz page posts its results to /api/results, and they're saved as
learner/inbox/<topic>--<attempt>.txt. The text is the same as the "Copy results for
Claude" export, so `/assess` with no arguments can review it without any pasting.
Changing the self-grading ticks after submitting re-posts the same attempt, which
overwrites its file. Opened any other way (file://, http.server), the page falls back to
the copy button.
"""

import argparse
import functools
import json
import re
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from learnkb.learner import LEARNER
from learnkb.site import SITE, build

INBOX = LEARNER / "inbox"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ATTEMPT = re.compile(r"^[0-9T-]{10,25}$")
MAX_BYTES = 256 * 1024


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

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
            print(f"saved {path.relative_to(LEARNER.parent)}: run /assess in Claude Code to review it", flush=True)
        self.reply(200, {"saved": str(path.relative_to(LEARNER.parent))})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--open", action="store_true", help="open the site in a browser")
    parser.add_argument("--no-build", action="store_true", help="serve site/ as it is, without rebuilding")
    args = parser.parse_args()
    if not args.no_build and build() != 0:
        sys.exit(1)
    if not (SITE / "index.html").exists():
        sys.exit("site/ is empty; run `uv run learnkb-site` first")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                     functools.partial(Handler, directory=str(SITE)))
    except OSError as exc:
        sys.exit(f"can't listen on port {args.port} ({exc.strerror}); is another server running? "
                 "Stop it or pass --port")
    server.daemon_threads = True
    url = f"http://localhost:{args.port}"
    print(f"learning site on {url}; quiz results go to learner/inbox/. Ctrl+C to stop", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
