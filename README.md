# Agent Skills Hub

A small "skills hub" that lets you pull skills from upstream repos (in `sources/`) and expose them to:

- **Claude Code** via `~/.claude/skills/`
- **Codex** via `~/.codex/skills/`

It does this by creating a real directory per skill, **copying `SKILL.md`**, and symlinking the remaining contents (so tools that ignore symlinked dirs still discover `SKILL.md`).

## Repo layout

- `sources/` - upstream skill repos (submodules or plain clones)
- `scripts/skills-link.py` - installer/uninstaller (link manager)

## Quick start

```bash
git clone <this-repo> ~/agent-skills
cd ~/agent-skills

git submodule update --init --recursive

# Install into HOME (default)
./scripts/skills-link.py
```

That will create/refresh:

* `~/.claude/skills/*`  (directories with a real `SKILL.md` plus symlinks)
* `~/.codex/skills/*`   (directories with a real `SKILL.md` plus symlinks)

## Update skills

Pull upstream changes, then re-link:

```bash
git submodule update --remote --merge

./scripts/skills-link.py
```

## Install to the current directory (repo-local)

If you want project-scoped skills instead of HOME:

```bash
./scripts/skills-link.py --here
```

This installs into:

* `./.claude/skills/`
* `./.codex/skills/`

## Uninstall

Removes only **hub-managed entries** from the target directories.
It will **not** delete any custom folders/files (so your own custom skills remain).

```bash
# HOME uninstall (default)
./scripts/skills-link.py --uninstall

# Repo-local uninstall
./scripts/skills-link.py --here --uninstall
```

## Adding another upstream repo

```bash
git submodule add <UPSTREAM_REPO_URL> sources/<name>
git submodule update --init --recursive
./scripts/skills-link.py
```

## Notes / gotchas

* Skill link names are derived from the path under `sources/`; if sanitization collides, the script adds a short hash suffix.
* The link script writes `.skills-hub.json` in each target dir to track hub-managed entries and avoid touching non-hub skills.
* The link script dedupes by exact skill content hash and by `name:` in `SKILL.md`, keeping the newest copy (git commit time when available, otherwise file mtime). It prints any skipped duplicates and requires `python3`.
* If you move `~/agent-skills`, re-run the script to refresh links.

## Sources (submodules)

If you’re using git submodules, this is the list we currently track:

* `sources/anthropics-skills` — [https://github.com/anthropics/skills](https://github.com/anthropics/skills)
* `sources/skillcreatorai-ai-agent-skills` — [https://github.com/skillcreatorai/Ai-Agent-Skills.git](https://github.com/skillcreatorai/Ai-Agent-Skills.git)
* `sources/composio-awesome-claude-skills` — [https://github.com/ComposioHQ/awesome-claude-skills.git](https://github.com/ComposioHQ/awesome-claude-skills.git)
* `sources/rknall-claude-skills` — [https://github.com/rknall/claude-skills.git](https://github.com/rknall/claude-skills.git)
* `sources/lmorchard-agent-skills` — [https://github.com/lmorchard/lmorchard-agent-skills.git](https://github.com/lmorchard/lmorchard-agent-skills.git)
* `sources/kurrent-coding-agent-skills` — [https://github.com/kurrent-io/coding-agent-skills.git](https://github.com/kurrent-io/coding-agent-skills.git)
* `sources/feiskyer-codex-settings` — [https://github.com/feiskyer/codex-settings.git](https://github.com/feiskyer/codex-settings.git)

(If you add more, update this list)
