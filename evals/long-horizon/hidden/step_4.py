from _h import Case


class Recurring(Case):
    def rule(self, start, amount="5.00", *extra):
        return self.ok("recur", "add", "--start", start, "--amount", amount, "--category", "sub", *extra)

    def dates(self):
        return [row.split()[0] for row in self.ok("list").splitlines()]

    def test_rule_numbers_count_up(self):
        self.assertEqual(self.rule("2026-01-01"), "recur 1\n")
        self.assertEqual(self.rule("2026-01-01"), "recur 2\n")

    def test_materialize_is_inclusive_and_reports_count(self):
        self.rule("2026-01-15")
        self.assertEqual(self.ok("materialize", "--through", "2026-03-14"), "materialized 2\n")
        self.assertEqual(self.dates(), ["2026-01-15", "2026-02-15"])
        self.assertEqual(self.ok("materialize", "--through", "2026-03-15"), "materialized 1\n")

    def test_day_clamps_then_restores(self):
        self.rule("2026-01-31")
        self.ok("materialize", "--through", "2026-04-30")
        self.assertEqual(self.dates(), ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"])

    def test_materialize_twice_creates_nothing(self):
        self.rule("2026-01-01")
        self.ok("materialize", "--through", "2026-02-28")
        self.assertEqual(self.ok("materialize", "--through", "2026-02-28"), "materialized 0\n")
        self.assertEqual(self.ok("total"), "10.00\n")

    def test_voided_occurrence_is_not_recreated(self):
        self.rule("2026-01-01")
        self.ok("materialize", "--through", "2026-02-28")
        self.ok("void", "1")
        self.assertEqual(self.ok("materialize", "--through", "2026-03-31"), "materialized 1\n")
        self.assertEqual(self.dates(), ["2026-02-01", "2026-03-01"])

    def test_created_entries_share_ids_and_currency_rules(self):
        self.add("2026-01-01", "1.00", "a")
        self.rule("2026-01-10", "10.05", "--currency", "EUR", "--note", "plan")
        self.ok("materialize", "--through", "2026-01-31")
        self.assertEqual(self.ok("list", "--ids").splitlines()[-1], "#2  2026-01-10  sub              10.05 EUR  plan")
        self.assertEqual(self.ok("total", rates=True), "12.06\n")
        self.assertEqual(
            self.ok("report", "--month", "2026-01", rates=True),
            "a                 1.00\nsub              11.06\nTOTAL            12.06\n",
        )

    def test_rule_values_are_validated(self):
        self.refused("invalid amount", "recur", "add", "--start", "2026-01-01", "--amount", "-1", "--category", "s")
        self.refused("invalid date", "recur", "add", "--start", "nope", "--amount", "1", "--category", "s")
        self.refused("invalid currency", "recur", "add", "--start", "2026-01-01", "--amount", "1", "--category", "s", "--currency", "x")

    def test_rule_added_to_original_file(self):
        self.seed_format_file([{"date": "2026-01-05", "amount": "7.00", "category": "food", "note": ""}])
        self.rule("2026-01-01")
        self.ok("materialize", "--through", "2026-01-31")
        self.assertEqual(self.ok("total"), "12.00\n")
