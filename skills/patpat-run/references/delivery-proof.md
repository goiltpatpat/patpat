# Delivery Proof

Contract between durable state and delivery deciding which proof covers a commit, when each gate is checked, what a slice or program may deliver, and what a merge must prove. Neither store grants authority; [default delivery](../../patpat-loop/playbooks/default-delivery.md) still reacquires it.

## Decisions

**A proof covers content, and a commit is bound by its tree.** A run receipt covers head `H` when:
1. The proven worktree tree equals `H^{tree}`, and the recorded commit is `H` or an ancestor of `H`.
2. The checkout is clean at `H`.

The receipt records that tree, staying valid across staging and committing. A program verdict names a commit directly (1 holds by identity; `check-delivery` enforces 2).

**Admission and exact-head proof are separate gates on the same receipts.**

| Gate | Asks | Passes when | Survives |
| --- | --- | --- | --- |
| `commit` | May staged content become a commit? | Receipts cover worktree; index holds exact content | Nothing: run after staging |
| `ship` | May head be pushed or exposed in a PR? | Receipts cover worktree; checkout is clean at `HEAD` | Push, PR creation |
| `merge` | May head land? | `ship`; `explicit-merge`; ready `pr_watch` receipt bound to `HEAD`; `HEAD` contains current base | Until any of those change |

All three refuse at `BLOCKED`. Proof-first is default (delivery intent often arrives late); commit-first is required when proof depends on commit identity (e.g., `git log` or Git-derived version). Skip `commit` when content is already committed.

**`REPORT` stays terminal; evaluating a gate is not recording.** Per [execution graph](../../patpat-loop/references/execution-graph.md), delivery follows `REPORT` without reopening the run (all three gates can pass at `REPORT`, or the run can stay open until delivery finishes). A new head or late `land` starts a new scoped run at that head; nothing reopens a run or transfers approval.

**Slice vs whole-program delivery:**
- *Slice:* `check-delivery --unit <id>`. Unit and all transitive dependencies are complete with fresh evidence; checkout is clean at unit head; siblings may be pending. Does not read the program delivery gate.
- *Whole program:* `check-delivery` without `--unit`. Every unit is complete, delivery gate is open, and one unit transitively depends on every other unit and contains their heads (derived, not stored; e.g., stack tip or final integration unit with whole-system proof). Independent units cannot open the whole-program gate.

**Merge containment.** `HEAD` must contain the current base (`--base-head` from fresh fetch) so merge commit, squash, or fast-forward produces the proven tree. After a queue sibling lands, the next slice updates onto the new base, records its new head, and proves again.

**One gate per head.** Program unit / integrated head uses `program_state.py check-delivery`; other durable work uses `run_state.py check-gate`.

## Commands

Stores live under one worktree's Git metadata (`--root` = creating worktree; removing a linked worktree deletes its run store). Declare merge authority at `init --authority explicit-merge` or in the plan's `delivery` claim.

Save provider receipt with `github_observe.py` (which prints the document `pr_watch.py` evaluates; `pr_watch.py`'s verdict is not a receipt). Runs read `<run store>/provider-receipt.json`; programs take `--provider-receipt <file>`.

Run in a POSIX shell (PowerShell 5.1 `>` writes UTF-16, which gates refuse). `<skills>` = installed skills dir (`skills` in this repo); `--deadline` = UTC timestamp ending in `Z`. Every Git command uses `-C <worktree>`. Each command exits 0 only on pass.

Single durable run, proof first (skip `git add`, `commit` gate, and `git commit` if already committed):

```sh
RUN=<skills>/patpat-run/scripts/run_state.py
git -C <worktree> add <exactly the proven paths>
python3 "$RUN" check-gate --root <worktree> --run-id <run> --gate commit
git -C <worktree> commit
python3 "$RUN" check-gate --root <worktree> --run-id <run> --gate ship
git -C <worktree> push                    # then open or update the PR
git -C <worktree> fetch origin <base>
python3 <skills>/patpat-ship/scripts/github_observe.py --repository <owner/repo> --pull-request <n> \
  --expected-head <sha> --expected-base <base> --require-review --required-check <name> --deadline <utc> \
  > <run store>/provider-receipt.json
python3 "$RUN" check-gate --root <worktree> --run-id <run> --gate merge \
  --base-head "$(git -C <worktree> rev-parse origin/<base>)"
```

Program slice (omit `--unit` for integrated head):

```sh
PROGRAM=<skills>/patpat-run/scripts/program_state.py
python3 "$PROGRAM" --root <coordinator worktree> --program <id> check-delivery \
  --unit <unit> --checkout <unit worktree>
git -C <unit worktree> push               # then open or update the PR
git -C <unit worktree> fetch origin <base>
python3 "$PROGRAM" --root <coordinator worktree> --program <id> check-delivery \
  --unit <unit> --checkout <unit worktree> --gate merge \
  --provider-receipt <file> --base-head "$(git -C <unit worktree> rev-parse origin/<base>)"
```

## Shapes and signatures

```python
# run_state.py: additive field, no schema bump
record = {..., "snapshot": "git:<head>:<digest>", "tree": "<candidate tree>" or None}

current_candidate(root) -> {"snapshot": str, "worktree_tree": str | None, "tree": str | None, "head": str}
worktree_matches_head(root, candidate) -> bool
index_holds_candidate(root, candidate) -> bool
merge_result_is_proven(root, head, base_head) -> tuple[bool, str]
evaluate_provider_receipt(path, head) -> tuple[bool, str, bool]
check_gate(root, run_id, gate, base_head=None) -> tuple[bool, str]

# program_state.py: no stored field or schema change
integrated_head(root, state) -> str | None
check_delivery(root, program_id, unit_id=None, gate="ship", checkout=None,
               provider_receipt=None, base_head=None) -> dict
```

Candidates are rebuilt from `HEAD` in a private index/object dir (assume-unchanged cannot hide edits; gates add no objects and leave the real index unchanged). `tree` is `None` if the repo has any gitlink (including clean submodules): receipts then match by exact snapshot only, `commit` refuses, and commit-first applies. Clean checkout also requires every populated gitlink to be clean at its own head. Legacy receipts without `tree` follow the same snapshot rule.

## Failure modes

| Situation | Result | Next step |
| --- | --- | --- |
| Hook/amend changed committed tree | `ship` fails as stale | Prove new head |
| Same-tree amend/rebase of proven commit | `ship` fails as stale | Prove new head (tree-equal reword on proof's own base still passes) |
| Partial or empty staging | `commit` fails | Stage exact proven content |
| Repo has no required check | `merge` blocked (`pr_watch.py` cannot reach `ready`) | Stop and report per [authorized delivery](../../patpat-loop/playbooks/authorized-delivery.md); user may add a check + new scoped run, or merge personally |
| Unrelated dirty files during proof | `commit`/`ship` fail | Commit in-scope paths, then start a new run in a clean linked worktree at that commit |
| Repo holds a gitlink | `commit` fails | Commit first, then prove that head |
| Base moved | `merge` fails | Update onto base and prove new head |
| New head after `REPORT` | `ship` fails (run cannot record) | Start a new scoped run |
| `land` arrives after init | `merge` fails on authority | Start a new scoped run declaring it (old approval does not carry) |
| Run stopped at `BLOCKED` | All delivery gates fail | Resolve blocker in a new run |
| Squash-landed dependency | Dependent head no longer contains it | Set dependency head to landed commit and re-prove; downstream proof revoked |
| Dependency reassigned or evidence changed | All slices above it fail | Re-prove dependency |
| Dispatch cutoff passed when slice must update | `set-head` refuses | Run `set-gate dispatch open` with `--reason`, same `--receipt` and `--integration-owner`, and `--clear-budget` or `--deadline` + `--integration-reserve-minutes` (never close dispatch first—closing revokes assignments and clears proof) |
| Independent units, whole-program request | Gate refuses to open | Deliver slices or add an integration unit |

## Receipt files and limits

- **Receipt files:** `verify_review.py` defaults to Git metadata (`<git-dir>/patpat/review-receipt.json`, keeping the worktree clean); `verify_delivery.py` defaults to `.patpat/delivery-receipt.json` in the worktree, where untracked files dirty the checkout and fail `commit`/`ship`/`merge`—pass `--receipt` outside the repo or list it in `.git/info/exclude`. Write both after the commit they describe (`head_sha`). A proof-first review stays valid via its run receipt when trees match; `verify_review.py` then needs a receipt naming the committed head, not a second review of identical bytes.
- **Base & timing:** `--base-head` comes from a fresh fetch (`pr_watch` does not observe base; any ancestor passes); base or PR head can still change between gate and merge.
- **Merge methods:** Rebase merge replays commits, so hand-edited merge commits can yield a different tree; check the merged revision afterward per [authorized delivery](../../patpat-loop/playbooks/authorized-delivery.md).
- **Tree vs bytes & sparse checkouts:** Tree equality covers Git-visible content after clean filters (`autocrlf`/smudge may differ from worktree bytes; ignored files, external inputs, env stay outside). Gitlinks record pointers only (nested commits may be unpushed). Sparse checkouts fail every time—use a full checkout.
- **Program verdicts & enforcement:** `program_state.py` checks that a verdict's head exists, not that the proof ran on a clean checkout (self-asserted); run receipts catch dirty checkouts. Plan actions reflect plan claims, not current authority. Gates are agent-invoked checks, not host enforcement; clean filters like LFS may write caches during reads. Older code still reads receipts with the additive `tree` field under its stricter snapshot rule.
