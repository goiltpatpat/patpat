# Catch-Up Playbook

Read [repository truth](../principles/repository-truth.md) and [guard the context window](../principles/guard-the-context-window.md).

Use this playbook when the user asks to be caught up on what happened since their last message, or on where the work stands. [Session pickup](session-pickup.md) resynchronizes the agent; this playbook briefs the human. Stay read-only: do not change code, start jobs, or post anything.

1. **Gather.** Collect this session's work since the user's last message, worker and subagent reports, and messages from other sessions. Re-check the live state of every PR, CI run, branch, and run store the work touched. A report is a lead, not a state; correct any number that does not match its source and say so.
2. **Separate action items.** An action item is a call only the user can make: a product choice, an approval, a destructive or external action, or access the agent lacks. Work the agent can still do is not an action item. Include items raised before the user's last message that still wait on them. Never invent one to fill the reply.
3. **Open with the waiting calls.** One sentence names what waits on the user, or says nothing does. If nothing happened and nothing waits, say so and stop.
4. **Summarize outcomes.** One plain line per thing the user asked for: what came of it and whether it is verified, partially verified, running, failed, or not checked. Use the report vocabulary from the [operating protocol](../references/operating-protocol.md#evidence). Name bugs found on the way. Keep the story under about 100 words; leave out hashes, paths, and commands unless the user needs one to act.
5. **Lay out each call.** Give the call, your pick, what it changes for users, the evidence behind the pick, and its risk, even when the risk is low. For a choice between options, give each option's gain and cost. Mark anything irreversible. Write "unknown" for a fact the call needs that you lack. The reply alone must be enough to decide.
6. **Use a picture only when it explains a mechanism or a dependency chain** better than a sentence, per [earned representation](../references/earned-representation.md). Never draw a status list or invent a number.
