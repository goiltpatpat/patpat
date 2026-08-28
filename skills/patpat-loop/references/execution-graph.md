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
                  -> REVIEW
                      -> LEARN?
                          -> REPORT
                              -> DEFAULT SHIP (commit + PR)
                                  -> LAND? -> MERGE green verified PR
```

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

Stop at an approval gate when the next transition would delete data, alter production, weaken a safety boundary, change billing or permissions, force-push, publish a package, or deploy. Explicit Patpat activation authorizes default commit-and-PR after proof unless a higher-priority rule or opt-out blocks it. Merge still requires explicit land or merge language and green checks. Overnight, going to bed, and don't-stop language stop at merge-ready.

Use a bounded loop. A retry must add evidence or change the hypothesis, implementation, verifier, or environment. After three failures caused by the same unchanged blocker, report the blocker and the evidence required to continue.

`patpat-run` persists only the mutating path through this graph. Read-only answers and diagnosis-only blockers report directly without creating durable run state.
