# Investigation Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), and [earned parallelism](../principles/earned-parallelism.md).

Use this playbook for how-does-X-work, placement, ownership, layering, and "are we sure" questions. It is the how-equivalent. There is no `/how` slash skill. Why-shaped historical questions ("why was this shaped this way?") stay on [rationale-forensics](rationale-forensics.md). Stay read-only. Do not mutate. Do not open a PR from inspect.

## Mode

- **Explain** (default): answer how it works, where it lives, who owns it, and which layer it sits in.
- **Critique** (only after Explain): add verdicts `Act on` / `Consider` / `Noted` / `Dismissed`. Never critique before the explanation exists.

## Complexity

Lean simple. One read-only pass is the default. Treat the question as complex only when independent evidence sources must be gathered before a coherent explanation (several files, several layers, or a placement dispute). Complex work uses 2-4 read-only explorers with distinct angles, each returning structured findings, then one explainer. The explainer performs synthesis: reconcile overlap and contradictions; the explainer's explanation is the product (light edit only). If isolation is missing, run serially. Explorers never write.

## Steps

1. Restate the question. If it is why-shaped, stop and use rationale-forensics. If it asks to fix or ship, stop; this playbook does not implement.
2. Choose Explain or Critique. Critique still runs Explain first.
3. Apply the complexity gate. Simple = one pass. Complex = 2-4 read-only explorers then one explainer, or serial fallback.
4. Trace the live path: callers, callees, config, tests. Cite files and functions. Do not invent symbols.
5. Label every material conclusion `confirmed`, `inferred`, or `unknown`.
6. Put placement, ownership, and layering in **Where Things Live**, with an explicit owner and layer for each load-bearing symbol.
7. If Critique was requested, attach verdicts after the explanation. No model-panel names in the report.
8. Do not mutate the repository. Do not open a PR. Recommend the smallest safe patch only when asked, then stop.

## Report

Follow [the how-report contract](../../patpat-inspect/references/how-report.md). Required sections, in order:

1. Overview
2. Key Concepts
3. How It Works
4. Where Things Live
5. Gotchas

## Teach

When the user asks you to teach them or help them really understand the path, the user-facing reply is the explanation, not a report about the work. Weave how findings and, when reasons matter, rationale-forensics findings into one plain layered explanation. Keep why hedges. Prefer the smallest useful form from [earned representation](../references/earned-representation.md) when flow or ownership is hard in prose; teach may still add one part at a time. Required how-report and why-report headings remain the inspect artifact. There is no `/teach` skill.
