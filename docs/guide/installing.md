# Installing Patpat

Patpat keeps one canonical `skills/` tree and thin host adapters. Select one installation route; do not combine native and copied installations in the same host scope.

Agents should follow [`AGENTS.md`](../../AGENTS.md). The published source is `https://github.com/goiltpatpat/patpat`. The Codex plugin id is `patpat@patpat`.

Stage a working tree that contains Memory Bank or other ignored files before native Codex or Antigravity install. A clean clone of the published repository does not need staging.

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

Do not `marketplace add` a dirty checkout. Start a new task after installation and invoke `$patpat-loop`. Package installation and prompt-time discovery are separate checks.

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

The Cursor manifest at `.cursor-plugin/plugin.json` is structurally validated and includes one read-only reviewer adapter. Live native loading is unverified. Until a live project load is proven, install project-scoped skills through the portable route and reload Cursor. Do not claim `/add-plugin patpat`.

## Portable Agent Skills

Use this no-global-write route only after proving the selected host reads the selected project skills directory. For a host that does not use `.agents/skills`, substitute its proven project-scoped skill root:

```bash
python3 scripts/install_skills.py \
  --target /absolute/path/to/project/.agents/skills \
  --dry-run

python3 scripts/install_skills.py \
  --target /absolute/path/to/project/.agents/skills
```

The installer performs a new copy or development symlink installation. It does not update, merge, or remove existing skills. Never point it at a guessed home directory or a directory containing another Patpat installation.

## Invocation

No `/skill` form is verified.

| Host | Invoke after a fresh session |
| --- | --- |
| Codex | `$patpat-loop` |
| Portable / generic Agent Skills | `Use patpat-loop to ...` |
| Antigravity | host UI or `Use patpat-loop to ...` |
| Cursor | host UI or `Use patpat-loop to ...` after reload |

## Verification

```bash
python3 scripts/validate.py --self-test
python3 scripts/install_skills.py --self-test
python3 scripts/stage_plugin.py --self-test
python3 scripts/smoke_codex_plugin.py
python3 scripts/smoke_antigravity_plugin.py
agy plugin validate .
```

For each selected host, inspect the installed catalog, start a fresh task or session, invoke `patpat-loop`, and verify that it loads only the workflow and references required by the request.
