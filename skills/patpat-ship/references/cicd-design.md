# CI/CD Pipeline Design and Hardening

Reference playbook for designing, hardening, and auditing vendor-agnostic CI/CD and release pipelines under [`patpat-ship`](../SKILL.md).

## 1. Stack and Policy Discovery

CI is project-owned and vendor-agnostic: add or tune workflows only on explicit user request or after the user accepts a surfaced gap suggestion. Inspect language/runtime floor, package manager, lockfiles, existing CI provider (`.github/workflows/`, `.gitlab-ci.yml`, `.circleci/`, `azure-pipelines.yml`, `Jenkinsfile`), branch protection, and release targets. Use [CI/CD stack patterns](cicd-stack-patterns.md) for per-stack commands, caches, and matrices.

## 2. Multi-Stage CI Design (Shape-2)

- **Least-privilege permissions**: declare top-level `permissions: { contents: read }` (or `{}`) and grant `write` scopes only on the specific job that requires them.
- **Concurrency**: define `concurrency:` on every workflow—cancel redundant PR runs (`cancel-in-progress: true` on PR-only CI, or `cancel-in-progress: ${{ github.event_name == 'pull_request' }}` on shared PR/branch/tag workflows) and keep `cancel-in-progress: false` on release or deploy workflows.
- **Staged fast-fail gates**: run lint, format, and typecheck first; follow with cached runtime/OS test matrices, CLI/import smoke checks, and build plus artifact/metadata checks (`twine check`, `npm pack --dry-run`, binary smoke).
- **Strict, current tooling**: set `timeout-minutes` on every job; use current action majors and supported runners; keep gates strict with no `continue-on-error: true` or `|| true` / `|| :` / `; true` bypasses.

## 3. Idempotent Release CD and Supply-Chain Hygiene

- Verify tag-to-manifest version parity before building artifacts, emit `SHA256SUMS.txt`, and keep release uploads idempotent so retries recover cleanly without duplicate assets.
- Gate OIDC Trusted Publishing (`id-token: write`) and every publish or release step behind an explicit `environment:` or `if:` guard (or tag/release-only trigger).
- Pause for explicit user confirmation before any tag push, package publish, or production deploy, stating blast radius, rollback, and verification per the [operating protocol](../../patpat-loop/references/operating-protocol.md).

## 4. Local-First Pre-Push Gate and Remote Watch Handoff

Run the exact CI lint, typecheck, test, and build commands locally before pushing, and surface runner or action deprecations. Hand remote CI watch, check-run observation, and PR readiness to [`patpat-ship`](../SKILL.md) and [PR Readiness Handoff](../../patpat-loop/playbooks/pr-handoff.md).

## 5. Mechanical Verification

Run [`../scripts/verify_cicd.py`](../scripts/verify_cicd.py) (`python3 skills/patpat-ship/scripts/verify_cicd.py --root <workspace-root>`) and resolve all reported errors before claiming workflows are hardened or ready for delivery.
