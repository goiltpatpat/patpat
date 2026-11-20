# Self-Editing Installed Plugin Cache Paths

## Rejected idea

Allowing reflection, learning, or skill-maintenance workflows (`patpat-learn`, `patpat-skill`) to edit skill or hook files directly inside a host's installed plugin cache directory (e.g., `plugins/cache/`, `~/.claude/plugins/cache/`, `~/.cursor/plugins/`).

## Why it is out of scope

Host plugin caches are managed install artifacts overwritten on plugin updates, reinstalls, or cache GC. Edits made inside a cache directory are silently lost on upgrade, diverge from the canonical repository, and bypass source-control review and validation.

## What we do instead

- Refuse direct edits to any installed plugin cache path.
- Route skill or rule improvements either to the canonical source repository (on a branch, with `scripts/validate.py` passing) or, for user-local overrides, preview the explicit local destination (project skills dir or user skills dir) and copy/edit locally only after explicit user approval.
