# Guard the Context Window

The context window is a finite, scarce, high-value working memory space. Protect it from noise, flooding, and sprawl.

1. Avoid dumping large raw blobs, full directory traversals, or un-filtered AST logs into conversational context.
2. Summarize, filter, and index information at the source using compact tools and scripts before reporting findings.
3. Subagents and background tasks must return concise syntheses, key diffs, and verification receipts, not voluminous raw execution transcripts.
4. Keep context clean so that critical constraints, instructions, and error signals remain prominent and uncorrupted.
