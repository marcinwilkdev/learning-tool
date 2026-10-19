#!/bin/bash
# Double-click in Finder to serve the learning site and the admin panel
# (uv run learnkb-serve) and open http://localhost:8000. Close the window, or press
# Ctrl+C, to stop the server.

cd "$(dirname "$0")" || exit 1
PORT=8000

fail() {
  echo
  echo "$1"
  echo
  read -r -n 1 -p "Press any key to close this window."
  exit 1
}

# Already running (another window, or started from a terminal): just open it.
if curl -sf -o /dev/null -I "http://localhost:$PORT/admin/"; then
  echo "The learning site is already running; opening it."
  open "http://localhost:$PORT/"
  exit 0
fi

# Finder doesn't load the shell profile, so look where uv usually lives too.
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
command -v uv >/dev/null || fail "uv isn't installed. Install it (https://docs.astral.sh/uv/) and try again."

branch=$(git branch --show-current 2>/dev/null)
echo "Learning tool${branch:+ on branch $branch}"
case "$branch" in
  learn/*) ;;
  *) echo "(No subject here: switch to a learn/<subject> branch to see its site.)" ;;
esac
echo

uv run learnkb-serve --open --port "$PORT" || fail "The server stopped with an error (see above)."
