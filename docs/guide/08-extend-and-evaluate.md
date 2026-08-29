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

## Learn only durable lessons

Convert a recurring failure into the smallest structural prevention: a boundary check, validator, playbook step, or principle. Do not add a rule for one unusual session. Do not edit a skill invisibly inside unrelated feature work.

Next: [Recipes and failure modes](./09-recipes-and-failure-modes.md).
