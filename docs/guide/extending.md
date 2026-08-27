# Extending Patpat

Extend Patpat only when a recurring task or observed failure mode changes agent decisions.

## Choose the smallest extension

1. Tighten an existing principle when one invariant was missing.
2. Adjust a playbook when sequencing or evidence requirements were wrong.
3. Add a workflow skill when a distinct user intent needs independent discovery.
4. Add a specialized agent only when the role recurs, has isolated ownership, and improves measured outcomes.
5. Add a script when deterministic execution or validation is safer than repeated prose.

Do not add a file when an existing canonical location can absorb the lesson cleanly. Keep host-specific commands out of engineering workflows; centralize verified installation commands in `patpat-setup` and the installation guide.

## Add a workflow skill

Apply [`patpat-skill`](../../skills/patpat-skill/SKILL.md). Create `skills/<name>/SKILL.md`. Use lowercase kebab-case for both the folder and frontmatter `name`. Write a discriminating `description` that states the capability and trigger. Keep the body imperative and reference shared principles instead of duplicating them.

Define:

- inputs and repository evidence to inspect;
- the bounded procedure;
- the proof contract and authoritative surface;
- stop and approval conditions;
- the output contract.

Add the route to `patpat-loop` only when the new intent cannot route safely through an existing workflow.

## Evaluate the extension

Run `python3 scripts/validate.py --self-test`, then apply [`patpat-eval`](../../skills/patpat-eval/SKILL.md) with at least one realistic prompt that should trigger the skill and one neighboring prompt that should not. Inspect the produced plan, edits, commands, and evidence. Do not promote a skill because its prose looks convincing.

When a repository cannot repeatedly exercise its authoritative surface, apply [`patpat-verifier`](../../skills/patpat-verifier/SKILL.md) and keep the resulting verifier project-local. When an evaluation exposes a recurring failure, apply [`patpat-learn`](../../skills/patpat-learn/SKILL.md) and encode the lesson at the earliest enforceable boundary.

Require a stable verifier, independent work slices, a named integration owner, and integrated proof before adding parallel-agent behavior. Keep agents optional until they earn their maintenance and context cost.

## Extend agents and automation

Keep a role's canonical contract in `skills/`. Add a host-native adapter only when the host schema can enforce a useful boundary, and keep the adapter limited to loading that contract. Do not claim native support on hosts that only receive the role as a skill.

Apply [`patpat-automation`](../../skills/patpat-automation/SKILL.md) only after a concrete provider, trigger, actions, secret source, sandbox, and verifier exist. Keep a new automation disabled until dry-run evidence and independent review pass. Do not create a dormant integration pack for structural symmetry.
