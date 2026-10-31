from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VERIFIER = Path(__file__).resolve().parents[1] / "skills" / "00-workspace-mapper" / "scripts" / "verify_context_graph.py"


class WorkspaceMapperVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="patpat-workspace-map-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self._git("init", "--quiet")
        self._git("config", "user.name", "Patpat Test")
        self._git("config", "user.email", "patpat@example.invalid")
        (self.root / "project.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
        self._git("add", "project.toml")
        self._git("commit", "--quiet", "-m", "fixture")
        (self.root / ".patpat").mkdir()
        self.write_graph()

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def graph(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source": {
                "revision": self._git("rev-parse", "--verify", "HEAD"),
                "worktree": "clean",
                "evidence_paths": ["project.toml"],
            },
            "entities": {
                "entrypoints": [],
                "services": [],
                "databases": [],
                "test_runners": [],
                "build_scripts": [],
            },
            "unknowns": [],
        }

    def write_graph(self, graph: dict[str, object] | None = None, suffix: bytes = b"") -> None:
        payload = json.dumps(graph or self.graph(), separators=(",", ":")).encode("utf-8") + suffix
        (self.root / ".patpat" / "context-graph.json").write_bytes(payload)

    def verify(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--root", str(self.root)],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_clean_snapshot_passes(self) -> None:
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("workspace-map-current: verified", result.stdout)

    def test_verifier_does_not_refresh_git_index(self) -> None:
        source = self.root / "project.toml"
        current = source.stat().st_mtime_ns
        os.utime(source, ns=(current + 5_000_000_000, current + 5_000_000_000))
        index = Path(self._git("rev-parse", "--git-path", "index"))
        if not index.is_absolute():
            index = self.root / index
        before_bytes = index.read_bytes()
        before_mtime = index.stat().st_mtime_ns

        result = self.verify()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(index.read_bytes(), before_bytes)
        self.assertEqual(index.stat().st_mtime_ns, before_mtime)

    def assert_hidden_evidence_change_rejected(self, flag: str, reset_flag: str) -> None:
        self._git("update-index", flag, "project.toml")
        (self.root / "project.toml").write_text("[project]\nname = 'changed'\n", encoding="utf-8")
        result = self.verify()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("assume-unchanged or skip-worktree", result.stderr)
        self._git("update-index", reset_flag, "project.toml")

    def test_skip_worktree_evidence_change_is_stale(self) -> None:
        self.assert_hidden_evidence_change_rejected("--skip-worktree", "--no-skip-worktree")

    def test_assume_unchanged_evidence_change_is_stale(self) -> None:
        self.assert_hidden_evidence_change_rejected(
            "--assume-unchanged", "--no-assume-unchanged"
        )

    @unittest.skipUnless(os.name == "posix", "custom fsmonitor fixture requires a POSIX shell")
    def test_repository_fsmonitor_command_is_not_executed(self) -> None:
        marker = Path(self.temporary.name) / "fsmonitor-ran"
        helper = Path(self.temporary.name) / "fsmonitor.sh"
        helper.write_text(
            "#!/bin/sh\n"
            f"printf invoked > {shlex.quote(str(marker))}\n"
            "printf 'token\\000'\n",
            encoding="utf-8",
        )
        helper.chmod(0o700)
        self._git("config", "core.fsmonitor", str(helper))

        result = self.verify()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(marker.exists(), "verifier invoked target-controlled fsmonitor")

    def test_entity_count_limit_is_enforced(self) -> None:
        graph = self.graph()
        entities = graph["entities"]
        assert isinstance(entities, dict)
        entities["entrypoints"] = [
            {"path": "project.toml", "evidence_path": "project.toml", "evidence": "project.toml:1"}
            for _ in range(41)
        ]
        self.write_graph(graph)

        result = self.verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at most 40 entries", result.stderr)

    def test_graph_byte_limit_is_enforced(self) -> None:
        self.write_graph(suffix=b" " * (32 * 1024))

        result = self.verify()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("32 KiB size limit", result.stderr)

    def test_extract_symbols_self_test(self) -> None:
        script = Path(__file__).resolve().parents[1] / "skills" / "00-workspace-mapper" / "scripts" / "extract_symbols.py"
        result = subprocess.run(
            [sys.executable, str(script), "--self-test"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
