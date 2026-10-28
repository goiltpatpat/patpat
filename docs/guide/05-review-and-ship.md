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

When delivery intent exists, after successful proof and independent review:

1. inspect git status and the complete in-scope diff;
2. exclude unrelated files, secrets, local configuration, and generated noise;
3. create one meaningful commit;
4. non-force push the branch;
5. open or update one ready pull request;
6. watch required checks and address evidence-backed review findings.

The pull request should explain the changed behavior, why it changed, how it was verified, and what remains uncertain.

Provider observations must bind the provider repository, pull-request number, head, and base branch to the expected target and include PR state, unresolved review-thread count, checks, review decision, draft state, conflict-level mergeability, and the provider's aggregate merge state. A different provider target, closed or merged PR, changed head or base, unresolved review thread, or blocked aggregate merge state fails closed before merge-ready handoff.

On GitHub.com, `skills/patpat-ship/scripts/github_observe.py` captures this contract through a static read-only GraphQL query pinned to `github.com`. `mergeable` reports conflict-level mergeability; [`mergeStateStatus`](https://docs.github.com/en/graphql/reference/pulls#merge-state-status) reports the aggregate provider merge state. Only `CLEAN` and `HAS_HOOKS` can support a ready verdict. `UNKNOWN` and `UNSTABLE` remain pending. `BLOCKED` remains pending only while another observed gate is pending and no other blocker exists; it blocks when that gate clears without the provider state changing or when the watch budget expires. `BEHIND`, `DIRTY`, and `DRAFT` block readiness. The observer requires an explicit expected head and base, never prints credentials, and refuses incomplete pagination instead of treating a truncated result as complete. Name required checks from verified repository policy. An empty required-check set remains blocked, including when the legacy `--allow-no-required-checks` flag is present, because the current observation does not bind provider policy evidence. Pipe the observation JSON into `pr_watch.py`; keep polling and every provider mutation outside both scripts.

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

Review threads use bounded cursor pagination: at most 10 pages and 1,000 threads per pass, with one cumulative 1 MiB response budget and 30-second fetch budget across all requests. A complete single page needs one request. Multiple pages require two complete passes with identical ordered thread IDs/resolution states and unchanged PR metadata, including head, base, checks and review policy. Missing or repeated cursors, duplicate IDs, changed totals, inconsistent metadata, GraphQL errors and exhausted budgets refuse the observation. Checks, and rules used to prove a no-review exemption, still reject truncated connections at 100 entries. The two passes detect observable drift; they are not an atomic snapshot and cannot rule out changes between reads that revert, or changes after collection. This adapts the coverage lesson from [pstack #484](https://github.com/cursor/plugins/commit/ff8f83da30af) to Patpat's conservative readiness contract.

Observation schema v5 binds the expected base branch, includes the aggregate provider merge state, and preserves the no-required-check field for compatibility, but that field does not grant readiness without provider policy evidence. The CLI and both watchers timestamp the observation before fetching; collection time counts toward its age. The watcher evaluates freshness against its own UTC clock. Set a bounded `max_observation_age_seconds`; expired observations or timestamps beyond the bounded clock skew cannot become merge-ready evidence. Older observations fail closed and must be recollected; do not fill new fields from guesses.

A null GitHub review decision remains review-required unless the same response proves no approval requirement through the exact base ref's classic protection and complete [active repository/organization rules](https://docs.github.com/en/graphql/reference/git#ref), with `mergeStateStatus=CLEAN`. The observer retains that policy in `observation.review_policy`; it is provider-derived observation data, not a signed attestation. Approval counts, code-owner or last-push approval, and required reviewer lists prevent the exemption. Uninterpreted rule types remain conservative; the exemption currently recognizes pull-request, required-status-check, deletion, and non-fast-forward rules only. Explicit provider review restrictions and `--require-review` still win. This does not replace Patpat's independent local review or grant merge authority.

## Keep merge authority separate

Opening a pull request is the default delivery boundary. `Finish`, `keep going`, `overnight`, or a PR readiness handoff do not authorize merge. Only explicit `land` or `merge` language permits Patpat to merge a green reviewed pull request. Production deployment and package publication remain separate approval gates.

Next: [Run durable work](./06-durable-runs.md).
