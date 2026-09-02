"""Stop hook: write Claude's final response text to stuff.txt at the project root.

Reads the hook payload (JSON on stdin), walks the session transcript, and dumps
the text of the last assistant turn to <project>/stuff.txt so it can be opened
and read directly with a screen reader instead of hunting through the terminal.

The text is lightly reformatted for screen-reader comfort on the way out: bold
markers (**) are stripped, and hyphen bullet markers are swapped for asterisks.
Fenced code blocks are left exactly as written.
"""
import json
import os
import re
import sys


def _screen_reader_friendly(text: str) -> str:
    """Strip ** bold markers and turn '- ' bullets into '* ' bullets, outside
    of fenced code blocks."""
    out = []
    in_fence = False
    fence_re = re.compile(r"^\s*(```|~~~)")
    bullet_re = re.compile(r"^(\s*)-(\s+)")
    for line in text.split("\n"):
        if fence_re.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        line = bullet_re.sub(r"\1*\2", line)
        line = line.replace("**", "")
        out.append(line)
    return "\n".join(out)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0

    project_dir = payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    out_path = os.path.join(project_dir, "stuff.txt")

    try:
        raw_lines = open(transcript_path, encoding="utf-8").read().splitlines()
    except Exception:
        return 0

    records = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except Exception:
            continue

    # Find the last genuine user prompt (not a tool_result), skipping sidechains.
    last_user = -1
    for i, rec in enumerate(records):
        if rec.get("type") != "user" or rec.get("isSidechain"):
            continue
        content = rec.get("message", {}).get("content")
        if isinstance(content, str):
            last_user = i
        elif isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "text" for b in content
        ):
            last_user = i

    # Collect assistant text blocks emitted after that prompt.
    chunks = []
    for rec in records[last_user + 1:]:
        if rec.get("type") != "assistant" or rec.get("isSidechain"):
            continue
        content = rec.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if text:
                    chunks.append(text)

    final_text = "\n\n".join(chunks).strip()
    if not final_text:
        return 0

    final_text = _screen_reader_friendly(final_text)

    try:
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(final_text + "\n")
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
