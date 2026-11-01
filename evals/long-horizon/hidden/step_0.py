from _h import Case


class Seed(Case):
    def test_add_prints_added_and_list_normalizes_amount(self):
        self.assertEqual(self.ok("add", "--date", "2026-01-05", "--amount", "5", "--category", "food"), "added\n")
        self.assertEqual(self.ok("list"), "2026-01-05  food              5.00\n")

    def test_list_includes_note(self):
        self.add("2026-01-05", "12.50", "food", note="lunch out")
        self.assertEqual(self.ok("list"), "2026-01-05  food             12.50  lunch out\n")

    def test_list_sorts_by_date_keeping_insertion_order(self):
        self.add("2026-02-01", "1.00", "b")
        self.add("2026-01-01", "2.00", "a")
        self.add("2026-02-01", "3.00", "a")
        self.assertEqual([row.split()[2] for row in self.ok("list").splitlines()], ["2.00", "1.00", "3.00"])

    def test_list_and_total_filter_by_category(self):
        self.add("2026-01-01", "1.25", "a")
        self.add("2026-01-02", "2.50", "b")
        self.assertEqual(self.ok("list", "--category", "b"), "2026-01-02  b                 2.50\n")
        self.assertEqual(self.ok("total", "--category", "a"), "1.25\n")

    def test_total_is_exact_decimal(self):
        for amount in ("0.10", "0.20", "1.15"):
            self.add("2026-01-01", amount, "a")
        self.assertEqual(self.ok("total"), "1.45\n")

    def test_invalid_amounts_change_nothing(self):
        for bad in ("-1", "0", "abc", "1.234", "NaN"):
            self.refused("invalid amount", "add", "--date", "2026-01-01", "--amount", bad, "--category", "a")
        self.assertEqual(self.ok("total"), "0.00\n")

    def test_invalid_date(self):
        self.refused("invalid date", "add", "--date", "2026-02-30", "--amount", "1", "--category", "a")

    def test_missing_ledger_is_empty(self):
        self.assertEqual(self.ok("list"), "")
        self.assertEqual(self.ok("total"), "0.00\n")

    def test_reads_original_file_format(self):
        self.seed_format_file([{"date": "2026-01-05", "amount": "7.00", "category": "food", "note": "old"}])
        self.assertEqual(self.ok("list"), "2026-01-05  food              7.00  old\n")
        self.add("2026-01-06", "1.00", "food")
        self.assertEqual(self.ok("total"), "8.00\n")
