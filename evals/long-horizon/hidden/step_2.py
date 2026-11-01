from _h import Case


class Currency(Case):
    def test_total_converts_each_entry_then_sums(self):
        self.add("2026-01-01", "10.05", "a", "--currency", "EUR")
        self.add("2026-01-02", "10.05", "a", "--currency", "EUR")
        self.add("2026-01-03", "1.00", "a")
        self.assertEqual(self.ok("total", rates=True), "23.12\n")

    def test_report_prints_usd_by_category(self):
        self.add("2026-01-01", "100.00", "a", "--currency", "JPY")
        self.add("2026-01-02", "2.00", "b")
        self.assertEqual(
            self.ok("report", "--month", "2026-01", rates=True),
            "a                 0.67\nb                 2.00\nTOTAL             2.67\n",
        )

    def test_list_marks_foreign_lines_only_and_needs_no_rates(self):
        self.add("2026-01-01", "10.00", "food", "--currency", "EUR", note="lunch")
        self.add("2026-01-02", "3.00", "food", note="tea")
        self.assertEqual(
            self.ok("list"),
            "2026-01-01  food             10.00 EUR  lunch\n2026-01-02  food              3.00  tea\n",
        )

    def test_missing_rate_names_currency(self):
        self.add("2026-01-01", "1.00", "a", "--currency", "GBP")
        self.refused("no rate for GBP", "total", rates=True)
        self.refused("no rate for GBP", "report", "--month", "2026-01")

    def test_usd_needs_no_rates_file(self):
        self.add("2026-01-01", "1.00", "a", "--currency", "USD")
        self.assertEqual(self.ok("total"), "1.00\n")

    def test_invalid_currency(self):
        for bad in ("eur", "EURO", "E1R"):
            self.refused("invalid currency", "add", "--date", "2026-01-01", "--amount", "1", "--category", "a", "--currency", bad)

    def test_original_file_entries_are_usd(self):
        self.seed_format_file([{"date": "2026-01-05", "amount": "7.00", "category": "food", "note": ""}])
        self.add("2026-01-06", "10.00", "food", "--currency", "EUR")
        self.assertEqual(self.ok("total", rates=True), "18.00\n")
