---
name: patpat-eval
description: Evaluate whether an agent skill triggers and performs correctly using scoped, evidence-based trials. Use after non-trivial skill changes or when routing quality is uncertain.
disable-model-invocation: true
---

# Patpat Eval

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md) and apply the [behavioral evaluation playbook](../patpat-loop/playbooks/behavioral-eval.md).

Define the target behavior and rubric before running a trial. Include at least one prompt that should trigger the skill and one neighboring prompt that should not. Run trials against the user-authorized project. Use only an already-approved isolation surface when independent state is necessary; do not create a canary or disposable project solely for evaluation. If isolation needed by a criterion is unavailable, mark that criterion `INCONCLUSIVE`; other safe, non-mutating criteria may still be proven in one trial. Mark repeat-rate claims `INCONCLUSIVE` when equivalent independent trials cannot be run safely.

Judge produced artifacts, commands, observations, scope control, and cleanup. Do not treat an agent's explanation or confidence as evidence. Record environmental limits and keep comparisons sequential unless isolation and integration proof have earned parallel execution.

At least one frozen rubric criterion must use the behavioral oracle defined in [proof over proxy](../patpat-loop/principles/proof-over-proxy.md): an observable result or material effect through the interface the user or host uses. Reject a trial whose passing evidence only shows that a helper was called, a value is present, a constant or prompt is unchanged, or no exception was raised.

Freeze the rubric before the first trial. Record `PASS` only when inspectable evidence satisfies every predeclared criterion; record `FAIL` when observed behavior violates any criterion and `INCONCLUSIVE` when required evidence is missing or uninspectable. Never weaken or reinterpret the rubric after observing output. Do not rewrite a failed trial as a pass; record a corrected candidate as a new trial.

Promote the skill only when structural validation passes and the behavioral evidence receives `PASS` under the frozen rubric.
