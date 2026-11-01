"""Run hidden steps 0..N against LH_SNAPSHOT and write one outcome per test id as JSON."""

from __future__ import annotations

import importlib
import json
import sys
import unittest


class Collect(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.outcomes = {}

    def addSuccess(self, test):
        self.outcomes[test.id()] = True

    def addFailure(self, test, err):
        self.outcomes[test.id()] = False

    def addError(self, test, err):
        self.outcomes[test.id()] = False


def main() -> int:
    upto, out = int(sys.argv[1]), sys.argv[2]
    suite = unittest.TestSuite()
    for step in range(upto + 1):
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(f"step_{step}")))
    result = Collect()
    suite.run(result)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(result.outcomes, handle, indent=1, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
