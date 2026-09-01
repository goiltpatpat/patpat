# Extend and Evaluate Patpat

Keep Patpat's core small. Add repository-specific truth at the narrowest layer that can enforce it.

## Choose the extension point

| Need | Extension |
| --- | --- |
| One durable engineering invariant | Add a short principle reference |
| A repeatable sequence inside the main loop | Add a playbook |
| A focused operation users invoke directly | Add a skill folder with `SKILL.md` |
| Proof against a real project surface | Add or maintain a project verifier |
| Host-specific read-only behavior | Add a thin native adapter only when the host contract is proven |

Use the [extension reference](./extending.md) for structure and validation details.

## Prefer a project verifier

The highest-value extension is often a verifier that can drive the real application, inspect the authoritative state, and clean up safely. Keep environment knowledge with the project instead of expanding the general plugin with one repository's commands. Give each verifier a small feature map that links user claims to source entry points, exact exercises, proof surfaces, prerequisites, and cleanup. Prove one mapped feature before treating a new verifier as usable; maintainers later drive every mapped feature or record why it is unreachable.

```text
/patpat create a project verifier for the import flow. It must seed a fixture, run the real command, inspect persisted rows, and remove test data.
```

## Write operational skill text

Each skill lives in its own folder and uses a `SKILL.md` with `name` and `description` frontmatter. Write imperative instructions. State inputs, stop conditions, proof, and outputs. Reference detailed material instead of repeating the operating protocol.

## Evaluate behavior, not prose

Test whether the skill triggers on representative prompts, reads the required sources, follows its constraints, and produces the expected evidence. Keep candidate tasks isolated and organic. Review actual files and actions; do not score an agent from its self-report alone.

Patpat's deterministic eval scripts are contract tests, not live-agent evidence. To run Patpat's Codex contract canary, commit the candidate revision, then run `python3 scripts/probe_codex_behavior.py --model <requested-model> --output-dir /absolute/new/non-git/evidence-directory`. The manual canary installs that exact revision in an isolated Codex home, runs one read-only and one bounded-mutation task, rejects observed mutation-capable commands on the read-only path, checks response-shape conformance, preserves private JSONL plus `receipt.json` outside every Git worktree, writes a strict allowlisted `attestation.json`, and removes its temporary workspaces and copied authentication file. Inspect the attestation before explicitly posting or uploading it; generation alone does not make evidence externally inspectable. Promote only through `scripts/publish_codex_attestation.py`, which re-hashes raw receipt.json and trial event streams; generation is still not external. External inspectability is the Actions artifact, not a Git blob. Producer timestamps are wall-clock observations, not trusted timestamps. This canary is a detector, not a pre-tool gate, and it does not prove independent review, host-attested skill activation, every route, the resolved provider snapshot, unobserved transient effects, or transfer across Codex versions, requested models, hosts, and Patpat revisions.

## Learn only durable lessons

Convert a recurring failure into the smallest structural prevention: a boundary check, validator, playbook step, or principle. Do not add a rule for one unusual session. Do not edit a skill invisibly inside unrelated feature work.

Next: [Recipes and failure modes](./09-recipes-and-failure-modes.md).
