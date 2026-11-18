"""Tests for scripts/update_releases.py, derived from R-RELEASES-FRESH and R-RELEASES-SAFE.

START_MODULE_CONTRACT
  PURPOSE: prove that the releases block shows each flagship's own latest release,
           and that any failure leaves README.md byte-for-byte as it was.
  SCOPE:   main() through its public parameters on a temporary README; the network is
           replaced either by a fake fetch or, for the gh boundary, by a fake subprocess.run.
  DEPENDS: unittest (standard library).
  LINKS:   V-M-RELEASES; R-RELEASES-FRESH, R-RELEASES-SAFE.
END_MODULE_CONTRACT
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "update_releases.py"
_spec = importlib.util.spec_from_file_location("update_releases", SCRIPT)
assert _spec is not None and _spec.loader is not None, SCRIPT
ur = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ur)

README_TEXT = (
    "# Профиль\n\n## Свежие релизы\n\n"
    "<!--RELEASES:START-->\n- old line\n<!--RELEASES:END-->\n\n"
    "**Связаться:** текст после блока.\n"
)
BASE = "https://github.com/Vladimir-Human"
RELEASES = {
    "ru-marketplace-mcp": {
        "tag_name": "v2.11.1",
        "html_url": f"{BASE}/ru-marketplace-mcp/releases/tag/v2.11.1",
        "published_at": "2026-11-18T18:23:52Z",
    },
    "humanizer-ru": {
        "tag_name": "v4.0.0",
        "html_url": f"{BASE}/humanizer-ru/releases/tag/v4.0.0",
        "published_at": "2026-03-01T05:00:00Z",
    },
}
ROW_RMM = f"- **ru-marketplace-mcp** [v2.11.1]({BASE}/ru-marketplace-mcp/releases/tag/v2.11.1) · 18 ноября 2026\n"
ROW_HUM = f"- **humanizer-ru** [v4.0.0]({BASE}/humanizer-ru/releases/tag/v4.0.0) · 1 марта 2026\n"


def fetch_from(releases: dict, failing: str | None = None):
    def fetch(repo: str) -> dict:
        if repo == failing:
            raise LookupError(f"{repo}: gh exit 1: HTTP 502")
        return releases[repo]
    return fetch


def expected(rows: str) -> bytes:
    return README_TEXT.replace("- old line\n", rows).encode("utf-8")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.readme = Path(self.dir.name) / "README.md"
        self.write(README_TEXT)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def write(self, text: str) -> None:
        self.readme.write_bytes(text.encode("utf-8"))

    def assert_fails_untouched(self, fetch=None) -> None:
        before = self.readme.read_bytes()
        kwargs = {"readme": self.readme} if fetch is None else {"readme": self.readme, "fetch": fetch}
        self.assertEqual(ur.main(**kwargs), 1)
        self.assertEqual(self.readme.read_bytes(), before)


class FreshBlock(Base):
    # R-RELEASES-FRESH.every-flagship
    def test_each_row_carries_its_own_repo_tag_url_and_date(self) -> None:
        self.assertEqual(ur.main(readme=self.readme, fetch=fetch_from(RELEASES)), 0)
        self.assertEqual(self.readme.read_bytes(), expected(ROW_RMM + ROW_HUM))

    # R-RELEASES-FRESH.every-flagship
    def test_a_new_release_of_one_repo_changes_only_its_row(self) -> None:
        ur.main(readme=self.readme, fetch=fetch_from(RELEASES))
        newer = copy.deepcopy(RELEASES)
        newer["humanizer-ru"].update(tag_name="v4.3.0", html_url=f"{BASE}/humanizer-ru/releases/tag/v4.3.0",
                                     published_at="2026-11-18T04:22:17Z")
        self.assertEqual(ur.main(readme=self.readme, fetch=fetch_from(newer)), 0)
        row = f"- **humanizer-ru** [v4.3.0]({BASE}/humanizer-ru/releases/tag/v4.3.0) · 18 ноября 2026\n"
        self.assertEqual(self.readme.read_bytes(), expected(ROW_RMM + row))


class SafeBlock(Base):
    # R-RELEASES-SAFE.no-partial-block
    def test_one_failed_lookup_leaves_readme_untouched(self) -> None:
        for repo in ur.REPOS:
            with self.subTest(failing=repo):
                self.assert_fails_untouched(fetch_from(RELEASES, failing=repo))

    # R-RELEASES-SAFE.no-partial-block
    def test_each_bad_field_alone_leaves_readme_untouched(self) -> None:
        bad_values = {"missing": ..., "null": None, "blank": " ", "multiline": "x\ny"}
        for repo in ur.REPOS:
            for key in ur.FIELDS:
                for name, value in bad_values.items():
                    with self.subTest(repo=repo, field=key, value=name):
                        broken = copy.deepcopy(RELEASES)
                        if value is ...:
                            del broken[repo][key]
                        else:
                            broken[repo][key] = value
                        self.assert_fails_untouched(fetch_from(broken))
        for name, url in {"other repo": f"{BASE}/humanizer-ru/releases/tag/v2.11.1",
                          "not a release": "https://example.com/v2.11.1"}.items():
            with self.subTest(html_url=name):
                broken = copy.deepcopy(RELEASES)
                broken["ru-marketplace-mcp"]["html_url"] = url
                self.assert_fails_untouched(fetch_from(broken))
        with self.subTest(published_at="not a date"):
            broken = copy.deepcopy(RELEASES)
            broken["humanizer-ru"]["published_at"] = "yesterday"
            self.assert_fails_untouched(fetch_from(broken))

    # R-RELEASES-SAFE.one-block
    def test_anything_but_one_start_line_then_one_end_fails_without_writing(self) -> None:
        start, end = "<!--RELEASES:START-->", "<!--RELEASES:END-->"
        one = f"{start}\n- x\n{end}\n"
        cases = {
            "missing": "# Профиль без блока\n",
            "doubled": one + "\n" + one,
            "nested start": f"{start}\nтекст владельца\n{start}\n- x\n{end}\n",
            "extra end": one + f"\nтекст\n{end}\n",
            "reversed": f"{end}\n- x\n{start}\n",
            "start not on its own line": f"{start} - x\n{end}\n",
        }
        for name, text in cases.items():
            with self.subTest(markers=name):
                self.write(text)
                self.assert_fails_untouched(fetch_from(RELEASES))


class GhBoundary(Base):
    """The real latest() with only subprocess.run replaced."""

    def run_gh(self, side_effect) -> list:
        with mock.patch.object(ur.subprocess, "run", side_effect=side_effect) as run:
            self.result = ur.main(readme=self.readme)
        return run.call_args_list

    # R-RELEASES-FRESH.every-flagship
    def test_gh_answers_are_parsed_into_the_block(self) -> None:
        def answer(cmd, **kwargs):
            repo = cmd[2].split("/")[2]
            return subprocess.CompletedProcess(cmd, 0, json.dumps(RELEASES[repo]), "")
        calls = self.run_gh(answer)
        self.assertEqual(self.result, 0)
        self.assertEqual(self.readme.read_bytes(), expected(ROW_RMM + ROW_HUM))
        self.assertEqual([c.args[0] for c in calls],
                         [["gh", "api", f"repos/Vladimir-Human/{r}/releases/latest"] for r in ur.REPOS])

    # R-RELEASES-SAFE.timeout
    def test_every_gh_call_has_a_60_second_limit_and_a_timeout_fails_safely(self) -> None:
        def hang(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))
        calls = self.run_gh(hang)
        self.assertEqual(self.result, 1)
        self.assertEqual(self.readme.read_bytes(), README_TEXT.encode("utf-8"))
        self.assertTrue(calls)
        for call in calls:
            self.assertEqual(call.kwargs.get("timeout"), 60)

    # R-RELEASES-SAFE.no-partial-block
    def test_gh_error_or_bad_json_from_one_repo_fails_safely(self) -> None:
        for name, (code, out) in {"exit 1": (1, ""), "bad json": (0, "<html>502</html>")}.items():
            for bad_repo in ur.REPOS:
                with self.subTest(case=name, repo=bad_repo):
                    def answer(cmd, **kwargs):
                        repo = cmd[2].split("/")[2]
                        if repo == bad_repo:
                            return subprocess.CompletedProcess(cmd, code, out, "HTTP 502")
                        return subprocess.CompletedProcess(cmd, 0, json.dumps(RELEASES[repo]), "")
                    self.run_gh(answer)
                    self.assertEqual(self.result, 1)
                    self.assertEqual(self.readme.read_bytes(), README_TEXT.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
