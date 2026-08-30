# Review and Ship

Verification asks whether the intended claim holds. Review asks what the implementation or proof missed. Keep those judgments separate before delivery.

## Review against the contract

The reviewer reads the request, diff, affected contracts, and evidence. It tries to falsify correctness, regression safety, security, performance, and side-effect claims without editing the implementation.

Useful findings state:

- the concrete failure;
- the code or evidence anchor;
- why it matters;
- the smallest safe correction.

Style preferences without behavioral impact stay out of the blocking set.

## Re-run after material change

Evidence belongs to the artifact it tested. If review changes the implementation, rerun the affected checks and review the current head. Do not reuse a green result from an earlier diff.

## Ship one coherent change

After explicit Patpat activation, successful proof, and independent review:

1. inspect git status and the complete in-scope diff;
2. exclude unrelated files, secrets, local configuration, and generated noise;
3. create one meaningful commit;
4. non-force push the branch;
5. open or update one ready pull request;
6. watch required checks and address evidence-backed review findings.

The pull request should explain the changed behavior, why it changed, how it was verified, and what remains uncertain.

Provider observations must bind the provider repository, pull-request number, head, and base branch to the expected target and include PR state, unresolved review-thread count, checks, review decision, draft state, and mergeability. A different provider target, closed or merged PR, changed head or base, or any unresolved review thread fails closed before merge-ready handoff.

On GitHub.com, `skills/patpat-ship/scripts/github_observe.py` captures this contract through a static read-only GraphQL query pinned to `github.com`. It requires an explicit expected head and base, never prints credentials, and refuses incomplete pagination instead of treating a truncated result as complete. Name required checks from verified repository policy. An empty required-check list fails closed unless `--allow-no-required-checks` explicitly records that CI is not required; do not use that override to bypass an unknown policy. Pipe the observation JSON into `pr_watch.py`; keep polling and every provider mutation outside both scripts.

```bash
python3 skills/patpat-ship/scripts/github_observe.py \
  --repository OWNER/REPO \
  --pull-request 17 \
  --expected-head FULL_COMMIT_SHA \
  --expected-base main \
  --required-check tests \
  --deadline 2026-08-30T00:00:00Z \
  | python3 skills/patpat-ship/scripts/pr_watch.py --input -
```

Observation schema v4 binds the expected base branch and the explicit no-required-check override, then evaluates freshness against the watcher's own UTC clock. Set a bounded `max_observation_age_seconds`; expired observations or timestamps beyond the bounded clock skew cannot become merge-ready evidence. Older observations fail closed and must be recollected; do not fill new fields from guesses.

## Keep merge authority separate

Opening a pull request is the default delivery boundary. `Finish`, `keep going`, `overnight`, or `babysit` do not authorize merge. Only explicit `land` or `merge` language permits Patpat to merge a green reviewed pull request. Production deployment and package publication remain separate approval gates.

Next: [Run durable work](./06-durable-runs.md).
