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
                      -> LEARN?
                          -> REPORT
                              -> DEFAULT SHIP (commit + PR)
                                  -> LAND? -> MERGE green verified PR
```

Inspect, execute, or measure before asking. Ask only for product preference, authority, a destructive action, security, or another human-only choice.

Choose the smallest reliable path from signals: reversibility, blast radius, uncertainty, external side effects, security, auth, billing, architecture, duration, parallel need, and delivery or merge intent. Do not expose named user-selectable modes. Default commit-and-PR requires delivery intent.

Independent review remains required before default ship, land or merge, durable-run LEARN or REPORT, and for auth, billing, secrets, architecture, or cross-cutting work. Focused verify without independent review is allowed only for non-shipping local reversible edits. Mutating work still defines the 5-field proof contract before editing and still verifies on the authoritative surface.

Failure edges:

```text
VERIFICATION, REVIEW, PROVIDER, OR USAGE CONTRADICTION
  -> requirement or design assumption invalid -> INSPECT (resolve/design first)
  -> claim, surface, action, or expectation invalid -> PROOF CONTRACT
  -> implementation wrong under a valid contract -> ACT
  -> valid claim lacks evidence -> VERIFY
  -> environment blocker -> INSPECT or report the blocker

LEARN?
  -> recurring failure -> encode the smallest enforceable constraint -> VERIFY
  -> one-off fact       -> REPORT
```

Stop at an approval gate when the next transition would delete data, alter production, weaken a safety boundary, change billing or permissions, force-push, publish a package, or deploy. Explicit Patpat activation authorizes the loop, proof, and verify; default commit-and-PR still requires delivery intent. Merge still requires explicit land or merge language and green checks. Overnight, going to bed, and don't-stop language are delivery intent and stop at merge-ready.

Use a bounded loop. A retry must add evidence or change the hypothesis, implementation, verifier, or environment. After three failures caused by the same unchanged blocker, report the blocker and the evidence required to continue.

`patpat-run` persists only the mutating path through this graph. Read-only answers and diagnosis-only blockers report directly without creating durable run state.

In durable runs, VERIFY and REVIEW may return directly to INSPECT or PROOF_CONTRACT. Returning to an earlier contract decision clears the old contract and verification/review receipts and advances the evidence epoch; record the revised 5-field contract before ACT. An initial contract recorded during INSPECT survives the forward transition to PROOF_CONTRACT. Record the contradiction and next decision in the existing decision trail. REPORT remains terminal: new post-delivery evidence starts a new scoped run if durable state is needed, without reopening old approval or proof.
