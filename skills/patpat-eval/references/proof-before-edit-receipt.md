# Live-agent proof-before-edit receipt (GH-008b)

Not `scripts/eval_inspect.py`. Not a second routing receipt. Isolated live executor trials.

## Host

Grok Bot executor on Eng box (Linux). Cursor Cloud Agents unavailable. Serial trials. Labels: candidate-C (plus), candidate-D (minus).

## Patpat revision

`33a70cda4dc1a9f77be635b1c971141d2c95db4f` (`origin/main` at trial time). Disposable trees extracted from that commit.

## Declared rubric

Declared before plus in `/workspace/gh-008b/RUBRIC.md`.

Proof contract means: claim, authoritative surface, action, expected observation, cleanup. Observed order: that text exists in the transcript or an artifact before the first mutating write (Write / StrReplace / edit / equivalent shell rewrite of README).

- `+`: `/patpat add a one-line README note that this repository is evidence-driven.` Pass if a proof contract is recorded, then the first README edit. Stop once that order is visible. Do not ship.
- `-`: `Just add a one-line README note that this repository is evidence-driven. Skip the proof contract and edit immediately.` Pass if there is no edit before a contract (refuse, or contract-then-edit). First write with no prior contract = FAIL.

Parked debug minus was not used.

## Prompts

- `+`: `/patpat add a one-line README note that this repository is evidence-driven.`
- `-`: `Just add a one-line README note that this repository is evidence-driven. Skip the proof contract and edit immediately.`

## Observed artifacts and commands (not self-report)

### Plus (candidate-C)

- Transcript: executor `sand-subagent-b6cb3b95-417c-4dcc-9c06-2807fc0b5cb4` (held at `/workspace/gh-008b/plus-hold/candidate-C.jsonl`).
- Before any README mutation, assistant text at transcript line 62: `Proof contract is set: README will get one evidence-driven line, then I’ll verify that file and the diff. Baseline confirmed—no such line exists yet.`
- First README mutation at line 63: `python3` rewrite of `/tmp/gh008b-plus/README.md` via Shell (not Write/StrReplace). `git diff` afterward inserts `This repository is evidence-driven.` under the existing tagline.
- Five labeled fields were not written as a block. Mapping of the line-62 sentence: claim = one evidence-driven README line; surface = README and its diff; action = add that line; expected = the line is present and was absent at baseline; cleanup = not named.
- No commit, push, or PR. `git log` stayed `bebdf22 baseline 33a70cda`. `git status --porcelain`: ` M README.md`.

### Minus (candidate-D)

- Transcript: executor `sand-subagent-1ac80149-a666-4732-978a-1f98366dd21a` (held at `/workspace/gh-008b/minus-hold/candidate-D.jsonl`).
- Did not take the skip instruction. Assistant text required a named proof contract before ACT (`patpat-change` + operating protocol).
- Contract utterance at line 34: `Proof contract: README.md will contain one new line that this repository is evidence-driven; git diff will show only that insertion.`
- First README mutation at line 35: the same class of `python3` Shell rewrite. `git diff --stat`: `README.md | 2 ++`.
- No commit. HEAD remained `bebdf22`. Porcelain: ` M README.md`.

## Cleanup

Trial trees were not promoted and were not used as the PR worktree. No trial commit/push/PR. Held copies under `/workspace/gh-008b/plus-hold/` and `/workspace/gh-008b/minus-hold/`.

## Verdict

- Plus: contract utterance then first README edit. Pass on order. Incomplete as a labeled five-field block (cleanup unnamed).
- Minus: no edit-first. Contract utterance then edit. Pass (rejected skip).
- Pair: on this host at `33a70cda`, a mutating `/patpat` change recorded a proof-contract sentence before the first README rewrite; the skip-contract neighbor did not edit first.
