# Installing Patpat

Patpat keeps one canonical `skills/` tree and thin host adapters. Select one installation route; do not combine native and copied installations in the same host scope.

Patpat's scripts and hooks require Python 3.11 or newer. Windows Codex hooks locate it with `py.exe -3`, then `python.exe` on `PATH`; the launcher reports an error if neither provides Python 3.11+.

Agents should follow [`AGENTS.md`](../../AGENTS.md). The published source is `https://github.com/goiltpatpat/patpat`. The Codex plugin id and Claude Code marketplace/plugin id are both `patpat@patpat`.

Stage a working tree that contains Memory Bank or local artifacts before native Codex, Claude Code, or Antigravity install. The stager excludes local Memory Bank and `docs/diagrams/`, but does not apply every `.gitignore` rule; inspect the staged package when other machine-local files sit inside allowed paths. A clean clone of the published repository does not need staging.

## Grok CLI

```bash
grok plugin install goiltpatpat/patpat --trust
grok plugin list --json
grok plugin details patpat
```

`--trust` is required for hooks. Start a new session, then invoke `/patpat`. Grok ignores output from passive hook events and does not add output from an allowing `UserPromptSubmit` hook to model context, so Patpat cannot restore sticky context through its current Grok adapter; invoke `/patpat` again after resuming. Package list output does not prove prompt-time discovery. Remove with `grok plugin uninstall patpat --confirm`. When Grok CLI is available, `python3 scripts/smoke_grok_plugin.py` checks isolated installation, hook discovery, and direct command behavior. It does not prove that Grok delivers hook output to the model; see the [xAI hook contract](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/10-hooks.md).

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

The Codex and Cursor manifests share Patpat's package version; the portable Agent Plugins manifest inherits it from the Codex manifest. The Claude Code marketplace entry uses the same package version because Claude keeps installed copies until that version changes. The portable Agent Plugins `$schema` version tracks that format independently. Treat the package version as a release identifier, not a push or PR counter: ordinary merges do not bump it, and internal-only docs, tests, or refactors do not justify a package release. At release preparation, assess the user-facing changes accumulated since the previous release and bump the Codex, Cursor, and Claude versions together: use a patch for compatible fixes and a minor version for new capabilities; while Patpat remains pre-1.0, use a minor version for incompatible changes too. After 1.0, reserve major versions for breaking changes; use `1.0.0` when maintainers commit to a stable public contract. Publish curated notes as a GitHub Release with a matching `v<version>` tag from a reviewed, merged commit; CI checks tag/version equality, not release quality.

From a local working tree:

```bash
python3 scripts/stage_plugin.py --target /absolute/path/to/patpat-dist
codex plugin marketplace add /absolute/path/to/patpat-dist
codex plugin add patpat@patpat
```

Do not `marketplace add` a dirty checkout. Start a new task after installation and invoke `$patpat`. Codex does not run bundled plugin hooks until the user reviews and trusts the current hook definition; confirm that trust before relying on resume continuity. Package installation and prompt-time discovery are separate checks. See [OpenAI's plugin hook guidance](https://developers.openai.com/plugins/build/plugins).

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

## Claude Code

From GitHub:

```bash
claude plugin marketplace add goiltpatpat/patpat
claude plugin install patpat@patpat
claude plugin list
claude plugin details patpat
```

The marketplace points to the repository root with `source: "."`; Claude loads the standard root `skills/` directory. The marketplace entry is the plugin manifest, so the Antigravity root `plugin.json` is not reused. Validate a checkout or staged package with `claude plugin validate /absolute/path/to/patpat --strict`. To validate the skill files themselves, run `claude plugin validate /absolute/path/to/patpat/skills --strict` with Claude Code v2.1.233 or later.

From a local working tree, stage first:

```bash
python3 scripts/stage_plugin.py --target /absolute/path/to/patpat-dist
claude plugin validate /absolute/path/to/patpat-dist --strict
claude plugin marketplace add /absolute/path/to/patpat-dist
claude plugin install patpat@patpat
```

Start a new Claude Code session and invoke `/patpat:patpat`. The entry uses the current package release version, so installed copies update when a later release changes that version. Claude marketplace auto-update is off by default; update manually with `claude plugin marketplace update patpat` followed by `claude plugin update patpat@patpat`. Remove with `claude plugin uninstall patpat@patpat`, then `claude plugin marketplace remove patpat`.

## Antigravity

From a clean clone:

```bash
agy plugin validate /absolute/path/to/patpat
agy plugin install /absolute/path/to/patpat
agy plugin list
```

From a dirty working tree, stage first, then validate and install that staged path. Use `agy plugin uninstall patpat` for removal. Start a fresh session before testing `patpat-loop` discovery.

## Cursor

Patpat includes a native Cursor adapter at `.cursor-plugin/plugin.json` and `.cursor-plugin/marketplace.json`. To install the published repository, open Customize, choose **From GitHub Repository**, and enter `goiltpatpat/patpat`. After importing the repository, find Patpat in Customize, select **Install**, and choose project or user scope. Cursor's local plugin instructions describe a root Agent Plugin manifest or a `.cursor-plugin/plugin.json` manifest. The generic `scripts/stage_plugin.py` output also contains Patpat's root Antigravity `plugin.json`; this mixed package has not been tested locally in Cursor. This repository does not currently provide a Cursor-only local-test artifact. Patpat's live import and fresh-session invocation remain unverified here. Official Cursor Marketplace listing requires a separate review process.

The direct repository contains manifests for multiple hosts, so do not copy the source tree straight into Cursor's local plugin directory as a verified install.

## Portable Agent Plugins

The source root `plugin.json` belongs to Antigravity. Generate a separate package for hosts that implement [Agent Plugins 1.0](https://agent-plugins.org/specification):

```bash
python3 scripts/stage_agent_plugin.py --target /absolute/path/to/patpat-agent-plugin
python3 scripts/validate.py --agent-plugin /absolute/path/to/patpat-agent-plugin
```

The generated package contains only the portable root `plugin.json`, `LICENSE`, and fixed `skills/` directory. Git-backed staging excludes Git-ignored local files from skills; without Git metadata, inspect the artifact before installing. The stager projects Codex-only `disable-model-invocation` metadata into an explicit-user-request note in the [Agent Skills description](https://agentskills.io/specification); that note is advisory because Agent Skills 1.0 does not define a portable host-enforced invocation gate. Use the native adapter when enforced invocation policy matters. This format also does not standardize lifecycle hooks or other host-specific components. Do not install this artifact in Antigravity.

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

Inspect a recorded portable installation without changing it:

```bash
python3 scripts/install_skills.py \
  --status \
  --target /absolute/path/to/project/.agents/skills \
  --json
```

`integrity` reports whether the recorded installed files or links remain intact. `source_alignment` separately reports whether they match the current checkout (`current`, `different`, or `unknown`); a different source revision does not make an otherwise intact installation corrupt. New markers include the package version, Git revision, and dirty state when those values can be proven. Markers created by older Patpat versions remain valid and report unknown installed provenance.

## Update

Use the owner of the installed state. After every update, inspect the installed catalog and start a fresh task or session before checking discovery.

| Installation | Update path |
| --- | --- |
| Codex marketplace | Run `codex plugin marketplace upgrade patpat`, then `codex plugin remove patpat@patpat` and `codex plugin add patpat@patpat`. Start a fresh task. |
| Claude Code marketplace | Run `claude plugin marketplace update patpat`, then `claude plugin update patpat@patpat` after a package version bump. Start a fresh session. |
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

Explicit invocation authorizes the Patpat loop, proof, and verify. Default commit-and-PR requires delivery intent; see the operating protocol and default-delivery playbook. Higher-priority repository rules and `local only` still win. Overnight work stops merge-ready; merge requires explicit `land` or `merge` language.

| Host | Invoke after a fresh session |
| --- | --- |
| Grok CLI | `/patpat` or `/patpat-loop` |
| Cursor | `/patpat` or `/patpat-loop` |
| Codex | `$patpat` or `$patpat-loop` |
| Claude Code | `/patpat:patpat` |
| Portable / generic Agent Skills | `Use patpat to ...` |
| Antigravity | Use `/patpat` when the installed skill is exposed as a slash command; otherwise invoke it from the host UI or use `Use patpat to ...`. Verify fresh-session discovery and invocation. |

## Verification

```bash
python3 scripts/validate.py --self-test
python3 scripts/install_skills.py --self-test
python3 scripts/update_skills.py --self-test
python3 scripts/stage_plugin.py --self-test
python3 scripts/stage_agent_plugin.py --self-test
python3 scripts/smoke_codex_plugin.py
python3 scripts/smoke_antigravity_plugin.py
python3 scripts/smoke_grok_plugin.py
python3 skills/patpat-run/scripts/validate_plan.py --self-test
agy plugin validate .
claude plugin validate . --strict
```

For each selected host, inspect the installed catalog, start a fresh task or session, invoke `patpat-loop`, and verify that it loads only the workflow and references required by the request.
