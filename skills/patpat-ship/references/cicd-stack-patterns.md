# CI/CD Stack Patterns

Reference matrix for multi-stage CI, artifact verification, and idempotent release CD across common stacks. Adapt commands to the project's actual package manager and lockfile; run the exact CI commands locally before pushing.

## Stage Matrix by Stack

| Stack | Fast-Fail Gate (Lint / Format / Typecheck) | Test Matrix & Cache | Build, Smoke & Metadata Check | Release Parity & OIDC Publish |
| --- | --- | --- | --- | --- |
| **Python** | `ruff check .`, `ruff format --check .`, `mypy` or `pyright` | Matrix across supported `python-version` + OS (`ubuntu-latest`, `windows-latest` if path-sensitive); cache `pip` / `uv` / `poetry` via lockfile hash | `python -m build`, `twine check dist/*`, install wheel in clean venv and run import/CLI `--help` smoke | Assert `v<pyproject.toml version> == GITHUB_REF_NAME`; `sha256sum dist/* > SHA256SUMS.txt`; `pypa/gh-action-pypi-publish` with `id-token: write` inside `environment: pypi` |
| **Node / TypeScript** | `eslint .` / `biome check .`, `tsc --noEmit` | Matrix across LTS Node majors (`20`, `22`); `npm ci` / `pnpm install --frozen-lockfile` with lockfile cache | `npm run build`, `npm pack --dry-run` (verify tarball file list), execute built CLI/entrypoint smoke | Assert `v<package.json version> == GITHUB_REF_NAME`; `npm publish --provenance --access public` with `id-token: write` inside `environment: npm` |
| **Go** | `gofmt -l .` (must be empty), `go vet ./...`, `golangci-lint run` | Matrix across supported Go versions + target OS; `actions/setup-go@v5` built-in module cache | `go build ./...`, `go test -race ./...`, run compiled binary `--version` / `--help` smoke | Assert tag matches version constant/metadata; cross-compile checksums (`SHA256SUMS.txt`); idempotent GitHub Release upload (`--clobber` or tag-gated) |
| **Rust** | `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings` | Matrix across MSRV + `stable` and target OS; cache `~/.cargo` + `target/` keyed on `Cargo.lock` | `cargo test --locked`, `cargo build --release --locked`, `cargo package --list`, binary smoke | Assert `v<Cargo.toml version> == GITHUB_REF_NAME`; `SHA256SUMS.txt` for release archives; `cargo publish --locked` inside `environment: crates-io` |
| **Docker / Multi-Stack** | Per-stack lint/typecheck jobs in parallel + `hadolint Dockerfile` | Path-filtered or parallel per-language test jobs; BuildKit registry/GHA layer cache (`cache-from`/`cache-to`) | `docker build` + container startup/healthcheck smoke (`docker run --rm <img:sha> <smoke-cmd>`) | Tag images by immutable `sha-<short>` and semver tag; sign with Cosign/OIDC (`id-token: write` + `packages: write`) inside `environment: release` |

## Cross-Stack Hardening Rules

1. **Permissions**: declare top-level `permissions: { contents: read }` (or `{}`). Grant `write` scopes only at the job level where required.
2. **Concurrency**:
   - PR/branch CI: `group: ${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`.
   - Release/deploy: `group: release-${{ github.ref }}` with `cancel-in-progress: false`.
3. **Timeouts & Hygiene**: set `timeout-minutes` on every job; pin third-party actions to full commit SHAs with version comments (`# v4`) where security posture warrants it; avoid retired runners (`ubuntu-20.04`, `macos-11`/`12`, `windows-2019`) and deprecated Node 16/20 action majors.
4. **Release Gates**:
   - Require `environment:` or an explicit `if:` tag/release guard on every job holding `id-token: write` or running publish/deploy commands.
   - Verify manifest-to-tag version parity before any upload or publish step.
   - Keep uploads idempotent so a retried release job recovers cleanly without duplicating assets.
5. **Non-GitHub Providers**: map the same invariants to GitLab CI (`interruptible: true` on PRs, `false` on deploy; `id_tokens:` scoped to protected tag environments), CircleCI (restricted contexts + approval jobs), or Azure Pipelines (deployment environments + exclusive lock checks).
