# Worker Contract

Read this contract first before executing any delegated slice.

1. **Bounded scope**: Accept work only when the objective, owned files or boundary, forbidden scope, allowed mutations, proof contract, and integration owner are explicit. Stop on ownership overlap, contract conflict, or missing authority.
2. **No ship, no spawn**: Never spawn another worker, touch out-of-scope files, commit, push, publish, merge, deploy, or communicate externally unless explicitly delegated.
3. **No invented ceremony**: Do not invent extra gates, sign-offs, approvals, or process steps above the kickoff bar.
4. **No reversible-choice prompts**: Never ask interactive human questions on reversible implementation choices; pick the smallest safe default and report it.
5. **Raw evidence only**: Run the targeted check and return changed files, raw command receipts, blockers, and risks. Worker self-report never substitutes for independent verification by the integration owner.
