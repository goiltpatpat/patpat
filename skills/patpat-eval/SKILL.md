---
name: patpat-eval
description: Evaluate whether an agent skill triggers and performs correctly using isolated, evidence-based trials. Use after non-trivial skill changes or when routing quality is uncertain.
---

# Patpat Eval

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md) and apply the [behavioral evaluation playbook](../patpat-loop/playbooks/behavioral-eval.md).

Define the target behavior and rubric before running a trial. Include at least one prompt that should trigger the skill and one neighboring prompt that should not. Run candidates in isolated temporary workspaces with equivalent context, sanitized labels, and no hidden access to the expected conclusion.

Judge produced artifacts, commands, observations, scope control, and cleanup. Do not treat an agent's explanation or confidence as evidence. Record environmental limits and keep comparisons sequential unless isolation and integration proof have earned parallel execution.

Promote the skill only when structural validation passes and the behavioral evidence satisfies the predeclared rubric.
