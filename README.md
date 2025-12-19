# Agent Skills Hub

A small "skills hub" that lets you pull skills from upstream repos (in `sources/`) and expose them to:

- **Claude Code** via `~/.claude/skills/`
- **Codex** via `~/.codex/skills/`

It does this by **symlinking** each upstream skill directory (a folder containing `SKILL.md`) into those locations.

## Repo layout

- `sources/` - upstream skill repos (submodules or plain clones)
- `scripts/skills-link.sh` - installer/uninstaller (symlink manager)

## Quick start

```bash
git clone <this-repo> ~/agent-skills
cd ~/agent-skills

git submodule update --init --recursive

# Install into HOME (default)
./scripts/skills-link.sh
```

That will create/refresh:

* `~/.claude/skills/*`  (symlinks)
* `~/.codex/skills/*`   (symlinks)

## Update skills

Pull upstream changes, then re-link:

```bash
git submodule update --remote --merge

./scripts/skills-link.sh
```

## Install to the current directory (repo-local)

If you want project-scoped skills instead of HOME:

```bash
./scripts/skills-link.sh --here
```

This installs into:

* `./.claude/skills/`
* `./.codex/skills/`

## Uninstall

Removes only the **symlinks created by this hub** from the target directories.
It will **not** delete any real folders/files (so your own custom skills remain).

```bash
# HOME uninstall (default)
./scripts/skills-link.sh --uninstall

# Repo-local uninstall
./scripts/skills-link.sh --here --uninstall
```

## Adding another upstream repo

```bash
git submodule add <UPSTREAM_REPO_URL> sources/<name>
git submodule update --init --recursive
./scripts/skills-link.sh
```

## Notes / gotchas

* Skill link names are derived from the path under `sources/` (so they’re unique hopefully).
* If two upstream repos ship skills with the same *internal* `name:` in `SKILL.md`, the tool that loads them might behave weirdly depending on how it resolves duplicates. TODO: Test this, and detect if it happens.
* If you move `~/agent-skills`, re-run the script to refresh symlinks.

## Sources (submodules)

If you’re using git submodules, this is the list we currently track:

* `sources/anthropics-skills` — [https://github.com/anthropics/skills](https://github.com/anthropics/skills)

(If you add more, update this list)
