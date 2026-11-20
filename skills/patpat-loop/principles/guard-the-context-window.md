# Guard the Context Window

**Rule:** Protect context as scarce runtime training data: filter/summarize at the source (never dump raw logs or full traversals), require concise findings/receipts from subagents (ban open-ended agent chatter), compress dead-end debugging into one causal breadcrumb, and place active paths, error signatures, and hard constraints last for recency.

**Test:** Before posting or handing off, strip any raw blob, duplicate rule, or dead-end transcript that does not change the next decision.
