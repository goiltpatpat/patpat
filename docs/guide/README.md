# The Patpat Guide

Patpat is an engineering control loop for work that must be proven. Give it the outcome, the constraints, and the observation that would count as success. Patpat chooses the narrowest playbook that can close that loop.

Read these pages in order once. Return to a page when its decision becomes relevant.

1. [Install and prove discovery](./01-install-and-prove.md). Separate package installation from prompt-time skill discovery.
2. [Route work through Patpat](./02-operating-loop.md). State the goal and proof surface; let the router select the workflow.
3. [Understand and design](./03-understand-and-design.md). Establish repository truth, blast radius, and contracts before editing.
4. [Build, debug, and verify](./04-build-debug-and-verify.md). Make the smallest safe change and prove it on the strongest practical surface.
5. [Review and ship](./05-review-and-ship.md). Challenge the evidence, then commit and open a focused pull request.
6. [Run durable work](./06-durable-runs.md). Pause, resume, and finish multi-phase work from content-bound evidence.
7. [Earn parallelism](./07-earned-parallelism.md). Isolate work before increasing concurrency.
8. [Extend and evaluate](./08-extend-and-evaluate.md). Add project rules, verifiers, and skills without bloating the core.
9. [Recipes and failure modes](./09-recipes-and-failure-modes.md). Copy useful prompts and avoid common trust failures.

The [installation reference](./installing.md), [extension reference](./extending.md), and [capability map](./capability-map.md) hold details that should not be repeated across the tutorial.

## If you remember one thing

Give Patpat a claim and a way to falsify it:

```text
/patpat the retry path writes duplicate rows. Reproduce it against the real write path, fix the root cause, and show the resulting records.
```

Do not list the skills you think it should call. A checkable outcome is better routing input than a ceremonial workflow.

Next: [Install and prove discovery](./01-install-and-prove.md).
