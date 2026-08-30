# Fix Root Causes

Reproduce the symptom when safe and practical. Otherwise trace the relevant contract or code path without triggering the harmful effect. Locate the earliest incorrect state and state a falsifiable causal mechanism before editing.

Do not silence the final symptom with a guard, retry, fallback, or wider timeout unless the user explicitly requests a bounded mitigation and the underlying risk remains visible.
