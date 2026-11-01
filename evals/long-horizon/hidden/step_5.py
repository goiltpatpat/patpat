import os

from _h import Case

ROWS = [
    {"date": "2026-01-05", "amount": "7.00", "category": "food", "note": "old"},
    {"date": "2026-01-03", "amount": "2.00", "category": "fuel", "note": ""},
]


class Storage(Case):
    def test_new_ledger_is_sqlite(self):
        self.add("2026-01-01", "1.00", "a")
        self.assertTrue(self.is_sqlite())
        self.assertEqual(self.ok("total"), "1.00\n")

    def test_original_file_migrates_and_keeps_exact_bytes(self):
        self.seed_format_file(ROWS)
        with open(self.file, "rb") as handle:
            before = handle.read()
        self.assertEqual(self.ok("list").splitlines()[0], "2026-01-03  fuel              2.00")
        self.assertTrue(self.is_sqlite())
        with open(self.file + ".bak", "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_later_runs_leave_backup_alone(self):
        self.seed_format_file(ROWS)
        self.ok("list")
        with open(self.file + ".bak", "rb") as handle:
            before = handle.read()
        self.add("2026-01-06", "1.00", "food")
        self.ok("void", "1")
        with open(self.file + ".bak", "rb") as handle:
            self.assertEqual(handle.read(), before)
        self.assertEqual(self.ok("total"), "3.00\n")

    def test_unrecognized_file_is_untouched(self):
        with open(self.file, "wb") as handle:
            handle.write(b"not a ledger\n")
        self.refused("unrecognized store", "list")
        self.refused("unrecognized store", "add", "--date", "2026-01-01", "--amount", "1", "--category", "a")
        with open(self.file, "rb") as handle:
            self.assertEqual(handle.read(), b"not a ledger\n")
        self.assertFalse(os.path.exists(self.file + ".bak"))

    def test_ids_voids_currency_and_rules_live_in_sqlite(self):
        self.add("2026-01-01", "1.00", "a", "--currency", "EUR")
        self.add("2026-01-02", "2.00", "a")
        self.ok("void", "2")
        self.ok("recur", "add", "--start", "2026-01-15", "--amount", "3.00", "--category", "s")
        self.ok("materialize", "--through", "2026-01-31")
        self.assertTrue(self.is_sqlite())
        self.assertEqual(self.ok("materialize", "--through", "2026-01-31"), "materialized 0\n")
        self.assertEqual(self.ok("total", rates=True), "4.10\n")
        self.assertEqual(self.ok("list", "--all", "--ids").splitlines()[1], "#2  2026-01-02  a                 2.00 [void]")
        self.add("2026-02-01", "1.00", "a")
        self.assertEqual(self.ok("list", "--ids").splitlines()[-1].split()[0], "#4")

    def test_migrated_entries_take_later_features(self):
        self.seed_format_file(ROWS)
        self.ok("void", "1")
        self.ok("recur", "add", "--start", "2026-01-31", "--amount", "1.00", "--category", "s")
        self.ok("materialize", "--through", "2026-02-28")
        self.assertTrue(self.is_sqlite())
        self.assertEqual(
            self.ok("report", "--month", "2026-02"),
            "s                 1.00\nTOTAL             1.00\n",
        )
        self.assertEqual(self.ok("list", "--ids", "--month", "2026-01").splitlines()[0].split()[0], "#2")
