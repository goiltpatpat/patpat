# Install and Prove Discovery

Installation is complete only when the active host can discover Patpat in a fresh task. A copied folder or successful package command proves files moved; it does not prove prompt-time availability.

## Use the host-owned path

Choose one installation owner and keep updates on that path:

| Host | Install owner | Fresh-task invocation |
| --- | --- | --- |
| Cursor | Native plugin when proven; otherwise project skills | `/patpat` |
| Codex | Codex plugin marketplace | `$patpat` |
| Antigravity | Validated local plugin clone | `Use patpat to ...` |
| Grok CLI | Grok plugin manager | `/patpat` |
| Portable Agent Skills host | Transactional installer | `Use patpat to ...` |

Use the exact commands and update behavior in the [installation reference](./installing.md). Do not mix a marketplace install with a manually copied update; the next update may replace or ignore the wrong owner.

## Prove the package

Run the host's validation or inventory command. Confirm that the installed source is the expected repository and version. For portable copies, retain the ownership record created by the installer; the updater uses it to detect local tampering and roll back failed replacements.

## Prove discovery

Start a new task or session. Ask the host to invoke Patpat explicitly:

```text
Use patpat to inspect this repository and report the proof surface you would use. Do not edit yet.
```

A valid response should frame the task, inspect repository evidence, and name a proof contract. A generic answer that never reads Patpat is not a successful install.

## Prove the update path

Update through the same owner, start another fresh task, and confirm discovery again. Symlinks follow source edits, but they do not discover newly added skill folders until the host refreshes its catalog.

If a host is marked unverified in the [installation reference](./installing.md), treat it as unverified. Do not convert a manifest check into a claim that a live host loaded the plugin.

Next: [Route work through Patpat](./02-operating-loop.md).
