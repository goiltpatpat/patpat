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
VERIFY FAILED
  -> implementation defect -> ACT
  -> verifier defect       -> PROOF CONTRACT
  -> environment blocker   -> INSPECT or REPORT

REVIEW FAILED
  -> unsafe or out of scope -> ACT or request authority
  -> evidence gap           -> VERIFY

LEARN?
  -> recurring failure -> encode the smallest enforceable constraint -> VERIFY
  -> one-off fact       -> REPORT
```

Stop at an approval gate when the next transition would delete data, alter production, weaken a safety boundary, change billing or permissions, force-push, publish a package, or deploy. Explicit Patpat activation authorizes the loop, proof, and verify; default commit-and-PR still requires delivery intent. Merge still requires explicit land or merge language and green checks. Overnight, going to bed, and don't-stop language are delivery intent and stop at merge-ready.

Use a bounded loop. A retry must add evidence or change the hypothesis, implementation, verifier, or environment. After three failures caused by the same unchanged blocker, report the blocker and the evidence required to continue.

`patpat-run` persists only the mutating path through this graph. Read-only answers and diagnosis-only blockers report directly without creating durable run state.
