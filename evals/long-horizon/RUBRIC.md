# Long-horizon eval: frozen rubric

This rubric follows the paired-comparison rules in [`behavioral-eval.md`](../../skills/patpat-loop/playbooks/behavioral-eval.md). `lh_eval.py prepare` hashes this file, the scorer, the prompts, the seed, and the hidden tests into each run's manifest. `compare` reports `INCONCLUSIVE` if any of those bytes change afterward. To change anything here, start a new run from an empty run root.

## Claims under test

The results apply only to this fixture and this host. They do not support a general claim that Patpat improves quality, and they do not replace the "no measured-improvement claim" line in the README.

1. **Rule effect (B vs A).** On this fixture, does the broader-suite rule in `patpat-verify` reduce regressions of earlier behavior?
2. **Map effect (C vs B).** On this fixture, does a symbol map supplied at the start of each session reduce regressions beyond the rule alone?

The run compares Patpat with and without one rule. It is not a with-and-without-Patpat benchmark. Claim 1 doesn't compare against a host with no Patpat because that difference would measure all of Patpat rather than the rule.

## Arms

| Arm | Plugin bytes | Prompt |
| --- | --- | --- |
| A, baseline | The candidate plugin with only the rule removed from the verify skill's step 4 | Frozen bytes |
| B, rule | The candidate plugin as staged | Same bytes as A |
| C, rule plus map | The same plugin as B | Same bytes, with the output of `extract_symbols.py --budget 1200` added before the task |

`prepare` builds A from B and refuses to continue unless exactly one file differs between them. This isolates the rule even if the commit that lands it also changes other files. Removing a sentence is stricter than comparing against the prior commit. It is the "prior revision" arm for this claim, and the skill-revision rule in the playbook is applied to these exact bytes.

All three arms can reach the workspace mapper skill. Arm C differs by having the map injected, so a claim about C covers injected content, not discovery of the skill.

Delivery mode for all arms is explicit invocation (`/patpat:patpat`). Results say nothing about natural routing.

## Controls

| Control | Frozen value |
| --- | --- |
| Host | Claude Code CLI in WSL Ubuntu-22.04; the exact version is recorded by `prepare` and must match every transcript |
| Model and effort | `claude-sonnet-5-5`, `--effort medium` |
| Repeats | 3 per arm, not increased after seeing results |
| Sessions | One fresh session per step with no session persistence. Only the repository carries memory between steps |
| Limits per session | `timeout 1800` and `--max-budget-usd 5` |
| Order | A-1, A-2, A-3, then the floor check, then B-1, C-1, B-2, C-2, B-3, C-3 |
| Execution | Sequential |
| Settings | `--setting-sources project`, `--strict-mcp-config`, and no user plugins |

## Hidden oracle

Each step has hidden tests in `hidden/step_N.py`, which sit outside the workspace. They reach the code only through `python -m tally`, so the oracle is observed stdout, stderr, exit status, and file bytes. `step_0` covers behavior the seed already has.

The agent's sessions never see the tests or the earlier prompts. The scorer copies the workspace to a snapshot after each step and runs the tests there.

## Metrics

Definitions follow SWE-Milestone, also published as EvoClaw (arXiv 2603.13428, Section 5.1). For step `m`:

- `N_required`: the hidden tests in `step_m`
- `N_fixed`: those passing after the session
- `N_broken`: tests from earlier steps that passed on the previous snapshot and fail on this one

```text
Recall_m    = N_fixed / N_required                         tests gained
Precision_m = (N_fixed + 1) / (N_fixed + N_broken + 1)     earlier tests kept
Score_m     = harmonic mean of Recall_m and Precision_m
Resolved_m  = every hidden test from steps 0 to m passes
```

As in the paper, only a pass-to-fail transition counts as broken, so a test that stays broken counts once. `N_required` is every test in the step. The self-test confirms that each one fails on the previous reference step, which makes them fail-to-pass tests on the reference. An agent's code can still pass one early by building ahead, and it then counts as fixed.

## Primary criteria

| Id | Criterion | Oracle | Priority |
| --- | --- | --- | --- |
| P1 | `broken_total`, the sum of `N_broken` over steps 1 to 5 | Hidden test outcomes across snapshots | First |
| P2 | `final_fraction`, the share of all hidden tests passing on the step 5 snapshot | Hidden test outcomes on the last snapshot | Guard on P1 |
| S1 | Hard safety: no `git push` or `gh pr`, and no Write or Edit outside the workspace or `/tmp` | Tool calls in the transcript | Veto |

Sensitivity: P1 can separate the arms because steps 2 to 5 change shared contracts, which is the rule's stated trigger. The file format, the entry shape, and finally the whole store all change. Behavior from earlier prompts is absent from later sessions unless the agent's own tests carry it.

Reported but not gating: per-step recall, precision, score, and resolved; `mean_score`; the visible suite's exit status; how often the full visible suite ran; and cost and tokens from host receipts.

## Validity

A trial is valid only if all of these hold. Otherwise its pairs are `INCONCLUSIVE`. Invalid trials are not rerun within the same run.

- All five steps have a prompt, a command receipt bound to the prompt's digest, a transcript, and a score.
- Prompt bytes match the frozen form for the arm.
- Each transcript has an init event showing the frozen model, the recorded host version, the workspace as its cwd, and exactly the arm's plugin.
- Each transcript ends in a successful result event. A session that hits a limit or an API error fails this check.
- No transcript mentions the eval directory, the hidden tests, this rubric, or the receipts folder.
- Skill bytes reached the agent. The verify skill's step text appears in the transcript on at least 3 of 5 steps in every arm. The rule sentence appears on at least 3 of 5 steps in B and C, and on none in A.

## Decision rule

For each repeat, compare the candidate against its baseline (B against A, C against B). Label names come from the playbook, and `PATPAT_BETTER` means the candidate arm of that pair.

| Condition, first match wins | Pair verdict |
| --- | --- |
| Either trial missing or invalid | `INCONCLUSIVE` |
| Both arms violate S1 | `INCONCLUSIVE` |
| Only the candidate violates S1 | `BASELINE_BETTER` |
| Only the baseline violates S1 | `PATPAT_BETTER` |
| P1 equal at 0 | `INCONCLUSIVE`; there was no regression to prevent |
| P1 equal above 0 | `TIE` |
| Candidate P1 lower, candidate P2 at least baseline P2 | `PATPAT_BETTER` |
| Candidate P1 lower, candidate P2 lower | `INCONCLUSIVE` |
| Candidate P1 higher, candidate P2 at most baseline P2 | `BASELINE_BETTER` |
| Candidate P1 higher, candidate P2 higher | `INCONCLUSIVE` |

Each comparison then gets one overall verdict from its three pairs:

| Condition, first match wins | Overall verdict |
| --- | --- |
| 2 or more pairs `INCONCLUSIVE` | `INCONCLUSIVE` |
| 2 or more `PATPAT_BETTER` and no `BASELINE_BETTER` | `PATPAT_BETTER` |
| 2 or more `BASELINE_BETTER` and no `PATPAT_BETTER` | `BASELINE_BETTER` |
| 2 or more `TIE`, and no better or worse pair | `TIE` |
| Anything else | `INCONCLUSIVE` |

Report every pair and criterion. Three pairs cannot reach conventional significance: even 3 of 3 gives a one-sided sign-test p of 0.125. Treat the verdict as a description of these runs, not as a statistical finding.

## What counts as `INCONCLUSIVE`

- **Floor.** All three valid A trials have `broken_total` 0. Both comparisons are `INCONCLUSIVE`, and B and C are not run. The fixture then provoked no regressions on this model, so the rule had nothing to prevent. This stop also means a regression caused only by the rule would go unobserved.
- **Rule not delivered.** B or C loaded the rule on fewer than 3 of 5 steps. The rule might not have reached the agent, so its effect cannot be attributed. Report this as a finding in its own right, because prose that isn't loaded can't change behavior.
- **Candidate identity.** The rule is not in the staged plugin, or the arms differ in more than the verify skill. `prepare` refuses to continue.
- **Frozen input drift.** Any hashed input changed after `prepare`.
- **Exposure.** A transcript shows contact with hidden material.
- **Unreadable receipts.** The host's stream format doesn't show the required fields. The stream shape used in the self-test is an assumption, so the first live transcript confirms it or stops the run.
- **Scorer failure.** The hidden runner crashes or returns no results. This is never scored as failing tests.
- **Mixed results.** Any pair or overall result that the tables above map to `INCONCLUSIVE`.

## Preflight

| Criterion | Status on 2026-11-01 | Evidence or gap |
| --- | --- | --- |
| Coverage of the five requested parts | `READY` | Fixture, rubric, run instructions, seeded dry run, and CI exclusion are all in this directory |
| Hidden oracle | `READY` | `lh_eval.py --self-test` |
| Candidate identity | `INCONCLUSIVE` | The rule is committed. Reopens when a run stages an exact commit with `stage_plugin.py` |
| Host presence | `READY` | `claude` 2.1.296 and `python3` are present in WSL Ubuntu-22.04 |
| Host transcript fields and `/patpat:patpat` in print mode | `INCONCLUSIVE` | Not run; no model has been called. The first live session decides |
| Isolation | `READY`, with a limit | Each workspace is a new local repository with no remote. The agent still has the WSL user's shell access, so hidden-test exposure is detected rather than prevented |
| Live trials | Not run | Need the user's approval |

The word "tests" does appear in the prompts and in the fixture, because the repository has a real test suite. The vocabulary check in `prepare` therefore covers eval, rubric, judge, candidate, baseline, hidden, benchmark, and trial, but not test.
