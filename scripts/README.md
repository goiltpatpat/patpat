# Patpat scripts

Tooling in `scripts/` splits into **user-facing package & validation tools** and **internal verification, audit, and evaluation harnesses**. All scripts use Python 3.11+ with the standard library.

## User-facing tooling

| Script | Purpose |
| --- | --- |
| `validate.py` | Validate Patpat manifests, skill frontmatter, ontology graph, pinned protocol contracts, hooks, and internal links (`--self-test` runs validator contract tests). |
| `stage_plugin.py` | Stage a clean, allowlisted multi-host Patpat distribution without local Memory Bank, `docs/diagrams/`, or test corpora. |
| `stage_agent_plugin.py` | Stage a portable Agent Plugins 1.0 package with projected skill frontmatter and standard root manifest. |
| `install_skills.py` | Install canonical skills into an explicit Agent Skills directory with conflict refusal, atomic promotion, rollback, `--status`, and `--verify-ready`. |
| `update_skills.py` | Safely update an existing portable `install_skills.py` copy installation with backup and lock protection. |
| `verify_ready.py` | Verify host environment, `/patpat` discovery, hook status, and core route presence. |
| `check_attribution.py` | Enforce repository attribution policy (no AI-agent `Co-Authored-By:` trailers or generated-with footers). |

## Internal verification, audit, and eval harnesses

| Script | Purpose |
| --- | --- |
| `eval_adversarial_controls.py` | Adversarial safety and authority-boundary control checks. |
| `eval_inspect.py` | Routing and read-only boundary checks for `patpat-inspect`. |
| `eval_parallel.py` | Parallelism, isolation, and program-coordination evaluation harness. |
| `eval_representation.py` | Earned-representation and diagram/statechart routing evaluation harness. |
| `eval_routing.py` | Skill trigger and route-catalog evaluation harness. |
| `eval_why.py` | Rationale-forensics evaluation harness. |
| `smoke_antigravity_plugin.py` | Antigravity plugin packaging and validation smoke test. |
| `smoke_codex_plugin.py` | Codex plugin packaging and validation smoke test. |
| `smoke_grok_plugin.py` | Grok CLI plugin packaging and validation smoke test. |
| `context_footprint.py` | Measure prompt-time skill metadata and context footprint across hosts. |
| `dry_run_loop.py` | Deterministic dry-run harness for the Patpat loop state machine and gates. |
| `probe_codex_behavior.py` | Live Codex host behavior probe used for fixture attestation. |
| `publish_codex_attestation.py` | Record and verify Codex host fixture attestations. |
| `sanitize_logs.py` | Redact secrets and machine-local paths from evaluation logs. |
| `worktree_audit.py` | Audit Git worktrees for merged, abandoned, or dirty state. |
