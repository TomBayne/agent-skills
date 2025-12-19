# Repository Guidelines

This repository is a lightweight hub that aggregates skill repositories under `sources/` and exposes them to Claude/Codex by symlinking skill folders that contain `SKILL.md`. Use the notes below when adding sources or adjusting the linking behavior.

## Project Structure & Module Organization
- `sources/` holds upstream skill repositories (usually git submodules listed in `.gitmodules`). Each skill is discovered by locating a `SKILL.md` file inside these trees.
- `scripts/skills-link.py` is the entry point for installing and removing symlinks.
- `README.md` documents usage and the current list of tracked sources; keep it updated when adding a new repo.

## Build, Test, and Development Commands
- `git submodule update --init --recursive` fetches all configured skill sources.
- `git submodule update --remote --merge` updates submodules to their latest remote revisions.
- `./scripts/skills-link.py` installs symlinks into `~/.claude/skills/` and `~/.codex/skills/`.
- `./scripts/skills-link.py --here` installs into `./.claude/skills/` and `./.codex/skills/` for repo-local use.
- `./scripts/skills-link.py --uninstall` removes only hub-created symlinks in the target directories.

## Coding Style & Naming Conventions
- Python scripts follow Python 3 with 4-space indentation, `snake_case` functions, and uppercase constants (see `scripts/skills-link.py`).
- Skills live at `sources/<repo>/<skill>/SKILL.md`. Keep directory names stable; symlink names are derived from the path and use `__` as separators (e.g., `repo__skill`).
- Avoid editing upstream submodule contents unless the change is intended to be contributed back.

## Testing Guidelines
- No automated tests are defined for the hub itself. Validate changes by running the link script and inspecting symlinks (e.g., `ls -l ~/.claude/skills`).
- For uninstall checks, run `./scripts/skills-link.py --uninstall` and confirm only hub links are removed.

## Commit & Pull Request Guidelines
- Commit messages in this repo are short, imperative, and sentence case (e.g., "Add anthropics skills as submodule"). Keep them concise without prefixes.
- PRs should describe which sources changed, include any `.gitmodules` updates, and note that linking was verified.

## Configuration Tips
- The `--here` option creates `.claude/` and `.codex/` directories in the repo; keep these local and uncommitted.
