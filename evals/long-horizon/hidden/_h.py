"""Drive the ledger only through `python -m tally`, as a user would."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

UNDER_TEST = os.environ["LH_SNAPSHOT"]


class Case(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.dir.cleanup)
        self.file = os.path.join(self.dir.name, "ledger.db")
        self.rates = os.path.join(self.dir.name, "rates.json")
        with open(self.rates, "w", encoding="utf-8") as handle:
            json.dump({"EUR": "1.10", "JPY": "0.0067"}, handle)

    def tally(self, *args, rates=False):
        env = dict(os.environ, PYTHONPATH=UNDER_TEST, PYTHONDONTWRITEBYTECODE="1")
        prefix = ["--file", self.file] + (["--rates", self.rates] if rates else [])
        return subprocess.run(
            [sys.executable, "-m", "tally", *prefix, *args],
            capture_output=True,
            text=True,
            cwd=self.dir.name,
            env=env,
            timeout=20,
        )

    def ok(self, *args, rates=False):
        done = self.tally(*args, rates=rates)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def refused(self, message, *args, rates=False):
        done = self.tally(*args, rates=rates)
        self.assertEqual((done.returncode, done.stderr), (2, f"error: {message}\n"))

    def add(self, day, amount, category, *extra, note=""):
        self.ok("add", "--date", day, "--amount", amount, "--category", category, "--note", note, *extra)

    def seed_format_file(self, rows):
        with open(self.file, "w", encoding="utf-8") as handle:
            json.dump(rows, handle)

    def is_sqlite(self):
        with open(self.file, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
