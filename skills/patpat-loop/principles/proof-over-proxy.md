# Proof Over Proxy

**Rule:** Translate every material user and safety requirement into an observable 5-field proof contract (`Claim`, `Surface`, `Action`, `Expect`, `Cleanup`) before editing; never weaken an expectation to fit a failing result. Verify on the authoritative surface through the real user/verifier interface using the Onion Model: (1) Static/Type -> (2) Empirical Execution -> (3) Mutation Resilience (fault-inject to ensure tests fail on broken logic) -> (4) Adversarial Audit on high-risk boundaries (never burn review tokens before lower gates pass).

Reject synthetic mock illusions and reward-hacking bypasses (skipped tests, linter suppressions, empty catches, arbitrary sleeps). Derive expected values from the requirement or an independent reference, never by running the changed subject and copying its output; a baseline captured before a behavior-preserving change is that reference. The opposite failure also counts: a test that fails when only internals change and every observable result stays the same is pinned to the implementation, so rewrite it against the contract or delete it. Pair every "no call happened" assertion with a case where the call does happen. Assert error types/codes callers branch on, await async results, and assert changed state/effects for void calls. Classify oracles (repository, runtime, independent reference, lockstep), require independent/lockstep oracles for runtime equivalence, and bind durable evidence to exact revision, inputs, environment, and oracle (recollect if any binding changes).

**Test:** Would the check still pass if the subject returned `None`/`undefined`, skipped the work, or only called an internal helper? If yes, replace it with an observable input->effect oracle, or mark the claim `INCONCLUSIVE`.

## Close the deliverable set

Reconcile every required deliverable and destination against actual rendered or live output before claiming completion (file existence, compilation, timestamps, cached output, or delivery receipts alone are not proof). Report each output separately; use `partially verified` for unchecked outputs, and mark the task incomplete if any required output is missing or failed.
