import sys

# Windows writes piped output (Claude Code reads every command through a pipe) in the
# ANSI code page, which can't encode arrows and fails on many non-English letters. The
# wiki can be in any language, so print UTF-8 everywhere.
for stream in (sys.stdout, sys.stderr):
    if stream and getattr(stream, "encoding", "utf-8").lower().replace("-", "") != "utf8":
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
