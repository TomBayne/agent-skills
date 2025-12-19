#!/usr/bin/env python3
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

MANIFEST_FILENAME = ".skills-hub.json"
MANIFEST_VERSION = 1
SENTINEL_FILENAME = ".skills-hub-target"
MANAGED_FILES = {SENTINEL_FILENAME, "SKILL.md"}
IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "node_modules",
}
IGNORED_FILE_NAMES = {".DS_Store", "Thumbs.db", ".coverage"}
IGNORED_FILE_SUFFIXES = (".pyc", ".pyo")


def usage(prog):
    return f"""\
{prog} [--here] [--uninstall]

Default (no flags):
  Install into HOME:
    ~/.claude/skills/
    ~/.codex/skills/

--here:
  Install into the current directory:
    ./.claude/skills/
    ./.codex/skills/

--uninstall:
  Remove ONLY hub-managed entries in the target skills dirs.
  Leaves non-hub entries intact (preserves your own custom skills).
"""


def parse_args(argv, prog):
    here = False
    uninstall = False

    for arg in argv:
        if arg == "--here":
            here = True
        elif arg == "--uninstall":
            uninstall = True
        elif arg in ("-h", "--help"):
            print(usage(prog))
            sys.exit(0)
        else:
            print(f"Unknown arg: {arg}", file=sys.stderr)
            print(usage(prog), file=sys.stderr)
            sys.exit(2)

    return here, uninstall


def should_skip_dir(name):
    return name in IGNORED_DIR_NAMES


def should_skip_file(name):
    if name in IGNORED_FILE_NAMES:
        return True
    return name.endswith(IGNORED_FILE_SUFFIXES)


def name_max_for_dir(target_dir):
    try:
        value = os.pathconf(target_dir, "PC_NAME_MAX")
    except (AttributeError, ValueError, OSError):
        return 255
    return value if value and value > 0 else 255


def clamp_link_name(name, hash_source, name_max):
    if name_max is None or len(name) <= name_max:
        return name
    suffix = f"__{short_hash(hash_source)}"
    if name_max <= len(suffix):
        return suffix[-name_max:]
    return f"{name[: name_max - len(suffix)]}{suffix}"


def ensure_unique_name(name, hash_source, name_max, used):
    candidate = clamp_link_name(name, hash_source, name_max)
    key = candidate.casefold()
    if key not in used:
        used.add(key)
        return candidate
    for counter in range(1, 1000):
        salt = f"{hash_source}#{counter}"
        candidate = clamp_link_name(f"{name}__{short_hash(salt)}", salt, name_max)
        key = candidate.casefold()
        if key not in used:
            used.add(key)
            return candidate
    fallback = clamp_link_name(short_hash(hash_source), hash_source, name_max)
    used.add(fallback.casefold())
    return fallback


def manifest_path(target_dir):
    return os.path.join(target_dir, MANIFEST_FILENAME)


def read_manifest(target_dir):
    path = manifest_path(target_dir)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}, False
    except (OSError, json.JSONDecodeError):
        print(f"warning: unreadable manifest: {path}", file=sys.stderr)
        return {}, False
    if not isinstance(data, dict):
        print(f"warning: invalid manifest format: {path}", file=sys.stderr)
        return {}, False
    return data, True


def manifest_sources_dir(manifest):
    sources_dir = manifest.get("sources_dir")
    if isinstance(sources_dir, str) and sources_dir:
        return sources_dir
    return None


def manifest_link_targets(manifest):
    links = manifest.get("links", [])
    if not isinstance(links, list):
        return {}
    targets = {}
    for entry in links:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        target = entry.get("target")
        if isinstance(name, str) and name:
            targets[name] = target if isinstance(target, str) else ""
    return targets


def write_manifest(target_dir, manifest):
    path = manifest_path(target_dir)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_path, path)
    except OSError:
        print(f"warning: failed to write manifest: {path}", file=sys.stderr)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def remove_manifest(target_dir):
    path = manifest_path(target_dir)
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    except OSError:
        print(f"warning: failed to remove manifest: {path}", file=sys.stderr)


def sentinel_path(target_dir):
    return os.path.join(target_dir, SENTINEL_FILENAME)


def read_sentinel(target_dir):
    path = sentinel_path(target_dir)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().strip()
    except FileNotFoundError:
        return None
    except OSError:
        print(f"warning: unreadable sentinel: {path}", file=sys.stderr)
        return None
    return value or None


def write_sentinel(target_dir, target):
    path = sentinel_path(target_dir)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(target)
            handle.write("\n")
    except OSError:
        print(f"warning: failed to write sentinel: {path}", file=sys.stderr)


def resolve_link_target(path):
    try:
        link_target = os.readlink(path)
    except OSError:
        return None
    if not link_target:
        return None
    if os.path.isabs(link_target):
        return os.path.realpath(link_target)
    return os.path.realpath(os.path.join(os.path.dirname(path), link_target))


def is_hub_link(resolved_path, sources_dirs, manifest_target=None):
    if not resolved_path:
        return False
    for sources_dir in sources_dirs:
        if sources_dir and is_under_sources(resolved_path, sources_dir):
            return True
    if manifest_target:
        try:
            if os.path.realpath(manifest_target) == resolved_path:
                return True
        except OSError:
            pass
    return False


def is_hub_dir(path, sources_dirs, manifest_target=None):
    if not os.path.isdir(path):
        return False
    sentinel_target = read_sentinel(path)
    if sentinel_target:
        resolved = os.path.realpath(sentinel_target)
        if manifest_target:
            try:
                if os.path.realpath(manifest_target) == resolved:
                    return True
            except OSError:
                return False
        for sources_dir in sources_dirs:
            if sources_dir and is_under_sources(resolved, sources_dir):
                return True
        return False
    skill_target = resolve_link_target(os.path.join(path, "SKILL.md"))
    if not skill_target:
        return False
    if manifest_target:
        try:
            manifest_real = os.path.realpath(manifest_target)
        except OSError:
            manifest_real = None
        if manifest_real and is_under_sources(skill_target, manifest_real):
            return True
    for sources_dir in sources_dirs:
        if sources_dir and is_under_sources(skill_target, sources_dir):
            return True
    return False


def strip_inline_comment(value):
    if "#" not in value:
        return value
    index = value.find("#")
    if index == 0:
        return ""
    if value[index - 1].isspace():
        return value[:index].rstrip()
    return value


def parse_quoted_value(value):
    quote = value[0]
    result = []
    index = 1
    while index < len(value):
        char = value[index]
        if quote == '"' and char == "\\" and index + 1 < len(value):
            result.append(value[index + 1])
            index += 2
            continue
        if quote == "'" and char == "'" and index + 1 < len(value) and value[index + 1] == "'":
            result.append("'")
            index += 2
            continue
        if char == quote:
            return "".join(result).strip()
        result.append(char)
        index += 1
    return "".join(result).strip()


def parse_block_value(block_lines, indicator):
    if not block_lines:
        return ""
    min_indent = None
    for line in block_lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        if min_indent is None or indent < min_indent:
            min_indent = indent
    if min_indent is None:
        return ""
    normalized = []
    for line in block_lines:
        if not line:
            normalized.append("")
        else:
            normalized.append(line[min_indent:])
    if indicator == ">":
        return " ".join(part.strip() for part in normalized if part is not None).strip()
    return "\n".join(normalized).strip()


def parse_name_from_front_matter(lines):
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if not stripped.startswith("name:"):
            index += 1
            continue
        base_indent = len(line) - len(stripped)
        value = stripped.split(":", 1)[1].lstrip()
        if value == "" or value.startswith(("|", ">")):
            indicator = value[0] if value.startswith(("|", ">")) else "|"
            index += 1
            block_lines = []
            while index < len(lines):
                next_line = lines[index]
                if not next_line.strip():
                    block_lines.append("")
                    index += 1
                    continue
                indent = len(next_line) - len(next_line.lstrip())
                if indent <= base_indent:
                    break
                block_lines.append(next_line)
                index += 1
            return parse_block_value(block_lines, indicator)
        if value.startswith(("'", '"')):
            return parse_quoted_value(value)
        value = strip_inline_comment(value)
        return value.strip()
    return ""


def make_link_name(rel_path):
    name = re.sub(r"[\\/]", "__", rel_path)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return name


def short_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def build_link_entries(sources_dir, skill_dirs, name_max=None):
    entries = []
    for skill_dir in skill_dirs:
        rel = os.path.relpath(skill_dir, sources_dir)
        if rel == skill_dir or rel.startswith(".."):
            continue
        entries.append(
            {
                "dir": skill_dir,
                "rel": rel,
                "base": make_link_name(rel),
            }
        )

    by_base = {}
    for entry in entries:
        key = entry["base"].casefold()
        by_base.setdefault(key, []).append(entry)

    resolved = []
    used = set()
    for base_key in sorted(by_base):
        group = by_base[base_key]
        group_sorted = sorted(group, key=lambda e: e["rel"])
        if len(group_sorted) > 1:
            sys.stderr.write(
                f"Link name collision (case-insensitive) for {group_sorted[0]['base']}.\n"
            )
        for index, entry in enumerate(group_sorted):
            if index == 0:
                proposed = entry["base"]
            else:
                proposed = f"{entry['base']}__{short_hash(entry['rel'])}"
            final_name = ensure_unique_name(proposed, entry["rel"], name_max, used)
            entry["name"] = final_name
            if len(group_sorted) > 1:
                action = "keep" if index == 0 else "rename"
                sys.stderr.write(
                    f"  {action} {entry['rel']} as {final_name}\n"
                )
            elif final_name != proposed:
                sys.stderr.write(
                    f"Link name adjusted for {entry['rel']} -> {final_name}\n"
                )
            resolved.append(entry)
    return resolved


def iter_skill_dirs(sources_dir):
    for root, dirs, files in os.walk(sources_dir):
        dirs[:] = sorted([d for d in dirs if not should_skip_dir(d)])
        if "SKILL.md" in files:
            yield root


def parse_name(skill_dir):
    skill_md = os.path.join(skill_dir, "SKILL.md")
    try:
        with open(skill_md, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return ""
    if not lines or lines[0].strip() != "---":
        return ""
    front_matter = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        front_matter.append(line)
    if not front_matter:
        return ""
    return parse_name_from_front_matter(front_matter)


def hash_dir(skill_dir):
    hasher = hashlib.sha256()
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = sorted([d for d in dirs if not should_skip_dir(d)])
        files.sort()
        for filename in files:
            if should_skip_file(filename):
                continue
            path = os.path.join(root, filename)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            rel = os.path.relpath(path, skill_dir)
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            try:
                with open(path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(8192), b""):
                        hasher.update(chunk)
            except OSError:
                continue
            hasher.update(b"\0")
    return hasher.hexdigest()


def git_timestamp(skill_dir):
    try:
        root_proc = subprocess.run(
            ["git", "-C", skill_dir, "rev-parse", "--show-toplevel"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except FileNotFoundError:
        return None
    if root_proc.returncode != 0:
        return None
    git_root = root_proc.stdout.strip()
    if not git_root:
        return None
    rel = os.path.relpath(skill_dir, git_root)
    log_proc = subprocess.run(
        ["git", "-C", git_root, "log", "-1", "--format=%ct", "--", rel],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if log_proc.returncode != 0:
        return None
    ts = log_proc.stdout.strip()
    if not ts:
        return None
    try:
        return int(ts)
    except ValueError:
        return None


def max_mtime(skill_dir):
    max_ts = 0
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = [d for d in dirs if not should_skip_dir(d)]
        for filename in files:
            if should_skip_file(filename):
                continue
            path = os.path.join(root, filename)
            if not os.path.isfile(path) or os.path.islink(path):
                continue
            try:
                ts = int(os.path.getmtime(path))
            except OSError:
                continue
            if ts > max_ts:
                max_ts = ts
    return max_ts


def updated_at(skill_dir):
    ts = git_timestamp(skill_dir)
    if ts is not None:
        return ts
    return max_mtime(skill_dir)


def sort_key(entry):
    return (-entry["updated_at"], entry["dir"])


def log_duplicates(label, key, kept, skipped):
    kept_rel = kept["rel"]
    sys.stderr.write(
        f"{label} detected for {key}. Keeping {kept_rel}, skipping {len(skipped)}.\n"
    )
    for entry in skipped:
        sys.stderr.write(f"  skip {entry['rel']}\n")


def dedupe_by_hash(entries):
    by_hash = {}
    for entry in entries:
        by_hash.setdefault(entry["hash"], []).append(entry)
    kept = []
    for digest in sorted(by_hash):
        group = by_hash[digest]
        if len(group) == 1:
            kept.append(group[0])
            continue
        group_sorted = sorted(group, key=sort_key)
        kept.append(group_sorted[0])
        log_duplicates(
            "Exact duplicate content", digest, group_sorted[0], group_sorted[1:]
        )
    return kept


def dedupe_by_name(entries):
    by_name = {}
    unnamed = []
    for entry in entries:
        if not entry["name"]:
            unnamed.append(entry)
        else:
            by_name.setdefault(entry["name"], []).append(entry)
    kept = list(unnamed)
    for name in sorted(by_name):
        group = by_name[name]
        if len(group) == 1:
            kept.append(group[0])
            continue
        group_sorted = sorted(group, key=sort_key)
        kept.append(group_sorted[0])
        log_duplicates(
            "Duplicate skill name", name, group_sorted[0], group_sorted[1:]
        )
    return kept


def list_skill_dirs(sources_dir):
    entries = []
    for skill_dir in iter_skill_dirs(sources_dir):
        entries.append(
            {
                "dir": skill_dir,
                "rel": os.path.relpath(skill_dir, sources_dir),
                "name": parse_name(skill_dir),
                "hash": hash_dir(skill_dir),
                "updated_at": updated_at(skill_dir),
            }
        )
    if not entries:
        return []
    entries = dedupe_by_hash(entries)
    entries = dedupe_by_name(entries)
    return [entry["dir"] for entry in sorted(entries, key=lambda e: e["dir"])]


def build_manifest(sources_dir, entries):
    return {
        "version": MANIFEST_VERSION,
        "sources_dir": sources_dir,
        "links": sorted(entries, key=lambda e: e["name"]),
    }


def is_under_sources(resolved_path, sources_dir):
    try:
        return os.path.commonpath([sources_dir, resolved_path]) == sources_dir
    except ValueError:
        return False


def create_link_farm(dest_dir, source_dir):
    os.makedirs(dest_dir, exist_ok=True)
    write_sentinel(dest_dir, os.path.realpath(source_dir))
    skill_linked = False
    for entry in sorted(os.listdir(source_dir)):
        src = os.path.join(source_dir, entry)
        if os.path.isdir(src):
            if should_skip_dir(entry):
                continue
        elif os.path.isfile(src):
            if should_skip_file(entry):
                continue
        else:
            continue
        if entry == SENTINEL_FILENAME:
            continue
        if entry == "SKILL.md":
            dest = os.path.join(dest_dir, entry)
            if os.path.lexists(dest):
                print(f"skip (exists in hub dir): {dest}", file=sys.stderr)
                skill_linked = True
                continue
            try:
                shutil.copy2(src, dest)
            except OSError as exc:
                print(
                    f"warning: failed to copy SKILL.md: {dest} ({exc})",
                    file=sys.stderr,
                )
                continue
            skill_linked = True
            continue
        dest = os.path.join(dest_dir, entry)
        if os.path.lexists(dest):
            print(f"skip (exists in hub dir): {dest}", file=sys.stderr)
            continue
        try:
            os.symlink(os.path.realpath(src), dest)
        except OSError as exc:
            print(
                f"warning: failed to create symlink: {dest} ({exc})",
                file=sys.stderr,
            )
            continue
    return skill_linked


def remove_link_farm(path, sources_dirs, manifest_target=None, remove_dirty=False):
    if not is_hub_dir(path, sources_dirs, manifest_target):
        return False

    entries = []
    non_symlink = []
    for entry in os.listdir(path):
        entry_path = os.path.join(path, entry)
        entries.append((entry, entry_path))
        if entry in MANAGED_FILES:
            continue
        if os.path.islink(entry_path):
            continue
        non_symlink.append(entry)

    if non_symlink and not remove_dirty:
        print(
            f"skip (hub dir has non-symlink entries): {path}",
            file=sys.stderr,
        )
        return False

    for entry, entry_path in entries:
        if entry == SENTINEL_FILENAME:
            try:
                os.unlink(entry_path)
            except FileNotFoundError:
                pass
            except OSError:
                print(
                    f"warning: failed to remove sentinel: {entry_path}",
                    file=sys.stderr,
                )
            continue
        if entry == "SKILL.md" and os.path.isfile(entry_path):
            try:
                os.unlink(entry_path)
            except OSError:
                print(
                    f"warning: failed to remove SKILL.md: {entry_path}",
                    file=sys.stderr,
                )
            continue
        if os.path.islink(entry_path):
            try:
                os.unlink(entry_path)
            except OSError:
                print(
                    f"warning: failed to remove symlink: {entry_path}",
                    file=sys.stderr,
                )

    if non_symlink:
        return False

    try:
        os.rmdir(path)
    except OSError:
        print(f"warning: failed to remove hub dir: {path}", file=sys.stderr)
        return False
    return True


def remove_hub_entries_in_dir(target_dir, sources_dir, remove_dirty=False):
    os.makedirs(target_dir, exist_ok=True)

    manifest, manifest_exists = read_manifest(target_dir)
    manifest_targets = manifest_link_targets(manifest)
    sources_dirs = [sources_dir]
    manifest_sources = manifest_sources_dir(manifest)
    if manifest_sources and manifest_sources not in sources_dirs:
        sources_dirs.append(manifest_sources)

    if manifest_exists and manifest_targets:
        for name, target in manifest_targets.items():
            path = os.path.join(target_dir, name)
            if os.path.islink(path):
                resolved = resolve_link_target(path)
                if resolved is None:
                    print(
                        f"warning: skipping unreadable symlink: {path}",
                        file=sys.stderr,
                    )
                    continue
                if is_hub_link(resolved, sources_dirs, target):
                    try:
                        os.unlink(path)
                    except OSError:
                        print(
                            f"warning: failed to remove symlink: {path}",
                            file=sys.stderr,
                        )
                continue
            if os.path.isdir(path):
                remove_link_farm(
                    path,
                    sources_dirs,
                    manifest_target=target,
                    remove_dirty=remove_dirty,
                )
        return
    if manifest_exists and not manifest_targets:
        print(
            f"warning: manifest has no links, falling back to scan: {manifest_path(target_dir)}",
            file=sys.stderr,
        )

    for entry in os.listdir(target_dir):
        path = os.path.join(target_dir, entry)
        if os.path.islink(path):
            resolved = resolve_link_target(path)
            if resolved is None:
                print(
                    f"warning: skipping unreadable symlink: {path}",
                    file=sys.stderr,
                )
                continue
            if is_hub_link(resolved, sources_dirs):
                try:
                    os.unlink(path)
                except OSError:
                    print(f"warning: failed to remove symlink: {path}", file=sys.stderr)
            continue
        if os.path.isdir(path):
            remove_link_farm(path, sources_dirs, remove_dirty=remove_dirty)


def install_links_into_dir(target_dir, sources_dir, link_entries, manifest, manifest_exists):
    os.makedirs(target_dir, exist_ok=True)

    manifest_targets = manifest_link_targets(manifest)
    manifest_sources = manifest_sources_dir(manifest)
    sources_dirs = [sources_dir]
    if manifest_sources and manifest_sources not in sources_dirs:
        sources_dirs.append(manifest_sources)

    count = 0
    installed = []
    manifest_active = manifest_exists
    for entry in link_entries:
        dest = os.path.join(target_dir, entry["name"])

        if os.path.islink(dest):
            resolved = resolve_link_target(dest)
            if resolved is None:
                print(f"skip (unreadable symlink): {dest}", file=sys.stderr)
                continue
            if manifest_active:
                target = manifest_targets.get(entry["name"])
                if not target or not is_hub_link(resolved, sources_dirs, target):
                    print(
                        f"skip (existing symlink not managed): {dest}",
                        file=sys.stderr,
                    )
                    continue
            else:
                if not is_hub_link(resolved, sources_dirs):
                    print(
                        f"skip (existing symlink not managed): {dest}",
                        file=sys.stderr,
                    )
                    continue
            try:
                os.unlink(dest)
            except OSError:
                print(f"warning: failed to remove symlink: {dest}", file=sys.stderr)
                continue
        elif os.path.isdir(dest):
            manifest_target = manifest_targets.get(entry["name"]) if manifest_active else None
            if manifest_active and not manifest_target:
                print(f"skip (existing dir not managed): {dest}", file=sys.stderr)
                continue
            if not is_hub_dir(dest, sources_dirs, manifest_target):
                print(f"skip (existing dir not managed): {dest}", file=sys.stderr)
                continue
            if not remove_link_farm(
                dest,
                sources_dirs,
                manifest_target=manifest_target,
                remove_dirty=False,
            ):
                print(
                    f"skip (hub dir has non-symlink entries): {dest}",
                    file=sys.stderr,
                )
                continue
        elif os.path.lexists(dest):
            print(f"skip (exists, not symlink or dir): {dest}", file=sys.stderr)
            continue

        try:
            skill_linked = create_link_farm(dest, entry["dir"])
        except OSError as exc:
            print(
                f"warning: failed to create hub dir: {dest} ({exc})",
                file=sys.stderr,
            )
            continue
        if not skill_linked:
            print(f"warning: missing SKILL.md link in: {dest}", file=sys.stderr)
            remove_link_farm(
                dest,
                sources_dirs,
                manifest_target=entry["dir"],
                remove_dirty=True,
            )
            continue
        count += 1
        installed.append(
            {
                "name": entry["name"],
                "target": os.path.realpath(entry["dir"]),
                "rel": entry["rel"],
            }
        )

    return count, installed


def main():
    prog = os.path.basename(sys.argv[0])
    here, uninstall = parse_args(sys.argv[1:], prog)

    script_dir = os.path.dirname(os.path.realpath(__file__))
    root_dir = os.path.realpath(os.path.join(script_dir, ".."))
    sources_dir = os.path.join(root_dir, "sources")
    sources_dir_real = os.path.realpath(sources_dir)

    if not os.path.isdir(sources_dir):
        print(f"Missing sources directory: {sources_dir}", file=sys.stderr)
        return 1

    base_dir = os.getcwd() if here else os.path.expanduser("~")
    claude_dir = os.path.join(base_dir, ".claude", "skills")
    codex_dir = os.path.join(base_dir, ".codex", "skills")

    if uninstall:
        remove_hub_entries_in_dir(claude_dir, sources_dir_real, remove_dirty=True)
        remove_hub_entries_in_dir(codex_dir, sources_dir_real, remove_dirty=True)
        remove_manifest(claude_dir)
        remove_manifest(codex_dir)
        print("Uninstalled hub entries from:")
        print(f"  {claude_dir}")
        print(f"  {codex_dir}")
        return 0

    os.makedirs(claude_dir, exist_ok=True)
    os.makedirs(codex_dir, exist_ok=True)
    name_max = min(name_max_for_dir(claude_dir), name_max_for_dir(codex_dir))

    skill_dirs = list_skill_dirs(sources_dir_real)
    if not skill_dirs:
        print(f"No SKILL.md found under: {sources_dir}", file=sys.stderr)
        return 1
    link_entries = build_link_entries(sources_dir_real, skill_dirs, name_max)
    if not link_entries:
        print(f"No SKILL.md found under: {sources_dir}", file=sys.stderr)
        return 1

    remove_hub_entries_in_dir(claude_dir, sources_dir_real, remove_dirty=False)
    remove_hub_entries_in_dir(codex_dir, sources_dir_real, remove_dirty=False)

    claude_manifest, claude_manifest_exists = read_manifest(claude_dir)
    codex_manifest, codex_manifest_exists = read_manifest(codex_dir)

    c1, claude_entries = install_links_into_dir(
        claude_dir,
        sources_dir_real,
        link_entries,
        claude_manifest,
        claude_manifest_exists,
    )
    c2, codex_entries = install_links_into_dir(
        codex_dir,
        sources_dir_real,
        link_entries,
        codex_manifest,
        codex_manifest_exists,
    )

    write_manifest(claude_dir, build_manifest(sources_dir_real, claude_entries))
    write_manifest(codex_dir, build_manifest(sources_dir_real, codex_entries))

    print("Installed hub entries:")
    print(f"  Claude: {claude_dir} ({c1})")
    print(f"  Codex:  {codex_dir} ({c2})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
