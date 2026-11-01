from _h import Case


class Void(Case):
    def test_ids_are_shown_and_add_output_is_unchanged(self):
        self.assertEqual(self.ok("add", "--date", "2026-01-02", "--amount", "1", "--category", "a"), "added\n")
        self.add("2026-01-01", "2.00", "a")
        self.assertEqual(
            self.ok("list", "--ids"),
            "#2  2026-01-01  a                 2.00\n#1  2026-01-02  a                 1.00\n",
        )

    def test_void_hides_entry_from_list_total_report(self):
        self.add("2026-01-01", "1.00", "a")
        self.add("2026-01-02", "2.00", "b")
        self.assertEqual(self.ok("void", "1"), "voided 1\n")
        self.assertEqual(self.ok("list"), "2026-01-02  b                 2.00\n")
        self.assertEqual(self.ok("total"), "2.00\n")
        self.assertEqual(self.ok("report", "--month", "2026-01"), "b                 2.00\nTOTAL             2.00\n")

    def test_list_all_marks_void_and_combines_with_ids(self):
        self.add("2026-01-01", "1.00", "a", "--currency", "EUR", note="x")
        self.ok("void", "1")
        self.assertEqual(self.ok("list", "--all"), "2026-01-01  a                 1.00 EUR  x [void]\n")
        self.assertEqual(self.ok("list", "--all", "--ids"), "#1  2026-01-01  a                 1.00 EUR  x [void]\n")

    def test_void_errors(self):
        self.add("2026-01-01", "1.00", "a")
        self.refused("no entry 9", "void", "9")
        self.ok("void", "1")
        self.refused("entry 1 already voided", "void", "1")

    def test_ids_are_not_reused_after_void(self):
        self.add("2026-01-01", "1.00", "a")
        self.add("2026-01-02", "1.00", "a")
        self.ok("void", "2")
        self.add("2026-01-03", "1.00", "a")
        self.assertEqual(self.ok("list", "--ids", "--category", "a").splitlines()[-1].split()[0], "#3")

    def test_original_file_entries_are_numbered_in_file_order(self):
        self.seed_format_file(
            [
                {"date": "2026-02-01", "amount": "1.00", "category": "a", "note": ""},
                {"date": "2026-01-01", "amount": "2.00", "category": "a", "note": ""},
            ]
        )
        self.assertEqual(self.ok("void", "2"), "voided 2\n")
        self.assertEqual(self.ok("total"), "1.00\n")
        self.add("2026-03-01", "4.00", "a")
        self.assertEqual(self.ok("list", "--ids").splitlines()[-1].split()[0], "#3")

    def test_void_entry_cannot_cause_missing_rate(self):
        self.add("2026-01-01", "1.00", "a", "--currency", "GBP")
        self.add("2026-01-02", "2.00", "a")
        self.ok("void", "1")
        self.assertEqual(self.ok("total", rates=True), "2.00\n")
        self.assertEqual(self.ok("report", "--month", "2026-01", rates=True), "a                 2.00\nTOTAL             2.00\n")
