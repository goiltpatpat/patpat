# Long-horizon regression eval

This manual eval tests whether Patpat's broader-suite rule reduces regressions when an agent builds on its own earlier code. It is motivated by SWE-Milestone, also published as EvoClaw (arXiv 2603.13428). That paper reports scores falling from over 80% on isolated tasks to at most about 38% in continuous evolution, and attributes the ceiling to accumulating regressions.

**No live trial has been run, so this directory contains no measurement.** CI doesn't run it, and it isn't part of the staged plugin. Its method comes from [`patpat-eval`](../../skills/patpat-eval/SKILL.md) and the [behavioral evaluation playbook](../../skills/patpat-loop/playbooks/behavioral-eval.md). The frozen arms, metrics, and decision rule are in [RUBRIC.md](RUBRIC.md).

| Path | What it is |
| --- | --- |
| `fixture/seed/` | The small `tally` ledger repository each trial starts from |
| `fixture/prompts/` | The five sequential requests |
| `hidden/` | Hidden tests for the seed and each step; these never enter a workspace |
| `reference/` | One implementation that behaves as the fixture does after any step; used only by the dry run |
| `lh_eval.py` | Prepares runs, composes prompts, scores snapshots, checks transcripts, and applies the decision rule |

There is no agent driver. You start each session yourself using the commands below, and `lh_eval.py` never calls a model.

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

`prepare` refuses a plugin without the rule. It also hashes the frozen inputs and creates one workspace per trial under opaque names.

```bash
python3 "$LH/lh_eval.py" prepare --run-root "$RUN" --plugin-with-rule "$HOME/staged-$(git rev-parse --short HEAD)" --host-version "$(claude --version | cut -d' ' -f1)"
```

### 3. Define the session command

Paste this function into the shell you'll use for the run. It runs one session and then scores it.

```bash
run_step() {
  local arm=$1 repeat=$2 step=$3 prompt dir ws plugin
  prompt=$(python3 "$LH/lh_eval.py" prompt --run-root "$RUN" --arm "$arm" --repeat "$repeat" --step "$step") || return
  dir=$(dirname "$prompt")
  ws=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['trials'][sys.argv[2]])" "$RUN/manifest.json" "$arm-$repeat")
  plugin=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['plugins'][sys.argv[2]])" "$RUN/manifest.json" "$arm")
  local cmd=(claude -p --model claude-sonnet-5-5 --effort medium
    --output-format stream-json --verbose
    --plugin-dir "$plugin" --setting-sources project --strict-mcp-config --no-session-persistence
    --permission-mode acceptEdits --allowedTools "Bash,Read,Edit,Write,Glob,Grep,Skill"
    --disallowedTools "Read(/mnt/**)" "Grep(/mnt/**)" "Glob(/mnt/**)"
    --max-budget-usd 5)
  printf 'prompt_sha256=%s\ncommand=%s\n' "$(sha256sum "$prompt" | cut -d' ' -f1)" "${cmd[*]}" > "$dir/step_$step.cmd.txt"
  (cd "$ws" && timeout 1800 "${cmd[@]}" < "$prompt" > "$dir/step_$step.stream.jsonl" 2> "$dir/step_$step.stderr.txt")
  python3 "$LH/lh_eval.py" score --run-root "$RUN" --arm "$arm" --repeat "$repeat" --step "$step"
}

run_trial() {
  local step
  for step in 1 2 3 4 5; do run_step "$1" "$2" "$step"; done
  python3 "$LH/lh_eval.py" check --run-root "$RUN" --arm "$1" --repeat "$2"
}
```

### 4. Run the first session and inspect it

Start with one session. If its transcript shows `problems`, stop and record them. The transcript format and `/patpat:patpat` in print mode haven't been confirmed yet, and this session is what confirms them.

```bash
run_step A 1 1
```

Check that the init event lists the arm's plugin and that the skill loaded. If the host needs a different command, that is a verifier defect: correct it, start a new run root, and don't count the first attempt.

### 5. Run the baseline, then apply the floor check

```bash
for step in 2 3 4 5; do run_step A 1 "$step"; done; python3 "$LH/lh_eval.py" check --run-root "$RUN" --arm A --repeat 1
```

```bash
run_trial A 2; run_trial A 3; python3 "$LH/lh_eval.py" compare --run-root "$RUN"
```

If the report shows `"floor_stop": true`, stop here. The result is `INCONCLUSIVE` under the rubric, because this fixture and model produced no regressions to prevent.

### 6. Run the other arms

```bash
run_trial B 1; run_trial C 1; run_trial B 2; run_trial C 2; run_trial B 3; run_trial C 3
```

```bash
python3 "$LH/lh_eval.py" compare --run-root "$RUN"
```

`report.json` in the run root holds every pair and criterion. Per-step scores, transcripts, prompts, and their digests are under `receipts/`.

Report every pair, not only the overall verdict. Keep any claim to this fixture and this host, and don't describe a result as a measured improvement in Patpat.

## Limits

- Three repeats per arm are enough to describe these runs, not to establish statistical significance.
- All arms run on one small Python fixture with one model.
- The agent has ordinary shell access as the WSL user. Hidden-test exposure is detected in the transcript, not prevented. Agent code also runs during scoring, so use a WSL user with nothing sensitive reachable.
- The baseline runs before the other arms because of the floor check, so model or service drift over the run isn't controlled.
