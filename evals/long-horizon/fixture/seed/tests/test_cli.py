import os
import subprocess
import sys
import tempfile
import unittest


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.file = os.path.join(self.dir.name, "ledger.json")

    def tally(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "tally", "--file", self.file, *args],
            capture_output=True,
            text=True,
        )

    def add(self, day, amount, category, note=""):
        done = self.tally("add", "--date", day, "--amount", amount, "--category", category, "--note", note)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_list_shows_added_entry(self):
        self.add("2026-01-05", "12.5", "food", "lunch")
        self.assertEqual(self.tally("list").stdout, "2026-01-05  food             12.50  lunch\n")

    def test_total_is_exact(self):
        self.add("2026-01-05", "0.10", "food")
        self.add("2026-01-06", "0.20", "food")
        self.assertEqual(self.tally("total").stdout, "0.30\n")

    def test_bad_amount_is_rejected(self):
        done = self.tally("add", "--date", "2026-01-05", "--amount", "-1", "--category", "food")
        self.assertEqual(done.returncode, 2)
        self.assertEqual(done.stderr, "error: invalid amount\n")
        self.assertEqual(self.tally("list").stdout, "")


if __name__ == "__main__":
    unittest.main()
