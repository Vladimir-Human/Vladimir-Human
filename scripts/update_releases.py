#!/usr/bin/env python3
"""Rewrite the block between the RELEASES markers in README.md.

Reads the latest release of each flagship with `gh api` and prints one line per
repository. Run by .github/workflows/releases.yml; safe to run by hand.

START_MODULE_CONTRACT
  PURPOSE: keep the «Свежие релизы» block of the profile README equal to the
           latest GitHub release of every flagship repository.
  SCOPE:   README.md between <!--RELEASES:START--> and <!--RELEASES:END--> only.
  DEPENDS: gh CLI (GH_TOKEN in CI), Python 3.10+ standard library.
  LINKS:   M-RELEASES; R-RELEASES-FRESH, R-RELEASES-SAFE.
END_MODULE_CONTRACT

START_MODULE_MAP
  latest(repo)          -> release dict from `gh api`; LookupError on any failure
  line(repo, rel)       -> one Markdown line: repo, tag link, date in Russian;
                           ValueError on a missing/blank/multiline field or a foreign URL
  main(readme, fetch)   -> 0 when the block is current, 1 when README is left as is
                           (exactly one START line before exactly one END marker)
END_MODULE_MAP
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

OWNER = "Vladimir-Human"
REPOS = ["ru-marketplace-mcp", "humanizer-ru"]
README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!--RELEASES:START-->", "<!--RELEASES:END-->"
BLOCK = re.compile(f"({re.escape(START)}\n).*?({re.escape(END)})", re.S)
FIELDS = ("tag_name", "html_url", "published_at")
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
GH_TIMEOUT_SEC = 60


# START_BLOCK_FETCH
def latest(repo: str) -> dict:
    """Latest release of OWNER/repo; LookupError if gh fails, times out or is missing."""
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{OWNER}/{repo}/releases/latest"],
            capture_output=True, text=True, encoding="utf-8", timeout=GH_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LookupError(f"{repo}: {exc}") from exc
    if proc.returncode != 0:
        raise LookupError(f"{repo}: gh exit {proc.returncode}: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)
# END_BLOCK_FETCH


# START_BLOCK_RENDER
def line(repo: str, rel: dict) -> str:
    """One block line; ValueError when a field is missing, blank, multiline or foreign."""
    for key in FIELDS:
        value = rel.get(key) if isinstance(rel, dict) else None
        if not isinstance(value, str) or not value.strip() or "\n" in value:
            raise ValueError(f"{repo}: bad {key}: {value!r}")
    if not rel["html_url"].startswith(f"https://github.com/{OWNER}/{repo}/releases/tag/"):
        raise ValueError(f"{repo}: html_url is not a release of this repo: {rel['html_url']!r}")
    day = datetime.fromisoformat(rel["published_at"].replace("Z", "+00:00"))
    when = f"{day.day} {MONTHS[day.month - 1]} {day.year}"
    return f"- **{repo}** [{rel['tag_name']}]({rel['html_url']}) · {when}"
# END_BLOCK_RENDER


# START_BLOCK_WRITE
def main(readme: Path = README, fetch: Callable[[str], dict] = latest) -> int:
    """Replace the block only when every repository answered (R-RELEASES-SAFE)."""
    text = readme.read_text(encoding="utf-8")
    starts, ends = text.count(START), text.count(END)
    if starts != 1 or ends != 1 or not BLOCK.search(text):
        print(f"[M-RELEASES][BLOCK_WRITE] fail: expected one START line then one END marker, "
              f"found START x{starts}, END x{ends}; README left as is", file=sys.stderr)
        return 1
    try:
        lines = [line(repo, fetch(repo)) for repo in REPOS]
    except (LookupError, ValueError) as exc:  # KeyError is a LookupError, JSON errors are ValueError
        print(f"[M-RELEASES][BLOCK_FETCH] fail: {exc}; README left as is", file=sys.stderr)
        return 1
    new = BLOCK.sub(lambda m: m.group(1) + "\n".join(lines) + "\n" + m.group(2), text)
    if new != text:
        readme.write_text(new, encoding="utf-8", newline="\n")
    state = "updated" if new != text else "unchanged"
    print(f"[M-RELEASES][BLOCK_WRITE] {state}: " + "; ".join(lines))
    return 0
# END_BLOCK_WRITE


if __name__ == "__main__":
    sys.exit(main())
