# Runtime: where the scripts run, and how they reach the vault

Read this once per session, before the first script call. Getting it wrong is not
subtle: the scripts will report an empty vault and every gate will pass vacuously.

## The problem

There are two filesystems and they cannot see each other.

| Where | Holds | Reached by |
|---|---|---|
| The cloud container | **this plugin**, including every script | the ordinary `Bash` tool |
| The user's computer | **the vault**: every course, every note, every source | `device_bash`, with connected folders mounted under `$HOME/mnt/<folder>/` |

A script sitting in the plugin cannot open a single file in the vault. Every
script in this plugin is a vault-walker, so this has to be settled first.

## The three cases

**Case 1 — Cowork with the vault as a connected folder.** The normal case.
Install the script bundle into the vault once, then run everything with
`device_bash`, on the machine where the files actually are.

**Case 2 — Claude Code running locally on the user's machine.** The plugin and
the vault are on one filesystem. No install, no bridge: call the scripts at
`${CLAUDE_PLUGIN_ROOT}` directly with the ordinary shell.

**Case 3 — no connected folder and no local vault.** Nothing in this plugin can
run. Say so plainly, name what you would need, and stop. Do not stage a lesson's
files into the container and work on copies: a vault edited through copies drifts
from the vault on disk, and the student ends up with two versions of their notes.

## Case 1: the install

The bundle lives at `<vault>/.course-plugin/`. A leading dot, so Obsidian ignores
it entirely and it never appears in search, the graph or a folder listing. It
travels with the vault through iCloud, so every machine the student uses has it.

```
<vault>/.course-plugin/
├── VERSION                     one line: the plugin version that wrote this
├── shared/scripts/*.py
└── skills/<skill-name>/scripts/*.py
```

**Check before every first script call of a session:**

```bash
cat "$HOME/mnt/<folder>/.course-plugin/VERSION" 2>/dev/null || echo missing
```

If it is missing, or differs from the `version` in `.claude-plugin/plugin.json`,
install or refresh it:

1. Copy the script tree out of the plugin into the outputs directory, keeping the
   `shared/scripts` and `skills/<name>/scripts` layout, and write `VERSION`.
2. Write it onto the user's disk with `device_commit_files`, targeting
   `<vault>/.course-plugin/...`.

That transfer costs no tokens, because the file contents never pass through the
conversation. It happens once per plugin version, not once per run.

**Copy script files only.** The bundle holds `VERSION` and `*.py`, nothing else.
A sync that creates a directory per skill subfolder leaves empty `references/`
and `templates/` directories in the student's vault, which look like a broken
install; the model reads those files from the plugin itself, which is always
present in this case.

**Then set the prefix and use it for every call:**

```bash
PLUGIN="$HOME/mnt/<folder>/.course-plugin"
export PYTHONDONTWRITEBYTECODE=1
python3 "$PLUGIN/shared/scripts/vault.py" resolve --vault "$VAULT" --hint econ
```

`PYTHONDONTWRITEBYTECODE=1` on every call, because the vault syncs. Without it
Python writes a `__pycache__` directory beside the scripts, inside the student's
iCloud container, on every run.

**Why the bundle goes in the vault and not in the session's scratch space:** the
device shell starts fresh every call and its home directory is wiped with the
session. Re-installing fifty scripts at the start of every conversation is a cost
the student pays for nothing, and a half-finished re-install is a broken run.

## Rules that hold in every case

- **Work where the files are.** Read, search, edit in place, and write outputs
  next to their sources, in the same shell that can see the vault.
- **Never stage a text or data file into the container just to read or edit it.**
  The reasons to stage are narrow and specific: you must *look* at an image or a
  PDF page yourself, a library exists only in the container, or the student asked
  for a download in the chat.
- **Each `device_bash` call is a fresh shell with a short time limit.** Split long
  jobs into steps. Keep intermediates in the shell's own scratch space, outside
  `mnt/`, never in the student's folders.
- **Every script takes its paths as arguments.** None of them guesses a vault
  root from its own location, which is what keeps all three cases working from
  one copy of the code.
- **Deletion is refused until the user grants it**, per session, per folder. No
  script in this plugin deletes anything. A's archive cleanup asks for the grant
  first and says exactly what it will remove.

## If a script is missing or fails to import

Do not re-implement it inline, and do not work around it with a one-off shell
pipeline. A hand-rolled slugify or a hand-rolled link check produces a result
that disagrees with the rest of the plugin and nothing detects the disagreement.
Re-run the install, and if it still fails, report the failure and stop.
