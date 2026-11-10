#!/usr/bin/env python3
"""Rewrite the block between the RELEASES markers in README.md.

Reads the latest release of each flagship with `gh api` and prints one line per
repository. Run by .github/workflows/releases.yml; safe to run by hand.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

OWNER = "Vladimir-Human"
REPOS = ["ru-marketplace-mcp", "humanizer-ru"]
README = Path(__file__).resolve().parent.parent / "README.md"
BLOCK = re.compile(r"(<!--RELEASES:START-->\n).*?(<!--RELEASES:END-->)", re.S)
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def latest(repo: str) -> dict | None:
    proc = subprocess.run(
        ["gh", "api", f"repos/{OWNER}/{repo}/releases/latest"],
        capture_output=True, text=True, encoding="utf-8",
    )
    return json.loads(proc.stdout) if proc.returncode == 0 else None


def line(repo: str, rel: dict) -> str:
    day = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00"))
    when = f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    return f"- **{repo}** [{rel['tag_name']}]({rel['html_url']}) · {when}"


def main() -> None:
    lines = [line(r, rel) for r in REPOS if (rel := latest(r))]
    if not lines:
        return  # keep the old block rather than publish an empty one
    text = README.read_text(encoding="utf-8")
    new = BLOCK.sub(lambda m: m.group(1) + "\n".join(lines) + "\n" + m.group(2), text)
    if new != text:
        README.write_text(new, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
