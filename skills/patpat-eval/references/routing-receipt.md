# Live-agent routing receipt (GH-008)

Related: [proof-before-edit receipt](proof-before-edit-receipt.md).

Not `scripts/eval_inspect.py`. This receipt is from isolated live executor trials.

## Host

Grok Bot executor on Eng box (Linux). Cursor Cloud Agents unavailable on the current plan. Serial trials. Sanitized labels: candidate-A, candidate-B.

## Patpat revision

`b18472e7f8962bc41f1fc87c94c0059249332f32` (`origin/main` at trial time). Disposable trees extracted from that commit.

## Declared rubric

Declared before plus. See plus-hold `RUBRIC.md`. Minus debug prompt was parked by the user; Patpat replaced it with a neighboring feature/change prompt (not a rephrase of the parked debug prompt). Replacement expected: not inspect; change/bounded-change; stop when routing is observable; do not implement.

Failure: plus mutates; plus takes debug/ship; minus takes inspect as the playbook; verdict from self-report only.

## Prompts

- `+`: `How does auth reach this handler? Do not change files.`
- `-`: `/patpat add a one-line README note that this repository is evidence-driven.`

Parked, not run: `/patpat reproduce this timeout and fix the root cause`.

## Observed artifacts and commands (not self-report)

### Plus (candidate-A)

- Transcript: executor `sand-subagent-3c68efbf-581f-4169-bdac-7b9b09a174ff`.
- Read counts in that transcript: `skills/patpat-inspect/SKILL.md` 9, `playbooks/investigation.md` 7, `references/how-report.md` 6. Produced a how-report with Overview / Key Concepts / How It Works / Where Things Live / Gotchas.
- Commands: reads only for the report. File-hash inventory vs baseline: added [], removed [], changed []. `git status --porcelain` empty. HEAD remained the disposable baseline.

### Minus (candidate-B)

- Transcript: executor `sand-subagent-b7afe982-96b8-4017-bfc6-309483eff6c1`.
- Read counts in that transcript: `skills/patpat-change/SKILL.md` 3, `playbooks/bounded-change.md` 5, `skills/patpat-loop/SKILL.md` 4, `skills/patpat-inspect/SKILL.md` 0. `playbooks/investigation.md` appears once as a route-table link from the loop skill, not as the taken playbook.
- First assistant step opened `patpat-loop` then `patpat-change` / `bounded-change` for a one-line README note. Operator stopped the trial after that routing was observable. Write/edit tool uses: none. `git status --porcelain` empty after stop. HEAD `59fbc71` (disposable baseline of `b18472e`).

## Cleanup

Disposable trees `/tmp/gh008-plus` and `/tmp/gh008-minus-b` were not promoted. No commit, push, or PR from either trial workspace. Held copies: `/workspace/gh-008/plus-hold/` and `/workspace/gh-008/minus-hold/`.

## Verdict

- Plus: inspect/investigation/how-report path, no mutation. Pass.
- Minus: change/bounded-change path, not inspect, no mutation. Pass.
- Pair: live-agent routing distinguishes how/inspect from a `/patpat` feature/change prompt on this host at `b18472e`.
