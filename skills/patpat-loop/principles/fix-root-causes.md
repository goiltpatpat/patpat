# Fix Root Causes

**Rule:** Reproduce safely (or trace the contract/path), isolate the earliest incorrect state or diverging decision branch (trajectory forking), and state a falsifiable causal mechanism before editing. Never silence symptoms with guards, retries, fallbacks, or wider timeouts unless explicitly requested with the risk kept visible.

**Test:** After two fixes sharing one premise fail the same gate, stop before a third edit; run one safe observation that differs if the premise is false, and report the gap if it cannot distinguish causes.
