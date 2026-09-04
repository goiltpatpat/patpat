# How-report contract

Use this shape for every investigation Explain or Critique. Do not omit a section. Do not add a slash skill named `/how`. A teach reply may layer the same findings in plain language; it does not replace these headings in the inspect artifact.

## Required sections

Write these headings, in this order:

### Overview

One short statement of what the path does and what question this report answers.

### Key Concepts

Named types, functions, or files the reader must hold. Each item cites a file.

### How It Works

The control flow. Cite functions. Mark each material claim `confirmed`, `inferred`, or `unknown`. When flow is hard in prose, use the smallest earned form from [earned representation](../../patpat-loop/references/earned-representation.md) (often a call tree). Simple factual answers stay prose.

### Where Things Live

Placement, ownership, and layering. For each load-bearing symbol, name the owner skill or module and the layer (router, playbook, protocol, test). When ownership is hard in prose, prefer a shallow tree per [earned representation](../../patpat-loop/references/earned-representation.md). Simple factual answers stay prose.

### Gotchas

Misroutes, adjacent playbooks, and what this path must not do (no mutation, no PR, no merge).

## Critique

Only after Explain. Verdicts, one per finding:

- Act on
- Consider
- Noted
- Dismissed

## Forbidden in the report

Model-panel names, a `/how` skill, mutation, opening a PR, and treating a why-shaped question as this contract.
