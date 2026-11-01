from _h import Case


class Report(Case):
    def fill(self):
        self.add("2026-01-05", "10.00", "rent")
        self.add("2026-01-20", "2.50", "food")
        self.add("2026-01-21", "1.25", "food")
        self.add("2026-02-01", "9.00", "food")

    def test_report_groups_sorts_and_totals(self):
        self.fill()
        self.assertEqual(
            self.ok("report", "--month", "2026-01"),
            "food              3.75\nrent             10.00\nTOTAL            13.75\n",
        )

    def test_empty_month_prints_only_total(self):
        self.fill()
        self.assertEqual(self.ok("report", "--month", "2025-12"), "TOTAL             0.00\n")

    def test_list_month_combines_with_category(self):
        self.fill()
        self.assertEqual(self.ok("list", "--month", "2026-02", "--category", "food"), "2026-02-01  food              9.00\n")
        self.assertEqual(self.ok("list", "--month", "2026-02", "--category", "rent"), "")

    def test_total_month(self):
        self.fill()
        self.assertEqual(self.ok("total", "--month", "2026-02"), "9.00\n")
        self.assertEqual(self.ok("total", "--month", "2026-01", "--category", "food"), "3.75\n")

    def test_malformed_month(self):
        for bad in ("2026-13", "2026-1", "January"):
            self.refused("invalid month", "report", "--month", bad)
        self.refused("invalid month", "total", "--month", "2026-00")
