# Delivery Proof

This is the contract between durable state and delivery. It decides which proof covers a commit, when each gate is checked, what a slice or a whole program may deliver, and what a merge must prove. Neither store grants authority; [default delivery](../../patpat-loop/playbooks/default-delivery.md) still reacquires it.

## Observed before this contract

Reproduced against 0.8.0 with `run_state.py` and `program_state.py` unmodified:

| Path | Observed | Why it matters |
| --- | --- | --- |
| Verify, review, stage | `ship` flips to failed | Snapshot hashes the index, so staging identical bytes voids proof |
| Verify, review, commit | `ship` and `merge` fail; `REPORT` refused | The documented order cannot reach merge |
| Verify, review, `REPORT`, commit | `merge` fails; no receipt or transition is possible | A terminal run is stranded |
| Commit, verify, review, `REPORT` | `ship` and `merge` pass | Merge was reachable only through an undocumented order |
| Verify, review, nothing committed | `ship` passes | **False pass:** `HEAD` lacks the proven change |
| Proof at `HEAD` with an unrelated dirty file | `ship` passes | **False pass:** the proof ran on bytes the head does not contain |
| Independent units with sibling heads | `delivery_admitted` true | No commit contains both; the combination was never proven |
| Live `HEAD` unproven and dirty | `delivery_admitted` true | Verdict heads are never compared with a checkout |
| One slice complete, sibling pending | `delivery_ready` false | Autopilot's slice delivery has no admissible state |

## Decisions

**A proof covers content, and a commit is bound by its tree.** A run receipt covers head `H` when both hold:

1. The tree of the worktree it proved equals `H^{tree}`, and the commit it was recorded on is `H` or an ancestor of `H`.
2. The checkout is clean at `H`, so what was proven is exactly what `H` contains.

The receipt records that tree, so it stays valid across staging and committing without re-recording anything. A program verdict names a commit directly, so condition 1 holds by identity and `check-delivery` enforces condition 2 at delivery. A verdict's actor attests that the proof ran on a clean checkout of that commit; the store cannot observe it, as the limits below state.

**Admission and exact-head proof are separate gates on the same receipts.**

| Gate | Asks | Passes when | Survives |
| --- | --- | --- | --- |
| `commit` | May this staged content become a commit? | Receipts cover the worktree, and the index holds exactly that content | Nothing: run it after staging |
| `ship` | May this head be pushed or exposed in a PR? | Receipts cover the worktree, and the checkout is clean at `HEAD` | Push, PR creation |
| `merge` | May this head land? | `ship`; `explicit-merge`; a ready `pr_watch` receipt bound to `HEAD`; `HEAD` contains the current base | Until any of those changes |

All three refuse at `BLOCKED`.

Either order reaches the same `ship` predicate. Proof-first is the default because delivery intent often arrives after proof. Commit-first is required when a proof depends on commit identity, such as a check reading `git log` or a version derived from Git, because tree equality says nothing about those inputs. A proof contract with such a dependency must commit first and prove at that head. Skip the `commit` gate when the content is already committed.

**`REPORT` stays terminal, and evaluating a gate is not recording.** Per the [execution graph](../../patpat-loop/references/execution-graph.md), delivery follows `REPORT` and does not reopen the run. Gates read state and Git, so all three can pass at `REPORT`, and the run can also stay open until delivery finishes. A new head or a late `land` starts a new scoped run at that head. Nothing reopens a run or transfers approval.

**A slice delivers on its own proof; a whole program delivers on a single integrated head.**

- *Slice:* `check-delivery --unit <id>`. The unit and all of its transitive dependencies are complete with fresh evidence, and the checkout is clean at the unit's head. Siblings may be pending. This does not read the program delivery gate, which belongs to the whole program.
- *Whole program:* `check-delivery` without `--unit`. Every unit is complete, the delivery gate is open, and one unit transitively depends on every other unit and contains their heads. That head is derived, not stored, so it cannot go stale. A stack's tip qualifies. Independent units do not, even if one head happens to contain another; deliver them as slices, or declare a final unit depending on all of them and prove that merge. Give that unit a whole-system proof, because only its own plan proof runs against the combination.

**A merge is proven only when the head contains the base.** If the head contains the current base, a merge commit, a squash, or a fast-forward produces the proven tree. Otherwise the result is a combination nobody ran, whatever the provider reports. After a queue sibling lands, the next slice updates onto the new base, records its new head, and proves it again.

**Each delivered head has one gate.** A program unit or integrated head uses `program_state.py check-delivery`, and any other durable work uses `run_state.py check-gate`. An objective-level run beside a program does not gate that program's heads.

## Commands

Program stores and run stores live under one worktree's Git metadata, so `--root` names the worktree that created the store. Removing a linked worktree deletes the run store inside it. Declare merge authority at `init --authority explicit-merge` or in the plan's `delivery` claim.

Save the provider receipt with `github_observe.py`, which prints the document `pr_watch.py` evaluates, including its policy. `pr_watch.py`'s own verdict output is not a receipt. A run reads it from `<run store>/provider-receipt.json`; the gate names that path when the file is missing. A program takes any path through `--provider-receipt`.

Run these in a POSIX shell. PowerShell 5.1's `>` writes UTF-16, which the gate refuses as unreadable. `<skills>` is the installed skills directory, which is `skills` in this repository. `--deadline` is a UTC timestamp ending in `Z`. Every Git command targets the delivered checkout with `-C`, so it acts on the head the gate proved, whatever the current directory is.

Single durable run, proof first. When the content is already committed, skip `git add`, the `commit` gate, and `git commit`:

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

Program slice. Omit `--unit` for the integrated head:

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

Each command exits 0 only on a pass.

## Shapes and signatures

```python
# run_state.py: run receipts gain one additive field, without a schema bump
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

The candidate is rebuilt from `HEAD` in a private index and object directory, so assume-unchanged flags cannot hide an edit, and a gate adds no objects and leaves the real index unchanged. `tree` is `None` when the repository holds any gitlink, including a clean submodule, because a gitlink records only a pointer. Such a repository has no proof-first path: receipts match only by exact snapshot, the `commit` gate refuses, and commit-first remains. A clean checkout also requires every populated gitlink to be clean at its own head, by the same rebuilt-tree check. A receipt recorded before this contract has no `tree` and follows the same rule.

## Failure modes

| Situation | Result | Next step |
| --- | --- | --- |
| Hook or amend changed the committed tree | `ship` fails as stale | Prove the new head |
| Same-tree amend or rebase of a proven commit | `ship` fails as stale | Prove the new head; a tree-equal reword on the proof's own base still passes |
| Partial or empty staging | `commit` fails | Stage exactly the proven content |
| Unrelated dirty files during proof | Once in-scope paths are staged, `commit` fails; `ship` fails | Commit the in-scope paths, then start a new run in a clean linked worktree at that commit |
| Repository holds a gitlink | `commit` fails | Commit first, then prove that head |
| Base moved | `merge` fails | Update onto the base and prove the new head |
| New head after `REPORT` | `ship` fails; the run cannot record | Start a new scoped run |
| `land` arrives after init | `merge` fails on authority | Start a new scoped run declaring it; old approval does not carry |
| Run stopped at `BLOCKED` | Every delivery gate fails | Resolve the blocker in a new run |
| Squash-landed dependency | Dependent head no longer contains it | Set the dependency head to the landed commit and prove again; downstream proof is revoked |
| Dependency reassigned or its evidence changed | Every slice above it fails | Prove the dependency again |
| Dispatch cutoff passed when a slice must update | `set-head` refuses | Run `set-gate dispatch open` with `--reason`, the same `--receipt` and `--integration-owner`, and either `--clear-budget` or `--deadline` with `--integration-reserve-minutes`. Do not close dispatch first; closing revokes every assignment and clears all proof |
| Independent units, whole-program request | The gate refuses to open | Deliver slices or add an integration unit |

## Rejected alternatives

- **Remove the index from the snapshot.** Staging would stop voiding proof, but committing would still void it, and the false passes on uncommitted or unrelated content would remain.
- **Always commit before proving.** This has the least machinery, but it commits before proof whenever intent is known and forces a second independent review of identical bytes whenever intent arrives late. Identical re-review invites rubber-stamping.
- **Reopen `REPORT`, or add a mutating `seal` step.** Either makes terminal state negotiable and adds a step that can be skipped, while gates derive the same answer from Git.
- **Store an integration head or an integration record.** This needs a schema migration and a value that can drift. Deriving it from declared dependencies and ancestry reuses unit assignments, verdicts, and invalidation.
- **Treat ancestry alone as integration.** A head that happens to contain a sibling never declared it, so nothing says its proof covered the combination, and upstream changes would not revoke it.
- **Count a provider's mergeable status as proof of the result.** A repository without strict branch protection reports `CLEAN` for a head behind its base.

## Falsifiers

The design is wrong if any of these can be produced. Each has a deterministic case in the [`run_state.py`](../scripts/run_state.py) or [`program_state.py`](../scripts/program_state.py) self-test.

1. `ship` passes on a head whose tree differs from the proven tree, or while the checkout differs from that head, including through hidden edits, unseen untracked files, or a repository holding a gitlink.
2. Staging and committing exactly the proven content makes `ship` or `merge` unreachable, whether or not the run is at `REPORT`.
3. `merge` passes when `HEAD` does not contain the supplied base, when the base is missing, or when the provider receipt names another head.
4. `check-delivery` passes for a checkout at another head, a dirty checkout, or a checkout from another repository.
5. A whole program is admitted when no unit both depends on and contains every other unit.
6. A complete slice is refused because an unrelated sibling is pending, or admitted while any transitive dependency is incomplete.

## Receipt files

`verify_review.py` and `verify_delivery.py` default to `.patpat/review-receipt.json` and `.patpat/delivery-receipt.json` in the worktree. An untracked file there dirties the checkout, so `commit`, `ship`, and `merge` refuse. Pass `--receipt` with a path outside the repository, or list the path in `.git/info/exclude`. Both receipts name a `head_sha`, so write them after the commit they describe. A proof-first review stays valid through its run receipt when the proven tree equals that head's tree; `verify_review.py` then needs a receipt naming the committed head, not a second review of identical bytes.

## Limits

- **Base value.** `--base-head` is supplied by the caller from a fresh fetch; `pr_watch` does not observe the base commit. Any ancestor of the head passes, including a stale base or the head itself, and it is not tied to the receipt's `base_ref`.
- **Timing.** The base or the PR head can change between the gate and the merge.
- **Merge methods.** A provider's rebase merge replays commits, so a head with a hand-edited merge commit can produce a different tree. Check the merged revision afterward, as [authorized delivery](../../patpat-loop/playbooks/authorized-delivery.md) requires.
- **Tree versus bytes.** Tree equality covers Git-visible content after clean filters. With `autocrlf` or smudge filters, a proof read worktree bytes the tree stores differently. Ignored files, external inputs, and the process environment stay outside it, as they do for the snapshot.
- **Gitlinks.** A commit-first head holding a gitlink for an embedded repository contains only a pointer. The proof read the nested files, but that nested commit may not be pushed anywhere.
- **Sparse checkouts.** Absent files look deleted from the rebuilt tree, so a sparse worktree is refused every time. Prove and deliver from a full checkout.
- **Program verdicts.** The store checks that a verdict's head exists, not that the proof ran on a clean checkout of it. A verifier passing on an uncommitted fix that is later discarded is not detectable here, and verdict actors and evidence stay self-asserted. A run receipt does catch this case.
- **Plan actions.** A passing check reports the plan's claim, not current authority.
- **Enforcement.** These gates are agent-invoked checks, not host enforcement. Clean filters such as LFS may write their own caches while a gate reads the worktree.
- **Rollback.** Revert the commit. Program stores are unchanged, and run receipts with the extra field remain readable by older code, though older code applies its stricter snapshot rule.
