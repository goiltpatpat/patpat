# Assignment Generation Model

[`models/AssignmentGeneration.tla`](../models/AssignmentGeneration.tla) is a bounded transition model for the assignment-generation fence. It checks that every accepted write uses the current generation and that the total number of writes equals the number of accepted attempts. The model includes a caller's previously issued generations so reassignment to the same worker can expose stale output from an earlier assignment. Worker labels represent possession of an issued generation only; the Python API does not authenticate the caller or check actor identity in every mutation method, and this model makes no such claim.

The base configuration uses two workers, generations `0..3`, and traces of at most six actions. `NoStaleWrites` and `WritesMatchAcceptedAttempts` are the claimed product properties and each has a targeted mutant. `TypeOK` and `ActiveAssignmentHasIssuedToken` are auxiliary model-consistency invariants; they help validate the model's state shape and assignment bookkeeping but are not separate implementation guarantees in this pilot. The generation mutant disables the generation comparison and must violate `NoStaleWrites`. The rejected-write mutant appends a current-generation write during a rejected attempt; it must violate `WritesMatchAcceptedAttempts` while still satisfying the generation invariant.

## Check

Use an existing TLA+ installation. The Patpat script does not download or install tools; provide a path to `tla2tools.jar`:

```sh
python3 skills/patpat-run/scripts/check_assignment_model.py \
  --tlc-jar /absolute/path/to/tla2tools.jar
```

The script copies the model and three configurations into isolated temporary directories, checks the base model, requires both targeted mutant counterexamples, reports the TLC version, jar SHA-256, state counts, and mutant counterexample counts, then removes temporary output when it exits. Captured TLC output is limited to 8 MiB and successful runs do not print complete counterexample traces. A mutant receipt is rejected unless TLC exited successfully, completed, reported only the expected invariant, emitted a nonempty state trace and explored state counts, and reported no unrelated `Error:` line. Pass `--java` as a PATH command or an absolute/path-qualified executable; relative paths are resolved before TLC changes directories.

Run the implementation checks as a separate proof layer:

```sh
python3 skills/patpat-run/scripts/verify_assignment_fence.py --self-test
python3 skills/patpat-run/scripts/program_state.py --self-test
```

`program_state.py --self-test` exercises stale head, state, verdict, and inbox mutations after reassignment. It verifies that each rejection leaves the authoritative `state.json` bytes unchanged. A disposable source mutant that removes the generation comparison must make this self-test fail; do not mutate the live source tree for that check.

## Code mapping and limits

| Model | Implementation |
| --- | --- |
| `generation`, `assigned`, `owner` | `units[unit_id].assignment`, interpreted through `assignment_snapshot()` |
| `Assign(worker)` | Successful `assign_unit()` after its expected-generation and dispatch checks: increments generation and records the new actor |
| `Revoke` | `invalidate_assignment(..., advance_generation=True)`: increments the generation and clears the assignment |
| `AttemptWrite(token, worker)` | The generation-fence check in `require_current_assignment()`, called by `set_head()`, `set_unit_state()`, `record_verdict()`, and unit `append_inbox()` |
| `NoStaleWrites` | Every accepted model write uses the current generation |
| `WritesMatchAcceptedAttempts` | Each accepted attempt adds one write; a rejected attempt adds none |

The model assumes the dispatch gate is open, its bound evidence is fresh, each action is atomic, and a caller attempts only generations issued to that modeled worker. The caller label is an abstraction for which generation it holds, not an authentication boundary. The model bounds generations and trace length and does not cover generation exhaustion, file locking, simultaneous processes, host authentication, unauthorized guesses of another worker's current generation, external worker effects, or the complete program store. TLC checks this finite model, not Python implementation equivalence. The Python API self-test and bounded guard checker provide separate implementation evidence for their exercised cases.

**Historical receipt, stale for the current harness:** `55f3d2d3be448fc9974e1312474808591f2b4fb3` is the squash merge on `main`. The bounded model, API self-test, guard cases, model mutants, and isolated source mutant passed at PR source commit `31ac99079a951a2be4b91e09e3b806a270233d89`. The checker changed after that receipt, so it no longer proves the current harness. Run the command above with an inspectable jar and capture the reported TLC version, jar digest, state counts, and both mutant results before recording a new current anchor.
