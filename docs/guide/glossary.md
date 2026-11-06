# Glossary

The words Patpat uses, in plain terms. Reports use these words only when the reader needs them; otherwise they say the same thing in the reader's own words. Under each term, _Avoid_ lists words that blur it.

## Evidence

**Claim**: one sentence saying what will be true after the work, such as "a retry no longer writes a duplicate row".
_Avoid_: goal, ticket, task description

**Proof contract**: five fields defined before editing: Claim, Surface, Action, Expect, and Cleanup.
_Avoid_: test plan, acceptance checklist

**Authoritative surface**: the place where the claimed behavior actually happens or is used: the real command, the persisted rows, the rendered page, the provider's state.
_Avoid_: "it compiles", "tests pass" (those are proxies unless they exercise this surface)

**Proxy**: evidence about something other than the claim, such as a mock being called or a file existing. A proxy can point at a problem; it cannot prove the claim.
_Avoid_: smoke proof, sanity check

**Oracle**: what decides a check: a returned value, a changed state, an emitted effect, or a bounded invariant.
_Avoid_: assertion (an assertion can check a proxy)

**Receipt**: an inspectable record that binds evidence to the exact revision, inputs, and oracle it checked. A changed binding makes the receipt stale.
_Avoid_: log, summary, the agent's own account

**`verified`**: the claimed behavior was observed on its authoritative surface. Reports also use `partially verified`, `implemented but not verified`, and `not implemented`.
_Avoid_: done, works, should work

**`INCONCLUSIVE`**: required evidence is missing or cannot be inspected. It is not a failure and not a pass. It is final for that check in the current run, reopened only by new inspectable evidence or a material change to scope, host, connection, contract, or candidate.
_Avoid_: probably fine, flaky

## Work and authority

**Route**: the workflow chosen for the earliest unresolved decision: `inspect`, `debug`, `change`, `architect`, `verify`, `review`, `ship`, or `run`.
_Avoid_: mode (routes are chosen from evidence; Patpat exposes no user-selectable route modes; the optional session hook is a single on/off state)

**Playbook**: a decision path for one situation, such as a defect or a migration.

**Principle**: one durable rule, read when its trigger fires and cited only when it changed a decision.

**Delivery intent**: explicit commit, pull request, or ship language; `overnight`, `going to bed`, or `don't stop`; or explicit land or merge. Without it, changed work stops at the report with no commit or pull request. Higher-priority repository rules and `local only` override it.
_Avoid_: implied approval

**Land / merge**: required for merging, but not sufficient: the pull request must also be reviewed and its current head must pass its provider gate. `ship it` means commit and open a pull request, and overnight language stops at merge-ready.

**Independent review**: a read-only challenge of the change and its raw evidence, without the implementer's intended conclusion. A separate reviewer is used when available and authorized; otherwise a serial read-only pass is reported as such. A declared reviewer identity is not host-attested independence.
_Avoid_: second look

**Durable run**: multi-phase work that can pause and resume from content-bound gates, through `patpat-run`.

**Earned parallelism**: running several writable agents only after each slice is isolated and a stable verifier can judge each result. One owner is the default.

## Evaluation and formal checks

**Frozen rubric**: the criteria and oracles fixed before the first trial and never reinterpreted after seeing output.

**Calibrated judge**: a model judge whose labels agree with human anchor labels on the same checks. The default bar is Cohen's kappa at least 0.6 on at least 10 frozen anchors with at least 3 `PASS` and 3 `FAIL`. An uncalibrated judge is advisory only.
_Avoid_: LLM-as-judge score (without calibration)

**`reader-confirmed` / `agent-derived`**: whether a checked property was stated by the user or an existing contract, or written by the agent. A formal check of an `agent-derived` property proves conformance to an unconfirmed spec.

**Bug ledger**: the numbered record of bugs a formal check found and reproduced against real code, each with the reader's sentence, the broken rule, and its fix reference. A bug map draws the ledger on the current statechart.
