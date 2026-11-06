#!/usr/bin/env python3
"""Decision statistics for small behavioral evals (pure standard library).

Subcommands print one JSON object and exit 0; invalid input exits 2.

  rate       --passes K --trials N             Wilson 95% interval for a pass rate.
  pair       --candidate-wins B --baseline-wins C [--ties T] [--alpha A]
             Exact two-sided sign test on discordant pairs (exact McNemar).
  agreement  --a PASS,FAIL,... --b PASS,FAIL,... [--min-kappa K] [--min-items N] [--min-per-class M]
             Cohen's kappa between a judge and anchor labels.
"""
from __future__ import annotations

import argparse
import json
import math
import sys

Z95 = 1.959963984540054


def wilson(passes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    if trials <= 0 or not 0 <= passes <= trials:
        raise ValueError("require 0 <= passes <= trials and trials > 0")
    p = passes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def sign_test_p(wins_a: int, wins_b: int) -> float:
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = min(wins_a, wins_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def min_discordant_for(alpha: float) -> int:
    n = 1
    while 2 * 0.5**n >= alpha:
        n += 1
    return n


def pair_verdict(candidate_wins: int, baseline_wins: int, ties: int, alpha: float) -> dict:
    if min(candidate_wins, baseline_wins, ties) < 0 or not 0 < alpha < 1:
        raise ValueError("counts must be non-negative and 0 < alpha < 1")
    p = sign_test_p(candidate_wins, baseline_wins)
    if p < alpha and candidate_wins > baseline_wins:
        verdict = "CANDIDATE_BETTER"
    elif p < alpha and baseline_wins > candidate_wins:
        verdict = "BASELINE_BETTER"
    else:
        verdict = "INCONCLUSIVE"
    return {
        "candidate_wins": candidate_wins,
        "baseline_wins": baseline_wins,
        "ties": ties,
        "discordant": candidate_wins + baseline_wins,
        "p_value": round(p, 6),
        "alpha": alpha,
        "min_discordant_for_any_verdict": min_discordant_for(alpha),
        "verdict": verdict,
    }


def parse_labels(raw: str) -> list[str]:
    labels = [item.strip().upper() for item in raw.split(",")]
    if not raw.strip() or any(not label for label in labels):
        raise ValueError("labels must be a comma-separated list with no empty entries")
    unknown = sorted(set(labels) - {"PASS", "FAIL"})
    if unknown:
        raise ValueError(f"labels must be PASS or FAIL, got {unknown}")
    return labels


def cohen_kappa(a: list[str], b: list[str]) -> tuple[float, float | None]:
    if len(a) != len(b) or not a:
        raise ValueError("label lists must be non-empty and the same length")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    categories = set(a) | set(b)
    expected = sum((a.count(c) / n) * (b.count(c) / n) for c in categories)
    if expected == 1.0:
        return observed, None  # kappa is undefined when both raters use one label
    return observed, (observed - expected) / (1 - expected)


def agreement_verdict(a: list[str], b: list[str], min_kappa: float, min_items: int, min_per_class: int = 3) -> dict:
    if not 0 < min_kappa <= 1 or min_items < 1 or min_per_class < 1:
        raise ValueError("require 0 < min_kappa <= 1, min_items >= 1, and min_per_class >= 1")
    observed, kappa = cohen_kappa(a, b)
    if len(a) < min_items or kappa is None or min(b.count("PASS"), b.count("FAIL")) < min_per_class:
        verdict = "INCONCLUSIVE"
    elif kappa >= min_kappa:
        verdict = "CALIBRATED"
    else:
        verdict = "UNCALIBRATED"
    return {
        "items": len(a),
        "raw_agreement": round(observed, 4),
        "kappa": None if kappa is None else round(kappa, 4),
        "min_kappa": min_kappa,
        "min_items": min_items,
        "min_per_class": min_per_class,
        "verdict": verdict,
    }


def self_test() -> None:
    low, high = wilson(8, 10)
    assert (round(low, 3), round(high, 3)) == (0.49, 0.943), (low, high)
    assert wilson(0, 5)[0] == 0.0 and wilson(5, 5)[1] == 1.0
    assert round(sign_test_p(9, 1), 4) == 0.0215
    assert pair_verdict(9, 1, 3, 0.05)["verdict"] == "CANDIDATE_BETTER"
    assert pair_verdict(1, 9, 0, 0.05)["verdict"] == "BASELINE_BETTER"
    assert pair_verdict(3, 1, 6, 0.05)["verdict"] == "INCONCLUSIVE"
    assert pair_verdict(5, 0, 0, 0.05)["verdict"] == "INCONCLUSIVE"
    assert pair_verdict(6, 0, 0, 0.05)["verdict"] == "CANDIDATE_BETTER"
    assert min_discordant_for(0.05) == 6
    labels = parse_labels("PASS,PASS,FAIL,FAIL,PASS,FAIL,PASS,FAIL,PASS,FAIL")
    assert agreement_verdict(labels, labels, 0.6, 10)["verdict"] == "CALIBRATED"
    flipped = ["FAIL" if x == "PASS" else "PASS" for x in labels]
    assert agreement_verdict(labels, flipped, 0.6, 10)["verdict"] == "UNCALIBRATED"
    assert agreement_verdict(labels[:4], labels[:4], 0.6, 10)["verdict"] == "INCONCLUSIVE"
    all_pass = ["PASS"] * 12
    assert agreement_verdict(all_pass, all_pass, 0.6, 10) == {**agreement_verdict(all_pass, all_pass, 0.6, 10), "kappa": None, "verdict": "INCONCLUSIVE"}
    judge_all_pass = agreement_verdict(all_pass[:10], labels, 0.6, 10)
    assert judge_all_pass["kappa"] == 0.0 and judge_all_pass["verdict"] == "UNCALIBRATED"
    assert pair_verdict(4, 4, 0, 0.05)["p_value"] == 1.0
    assert pair_verdict(0, 0, 5, 0.05)["verdict"] == "INCONCLUSIVE"
    one_fail = ["PASS"] * 9 + ["FAIL"]
    assert agreement_verdict(one_fail, one_fail, 0.6, 10)["verdict"] == "INCONCLUSIVE"
    for bad in (lambda: parse_labels("PASS,PAS"), lambda: parse_labels("PASS,,FAIL"), lambda: parse_labels(" "), lambda: pair_verdict(1, 0, 0, 1.5), lambda: wilson(1, 0)):
        try:
            bad()
        except ValueError:
            pass
        else:
            raise AssertionError("invalid input accepted")
    print("eval_stats self-test passed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--self-test", action="store_true")
    sub = parser.add_subparsers(dest="command")
    rate = sub.add_parser("rate")
    rate.add_argument("--passes", type=int, required=True)
    rate.add_argument("--trials", type=int, required=True)
    pair = sub.add_parser("pair")
    pair.add_argument("--candidate-wins", type=int, required=True)
    pair.add_argument("--baseline-wins", type=int, required=True)
    pair.add_argument("--ties", type=int, default=0)
    pair.add_argument("--alpha", type=float, default=0.05)
    agree = sub.add_parser("agreement")
    agree.add_argument("--a", required=True, help="judge labels, comma-separated")
    agree.add_argument("--b", required=True, help="anchor labels, comma-separated")
    agree.add_argument("--min-kappa", type=float, default=0.6)
    agree.add_argument("--min-items", type=int, default=10)
    agree.add_argument("--min-per-class", type=int, default=3)
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0
    try:
        if args.command == "rate":
            low, high = wilson(args.passes, args.trials)
            result = {
                "passes": args.passes,
                "trials": args.trials,
                "rate": round(args.passes / args.trials, 4),
                "wilson95": [round(low, 4), round(high, 4)],
            }
        elif args.command == "pair":
            result = pair_verdict(args.candidate_wins, args.baseline_wins, args.ties, args.alpha)
        elif args.command == "agreement":
            result = agreement_verdict(parse_labels(args.a), parse_labels(args.b), args.min_kappa, args.min_items, args.min_per_class)
        else:
            parser.print_help()
            return 2
    except ValueError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
