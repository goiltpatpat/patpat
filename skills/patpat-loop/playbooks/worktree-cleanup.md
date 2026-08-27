# Worktree Cleanup Playbook

Read [preserve safety](../principles/preserve-safety.md), [repository truth](../principles/repository-truth.md), and [encode lessons](../principles/encode-lessons.md).

Use this playbook to prune merged or abandoned git worktrees and reclaim disk. Deletion is irreversible. This is the review. Simulator, DerivedData, and editor-cache deletion stay outside the core unless the live repo actually uses those surfaces.

1. Snapshot disk and list worktrees from `git worktree list` only. Do not type worktree paths by hand. Record size, age, merge state, uncommitted work, and whether a branch still has an open PR.
2. Treat the audit as advice, not permission. Confirm the in-use set against the user's pinned or active work. An in-use or pinned worktree is never safe.
3. Pause on irreversible loss. Uncommitted tracked edits require an explicit decision. Name untracked scratch files before dropping them. Clean, merged, and not-in-use may proceed.
4. Remove only the confirmed set, one path at a time: `git worktree remove <path>`, then `git worktree prune`. Branch refs survive. Do not `--force` a dirty worktree unless the user named that path and accepted data loss.
5. Re-list worktrees and report space reclaimed. Do not expand into iOS simulators, Xcode DerivedData, or editor caches unless this repository's live evidence shows those paths and the user named them.

**Reply:** disk before and after, worktrees pruned with one-line reasons, and every path held back (in-use, dirty, or unconfirmed).
