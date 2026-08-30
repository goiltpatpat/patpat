# Installing Patpat

Patpat keeps one canonical `skills/` tree and thin host adapters. Select one installation route; do not combine native and copied installations in the same host scope.

Agents should follow [`AGENTS.md`](../../AGENTS.md). The published source is `https://github.com/goiltpatpat/patpat`. The Codex plugin id is `patpat@patpat`.

Stage a working tree that contains Memory Bank or other ignored files before native Codex or Antigravity install. A clean clone of the published repository does not need staging.

## Grok CLI

```bash
grok plugin install goiltpatpat/patpat --trust
grok plugin list --json
grok plugin details patpat
```

`--trust` is required for hooks. Start a new session, then invoke `/patpat`. Package list output does not prove prompt-time discovery. Remove with `grok plugin uninstall patpat --confirm`. Validate isolated installation and hook execution with `python3 scripts/smoke_grok_plugin.py` when Grok CLI is available.

## Codex

From GitHub:

```bash
codex plugin marketplace add goiltpatpat/patpat
codex plugin add patpat@patpat
codex plugin list --json
```

Pin a release when one exists:

```bash
codex plugin marketplace add goiltpatpat/patpat --ref <release-tag-or-commit>
codex plugin add patpat@patpat
```

From a local working tree:

```bash
python3 scripts/stage_plugin.py --target /absolute/path/to/patpat-dist
codex plugin marketplace add /absolute/path/to/patpat-dist
codex plugin add patpat@patpat
```

Do not `marketplace add` a dirty checkout. Start a new task after installation and invoke `$patpat`. Package installation and prompt-time discovery are separate checks.

Update through Codex so its marketplace and cache remain consistent:

```bash
codex plugin marketplace upgrade patpat
codex plugin remove patpat@patpat
codex plugin add patpat@patpat
```

Remove the plugin and marketplace separately:

```bash
codex plugin remove patpat@patpat
codex plugin marketplace remove patpat
```

## Antigravity

From a clean clone:

```bash
agy plugin validate /absolute/path/to/patpat
agy plugin install /absolute/path/to/patpat
agy plugin list
```

From a dirty working tree, stage first, then validate and install that staged path. Use `agy plugin uninstall patpat` for removal. Start a fresh session before testing `patpat-loop` discovery.

## Cursor

Native marketplace publish is [cursor.com/marketplace/publish](https://cursor.com/marketplace/publish). After listing, install from Customize the same way as pstack. Until SearchPlugins returns patpat, do not claim the Grok Bot Installed tab. Keep the portable route below as the proven fallback. Do not claim `/add-plugin patpat`.

## Portable Agent Skills

Use this no-global-write route only after proving the selected host reads the selected project skills directory. For a host that does not use `.agents/skills`, substitute its proven project-scoped skill root:

```bash
python3 scripts/install_skills.py \
  --target /absolute/path/to/project/.agents/skills \
  --dry-run

python3 scripts/install_skills.py \
  --target /absolute/path/to/project/.agents/skills
```

The installer performs a new copy or development symlink installation. It records exact ownership for copied skills and symlink targets but does not overwrite an existing installation. Never point it at a guessed home directory or a directory containing another Patpat installation.

## Update

Use the owner of the installed state. After every update, inspect the installed catalog and start a fresh task or session before checking discovery.

| Installation | Update path |
| --- | --- |
| Codex marketplace | Run `codex plugin marketplace upgrade patpat`, then `codex plugin remove patpat@patpat` and `codex plugin add patpat@patpat`. Start a fresh task. |
| Grok CLI | Run `grok plugin update patpat`. Start a fresh session. |
| Antigravity clean clone | Run `git -C /absolute/path/to/patpat pull --ff-only`, `agy plugin validate /absolute/path/to/patpat`, then `agy plugin install /absolute/path/to/patpat`. Reuse the same path and start a fresh session. |
| Portable copy | Pull the trusted source checkout, run `scripts/update_skills.py` with explicit `--target`, new `--backup`, and `--dry-run`, then repeat without `--dry-run`. The updater refuses modified recorded files, backs up the previous catalog, and rolls back a failed promotion. |
| Portable development symlink | Update the source checkout, then run the same updater. It reconciles added, retired, and relocated links only from the recorded Patpat catalog, preserves unrecorded paths, and rolls back failed changes. Reload the host or start a fresh session. |
| Cursor native plugin | Update behavior remains unverified. Use the portable route until native install and update are proven in a live project. |

Example portable update:

```bash
python3 scripts/update_skills.py \
  --target /absolute/path/to/project/.agents/skills \
  --backup /absolute/path/to/project/.agents/patpat-backup-v0.6 \
  --dry-run

python3 scripts/update_skills.py \
  --target /absolute/path/to/project/.agents/skills \
  --backup /absolute/path/to/project/.agents/patpat-backup-v0.6
```

The backup path must not exist and must share a filesystem with the target. The updater touches only the Patpat catalog it validates and its `.patpat-update.lock`; concurrent updates to the same installation serialize and time out safely instead of interleaving. Keep the backup until the fresh-session discovery check passes.

## Invocation

Explicit invocation opts the active session into verified auto ship: commit the in-scope diff, non-force push, and open or update one ready pull request after verification and review. Higher-priority repository rules and `local only` still win. Overnight work stops merge-ready; merge requires explicit `land` or `merge` language.

| Host | Invoke after a fresh session |
| --- | --- |
| Grok CLI | `/patpat` or `/patpat-loop` |
| Cursor | `/patpat` or `/patpat-loop` |
| Codex | `$patpat` or `$patpat-loop` |
| Portable / generic Agent Skills | `Use patpat to ...` |
| Antigravity | host UI or `Use patpat to ...` |

## Verification

```bash
python3 scripts/validate.py --self-test
python3 scripts/install_skills.py --self-test
python3 scripts/update_skills.py --self-test
python3 scripts/stage_plugin.py --self-test
python3 scripts/smoke_codex_plugin.py
python3 scripts/smoke_antigravity_plugin.py
python3 scripts/smoke_grok_plugin.py
python3 skills/patpat-run/scripts/validate_plan.py --self-test
agy plugin validate .
```

For each selected host, inspect the installed catalog, start a fresh task or session, invoke `patpat-loop`, and verify that it loads only the workflow and references required by the request.
