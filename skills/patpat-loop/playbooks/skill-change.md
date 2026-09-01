# Skill Change Playbook

Read [repository truth](../principles/repository-truth.md), [smallest safe change](../principles/smallest-safe-change.md), and [encode lessons](../principles/encode-lessons.md).

1. Name the skill's single responsibility and the prompts it must accept and reject.
2. Inspect nearby skills, host constraints, validation scripts, and repository conventions.
3. Define the proof contract for structure, triggering, behavior, and safety.
4. Make the smallest change to `SKILL.md` and only the references or scripts it needs now. When the request came from learn, wait for approval, edit existing files only, and do not create a new SKILL.md or a `*-mode` skill (no new SKILL.md, no *-mode mint).
5. Run repository validation and resolve every introduced error.
6. Apply `patpat-eval` to changed behavior, routing, or descriptions.
7. Inspect the final diff for duplicated advice, vague verbs, placeholders, and unused files.
8. Report structural and behavioral evidence separately.
