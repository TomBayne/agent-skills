#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
skills-link.sh [--here] [--uninstall]

Default (no flags):
  Install into HOME:
    ~/.claude/skills/
    ~/.codex/skills/

--here:
  Install into the current directory:
    ./.claude/skills/
    ./.codex/skills/

--uninstall:
  Remove ONLY symlinks in the target skills dirs that point into this hub's ./sources/.
  Leaves non-symlink entries intact (preserves your own custom skills).
USAGE
}

HERE=0
UNINSTALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --here) HERE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SOURCES_DIR="${ROOT_DIR}/sources"

abspath() {
  # Works on macOS + Linux without requiring realpath(1)
  if command -v python3 >/dev/null 2>&1; then
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
    return
  fi
  perl -MCwd=abs_path -e 'print abs_path(shift)' "$1"
}

make_link_name() {
  # Unique name derived from path under ./sources
  # e.g. anthropics-skills/document-skills/pdf -> anthropics-skills__document-skills__pdf
  echo "$1" \
    | sed -e 's#[/\\]#__#g' \
          -e 's#[[:space:]]\+#_#g' \
          -e 's#[^A-Za-z0-9_.-]#_#g'
}

list_skill_dirs() {
  find "$SOURCES_DIR" -type f -name 'SKILL.md' -print0 2>/dev/null \
    | while IFS= read -r -d '' skill_md; do
        dirname "$skill_md"
      done
}

remove_hub_symlinks_in_dir() {
  local target_dir="$1"
  mkdir -p "$target_dir"

  shopt -s nullglob
  local entry link_target resolved
  for entry in "$target_dir"/*; do
    [[ -L "$entry" ]] || continue

    link_target="$(readlink "$entry" || true)"
    [[ -n "$link_target" ]] || { rm -f "$entry"; continue; }

    if [[ "$link_target" = /* ]]; then
      resolved="$(abspath "$link_target")"
    else
      resolved="$(abspath "$(dirname "$entry")/$link_target")"
    fi

    case "$resolved" in
      "$SOURCES_DIR"/*) rm -f "$entry" ;;
    esac
  done
}

install_links_into_dir() {
  local target_dir="$1"
  mkdir -p "$target_dir"

  local count=0
  local skill_dir rel link_name dest

  while IFS= read -r skill_dir; do
    rel="${skill_dir#${SOURCES_DIR}/}"
    [[ "$rel" != "$skill_dir" ]] || continue

    link_name="$(make_link_name "$rel")"
    dest="${target_dir}/${link_name}"

    if [[ -e "$dest" && ! -L "$dest" ]]; then
      echo "skip (exists, not symlink): $dest" >&2
      continue
    fi

    ln -sfn "$(abspath "$skill_dir")" "$dest"
    count=$((count + 1))
  done < <(list_skill_dirs | sort -u)

  echo "$count"
}

if [[ ! -d "$SOURCES_DIR" ]]; then
  echo "Missing sources directory: $SOURCES_DIR" >&2
  exit 1
fi

# Pick target base (HOME default)
if [[ "$HERE" -eq 1 ]]; then
  BASE_DIR="$PWD"
else
  BASE_DIR="$HOME"
fi

CLAUDE_DIR="${BASE_DIR}/.claude/skills"
CODEX_DIR="${BASE_DIR}/.codex/skills"

# Ensure there is at least one skill before installing
if [[ "$UNINSTALL" -eq 0 ]]; then
  if ! find "$SOURCES_DIR" -type f -name 'SKILL.md' -print -quit 2>/dev/null | grep -q .; then
    echo "No SKILL.md found under: $SOURCES_DIR" >&2
    exit 1
  fi
fi

if [[ "$UNINSTALL" -eq 1 ]]; then
  remove_hub_symlinks_in_dir "$CLAUDE_DIR"
  remove_hub_symlinks_in_dir "$CODEX_DIR"
  echo "Uninstalled hub symlinks from:"
  echo "  $CLAUDE_DIR"
  echo "  $CODEX_DIR"
  exit 0
fi

# Prune previous hub symlinks first (keeps your custom non-symlink skills intact)
remove_hub_symlinks_in_dir "$CLAUDE_DIR"
remove_hub_symlinks_in_dir "$CODEX_DIR"

c1="$(install_links_into_dir "$CLAUDE_DIR")"
c2="$(install_links_into_dir "$CODEX_DIR")"

echo "Installed symlinks:"
echo "  Claude: $CLAUDE_DIR ($c1)"
echo "  Codex:  $CODEX_DIR ($c2)"
