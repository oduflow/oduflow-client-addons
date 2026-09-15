#!/usr/bin/env python3
"""Проверка полноты, актуальности и структуры переводов документации."""

import argparse
import difflib
import hashlib
import re
import subprocess
import sys
from pathlib import Path


MARKER_RE = re.compile(
    r"^<!-- i18n source=(?P<source>[^ ]+) sha=(?P<sha>[0-9a-f]{12}) "
    r"lang=(?P<lang>[a-z]{2,3}) -->$"
)
SETTING_RE = re.compile(r"^- (?P<key>[a-z-]+):\s*(?P<value>.*)$")
LANG_RE = re.compile(r"^[a-z]{2,3}$")
HEADING_RE = re.compile(r"^(?P<level>#{1,6})\s+")
LIST_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>[-+*]|\d+[.)])\s+")
FENCE_RE = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
INLINE_CODE_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
LINK_TARGET_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")
URL_RE = re.compile(r"https?://[^\s<>)\]]+")


def parse_settings(path):
    settings = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SETTING_RE.match(line.strip())
        if match:
            settings[match.group("key")] = [
                value.strip()
                for value in match.group("value").split(",")
                if value.strip()
            ]
    return settings


def validate_settings(settings):
    sources = settings.get("source", [])
    targets = settings.get("targets", [])
    entries = settings.get("translate", []) + settings.get("source-only", [])
    if len(sources) != 1:
        raise ValueError("LANG.local.md must define exactly one source language")
    if not targets:
        raise ValueError("LANG.local.md must define at least one target language")
    if len(targets) != len(set(targets)):
        raise ValueError("LANG.local.md contains duplicate target languages")
    invalid_targets = [code for code in targets if not LANG_RE.match(code)]
    if invalid_targets:
        raise ValueError("Invalid target language: %s" % invalid_targets[0])
    for entry in entries:
        path = entry_path(entry)
        if not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("Invalid documentation path: %s" % entry)
        unknown_langs = entry_langs(entry) - set(targets)
        if unknown_langs:
            raise ValueError(
                "Unknown language restriction in %s: %s"
                % (entry, ", ".join(sorted(unknown_langs)))
            )


def source_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def split_marker(text):
    lines = text.splitlines(keepends=True)
    if not lines:
        return None, ""
    marker = MARKER_RE.match(lines[0].rstrip("\r\n"))
    if marker:
        return marker, "".join(lines[1:])
    return None, text


def read_mirror(path):
    try:
        return split_marker(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None, None


def iter_modules(addons_path):
    for manifest in sorted(addons_path.glob("*/__manifest__.py")):
        yield manifest.parent


def entry_langs(entry):
    """``changes/@ru`` -> ``{"ru"}``; без суффикса -- все цели."""
    _, _, langs = entry.partition("@")
    return {code.strip() for code in langs.split("+") if code.strip()}


def entry_path(entry):
    """Отбросить суффикс ограничения языка."""
    return entry.partition("@")[0]


def expand_entry(doc_dir, mirror_dir, entry):
    """Развернуть файл или каталог translate в относительные пути."""
    entry = entry_path(entry)
    if not entry.endswith("/"):
        return [entry]
    subdir = entry.rstrip("/")
    names = set()
    for base in (doc_dir / subdir, mirror_dir / subdir):
        if base.is_dir():
            names.update(
                "%s/%s" % (subdir, path.name)
                for path in base.glob("*.md")
            )
    return sorted(names)


def expected_files(doc_dir, mirror_dir, entries, lang):
    return {
        name
        for entry in entries
        if not entry_langs(entry) or lang in entry_langs(entry)
        for name in expand_entry(doc_dir, mirror_dir, entry)
    }


def table_columns(line):
    stripped = line.strip()
    if "|" not in stripped:
        return None
    if not (stripped.startswith("|") or stripped.endswith("|")):
        return None
    parts = re.split(r"(?<!\\)\|", stripped)
    if stripped.startswith("|"):
        parts = parts[1:]
    if stripped.endswith("|"):
        parts = parts[:-1]
    return len(parts) if len(parts) > 1 else None


def markdown_structure(text):
    """Вернуть переводонезависимый структурный отпечаток Markdown."""
    headings = []
    lists = []
    tables = []
    fences = []
    inline_code = []
    links = []
    urls = []
    open_fence = None
    fence_info = None
    fence_lines = []

    for line in text.splitlines():
        if open_fence:
            stripped = line.strip()
            if (
                stripped
                and set(stripped) == {open_fence[0]}
                and len(stripped) >= len(open_fence)
            ):
                fences.append((open_fence[0], fence_info, tuple(fence_lines), True))
                open_fence = None
                fence_info = None
                fence_lines = []
            else:
                fence_lines.append(line)
            continue

        fence = FENCE_RE.match(line)
        if fence:
            open_fence = fence.group("fence")
            fence_info = fence.group("info").strip()
            continue

        heading = HEADING_RE.match(line)
        if heading:
            headings.append(len(heading.group("level")))

        list_item = LIST_RE.match(line)
        if list_item:
            marker = list_item.group("marker")
            marker_kind = "ordered" if marker[0].isdigit() else "unordered"
            indent = len(list_item.group("indent").expandtabs(4))
            lists.append((indent, marker_kind))

        columns = table_columns(line)
        if columns:
            tables.append(columns)

        inline_code.extend(INLINE_CODE_RE.findall(line))
        links.extend(LINK_TARGET_RE.findall(line))
        urls.extend(URL_RE.findall(line))

    if open_fence:
        fences.append((open_fence[0], fence_info, tuple(fence_lines), False))

    return {
        "heading levels": tuple(headings),
        "list structure": tuple(lists),
        "table columns": tuple(tables),
        "fenced code": tuple(fences),
        "inline code": tuple(inline_code),
        "link targets": tuple(links),
        "URLs": tuple(urls),
    }


def structure_mismatches(source_text, mirror_text):
    source_structure = markdown_structure(source_text)
    mirror_structure = markdown_structure(mirror_text)
    return [
        name
        for name, value in source_structure.items()
        if value != mirror_structure[name]
    ]


def git_bytes(repo_root, ref, path):
    relative = path.relative_to(repo_root).as_posix()
    result = subprocess.run(
        ["git", "show", "%s:%s" % (ref, relative)],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def validate_git_ref(repo_root, ref):
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "%s^{commit}" % ref],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        raise ValueError("Git reference does not exist: %s" % ref)


def decoded_body(raw):
    if raw is None:
        return None
    try:
        return split_marker(raw.decode("utf-8"))[1]
    except UnicodeDecodeError:
        return None


def update_marker(path, filename, lang, sha):
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    marker = "<!-- i18n source=%s sha=%s lang=%s -->\n" % (
        filename, sha, lang)
    if not lines or not MARKER_RE.match(lines[0].rstrip("\r\n")):
        raise ValueError("Cannot update missing or malformed marker: %s" % path)
    path.write_text(marker + "".join(lines[1:]), encoding="utf-8")


def print_source_diffs(diffs, against):
    for relative, old_raw, new_raw in sorted(diffs):
        old_lines = old_raw.decode("utf-8", errors="replace").splitlines(True)
        new_lines = new_raw.decode("utf-8", errors="replace").splitlines(True)
        print("source-diff: %s" % relative)
        sys.stdout.writelines(difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="%s/%s" % (against, relative),
            tofile="working/%s" % relative,
        ))


def check(
    repo_root,
    selected_lang=None,
    against=None,
    show_diff=False,
    fix_markers=False,
    allow_unchanged=False,
    strict_structure=False,
):
    settings = parse_settings(repo_root / "LANG.local.md")
    validate_settings(settings)
    entries = settings.get("translate", [])
    targets = settings.get("targets", [])
    if selected_lang:
        if selected_lang not in targets:
            raise ValueError(
                "Language %s is not configured as a target" % selected_lang)
        targets = [selected_lang]
    if fix_markers and not against:
        raise ValueError("--fix-markers requires --against")
    if show_diff and not against:
        raise ValueError("--show-diff requires --against")
    if against:
        validate_git_ref(repo_root, against)

    problems = []
    updates = []
    diffs = {}
    for module in iter_modules(repo_root / "addons"):
        doc_dir = module / "doc"
        if not doc_dir.is_dir():
            continue
        for lang in targets:
            mirror_dir = doc_dir / "i18n" / lang
            filenames = expected_files(doc_dir, mirror_dir, entries, lang)
            existing_mirrors = {
                path.relative_to(mirror_dir).as_posix()
                for path in mirror_dir.rglob("*.md")
            } if mirror_dir.is_dir() else set()
            for filename in sorted(existing_mirrors - filenames):
                label = "%s:%s:%s" % (module.name, lang, filename)
                problems.append(("orphaned", label, "not configured for this language"))

            for filename in sorted(filenames):
                source = doc_dir / filename
                mirror = mirror_dir / filename
                label = "%s:%s:%s" % (module.name, lang, filename)
                if source.is_file() and not mirror.is_file():
                    problems.append(("missing", label, "mirror file is absent"))
                    continue
                if not source.is_file() and mirror.is_file():
                    problems.append(("orphaned", label, "source file is absent"))
                    continue
                if not source.is_file():
                    continue

                pair_problems = []
                marker, mirror_body = read_mirror(mirror)
                if mirror_body is None:
                    pair_problems.append(("invalid", label, "mirror is not readable UTF-8"))
                    problems.extend(pair_problems)
                    continue

                expected_sha = source_sha(source)
                if marker is None:
                    pair_problems.append(("marker", label, "missing or malformed marker"))
                elif (
                    marker.group("source") != filename
                    or marker.group("lang") != lang
                ):
                    pair_problems.append(("marker", label, "source or language mismatch"))
                elif marker.group("sha") != expected_sha:
                    pair_problems.append(("stale", label, "source SHA changed"))

                old_source = None
                old_mirror = None
                source_changed = False
                mirror_changed = False
                if against:
                    old_source = git_bytes(repo_root, against, source)
                    old_mirror = git_bytes(repo_root, against, mirror)
                    source_changed = old_source != source.read_bytes()
                    mirror_changed = old_mirror != mirror.read_bytes()
                    if source_changed:
                        relative = source.relative_to(repo_root).as_posix()
                        diffs[relative] = (
                            relative, old_source or b"", source.read_bytes())
                        old_body = decoded_body(old_mirror)
                        if (
                            old_source is not None
                            and old_body is not None
                            and old_body == mirror_body
                            and not allow_unchanged
                        ):
                            pair_problems.append((
                                "unchanged",
                                label,
                                "source changed since %s but mirror body did not" % against,
                            ))

                if strict_structure or source_changed or mirror_changed:
                    source_text = source.read_text(encoding="utf-8")
                    mismatches = structure_mismatches(source_text, mirror_body)
                    if mismatches:
                        pair_problems.append((
                            "structure",
                            label,
                            "mismatch: %s" % ", ".join(mismatches),
                        ))

                kinds = {problem[0] for problem in pair_problems}
                if (
                    fix_markers
                    and kinds == {"stale"}
                    and (mirror_changed or allow_unchanged)
                ):
                    update_marker(mirror, filename, lang, expected_sha)
                    updates.append(label)
                    pair_problems = []
                problems.extend(pair_problems)

    if show_diff:
        print_source_diffs(diffs.values(), against)
    for label in updates:
        print("updated: %s" % label)
    for kind, label, detail in problems:
        print("%s: %s (%s)" % (kind, label, detail))
    if problems:
        print(
            "Documentation translations are not synchronized: %d problem(s)."
            % len(problems)
        )
        return 1
    print("Documentation translations are synchronized for: %s" % ", ".join(targets))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", help="check one configured target language")
    parser.add_argument(
        "--against",
        help="compare source and mirror changes with a git reference",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="show source diffs relative to --against",
    )
    parser.add_argument(
        "--fix-markers",
        action="store_true",
        help="update stale SHA markers after all safety checks pass",
    )
    parser.add_argument(
        "--allow-unchanged",
        action="store_true",
        help="allow marker-only mirror updates after manual verification",
    )
    parser.add_argument(
        "--strict-structure",
        action="store_true",
        help="audit Markdown structure for every configured mirror",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        help="repository root; defaults to the skill's repository",
    )
    args = parser.parse_args()
    repo_root = (
        args.repo_root.resolve()
        if args.repo_root
        else Path(__file__).resolve().parents[4]
    )
    try:
        return check(
            repo_root,
            selected_lang=args.lang,
            against=args.against,
            show_diff=args.show_diff,
            fix_markers=args.fix_markers,
            allow_unchanged=args.allow_unchanged,
            strict_structure=args.strict_structure,
        )
    except (OSError, ValueError) as error:
        print("error: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
