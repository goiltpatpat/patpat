# Fix Root Causes

Reproduce the symptom when safe and practical. Otherwise trace the relevant contract or code path without triggering the harmful effect. Locate the earliest incorrect state and state a falsifiable causal mechanism before editing.

Do not silence the final symptom with a guard, retry, fallback, or wider timeout unless the user explicitly requests a bounded mitigation and the underlying risk remains visible.

When two fixes that share the same premise fail the same gate, stop before writing a third fix. Treat a premise as the explicit assumption that predicts the same failure, and a gate as the same observable acceptance check or user-visible outcome. State the shared premise, take a small rerunnable census of the actors or states involved, and test whether the premise explains the skew. A census is balanced when the relevant actors or states receive comparable treatment and outcomes; it is skewed when a repeatable assignment or asymmetry predicts the failure. If the census is balanced, keep the evidence and investigate another cause; if it is skewed, remove the assignment or asymmetry that keeps producing it instead of adding another compensating fix. The census is evidence for the causal hypothesis, not proof by itself: preserve a concrete reproduction or outcome comparison before removing the assignment.
