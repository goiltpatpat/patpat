# Proof Over Proxy

Define the claim before choosing a check.

Translate every material user requirement, including preservation and safety constraints, into an observable Claim and Expect in the existing 5-field proof contract. For several requirements, reuse short labels across Claim, Surface, Action, and Expect, then record a result or named evidence gap for each label. Keep one claim inline for a simple edit; do not create a separate requirements document. Reconcile coverage with the request before ACT and before claiming verified; an omitted requirement is an evidence gap even when every declared check passes. Change an expectation only when requirement or contract evidence justifies it, not to fit a failing result.

- Identify the authoritative artifact or user surface.
- Capture a baseline or reproduce the symptom when relevant.
- Run the smallest targeted automated check.
- Exercise the real behavior when practical.
- Observe the result and material side effects directly.
- Record the action, result, and limitation.

For tests and evaluators, call the subject through the interface its users or the authoritative verifier uses and assert a literal observed result or material side effect. A check that would still pass if the subject or imported implementation returned `undefined` or `None`, or that only proves a function was called, a constant was copied, or a fixture agrees with itself, is not behavioral proof. For void or side-effect-only behavior, assert the changed state or emitted effect; for async behavior, await the authoritative result; for nondeterministic behavior, assert a bounded invariant or independently derived effect rather than an exact unstable value. Replace proxy checks with a concrete input and expected output/effect. The opposite failure also counts: a test that fails when only internals change and every observable result stays the same is pinned to the implementation, so rewrite it against the contract or delete it. If a behavioral claim has no observable contract, mark the evidence `INCONCLUSIVE`; classify a claim as static only when the requirement itself is static from the outset.

Classify the oracle as repository, runtime, independent reference, or lockstep. Claims of runtime equivalence require an independent reference or lockstep comparison; a build, local implementation, or same-context reviewer cannot prove equivalence.

Bind durable evidence to the exact revision or snapshot it checked, the relevant inputs and environment, and the oracle used. A material change to any binding makes the evidence stale; recollect it instead of carrying a green result forward.

## Close the deliverable set

Reconcile each required deliverable and provider or destination against the actual output before claiming completion. Inspect each output in its intended form; for a user-facing image, interactive artifact, or web page, inspect the rendered or live surface when a suitable viewer is available. File existence alone is not proof.

Report evidence separately for each output. Use `partially verified` when an output exists but required evidence could not be checked. If a required output is missing or failed, report the task as incomplete and name that output; success elsewhere must not hide it.

Do not treat compilation, test success, file timestamps, cached output, or an agent summary as proof of a different claim.

Delivery receipts prove delivery only. When the requested outcome depends on post-delivery behavior, inspect that surface within existing authority or name the pending observation and responsible handoff. Keep the overall outcome partially verified until that evidence exists; do not infer permission to deploy or mutate production to obtain it.
