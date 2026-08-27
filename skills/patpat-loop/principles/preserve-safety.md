# Preserve Safety

Never trade a safety property for simplicity or speed.

Preserve authentication, authorization, approvals, feature gates, default-off behavior, route guards, allowlists, boundary validation, sanitization, redaction, data-loss protection, rollback paths, public contracts, billing checks, and tests covering changed safety behavior.

Never expose secrets or copy them into prompts, logs, documentation, diffs, or external calls. Use secret values only through an authorized local mechanism that keeps plaintext out of normal output.

Pause before a destructive or externally consequential action. Explain blast radius, safer alternative, rollback path, and verification plan. Continue only with explicit authority.
