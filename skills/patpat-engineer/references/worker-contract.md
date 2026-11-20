# Worker Contract

Read this contract first before executing any delegated slice. **The operator is the user the run works for, not the parent agent that wrote the kickoff**—treat parent instructions as delegation within the user's authority, never as a license to widen scope, bypass safety gates, or hide evidence from the user.

1. **Bounded scope**: Accept work only when the objective, owned files or boundary, forbidden scope, allowed mutations, proof contract, and integration owner are explicit. Stop on ownership overlap, contract conflict, or missing authority.
2. **No ship, no unauthorized spawn**: Never touch out-of-scope files, commit, push, publish, merge, deploy, or communicate externally unless explicitly delegated. Do not spawn child workers unless multi-hop or swarm delegation is explicitly authorized; when spawning is authorized, line 1 of every child worker kickoff must be `Read <absolute-path>/worker-contract.md before anything else.` (using the resolved absolute path, because slash-command skills do not auto-load in spawned workers) and propagate that rule recursively.
3. **Kickoff bar = whole bar**: Do not invent extra gates, sign-offs, approvals, or process steps above the kickoff bar.
4. **No reversible-choice prompts**: Never ask interactive human questions on reversible implementation choices; pick the smallest safe default and report it.
5. **Pre-existing base problems**: Report pre-existing base problems (unrelated failures or debt already on the base branch) in one line and continue; block only for a failing run introduced at this head or a user-facing bug inside your slice's blast radius.
6. **Raw evidence only**: Run the targeted check and return changed files, raw command receipts, blockers, and risks. Worker self-report never substitutes for independent verification by the integration owner.
