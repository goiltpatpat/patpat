# Recipes and Failure Modes

Use natural goals with observable outcomes. These prompts are starting points, not required syntax.

## Inspect without editing

```text
/patpat trace how session expiry reaches the UI. Show the owning layers and evidence. Read-only.
```

## Fix through reproduction

```text
/patpat reproduce the duplicate charge in the sandbox path first. Preserve every billing gate. Fix the root cause, rerun the same path, and request extra review.
```

## Make a bounded feature change

```text
/patpat add CSV export using the existing report query. Preserve column order and permissions. Verify the downloaded file with a representative fixture.
```

## Measure performance

```text
/patpat reduce peak memory for this import below 500 MB using the same dataset and environment. Keep output identical and report before and after measurements.
```

## Pause safely

```text
/patpat pause safely. Record the current proof, blocker, exact branch state, and next command. Do not open a PR.
```

## Drive a pull request without merging

```text
/patpat babysit this PR until required checks pass and review findings are resolved. Stop merge-ready.
```

## Common failure modes

- **Listing a ceremony instead of a goal.** A prescribed chain of skills can force the wrong order. State the outcome, constraints, and proof surface.
- **Treating installation as discovery.** Prove the skill in a fresh host task after every install or catalog-changing update.
- **Claiming success from a proxy.** A build is not proof of a user flow, stored value, network effect, or performance target.
- **Fixing before reproduction.** A plausible patch without the original failure can hide the real cause and cannot prove the repair.
- **Running writable agents in one worktree.** Use isolated worktrees or run serially.
- **Using old evidence after a change.** Bind proof to the current artifact and rerun affected checks.
- **Accepting every review comment.** Act on concrete correctness, safety, regression, and maintainability findings; dismiss unsupported preferences with reasons.
- **Turning long work into endless retries.** Use a checkable finish condition and stop after the third identical blocker.
- **Confusing PR delivery with merge authority.** Patpat may open a ready PR when delivery intent exists; merge still requires explicit `land` or `merge` language. Activation alone does not ship.
- **Adding project knowledge to the core.** Prefer a project verifier, local rule, or narrow playbook over another global abstraction.

Return to the [guide index](./README.md) or inspect the [capability map](./capability-map.md).
