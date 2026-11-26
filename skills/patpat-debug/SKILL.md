---
name: patpat-debug
description: Reproduce a defect, prove its root cause, and fix it with runtime verification evidence.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Codebase","requires_state":["workspace-root-open"],"produces_state":["defect-root-cause-isolated"],"verification_cmd":"git diff --check"}'
---

# Patpat Debug

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

For clear, bounded, reversible local work without delivery intent, use this skill and its relevant references; when routed from `patpat-loop`, its inline gate and principle index satisfy the start gate without loading the full operating protocol or rereading unchanged principle files. Otherwise read the [operating protocol](../patpat-loop/references/operating-protocol.md) and [execution graph](../patpat-loop/references/execution-graph.md) in full before acting. Escalate on uncertainty, security, auth, billing, secrets, architecture, cross-cutting work, or delivery intent. Define Claim, Surface, Action, Expect, and Cleanup before editing. Do not load the router or reread unchanged instructions already loaded in this session.

Read repository truth, [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), fix root causes, smallest safe change, and preserve safety. Apply the [defect playbook](../patpat-loop/playbooks/defect.md). When the user requests test-first work or a cheap deterministic regression target exists, apply [regression first](../patpat-loop/playbooks/regression-first.md).

Observe the failure before any production edit, or record an explicit why-not; report fail-before and pass-after on the same check.

## Phase 1: feedback-loop ladder and forced-mutation gate

Spend disproportionate effort building or tightening a fast, deterministic red loop before diagnosing. **Do not hypothesize root causes or edit production code without a red loop** (unless runtime reproduction is demonstrably unsafe or impossible, in which case record the explicit why-not, trace the contract or isolated non-harmful surrogate, and state that direct runtime proof is unavailable).

Climb to the highest fast, deterministic rung the defect supports, tightening upward whenever a loop is slow or flaky:

1. Existing unit or contract test.
2. New minimal unit or regression test isolating the defect.
3. Focused integration or component test with controlled fixtures.
4. One-shot CLI, script, or API invocation against local code.
5. Headless browser or UI driver script.
6. Local dev server plus scripted request or state replay.
7. Isolated container or sandboxed environment replay.
8. Captured trace, log, or fixture replay harness.
9. Narrowed HITL reproduction script (one-command launcher, exact human observation, clear pass/fail exit).
10. Static contract and code-path trace (only when runtime execution is unsafe or impossible; report missing runtime proof).

**Forced-mutation gate**: Before trusting a red loop, prove it is wired to the actual code under test. Introduce one temporary obvious mutation (or confirm a deliberate probe flips the observed output), verify the loop detects the change, revert the probe, and only then begin root-cause diagnosis. Never trust a reproduction that has not been proven sensitive to the subject.

Use **Causal-Chain Backtracking** to trace backward step-by-step from the observed failure to the earliest incorrect state transition or broken assumption before touching code (name the suspect boundary/line explicitly). If an initial probe or edit contradicts the active premise, rewind to the clean pre-edit breakpoint and update the causal hypothesis rather than stacking speculative patches on top of the last visible symptom.

If the user limited the request to diagnosis, stop after proving or bounding the root cause. Recommend the smallest patch without editing.

Change one causal variable at a time. Preserve only material failed hypotheses through the defect playbook as bounded, redacted evidence; do not retain raw logs or trivial attempts. Re-run the original reproduction when it remains safe and practical; otherwise run the predeclared non-triggering check and state the missing runtime proof. Never label an unobserved fix as verified.

When the defect is a mismatch against a reference image or migrated UI, apply the [visual equivalence playbook](../patpat-loop/playbooks/visual-equivalence.md) after reproducing the defect. Preserve the pre-edit reference and comparison harness.

## Proof closure

Define the five-field proof contract before any mutation. Close mutating work with:

- Always: [`patpat-verify`](../patpat-verify/SKILL.md), using authoritative evidence.
- When required: [`patpat-review`](../patpat-review/SKILL.md) for delivery intent, auth/security/billing/secrets, architecture or cross-cutting scope, durable-run LEARN or REPORT, land/merge, or another operating-protocol review gate.

For clear, bounded, reversible local work with none of those review requirements, proceed from verification to REPORT without independent review.
