# Pause Safely Playbook

Read [repository truth](../principles/repository-truth.md), [sequence verifiable units](../principles/sequence-verifiable-units.md), and [preserve safety](../principles/preserve-safety.md).

Use this playbook when the user asks to pause, go offline, restart the host, when context is about to compact, or when a diagnosed recovery requires scope or authority outside the approved task. Do not use it for "keep going", "going to bed, keep going", or "don't stop" unless the next safe action still crosses that boundary. Those requests otherwise continue through [multi-phase run](multi-phase-run.md). Resume is [session takeover](session-takeover.md) only when no valid Patpat run store exists; otherwise resume the named `patpat-run` node.

This is a pause, not a ship. Do not open a PR to pause. Do not merge.

1. Stop at a safe boundary. Finish the current atomic step or back out of it. Never stop mid-edit in a known-broken state. Start nothing new. Cancel nested workers.
2. Do not cross an irreversible line to pause. No new pull request, no force-push, no deploy, no secret rotation. A push is allowed only if a pull request already exists and the tree is verified, not as a pause ritual.
3. Make the work durable without inventing delivery authority. If a `patpat-run` store exists, write an atomic checkpoint and name the earliest resumable node. Write a resume note off-context: intent, progress, what is verified, current git state, next step, key files, gotchas. Prefer a path inside the repo's ignored or run-store directory over `/tmp` when a host-durable store exists.
4. Do not create a `wip:` commit unless the user already authorized commits for this session. If the tree is dirty and commits are not authorized, say so in one line and keep the resume note as the checkpoint.
5. Leave external delivery authority unchanged. Pause never authorizes merge.
6. For an anti-thrashing boundary pause, retain the `Diagnostic Delta` from the execution graph and name the exact scope, authority, or external evidence needed. Do not start the out-of-scope recovery as part of checkpointing.

**Reply:** loop state, what is on disk versus only in context (paths, no diff dumps), whether the tree is dirty, the checkpoint path, and the first action on resume.
