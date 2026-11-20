# Behavioral Evaluation Playbook

Read [proof over proxy](../principles/proof-over-proxy.md) and [earned parallelism](../principles/earned-parallelism.md).

## Evidence-feasibility preflight

Before freezing the rubric, make one read-only pass over existing in-scope evidence:

1. **Coverage.** Map every material user requirement and safety constraint to a mandatory criterion. Optional checks are non-gating. Incomplete coverage -> name gap, mark `INCONCLUSIVE`, do not freeze rubric or claim pass.
2. **Oracle and capture.** Name the observable oracle and existing evidence source per criterion (static evidence only for static requirements; missing oracle = `INCONCLUSIVE`). For event-triggered or asynchronous criteria, distinguish a product deadline from the evaluator's observation window. Timing claims need a documented or user-approved bound (else `INCONCLUSIVE`); otherwise predeclare one capture window (no event within it = `INCONCLUSIVE`, not `FAIL`; never extend or poll mid-trial).
3. **Capability and authority.** For local-only criteria, inspect path and artifact access. For host/provider criteria, inspect tool registration, connection, exact operation/schema, and authorization separately from existing metadata. Record the grant or policy and its scope when authority is required. Reuse one current receipt per host/session unless binding changes. Presence, credentials, or descriptions alone do not prove authorization, schema compatibility, or execution. If operation/schema metadata is not inspectable, mark only the dependent criterion `INCONCLUSIVE`. If live provider access is required and no approved read-only evidence establishes connection, record connection as `UNKNOWN` and the dependent criterion as `INCONCLUSIVE`; never probe a provider during preflight. Distinguish model-host transport from calls to the provider under test; report only what receipts prove and do not claim zero network activity without transport evidence.
4. **Isolation.** Record the already-approved surface and scope (host, project/provider, state, allowed actions, side effects). Verify with inspectable evidence that the current session is bound to that exact isolated target. A package copy or Git worktree does not prove independent provider state. If approval, its scope, or the current target binding is missing or ambiguous, do not run the dependent criterion; do not create a canary or disposable provider state to make it feasible.
5. **Candidate identity.** For claims about a candidate skill, verify with inspectable path and hash receipts that the actual loaded skill and relevant guidance bytes match the candidate; a hash of the repository copy alone does not prove the loaded bytes. If source identity is missing, mismatched, or uninspectable, mark candidate attribution `INCONCLUSIVE` and skip only that candidate-specific trial.
6. **Preflight status.** Use only `READY` or `INCONCLUSIVE` at preflight. `READY` is not a behavioral `PASS`. `UNKNOWN` describes a fact, not a status. Report per material criterion reusing current receipts. When a required fact is missing, mark only its dependent criterion `INCONCLUSIVE`, record the gap once, skip it for this run, and continue independent safe checks. Treat `INCONCLUSIVE` as terminal for that criterion in this run: do not repeat the same check, broaden the search, poll, probe, or ask the same question again. Reopen only after new inspectable evidence or a material change to scope, host, connection, contract, or candidate source. Trial verdicts remain `PASS`, `FAIL`, or `INCONCLUSIVE`.

For preflight-only requests, report one compact result and stop before routing or trials. A request for another report alone does not reopen an `INCONCLUSIVE` criterion: reuse its prior receipt/status if available; otherwise report that it is unavailable and keep the criterion `INCONCLUSIVE` without repeating the same check.

## Paired comparisons of skill effects

Use paired comparisons only when claiming a skill revision or set improves behavior. Before either arm, freeze: claim, baseline, prompt/inputs, task set, pair count, alpha, rubric, oracle, criterion priority, hard safety constraints, and pair decision rule.

- **New skill/set:** candidate set vs same context without those skills (keep shared repo/host policy unchanged; call it "without Patpat" only when all Patpat policy is absent).
- **Revision:** exact prior revision vs exact candidate revision.
- **Composition:** candidate composition vs strongest single skill or existing composition.

Match prompt/input bytes, repo snapshot, host/profile/version, model/settings, tools/schemas, permissions, context, and budgets wherever inspectable. Record per-arm loaded-skill inventories and hashes; never infer from repo contents or package listings. Isolate arms from each other's context, artifacts, rubric, expected outcome, and transcript; run sequentially unless isolation holds.

Predeclare task sensitivity: ≥1 required criterion must exercise the target capability with a distinguishing oracle (else incremental effect is `INCONCLUSIVE`, not `TIE`). Record delivery mode (`source-injected content`, `explicit invocation`, or `native host routing`) plus loaded paths/hashes: `source-injected content` proves supplied-content claims only; `explicit invocation` does not prove natural discovery; routing claims need a natural trigger and host routing evidence. For content-effect claims, verify non-skill surfaces do not leak target content to baseline (uninspectable = `INCONCLUSIVE`).

Score arms separately against the frozen oracle/rubric (`PATPAT_BETTER`, `BASELINE_BETTER`, `TIE`, `INCONCLUSIVE`); hard safety violations cannot be outweighed. Control mismatches, unproven inventories, missing oracle evidence, or an inconclusive arm make the pair `INCONCLUSIVE`. Never rerun a valid failed arm; a corrected candidate starts a new pair.

For paired trials with judgment-based criteria, use a separate authorized reviewer as an optional blind adjudicator. Give them both arms' outputs and the evidence needed to judge them in one packet, with randomized `A`/`B` labels and arm/model identifiers removed from metadata. The reviewer sees the same frozen rubric and scores each arm independently in one pass before unblinding. Keep the A/B mapping outside the packet until both scores are frozen. Preserve action and effect evidence needed for safety review; if the prompt, rubric, output, or required evidence reveals arm identity, record the review as unblinded. Use only a reviewer authorized to access the complete packet under the project's data-handling scope; do not send private repository content or transcripts to an external reviewer without explicit authorization. If no suitable reviewer or safe masking is available, use the frozen oracle and rubric and report `unblinded`; report reviewer independence separately and do not claim a blind review. Record whether the reviewer was separate from the trial executors and whether its model family differed. Blind judgment supplements, but never replaces, deterministic oracles or the hard safety veto.

Report every pair and criterion result plus summary counts without pooling away failures. Report time/token deltas only from comparable host receipts.

## Judges, uncertainty, and the failure flywheel

- **Deterministic oracles first.** Prefer binary/deterministic checks; reserve model judges for genuine judgment split into binary checks (never a holistic 1–5 score). Human scoring needs no calibration.
- **Calibrate gating model judges.** Before a model judge or blind adjudicator gates `PASS`, pair verdict, or promotion, calibrate each gating check against frozen human anchors (≥3 `PASS`, ≥3 `FAIL`, excluded from judge prompt):
  `python3 <patpat-eval skill directory>/scripts/eval_stats.py agreement --a <judge labels> --b <anchor labels> --min-kappa <frozen bar>`
  Default bar: Cohen's kappa ≥0.6 on ≥10 anchors (two humans: resolve first, bar `max(0.6, inter-human agreement)`; human agreement <0.6 means rewrite the check). Uncalibrated/`INCONCLUSIVE` judges stay advisory. Recalibrate on fresh held-out anchors after changing prompt, model, wording, or task distribution; never tune against an uncalibrated judge.
- **Comparisons as estimates.** Cite rates as `k/n` with Wilson 95% CI (`eval_stats.py rate`). Overall `PATPAT_BETTER`/`BASELINE_BETTER` requires exact sign test (`eval_stats.py pair`) clearing predeclared alpha (default `0.05`) on the frozen set. Exclude `INCONCLUSIVE` pairs from counts but report them (excess or one-arm skew -> overall `INCONCLUSIVE`). If planned pairs `< min_discordant_for_any_verdict`, state upfront that no overall verdict is reachable. Never switch on descriptive/`INCONCLUSIVE` results; statistics never override safety vetoes or failed mandatory criteria.
- **Failure flywheel.** Add privacy-safe regression cases from real escaped failures with frozen expected behavior; move consistently passing cases to a regression tier between runs (excluded from comparison claims) and track origin.

## Trial execution and receipts

1. Declare capability, failure conditions, and rubric before trials.
2. Prepare one positive trigger, one neighboring negative trigger, and a representative task when practical.
3. Use the approved surface only (no canary/disposable project); keep eval/judge/rubric vocabulary out of candidate-visible paths and prompts.
4. Run trials blinded to expected conclusion, rubric, and other arms. Hash exact prompts and frozen rubric before execution; bind prompt receipts to host receipts (redact secrets); preserve raw event stream/transcript by digest.
5. Inspect artifacts, commands, evidence, cleanup, and scope; verify post-cleanup receipt digests once (`INCONCLUSIVE` on mismatch; do not rerun solely to recreate receipts).
6. Score against the rubric, not self-reports. On missing/contradictory live results, check observer health once from existing evidence (never probe provider); if unresolved, mark `INCONCLUSIVE` and stop. After fixing a verifier defect, rerun only the invalidated check once; never rerun a valid failed trial.
7. Separate verifier/environment limitations from skill defects.
8. Promote, revise, or reject from observed behavior.

For stochastic/routing trials, predeclare bounded repeats (never increase mid-run); run sequentially unless state is independently isolated; if unsafe, run non-mutating cases only and mark repeat-rate claims `INCONCLUSIVE`. Each behavioral criterion needs an observable oracle (missing = `INCONCLUSIVE`); supervise process adherence, not outcome flukes.

Live-agent receipts record (reusing per host/session until binding changes): host/version, Patpat revision + uncommitted candidate hashes, frozen rubric, prompt & tool-schema paths/digests, actual loaded skill/guidance paths/hashes (both arms for pairs; uninspectable = `INCONCLUSIVE`), raw transcript path/digest, before/after artifacts/commands, cleanup, and verdict. Missing raw evidence = `INCONCLUSIVE`; receipts from another revision/host are stale.

Judgment failure classes are instruction-contract checks, not live-agent behavioral proof. Examples: unnecessary questions/planning/artifacts/fan-out/abstraction, over-rigor on simple work, under-escalation on risky work, proxy proof, symptom patches, ignored architecture friction, context-window waste, and crossed authority.
