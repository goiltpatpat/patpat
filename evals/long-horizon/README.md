# Long-horizon regression eval

This manual eval tests whether Patpat's broader-suite rule reduces regressions when an agent builds on its own earlier code. It is motivated by SWE-Milestone, also published as EvoClaw (arXiv 2603.13428). That paper reports scores falling from over 80% on isolated tasks to at most about 38% in continuous evolution, and attributes the ceiling to accumulating regressions.

**No live trial has been run, so this directory contains no measurement.** CI doesn't run it, and it isn't part of the staged plugin. Its method comes from [`patpat-eval`](../../skills/patpat-eval/SKILL.md) and the [behavioral evaluation playbook](../../skills/patpat-loop/playbooks/behavioral-eval.md). The frozen arms, metrics, and decision rule are in [RUBRIC.md](RUBRIC.md).

| Path | What it is |
| --- | --- |
| `fixture/seed/` | The small `tally` ledger repository each trial starts from |
| `fixture/prompts/` | The five sequential requests |
| `hidden/` | Hidden tests for the seed and each step; these never enter a workspace |
| `reference/` | One implementation that behaves as the fixture does after any step; used only by the dry run |
| `lh_eval.py` | Prepares runs, launches each session through `run-step`, scores snapshots, checks transcripts, and applies the decision rule |

`run-step` and `run-trial` launch `claude -p` and cost tokens. You start them yourself with the commands below. Every other `lh_eval.py` command, including `--self-test`, calls no model.

## Dry run

This costs no tokens. It takes about 5 minutes.

```bash
python3 evals/long-horizon/lh_eval.py --self-test
```

The reference implementation stands in for the agent, and the transcripts are synthetic. The dry run checks that:

- Every step's hidden tests fail before that step and pass after it.
- A clean run reports no regressions and full recall.
- A void regression seeded at step 4 is caught at step 4 and blamed on the step 3 tests.
- A rounding regression seeded at step 5 is caught at step 5 and blamed on the step 2 tests.
- A test that stays broken counts once.
- A broken hidden suite, a wrong plugin, a transcript that touches hidden material, an undelivered rule, and a changed rubric each stop the affected claim.
- The pair and overall decision rules give a valid verdict for every input combination.

Passing shows the scorer works. It says nothing about the rule or about Patpat.

## Live run

Live trials cost tokens: 15 sessions through the floor check and 75 sessions at most. With the frozen limit of $5 per session, spending is capped at about $75 and $375. Get the user's approval first.

Run everything in WSL Ubuntu-22.04 with the run root on the Linux filesystem, away from the repository.

### 1. Stage the candidate

The candidate must be a commit that contains the rule. Stage it from a clean checkout of that commit, and make sure this directory is the same in that checkout:

```bash
export LH="$PWD/evals/long-horizon"
export RUN="$HOME/t-$(date +%s)"
python3 scripts/stage_plugin.py --target "$HOME/staged-$(git rev-parse --short HEAD)"
```

### 2. Freeze the run

`prepare` refuses a plugin without the rule. It asks `claude --version` for the host version itself, hashes the frozen inputs, and creates one workspace per trial under opaque names. It stops if the host CLI is missing or reports no version.

```bash
python3 "$LH/lh_eval.py" prepare --run-root "$RUN" --plugin-with-rule "$HOME/staged-$(git rev-parse --short HEAD)"
```

The scorer core is host-neutral. Hidden tests, metrics, the decision rule, the leak scan, and receipt binding read only a normalized session. One adapter per host in `lh_eval.py` (`HOSTS`) owns the version probe, the frozen command, the plugin invocation in the prompt, the transcript parser, and the evidence that a transcript came from a real session of that host. Only `claude-code` is implemented and frozen by this rubric. A comparison is valid only between arms on the same host and model; a cross-host difference measures the host and model, not Patpat.

### 3. Who may operate the run

`run-step` composes the prompt, launches the frozen `claude -p` command, and writes the command receipt, transcript, and `run.json` digests itself. Never write or edit a file under `receipts/` by hand.

The operator must be a person or a plain shell, not an AI agent that can read `hidden/` or `reference/`. If the host CLI fails, is not logged in, or the first session shows `problems`, stop and report it. Never substitute another agent or host for the session, and never write a transcript. `check` rejects a step without `run.json`, a transcript edited after the session, a command other than the frozen one, a transcript without a host session id, turn count, duration, nonzero cost, or the plugin's `UserPromptSubmit` hook response, and a workspace that carries lines from the reference answer or the hidden tests. `check` and `compare` also rescore every step from its snapshot, so editing `score.json` or `trial.json` cannot move a metric. These checks catch lazy substitution and verbatim copying. They are not cryptographic: a binary that prints a host-shaped transcript, or a copy with its distinctive lines rewritten, still passes. A run is only as trustworthy as its operator.

### 4. Run the first session and inspect it

Start with one session. If its output shows `problems`, stop and record them.

```bash
python3 "$LH/lh_eval.py" run-step --run-root "$RUN" --arm A --repeat 1 --step 1
python3 -c "import json,sys; [print(e.get('subtype'), e.get('hook_event', ''), e.get('session_id', '')) for e in map(json.loads, open(sys.argv[1])) if e.get('type') == 'system']" "$RUN/receipts/A-1/step_1.stream.jsonl"
```

Check that the init event lists the arm's plugin, that a `UserPromptSubmit` hook response from Patpat appears, and that the skill loaded. If the host needs a different command, that is a verifier defect: correct it in `lh_eval.py`, start a new run root, and don't count the first attempt.

### 5. Run the baseline, then apply the floor check

```bash
for step in 2 3 4 5; do python3 "$LH/lh_eval.py" run-step --run-root "$RUN" --arm A --repeat 1 --step "$step"; done
python3 "$LH/lh_eval.py" check --run-root "$RUN" --arm A --repeat 1
```

```bash
python3 "$LH/lh_eval.py" run-trial --run-root "$RUN" --arm A --repeat 2
python3 "$LH/lh_eval.py" run-trial --run-root "$RUN" --arm A --repeat 3
python3 "$LH/lh_eval.py" compare --run-root "$RUN"
```

If the report shows `"floor_stop": true`, stop here. The result is `INCONCLUSIVE` under the rubric, because this fixture and model produced no regressions to prevent.

### 6. Run the other arms

```bash
for trial in "B 1" "C 1" "B 2" "C 2" "B 3" "C 3"; do
  set -- $trial
  python3 "$LH/lh_eval.py" run-trial --run-root "$RUN" --arm "$1" --repeat "$2"
done
python3 "$LH/lh_eval.py" compare --run-root "$RUN"
```

`report.json` in the run root holds every pair and criterion. Per-step scores, transcripts, prompts, and their digests are under `receipts/`.

Report every pair, not only the overall verdict. Keep any claim to this fixture and this host, and don't describe a result as a measured improvement in Patpat.

## Limits

- Three repeats per arm are enough to describe these runs, not to establish statistical significance.
- All arms run on one small Python fixture with one model.
- The agent has ordinary shell access as the WSL user. Hidden-test exposure is detected in the transcript, not prevented. Agent code also runs during scoring, so use a WSL user with nothing sensitive reachable.
- The baseline runs before the other arms because of the floor check, so model or service drift over the run isn't controlled.
- `check` and `compare` rerun the agent's code against the hidden tests. Code that writes beside itself or behaves differently between runs, or a hidden-test call that hits its 20-second timeout on a loaded machine, makes an honest trial `INCONCLUSIVE`. That fails safe but can cost a trial.
