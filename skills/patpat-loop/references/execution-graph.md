# Execution Graph

Use this graph to reduce degrees of freedom while preserving judgment.

```text
FRAME
  -> INSPECT
      -> READ-ONLY ANSWER -> REPORT
      -> DESIGN GATE -> PROOF CONTRACT
      -> PROOF CONTRACT
          -> ACT
              -> VERIFY
                  -> REPORT (non-shipping local reversible edits only)
                  -> REVIEW
                      -> changes required -> INSPECT / PROOF CONTRACT / ACT -> VERIFY
                      -> LEARN? (recurring failure only)
                          -> propose the smallest durable edit and wait for approval
                          -> encode only the approved lesson -> VERIFY -> REVIEW -> REPORT
                      -> REPORT (no lesson to encode)

REPORT --delivery intent only--> patpat-ship (external; run remains terminal)
patpat-ship -> LAND? -> MERGE (explicit land or merge; green reviewed PR)
```

Inspect, execute, or measure before asking. Ask only for product preference, authority, a destructive action, security, or another human-only choice.

Choose the smallest reliable path from signals: reversibility, blast radius, uncertainty, external side effects, security, auth, billing, architecture, duration, parallel need, and delivery or merge intent. Do not expose named user-selectable modes. Default commit-and-PR requires delivery intent.

Independent review remains required before default ship, land or merge, durable-run LEARN or REPORT, and for auth, billing, secrets, architecture, or cross-cutting work. Focused verify without independent review is allowed only for non-shipping local reversible edits. Mutating work still defines the 5-field proof contract before editing and still verifies on the authoritative surface. `REPORT` ends the run; conditional delivery is a separate `patpat-ship` workflow and does not reopen run state.

Failure edges:

```text
VERIFICATION, REVIEW, PROVIDER, OR USAGE CONTRADICTION
  -> requirement or design assumption invalid -> INSPECT (resolve/design first)
  -> claim, surface, action, or expectation invalid -> PROOF CONTRACT
  -> implementation wrong under a valid contract -> ACT
  -> valid claim lacks evidence -> VERIFY
  -> environment blocker -> INSPECT or report the blocker

LEARN?
  -> recurring failure -> propose the smallest enforceable constraint
       -> wait for approval before any edit
       -> shared or user-global change -> require explicit authority
       -> approved edit -> VERIFY -> REVIEW -> REPORT
       -> approval pending -> remain at LEARN
       -> approval declined -> REPORT without editing
  -> one-off fact       -> REPORT
```

Stop at an approval gate when the next transition would delete data, alter production, weaken a safety boundary, change billing or permissions, force-push, publish a package, or deploy. Explicit Patpat activation authorizes the loop, proof, and verify; default commit-and-PR still requires delivery intent. Merge still requires explicit land or merge language and green checks. Overnight, going to bed, and don't-stop language are delivery intent and stop at merge-ready.

## Bounded retry and Diagnostic Delta

Identify a repeated failure by the same proof step and stable blocker or error signature. Record the relevant candidate snapshot for each failure, but a changed snapshot alone does not break the streak when successive fixes preserve the same failed premise. A retry must add evidence or change the hypothesis, implementation, verifier, or environment; command spelling alone is not a change.

After the second consecutive failure, stop before any third execution and record one compact `Diagnostic Delta`. It must state `Expected`, `Actual`, `Changed`, `Hypothesis`, and `Next`:

```text
Expected: <predeclared observation>
Actual: <observed result and stable error signature>
Changed: <evidence or variable changed since the prior attempt, or none>
Hypothesis: <falsifiable causal explanation>
Next: <one discriminating action>
```

A third attempt is allowed only when `Next` changes at least one of the hypothesis, implementation, verifier, environment, or available evidence. Never rerun the same command against the same relevant state merely to seek a different result. If the discriminating action crosses the approved task boundary or requires new authority, follow [pause safely](../playbooks/pause-safely.md): preserve the current safe state and report the delta, boundary, and exact evidence or authority needed. After three failures caused by the same unchanged blocker, report the blocker and the evidence required to continue; durable runs enter `BLOCKED`.

`patpat-run` persists only the mutating path through this graph. Read-only answers and diagnosis-only blockers report directly without creating durable run state.

In durable runs, VERIFY and REVIEW may return directly to INSPECT or PROOF_CONTRACT. Returning to an earlier contract decision clears the old contract and verification/review receipts and advances the evidence epoch; record the revised 5-field contract before ACT. An initial contract recorded during INSPECT survives the forward transition to PROOF_CONTRACT. Record the contradiction and next decision in the existing decision trail. REPORT remains terminal: new post-delivery evidence starts a new scoped run if durable state is needed, without reopening old approval or proof.

After an approved edit, `VERIFY` advances the evidence epoch and invalidates prior verification and review receipts; obtain a fresh independent review before `REPORT`. The LEARN approval hold is a human authorization boundary, not a receipt enforced by `run_state.py`. Treat `LEARN` as proposal-pending; do not edit or transition to `VERIFY` until explicit approval is received.
