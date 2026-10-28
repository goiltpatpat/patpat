# Fix Root Causes

Reproduce the symptom when safe and practical. Otherwise trace the relevant contract or code path without triggering the harmful effect. Locate the earliest incorrect state and state a falsifiable causal mechanism before editing.

Do not silence the final symptom with a guard, retry, fallback, or wider timeout unless the user explicitly requests a bounded mitigation and the underlying risk remains visible.

When two fixes that share the same premise fail the same gate, stop before writing a third fix. State the assumption and the shared observable failure. Choose a safe, repeatable observation that would differ if the assumption were false, and use its result to guide the next hypothesis. A census of actors or states can help when distribution or assignment is relevant, but balance or skew alone does not establish causation. Preserve the reproduction or outcome comparison; if the observation cannot distinguish the alternatives, report the evidence gap instead of assuming a cause.
