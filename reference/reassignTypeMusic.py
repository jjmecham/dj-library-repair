import os
import hashlib
import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

from mutagen import File as MutagenFile

# ---- Global state flags ----
scan_path: Path | None = None
same_track_dry_run_done = False
same_track_done = False
hash_cleanup_dry_run_done = False
hash_cleanup_done = False
extension_dry_run_done = False
extension_done = False
final_naming_dry_run_done = False
final_naming_done = False
SKIPPED_EDGE_FILENAMES = {".mp3", ".flac"}
stage_counts: dict[str, dict[str, int | str]] = {}
ARCHIVE_FOLDERS = ("_COPIES_", "_FILTERED_", "_REVIEW_")
STAGE_COLORS = {
    "extensions": "\033[38;5;117m",
    "same-track": "\033[38;5;216m",
    "exact-copies": "\033[38;5;118m",
    "final-naming": "\033[38;5;229m",
    "snapshot": "\033[38;5;117m",
    "menu-path": "\033[38;5;33m",
    "menu-exit": "\033[38;5;196m",
    "info": "\033[97m",
    "error": "\033[38;5;208m",
}
ANSI_RESET = "\033[0m"
PROGRESS_TICKS = 20
_progress_line_stage: str | None = None
_progress_line_length = 0
_hash_plan_root: Path | None = None
_hash_plan_signature: dict[str, tuple[int, int, int]] = {}
_hash_plan_groups: dict[str, list[Path]] = {}
_hash_plan_audio_count = 0
workflow_snapshot_root: Path | None = None
workflow_snapshot_path: Path | None = None
workflow_start_total: int | None = None
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}"
    for prefix in ("COM", "LPT")
    for number in range(1, 10)
}
ASCII_STAGE_LABELS = {
    "extensions": "[EXT]",
    "same-track": "[MATCH]",
    "exact-copies": "[HASH]",
    "final-naming": "[NAME]",
    "snapshot": "[SNAPSHOT]",
    "menu-path": "[PATH]",
    "menu-exit": "[EXIT]",
}

AUDIO_FORMAT_EXTENSIONS = {
    "AAC": ".aac",
    "AIFF": ".aiff",
    "ASF": ".wma",
    "FLAC": ".flac",
    "MP3": ".mp3",
    "MP4": ".m4a",
    "MonkeysAudio": ".ape",
    "Musepack": ".mpc",
    "OggFLAC": ".oga",
    "OggOpus": ".opus",
    "OggSpeex": ".spx",
    "OggVorbis": ".ogg",
    "OptimFROG": ".ofr",
    "TrueAudio": ".tta",
    "WAVE": ".wav",
    "WavPack": ".wv",
}
NON_AUDIO_SUFFIXES = {
    ".crate", ".csv", ".cue", ".db", ".jpeg", ".jpg", ".json", ".log",
    ".m3u", ".m3u8", ".nml", ".pdf", ".png", ".txt", ".xml",
}

# ---- Helpers ----

def _enable_terminal_colors() -> bool:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        output_handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(output_handle, ctypes.byref(mode)):
            return False
        virtual_terminal_mode = 0x0004
        return bool(kernel32.SetConsoleMode(output_handle, mode.value | virtual_terminal_mode))
    except (AttributeError, OSError, TypeError):
        return False


COLOR_OUTPUT_ENABLED = _enable_terminal_colors()


def _color(text: str, stage: str) -> str:
    if COLOR_OUTPUT_ENABLED:
        return f"{STAGE_COLORS.get(stage, '')}{text}{ANSI_RESET}"
    label = ASCII_STAGE_LABELS.get(stage)
    return f"{label} {text}" if label else text


def _print_error(message: str) -> None:
    print(_color(message, "error"))


def _progress(stage: str, action: str, current: int, total: int) -> None:
    global _progress_line_stage, _progress_line_length
    if total <= 0:
        return
    interval = max(1, total // PROGRESS_TICKS)
    if current != total and current % interval != 0:
        return

    percent = current * 100 // total
    message = _color(f"Working... {percent}%", stage)
    interactive = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if not interactive and current != total:
        return

    if interactive:
        if _progress_line_stage is not None and _progress_line_stage != stage:
            sys.stdout.write("\n")
            _progress_line_length = 0
        padding = " " * max(0, _progress_line_length - len(message))
        sys.stdout.write("\r" + message + padding)
        sys.stdout.flush()
        _progress_line_stage = stage
        _progress_line_length = len(message)
        if current == total:
            sys.stdout.write("\n")
            sys.stdout.flush()
            _progress_line_stage = None
            _progress_line_length = 0
    else:
        print(message)


def _print_dry_run_summary(stage: str, changed_files: int, total_files: int) -> None:
    if total_files == 0:
        print(_color("Working... 100%", stage))
    print(_color(f"Total files changed: {changed_files}", "info"))
    print(_color(f"Total files: {total_files}", "info"))


def _archive_count(root: Path, folder_name: str) -> int:
    folder = root / folder_name
    return sum(1 for path in folder.iterdir() if path.is_file()) if folder.is_dir() else 0


def _managed_file_count(root: Path) -> int:
    return len(_keeper_files(root)) + sum(
        _archive_count(root, folder_name) for folder_name in ARCHIVE_FOLDERS
    )


def _record_stage_counts(
    stage: str,
    root_before: int,
    audio_before: int,
    root_after: int,
    audio_after: int,
    destination_folder: str,
    destination_before: int,
    destination_after: int,
    managed_before: int,
    managed_after: int,
) -> bool:
    stage_counts[stage] = {
        "root_before": root_before,
        "audio_before": audio_before,
        "root_after": root_after,
        "audio_after": audio_after,
        "destination_before": destination_before,
        "destination_after": destination_after,
        "destination_folder": destination_folder,
        "managed_before": managed_before,
        "managed_after": managed_after,
    }
    print(_color(
        f"[VALIDATED] {stage}: root files {root_before} → {root_after}; "
        f"audio {audio_before} → {audio_after}; "
        f"{destination_folder} {destination_before} → {destination_after}; "
        f"total files {managed_before} → {managed_after}",
        "info",
    ))
    balanced = managed_before == managed_after
    if not balanced:
        _print_error(f"[ERROR] Total tracked file count changed during {stage}.")
    return balanced


def _print_stage_ledger() -> None:
    if workflow_start_total is None:
        print(_color("Total files (starting number): [folder not selected]", "info"))
        return
    print(_color(f"Total files (starting number): {workflow_start_total}", "info"))
    stage_order = (
        ("extensions", "After Step 2/3 - Extension repair"),
        ("same-track", "After Step 4/5 - Same-track review"),
        ("exact-copies", "After Step 6/7 - Exact-copy cleanup"),
        ("final-naming", "After Step 8/9 - Final naming"),
    )
    for stage, label in stage_order:
        counts = stage_counts.get(stage)
        if counts is None:
            print(_color(f"{label}: pending", "info"))
        else:
            print(_color(f"{label}: {counts['root_after']} remain in root", "info"))


def _create_stage_snapshot(root: Path, stage: str) -> Path | None:
    snapshot_root = root / "_SNAPSHOTS_"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    snapshot = snapshot_root / f"{timestamp}-{stage}"
    sources = [(path, path.name) for path in _keeper_files(root)]
    for folder_name in ARCHIVE_FOLDERS:
        archive = root / folder_name
        if archive.is_dir():
            sources.extend(
                (path, str(Path(folder_name) / path.name))
                for path in archive.iterdir()
                if path.is_file()
            )

    try:
        required_bytes = sum(path.stat().st_size for path, _ in sources)
        available_bytes = shutil.disk_usage(root).free
        if required_bytes > available_bytes:
            print(_color(
                f"[ERROR] Snapshot needs {required_bytes:,} bytes but only "
                f"{available_bytes:,} bytes are free. Stage cancelled.",
                stage,
            ))
            return None

        snapshot.mkdir(parents=True)
        print(_color(f"[SNAPSHOT] Creating {snapshot} ({required_bytes:,} bytes)", stage))
        for index, (source, relative_name) in enumerate(sources, start=1):
            destination = snapshot / relative_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            _progress(stage, "snapshot files copied", index, len(sources))
        print(_color(f"[SNAPSHOT] Complete: {len(sources)} files", stage))
        return snapshot
    except Exception as error:
        shutil.rmtree(snapshot, ignore_errors=True)
        _print_error(f"[ERROR] Snapshot failed; stage cancelled: {error}")
        return None


def _ensure_workflow_snapshot(root: Path) -> Path | None:
    global workflow_snapshot_root, workflow_snapshot_path
    resolved_root = root.resolve()
    if workflow_snapshot_root == resolved_root and workflow_snapshot_path is not None:
        if workflow_snapshot_path.is_dir():
            return workflow_snapshot_path

    snapshot = _create_stage_snapshot(root, "snapshot")
    if snapshot is None:
        return None
    workflow_snapshot_root = resolved_root
    workflow_snapshot_path = snapshot
    return snapshot


def _menu_option(number: int, label: str, stage: str, is_next: bool = False) -> None:
    counts = stage_counts.get(stage)
    summary = ""
    if counts:
        summary = (
            f" | last: root {counts['root_before']}→{counts['root_after']}, "
            f"audio {counts['audio_before']}→{counts['audio_after']}, "
            f"{counts['destination_folder']} {counts['destination_before']}→{counts['destination_after']}"
        )
    text = f"{number}) {label}{summary}"
    if is_next and COLOR_OUTPUT_ENABLED:
        print(f"{STAGE_COLORS.get(stage, '')}\033[1m{text}{ANSI_RESET}")
    elif is_next:
        print(f"[NEXT] {text}")
    else:
        print(_color(text, stage))


def _next_menu_choice() -> tuple[int, str]:
    if scan_path is None:
        return 1, "menu-path"
    if not extension_dry_run_done:
        return 2, "extensions"
    if not extension_done:
        return 3, "extensions"
    if not same_track_dry_run_done:
        return 4, "same-track"
    if not same_track_done:
        return 5, "same-track"
    if not hash_cleanup_dry_run_done:
        return 6, "exact-copies"
    if not hash_cleanup_done:
        return 7, "exact-copies"
    if not final_naming_dry_run_done:
        return 8, "final-naming"
    if not final_naming_done:
        return 9, "final-naming"
    return 10, "menu-exit"

def input_path(prompt: str) -> Path | None:
    p = input(prompt).strip('"').strip()
    if not p:
        return None
    path = Path(p)
    if not path.exists() or not path.is_dir():
        _print_error(f"[ERROR] Invalid path: {path}")
        return None
    return path


def audio_extension(path: Path) -> str | None:
    try:
        audio = MutagenFile(path)
    except Exception:
        return None

    if audio is None:
        return None

    return AUDIO_FORMAT_EXTENSIONS.get(type(audio).__name__)


def _remove_parentheses(value: str) -> str:
    return value.replace("(", "").replace(")", "")


def _remove_prefix(value: str) -> str:
    return re.sub(r"^[0-9\-\s]+", "", value)


def _name_tag_keys(tags) -> list:
    return [
        key for key in tags.keys()
        if str(key).casefold() == "name"
        or str(key).casefold().startswith("txxx:name")
    ]


def _title_tag_keys(tags) -> list:
    return [
        key for key in tags.keys()
        if str(key).casefold() in {"tit2", "title", "©nam"}
        or "title" in str(key).casefold()
    ]


def _filename_tag_keys(tags) -> list:
    return [
        key for key in tags.keys()
        if str(key).casefold() in {"filename", "file name"}
        or str(key).casefold().startswith("txxx:filename")
    ]


def _tag_text_values(value) -> list[str] | None:
    if hasattr(value, "text"):
        values = value.text
        return [str(item) for item in values] if isinstance(values, list) else [str(values)]
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    if hasattr(value, "value"):
        return [str(value.value)]
    return None


def _name_tag_changes(path: Path, transform) -> list[tuple[str, list[str], list[str]]]:
    try:
        audio = MutagenFile(path)
    except Exception:
        return []
    if audio is None or not audio.tags:
        return []

    changes = []
    for key in _name_tag_keys(audio.tags):
        old_values = _tag_text_values(audio.tags[key])
        if old_values is None:
            continue
        new_values = [transform(value) for value in old_values]
        if old_values != new_values:
            changes.append((str(key), old_values, new_values))
    return changes


def _update_name_tags(path: Path, transform) -> int:
    try:
        audio = MutagenFile(path)
    except Exception:
        return 0
    if audio is None or not audio.tags:
        return 0

    changed_fields = 0
    for key in _name_tag_keys(audio.tags):
        tag_value = audio.tags[key]
        old_values = _tag_text_values(tag_value)
        if old_values is None:
            continue
        new_values = [transform(value) for value in old_values]
        if old_values == new_values:
            continue
        if hasattr(tag_value, "text"):
            tag_value.text = new_values
        elif isinstance(tag_value, list):
            audio.tags[key] = new_values
        else:
            audio.tags[key] = new_values[0] if len(new_values) == 1 else new_values
        changed_fields += 1

    if changed_fields:
        audio.save()
    return changed_fields


def _get_tag_text(tags, keys: list) -> str | None:
    for key in keys:
        values = _tag_text_values(tags[key])
        if values:
            value = values[0].strip()
            if value:
                return value
    return None


def _normalized_title(value: str) -> str:
    if value.strip().isdigit():
        return value.strip()
    title = _remove_prefix(_remove_parentheses(value))
    title = re.sub(
        r"(?i)\s+\d{2,3}\s+[a-g](?:#|b)?m?\s+\d+m\d+s$",
        "",
        title,
    )
    title = re.sub(r"(?i)[\s_-]+copy(?:[\s_-]*\d+)?$", "", title)
    return re.sub(r"\s+", " ", title).strip(" \t-_.,")


def _safe_filename_stem(value: str) -> str:
    stem = INVALID_FILENAME_CHARS.sub("-", value)
    stem = re.sub(r"\s+", " ", stem).rstrip(" .")
    if stem.split(".", 1)[0].upper() in RESERVED_WINDOWS_NAMES:
        stem = f"_{stem}"
    return stem


def _write_tag_text(audio, key, value: str) -> None:
    tags = audio.tags
    from mutagen.id3 import ID3, TIT2, TXXX

    if isinstance(tags, ID3):
        key_text = str(key)
        if key_text.casefold() == "tit2":
            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=[value]))
        elif key_text.casefold().startswith("txxx:"):
            description = key_text.split(":", 1)[1]
            matching_frames = [
                frame for frame in tags.getall("TXXX")
                if frame.desc.casefold() == description.casefold()
            ]
            if matching_frames:
                for frame in matching_frames:
                    frame.text = [value]
            else:
                tags.add(TXXX(encoding=3, desc=description, text=[value]))
        return

    current = tags.get(key)
    if current is not None:
        if hasattr(current, "text"):
            current.text = [value]
        elif hasattr(current, "value"):
            tags[key] = type(current)(value)
        elif isinstance(current, list):
            tags[key] = [value]
        else:
            tags[key] = value
        return

    if type(audio).__name__ == "MP4" and str(key).casefold() in {"title", "©nam"}:
        tags["\xa9nam"] = [value]
    elif type(audio).__name__ == "ASF":
        from mutagen.asf._attrs import ASFUnicodeAttribute

        tags["Title"] = [ASFUnicodeAttribute(value)]
    else:
        tags[str(key)] = [value]


def _set_final_metadata(path: Path, canonical_title: str, filename: str) -> int:
    audio = MutagenFile(path)
    if audio is None:
        raise ValueError("File is no longer recognized as audio")
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    changes = 0

    title_keys = _title_tag_keys(tags)
    if title_keys:
        for key in title_keys:
            if _get_tag_text(tags, [key]) != canonical_title:
                _write_tag_text(audio, key, canonical_title)
                changes += 1
    else:
        from mutagen.id3 import ID3

        title_key = "TIT2" if isinstance(tags, ID3) else "title"
        _write_tag_text(audio, title_key, canonical_title)
        changes += 1

    for key in _name_tag_keys(tags):
        if _get_tag_text(tags, [key]) != canonical_title:
            _write_tag_text(audio, key, canonical_title)
            changes += 1
    for key in _filename_tag_keys(tags):
        if _get_tag_text(tags, [key]) != filename:
            _write_tag_text(audio, key, filename)
            changes += 1

    if changes:
        audio.save()
    return changes


def _path_with_audio_extension(path: Path, extension: str) -> Path:
    known_extensions = set(AUDIO_FORMAT_EXTENSIONS.values())
    if path.suffix.lower() in known_extensions:
        return path.with_suffix(extension)
    return path.with_name(path.name + extension)


# ---- Duplicate and sanitation helpers ----

def _keeper_files(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_file())


def _audio_files(root: Path, progress_stage: str | None = None) -> list[Path]:
    files = _keeper_files(root)
    audio_files = []
    for index, path in enumerate(files, start=1):
        if audio_extension(path) is not None:
            audio_files.append(path)
        if progress_stage:
            _progress(progress_stage, "files checked", index, len(files))
    return audio_files


def _get_name_tag(path: Path) -> str | None:
    try:
        audio = MutagenFile(path)
    except Exception:
        return None
    if audio is None or not audio.tags:
        return None
    for key in _name_tag_keys(audio.tags):
        values = _tag_text_values(audio.tags[key])
        if values and values[0].strip():
            return values[0].strip()
    return None


def _metadata_completeness(path: Path) -> int:
    try:
        audio = MutagenFile(path)
    except Exception:
        return 0
    if audio is None:
        return 0

    aliases = {
        "title": {"tit2", "title", "©nam"},
        "artist": {"tpe1", "artist", "©art"},
        "album": {"talb", "album", "©alb"},
        "album_artist": {"tpe2", "albumartist", "aart"},
        "genre": {"tcon", "genre", "©gen"},
        "year": {"tdrc", "tyer", "date", "year", "©day"},
        "track": {"trck", "track", "tracknumber", "trkn"},
        "composer": {"tcom", "composer", "©wrt"},
    }
    populated_fields = set()
    if audio.tags:
        for key in audio.tags.keys():
            key_text = str(key).casefold()
            for field_name, field_aliases in aliases.items():
                if key_text in {alias.casefold() for alias in field_aliases}:
                    values = _tag_text_values(audio.tags[key])
                    if values and any(item.strip() for item in values):
                        populated_fields.add(field_name)
    score = len(populated_fields)
    info = getattr(audio, "info", None)
    if info is not None:
        score += int(bool(getattr(info, "length", None)))
        score += int(bool(getattr(info, "bitrate", None)))
    return score


def _candidate_metadata(path: Path) -> tuple[str | None, str | None, float | None]:
    try:
        audio = MutagenFile(path)
    except Exception:
        return None, None, None
    if audio is None or not audio.tags:
        return None, None, getattr(getattr(audio, "info", None), "length", None)

    title = _get_tag_text(audio.tags, _title_tag_keys(audio.tags))
    artist_keys = [
        key for key in audio.tags.keys()
        if str(key).casefold() in {"tpe1", "artist", "©art"}
    ]
    artist = _get_tag_text(audio.tags, artist_keys)
    duration = getattr(getattr(audio, "info", None), "length", None)
    return title, artist, duration


def _candidate_keys(path: Path) -> set[str]:
    try:
        audio = MutagenFile(path)
    except Exception:
        audio = None
    tags = audio.tags if audio is not None and audio.tags else None
    values = [path.stem]
    if tags:
        for keys in (_name_tag_keys(tags), _filename_tag_keys(tags), _title_tag_keys(tags)):
            value = _get_tag_text(tags, keys)
            if value:
                values.append(value)
    return {
        re.sub(r"[^\w]", "", _normalized_title(value).casefold(), flags=re.UNICODE)
        for value in values
        if _normalized_title(value)
    }


def _find_duplicate_groups(root: Path, files: list[Path] | None = None) -> dict[str, list[Path]]:
    candidate_files: dict[str, list[Path]] = {}
    if files is None:
        files = _audio_files(root)
    for index, path in enumerate(files, start=1):
        for candidate in _candidate_keys(path):
            candidate_files.setdefault(candidate, []).append(path)
        _progress("same-track", "candidate keys checked", index, len(files))

    parent: dict[Path, Path] = {}

    def find(path: Path) -> Path:
        parent.setdefault(path, path)
        if parent[path] != path:
            parent[path] = find(parent[path])
        return parent[path]

    def union(left: Path, right: Path) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for paths in candidate_files.values():
        unique_paths = sorted(set(paths))
        if len(unique_paths) > 1:
            for path in unique_paths[1:]:
                union(unique_paths[0], path)

    components: dict[Path, list[Path]] = {}
    for path in parent:
        components.setdefault(find(path), []).append(path)
    return {
        f"candidate-{index}": sorted(paths)
        for index, paths in enumerate(components.values(), start=1)
        if len(paths) > 1
    }


def _select_keeper(group: list[Path]) -> Path:
    return max(sorted(group), key=_metadata_completeness)


def _available_path(path: Path, reserved: set[Path] | None = None) -> Path:
    if reserved is None:
        reserved = set()
    candidate = path
    index = 1
    while candidate.exists() or candidate in reserved:
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        index += 1
    return candidate


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as error:
        _print_error(f"[ERROR] Could not hash {path.name}: {error}")
        return None


def _find_hash_duplicate_groups(
    root: Path,
    files: list[Path] | None = None,
    progress_stage: str = "exact-copies",
) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    if files is None:
        files = _audio_files(root)
    for index, path in enumerate(files, start=1):
        file_hash = sha256_file(path)
        if file_hash:
            groups.setdefault(file_hash, []).append(path)
        _progress(progress_stage, "files hashed", index, len(files))
    return {file_hash: group for file_hash, group in groups.items() if len(group) > 1}


def _root_file_signature(root: Path) -> dict[str, tuple[int, int, int]] | None:
    signature = {}
    try:
        for path in _keeper_files(root):
            stat = path.stat()
            signature[path.name] = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    except OSError as error:
        _print_error(f"[ERROR] Could not validate file set: {error}")
        return None
    return signature


def hash_cleanup_dry_run(root: Path):
    global _hash_plan_root, _hash_plan_signature, _hash_plan_groups, _hash_plan_audio_count
    audio_files = _audio_files(root, "exact-copies")
    groups = _find_hash_duplicate_groups(root, audio_files)
    signature = _root_file_signature(root)
    if signature is None:
        _hash_plan_root = None
        return False
    _hash_plan_root = root.resolve()
    _hash_plan_signature = signature
    _hash_plan_groups = {file_hash: list(group) for file_hash, group in groups.items()}
    _hash_plan_audio_count = len(audio_files)
    moves = sum(len(group) - 1 for group in groups.values())
    _print_dry_run_summary("exact-copies", moves, _managed_file_count(root))
    return True


def hash_cleanup_execute(root: Path):
    global _hash_plan_root, _hash_plan_signature, _hash_plan_groups, _hash_plan_audio_count
    print("\n=== EXACT-HASH DUPLICATE EXECUTE ===")
    if _hash_plan_root != root.resolve():
        _print_error("[ERROR] No hash dry-run plan exists for this folder. Run option 6; no hashes or files changed.")
        return False
    current_signature = _root_file_signature(root)
    if current_signature is None or current_signature != _hash_plan_signature:
        _print_error("[ERROR] Files changed since the hash dry run. Run option 6 again; no files moved.")
        return False

    snapshot = _ensure_workflow_snapshot(root)
    if snapshot is None:
        return False
    root_before = len(_keeper_files(root))
    managed_before = _managed_file_count(root)
    audio_before = _hash_plan_audio_count
    groups = {file_hash: list(group) for file_hash, group in _hash_plan_groups.items()}
    if _root_file_signature(root) != _hash_plan_signature:
        _print_error("[ERROR] Files changed while the snapshot was created. No files moved; rerun option 6.")
        return False
    review_before = _archive_count(root, "_REVIEW_")
    review_dir = root / "_REVIEW_"
    moved = 0
    succeeded = True
    if groups:
        review_dir.mkdir(exist_ok=True)
    for group_index, group in enumerate(groups.values(), start=1):
        keeper = _select_keeper(group)
        for path in group:
            if path == keeper:
                continue
            destination = _available_path(review_dir / path.name)
            try:
                shutil.move(str(path), str(destination))
                moved += 1
            except OSError as error:
                _print_error(f"[ERROR] Exact-copy move failed: {error}")
                succeeded = False
        _progress("exact-copies", "duplicate groups processed", group_index, len(groups))
    print(f"[SUMMARY] Exact duplicate files moved: {moved}")
    audio_after = len(_audio_files(root))
    review_after = _archive_count(root, "_REVIEW_")
    print(f"[COUNT] Audio: {audio_before} = remaining {audio_after} + moved {moved}")
    print(f"[COUNT] _REVIEW_: {review_after} = existing {review_before} + added {review_after - review_before}")
    counts_balanced = _record_stage_counts(
        "exact-copies", root_before, audio_before, len(_keeper_files(root)),
        audio_after, "_REVIEW_", review_before, review_after,
        managed_before, _managed_file_count(root),
    )
    _hash_plan_root = None
    _hash_plan_signature = {}
    _hash_plan_groups = {}
    _hash_plan_audio_count = 0
    return succeeded and counts_balanced


def duplicates_dry_run(root: Path):
    files = _audio_files(root, "same-track")
    dup_groups = _find_duplicate_groups(root, files)
    total_dups = sum(len(group) - 1 for group in dup_groups.values())
    _print_dry_run_summary("same-track", total_dups, _managed_file_count(root))
    return True


def duplicates_execute(root: Path):
    print("\n=== FILENAME DUPLICATES EXECUTE ===")
    snapshot = _ensure_workflow_snapshot(root)
    if snapshot is None:
        return False
    filtered_dir = root / "_FILTERED_"
    all_files = _keeper_files(root)
    root_before = len(all_files)
    managed_before = _managed_file_count(root)
    files = _audio_files(root, "same-track")
    audio_before = len(files)
    dup_groups = _find_duplicate_groups(root, files)
    filtered_before = _archive_count(root, "_FILTERED_")
    print(f"[INFO] Scanning {len(files)} audio files for duplicates...")
    print(f"[INFO] Non-audio or unrecognized files left untouched: {len(all_files) - len(files)}")

    if not dup_groups:
        print("[INFO] No duplicate groups found.")
        print(f"[COUNT] Audio: {len(files)} = remaining {len(files)} + moved 0")
        counts_balanced = _record_stage_counts(
            "same-track", root_before, audio_before, len(_keeper_files(root)),
            len(files), "_FILTERED_", filtered_before, filtered_before,
            managed_before, _managed_file_count(root),
        )
        return counts_balanced

    filtered_dir.mkdir(exist_ok=True)
    moves_succeeded = True
    moved_count = 0

    for group_index, group in enumerate(dup_groups.values(), start=1):
        keeper_source = _select_keeper(group)

        for path in group:
            if path != keeper_source:
                dest = _available_path(filtered_dir / path.name)
                try:
                    shutil.move(str(path), str(dest))
                    moved_count += 1
                except Exception as e:
                    _print_error(f"[ERROR] Same-track move failed: {e}")
                    moves_succeeded = False
        _progress("same-track", "duplicate groups processed", group_index, len(dup_groups))

    print("\n[INFO] Duplicate processing complete.")
    audio_after = len(_audio_files(root))
    filtered_after = _archive_count(root, "_FILTERED_")
    print(f"[COUNT] Audio: {len(files)} = remaining {audio_after} + moved to _FILTERED_ {moved_count}")
    print(f"[COUNT] _FILTERED_: {filtered_after} = existing {filtered_before} + added {filtered_after - filtered_before}")
    counts_balanced = _record_stage_counts(
        "same-track", root_before, audio_before, len(_keeper_files(root)),
        audio_after, "_FILTERED_", filtered_before, filtered_after,
        managed_before, _managed_file_count(root),
    )
    return moves_succeeded and counts_balanced


# ---- Name and Filename Sanitation ----

def _name_tag_plan(path: Path):
    try:
        audio = MutagenFile(path)
    except Exception:
        return 0, 0, []
    if audio is None or not audio.tags:
        return 0, 0, []

    parentheses_count = 0
    prefix_count = 0
    final_changes = []
    for key in _name_tag_keys(audio.tags):
        original = _tag_text_values(audio.tags[key])
        if original is None:
            continue
        without_parentheses = [_remove_parentheses(value) for value in original]
        without_prefix = [_remove_prefix(value) for value in without_parentheses]
        if original != without_parentheses:
            parentheses_count += 1
        if without_parentheses != without_prefix:
            prefix_count += 1
        if original != without_prefix:
            final_changes.append((key, without_prefix))
    return parentheses_count, prefix_count, final_changes


def _plan_filename_changes(root: Path, sources: list[Path], transform):
    copies_dir = root / "_COPIES_"
    planned = []
    reserved: set[Path] = set()
    for source in sources:
        transformed_name = transform(source.name)
        if transformed_name == source.name:
            continue
        destination = source.with_name(transformed_name)
        if (destination.exists() and destination != source) or destination in reserved:
            destination = _available_path(copies_dir / source.name, reserved)
        reserved.add(destination)
        planned.append((source, destination))
    return planned


def _sanitation_plan(root: Path):
    files = _keeper_files(root)
    name_parentheses = 0
    name_prefix = 0
    tag_changes = []
    filename_parentheses = _plan_filename_changes(root, files, _remove_parentheses)
    parenthesis_destinations = {source: destination for source, destination in filename_parentheses}
    after_parentheses = []

    for path in files:
        tag_parens, tag_prefix, changes = _name_tag_plan(path)
        name_parentheses += tag_parens
        name_prefix += tag_prefix
        if changes:
            tag_changes.append((path, changes))

        destination = parenthesis_destinations.get(path, path)
        if destination.parent != root / "_COPIES_":
            after_parentheses.append(destination)

    filename_prefix = _plan_filename_changes(root, after_parentheses, _remove_prefix)
    conflicts = []

    return name_parentheses, name_prefix, tag_changes, filename_parentheses, filename_prefix, conflicts


def sanitation_dry_run(root: Path):
    print("\n=== NAME AND FILENAME SANITATION DRY RUN ===")
    name_parentheses, name_prefix, tag_changes, filename_parentheses, filename_prefix, conflicts = _sanitation_plan(root)
    print(f"[STEP 1] NAME tag fields to clean parentheses: {name_parentheses}")
    print(f"[STEP 2] Filenames to clean parentheses: {len(filename_parentheses)}")
    print(f"[STEP 3] NAME tag fields to clean leading prefix: {name_prefix}")
    print(f"[STEP 4] Filenames to clean leading prefix: {len(filename_prefix)}")

    for path, changes in tag_changes[:50]:
        for key, new_values in changes:
            print(f"[PLAN] NAME tag {path.name} [{key}] → {new_values}")
    for source, destination in filename_parentheses[:50]:
        route = " (collision; send to _COPIES_)" if destination.parent.name == "_COPIES_" else ""
        print(f"[PLAN] Parentheses: {source.name} → {destination.name}{route}")
    for source, destination in filename_prefix[:50]:
        route = " (collision; send to _COPIES_)" if destination.parent.name == "_COPIES_" else ""
        print(f"[PLAN] Prefix: {source.name} → {destination.name}{route}")

    if conflicts:
        _print_error(f"[ERROR] Filename conflicts found: {len(conflicts)}")
        for conflict in conflicts[:20]:
            print(f"  {conflict}")
        return False

    print("[READY] No filename conflicts. Choose option 5 to execute sanitation.")
    return True


def _rename_files_with_transform(root: Path, transform) -> tuple[int, bool, dict[Path, Path]]:
    renamed = 0
    succeeded = True
    copies_dir = root / "_COPIES_"
    current_paths = {}
    for path in _keeper_files(root):
        new_name = transform(path.name)
        if new_name == path.name:
            current_paths[path] = path
            continue
        destination = path.with_name(new_name)
        try:
            if destination.exists() and destination != path:
                copies_dir.mkdir(exist_ok=True)
                destination = _available_path(copies_dir / path.name)
                shutil.move(str(path), str(destination))
            else:
                path.rename(destination)
            renamed += 1
            current_paths[path] = destination
        except Exception as e:
            _print_error(f"[ERROR] Rename failed for {path.name}: {e}")
            succeeded = False
            current_paths[path] = path
    return renamed, succeeded, current_paths


def sanitation_execute(root: Path):
    print("\n=== NAME AND FILENAME SANITATION EXECUTE ===")
    name_parentheses, name_prefix, tag_changes, filename_parentheses, filename_prefix, conflicts = _sanitation_plan(root)
    if conflicts:
        _print_error(f"[ERROR] Filename conflicts found: {len(conflicts)}. No sanitation performed.")
        return False

    tag_parentheses_updated = 0
    tag_prefix_updated = 0
    for path in _keeper_files(root):
        try:
            tag_parentheses_updated += _update_name_tags(path, _remove_parentheses)
        except Exception as e:
            _print_error(f"[ERROR] NAME tag update failed for {path.name}: {e}")

    renamed_parentheses, parentheses_succeeded, current_paths = _rename_files_with_transform(
        root, _remove_parentheses
    )

    for path in current_paths.values():
        try:
            tag_prefix_updated += _update_name_tags(path, _remove_prefix)
        except Exception as e:
            _print_error(f"[ERROR] NAME prefix update failed for {path.name}: {e}")

    renamed_prefix, prefix_succeeded, _ = _rename_files_with_transform(root, _remove_prefix)
    print(f"[INFO] NAME tag fields cleaned in parentheses pass: {tag_parentheses_updated}/{name_parentheses}")
    print(f"[INFO] Filenames cleaned in parentheses pass: {renamed_parentheses}/{len(filename_parentheses)}")
    print(f"[INFO] NAME tag fields cleaned in prefix pass: {tag_prefix_updated}/{name_prefix}")
    print(f"[INFO] Filenames cleaned in prefix pass: {renamed_prefix}/{len(filename_prefix)}")
    return parentheses_succeeded and prefix_succeeded


# ---- Extension Repair ----

def _analyze_keeper_extensions(root: Path, progress_stage: str | None = None):
    all_files = _keeper_files(root)
    files = []
    planned = []
    unrecognized = []
    ignored = []
    unverified = []

    for index, path in enumerate(all_files, start=1):
        extension = audio_extension(path)
        if extension is None:
            if path.suffix.lower() in NON_AUDIO_SUFFIXES:
                ignored.append(path)
            elif path.suffix.lower() in AUDIO_FORMAT_EXTENSIONS.values():
                unverified.append(path)
            else:
                unrecognized.append(path)
        elif path.suffix.lower() != extension:
            files.append(path)
            planned.append((path, extension))
        else:
            files.append(path)
        if progress_stage:
            _progress(progress_stage, "file types checked", index, len(all_files))

    return files, planned, unrecognized, ignored, unverified


def extension_dry_run(root: Path):
    files, planned, unrecognized, ignored, unverified = _analyze_keeper_extensions(root, "extensions")
    candidate_count = len(files) + len(unrecognized)
    _print_dry_run_summary("extensions", len(planned), _managed_file_count(root))
    if unrecognized:
        print(_color(f"Execute blocked: {len(unrecognized)} unrecognized files", "extensions"))
        return False
    return candidate_count > 0


def extension_execute(root: Path):
    print("\n=== EXTENSION REPAIR EXECUTE ===")
    snapshot = _ensure_workflow_snapshot(root)
    if snapshot is None:
        return False
    root_before = len(_keeper_files(root))
    managed_before = _managed_file_count(root)
    audio_before = len(_audio_files(root))
    copies_before = _archive_count(root, "_COPIES_")
    files, planned, unrecognized, ignored, unverified = _analyze_keeper_extensions(root, "extensions")
    copies_dir = root / "_COPIES_"
    candidate_count = len(files) + len(unrecognized)
    if not candidate_count:
        print("[INFO] No keeper files found.")
        return False

    if unrecognized:
        print(
            f"[ERROR] Only {len(files)}/{candidate_count} possible audio keepers "
            "were recognized. No files renamed."
        )
        return False

    handled_count = 0
    renamed_count = 0
    collision_count = 0
    for index, (path, extension) in enumerate(planned, start=1):
        _progress("extensions", "repairs processed", index, len(planned))
        new_name = _path_with_audio_extension(path, extension)
        try:
            if new_name.exists() and new_name != path:
                copies_dir = root / "_COPIES_"
                copies_dir.mkdir(exist_ok=True)
                destination = _available_path(copies_dir / path.name)
                shutil.move(str(path), str(destination))
                collision_count += 1
            else:
                path.rename(new_name)
                renamed_count += 1
            handled_count += 1
        except Exception as e:
            _print_error(f"[ERROR] Extension repair failed: {e}")

    print(f"\n[INFO] Audio keepers recognized: {len(files)}/{candidate_count}")
    print(f"[INFO] Extension repairs handled: {handled_count}/{len(planned)}")
    copies_after = len(list(copies_dir.iterdir())) if copies_dir.is_dir() else 0
    print(f"[COUNT] Planned repairs: {len(planned)} = renamed {renamed_count} + archived on collision {collision_count} + failed {len(planned) - handled_count}")
    print(f"[COUNT] Root files: {root_before} = now {len(_keeper_files(root))} + moved to _COPIES_ {collision_count}")
    print(f"[COUNT] _COPIES_: {copies_after} = existing {copies_before} + added {copies_after - copies_before}")
    counts_balanced = _record_stage_counts(
        "extensions", root_before, audio_before, len(_keeper_files(root)),
        len(_audio_files(root)), "_COPIES_", copies_before, copies_after,
        managed_before, _managed_file_count(root),
    )
    return handled_count == len(planned) and counts_balanced


def _final_naming_plan(root: Path):
    plans = []
    unresolved = []
    skipped = []
    reserved_destinations: set[Path] = set()
    reserved_archives: set[Path] = set()
    files = _audio_files(root, "final-naming")
    for index, path in enumerate(files, start=1):
        if (
            path.name.casefold() in SKIPPED_EDGE_FILENAMES
            or path.stem.casefold() in SKIPPED_EDGE_FILENAMES
        ):
            skipped.append(path)
            _progress("final-naming", "names analyzed", index, len(files))
            continue

        audio = MutagenFile(path)
        tags = audio.tags if audio is not None else None
        current_title = _get_tag_text(tags, _title_tag_keys(tags)) if tags else None
        canonical_title = _normalized_title(current_title or path.stem)
        extension = audio_extension(path)
        if not canonical_title or not extension:
            unresolved.append(path)
            continue

        filename_stem = _safe_filename_stem(canonical_title)
        if not filename_stem:
            unresolved.append(path)
            continue
        filename = f"{filename_stem}{extension}"
        destination = path.with_name(filename)
        collision = (
            (destination.exists() and destination != path)
            or destination in reserved_destinations
        )
        archive_path = None
        if collision:
            archive_path = _available_path(
                root / "_COPIES_" / path.name,
                reserved_archives,
            )
            reserved_archives.add(archive_path)
        else:
            reserved_destinations.add(destination)

        title_keys = _title_tag_keys(tags) if tags else []
        needs_title = not title_keys or any(
            _get_tag_text(tags, [key]) != canonical_title for key in title_keys
        )
        needs_name = any(
            _get_tag_text(tags, [key]) != canonical_title
            for key in (_name_tag_keys(tags) if tags else [])
        )
        needs_filename = any(
            _get_tag_text(tags, [key]) != filename
            for key in (_filename_tag_keys(tags) if tags else [])
        )
        tag_changes = int(needs_title) + int(needs_name) + int(needs_filename)
        plans.append((path, canonical_title, destination, archive_path, tag_changes))
        _progress("final-naming", "names analyzed", index, len(files))
    return plans, unresolved, skipped


def final_naming_dry_run(root: Path):
    plans, unresolved, skipped = _final_naming_plan(root)
    changed_files = sum(
        path != destination or archive_path is not None or tag_changes > 0
        for path, _, destination, archive_path, tag_changes in plans
    )
    _print_dry_run_summary("final-naming", changed_files, _managed_file_count(root))
    if unresolved:
        print(_color(f"Execute blocked: {len(unresolved)} unresolved audio files", "final-naming"))
        return False
    return True


def final_naming_execute(root: Path):
    print("\n=== FINAL NAMING EXECUTE ===")
    snapshot = _ensure_workflow_snapshot(root)
    if snapshot is None:
        return False
    root_before = len(_keeper_files(root))
    managed_before = _managed_file_count(root)
    plans, unresolved, skipped = _final_naming_plan(root)
    audio_before = len(_audio_files(root))
    copies_dir = root / "_COPIES_"
    copies_before = _archive_count(root, "_COPIES_")
    if unresolved:
        _print_error(f"[ERROR] {len(unresolved)} files need manual review. No final naming performed.")
        print(f"[COUNT] Audio: {audio_before} = planned {len(plans)} + unresolved {len(unresolved)} + skipped {len(skipped)}")
        return False

    finalized = 0
    archived = 0
    failed = 0
    succeeded = True
    for index, (path, canonical_title, destination, archive_path, _) in enumerate(plans, start=1):
        if archive_path is not None:
            copies_dir.mkdir(exist_ok=True)
            try:
                shutil.move(str(path), str(archive_path))
                archived += 1
            except OSError as error:
                _print_error(f"[ERROR] Could not archive a filename collision: {error}")
                succeeded = False
                failed += 1
            _progress("final-naming", "files processed", index, len(plans))
            continue

        try:
            tag_changes = _set_final_metadata(path, canonical_title, destination.name)
            if path != destination:
                path.rename(destination)
            finalized += 1
        except Exception as error:
            _print_error(f"[ERROR] Final naming operation failed: {error}")
            succeeded = False
            failed += 1
        _progress("final-naming", "files processed", index, len(plans))

    copies_after = _archive_count(root, "_COPIES_")
    audio_after = len(_audio_files(root))
    print(f"[SUMMARY] Files finalized: {finalized}/{len(plans)}")
    print(f"[SUMMARY] Files archived for collision: {archived}")
    print(f"[SUMMARY] Files failed: {failed}")
    print(f"[INFO] Edge-case files left untouched: {len(skipped)}")
    print(f"[COUNT] Planned files: {len(plans)} = finalized {finalized} + archived {archived} + failed {failed}")
    print(f"[COUNT] Audio: {audio_before} = remaining {audio_after} + moved to _COPIES_ {archived}")
    print(f"[COUNT] _COPIES_: {copies_after} = existing {copies_before} + added {copies_after - copies_before}")
    counts_balanced = _record_stage_counts(
        "final-naming", root_before, audio_before, len(_keeper_files(root)),
        audio_after, "_COPIES_", copies_before, copies_after,
        managed_before, _managed_file_count(root),
    )
    return succeeded and finalized + archived == len(plans) and counts_balanced


# ---- Menu ----

def main_menu():
    global scan_path, extension_dry_run_done, extension_done
    global same_track_dry_run_done, same_track_done
    global hash_cleanup_dry_run_done, hash_cleanup_done, final_naming_dry_run_done
    global workflow_snapshot_root, workflow_snapshot_path
    global workflow_start_total
    global final_naming_done
    global _hash_plan_root, _hash_plan_signature, _hash_plan_groups, _hash_plan_audio_count

    while True:
        print("\n" + _color("=============================", "info"))
        print(" Audio Library Repair (Python)")
        print("=============================")
        print(f"Current scan path: {scan_path if scan_path else '[NOT SET]'}")
        if scan_path:
            print(
                f"Root files: {len(_keeper_files(scan_path))}; "
                f"total tracked files (root + archives): {_managed_file_count(scan_path)}"
            )
        _print_stage_ledger()
        print(_color("-----------------------------", "info"))
        next_choice, next_stage = _next_menu_choice()
        _menu_option(1, "Set Scan Path", "menu-path", next_choice == 1)
        _menu_option(2, "Extension Repair → Dry Run", "extensions", next_choice == 2)
        _menu_option(3, "Extension Repair → Execute", "extensions", next_choice == 3)
        _menu_option(4, "Same-Track Review → Dry Run", "same-track", next_choice == 4)
        _menu_option(5, "Same-Track Review → Execute", "same-track", next_choice == 5)
        _menu_option(6, "Exact Copies → Dry Run", "exact-copies", next_choice == 6)
        _menu_option(7, "Exact Copies → Execute", "exact-copies", next_choice == 7)
        _menu_option(8, "Final Naming → Dry Run", "final-naming", next_choice == 8)
        _menu_option(9, "Final Naming → Execute", "final-naming", next_choice == 9)
        _menu_option(10, "Exit", "menu-exit", next_choice == 10)
        print(_color("=============================", "info"))

        choice = input("Choose an option: ").strip()

        # Gating logic
        if choice in {"2", "3", "4", "5", "6", "7", "8", "9"} and not scan_path:
            _print_error("[ERROR] Set scan path first (option 1).")
            continue

        if choice == "3" and not extension_dry_run_done:
            _print_error("[ERROR] Run a successful extension dry run first (option 2).")
            continue

        if choice in {"4", "5", "6", "7", "8", "9"} and not extension_done:
            _print_error("[ERROR] Run extension repair execute first (option 3).")
            continue

        if choice == "5" and not same_track_dry_run_done:
            _print_error("[ERROR] Run same-track dry run first (option 4).")
            continue

        if choice in {"6", "7", "8", "9"} and not same_track_done:
            _print_error("[ERROR] Run same-track execute first (option 5).")
            continue

        if choice == "7" and not hash_cleanup_dry_run_done:
            _print_error("[ERROR] Run exact-copy dry run first (option 6).")
            continue

        if choice in {"8", "9"} and not hash_cleanup_done:
            _print_error("[ERROR] Run exact-copy execute first (option 7).")
            continue

        if choice == "9" and not final_naming_dry_run_done:
            _print_error("[ERROR] Run a successful final-naming dry run first (option 8).")
            continue

        if choice == "1":
            p = input_path("Enter path to scan: ")
            if p:
                scan_path = p
                workflow_start_total = _managed_file_count(p)
                same_track_dry_run_done = False
                same_track_done = False
                hash_cleanup_dry_run_done = False
                hash_cleanup_done = False
                extension_dry_run_done = False
                extension_done = False
                final_naming_dry_run_done = False
                final_naming_done = False
                stage_counts.clear()
                workflow_snapshot_root = None
                workflow_snapshot_path = None
                _hash_plan_root = None
                _hash_plan_signature = {}
                _hash_plan_groups = {}
                _hash_plan_audio_count = 0
        elif choice == "2":
            assert scan_path is not None
            final_naming_done = False
            extension_done = False
            same_track_dry_run_done = False
            same_track_done = False
            hash_cleanup_dry_run_done = False
            hash_cleanup_done = False
            final_naming_dry_run_done = False
            extension_dry_run_done = extension_dry_run(scan_path)
        elif choice == "3":
            assert scan_path is not None
            if extension_execute(scan_path):
                extension_done = True
                same_track_dry_run_done = False
                same_track_done = False
                hash_cleanup_dry_run_done = False
                hash_cleanup_done = False
                final_naming_dry_run_done = False
        elif choice == "4":
            assert scan_path is not None
            final_naming_done = False
            same_track_done = False
            hash_cleanup_dry_run_done = False
            hash_cleanup_done = False
            final_naming_dry_run_done = False
            same_track_dry_run_done = duplicates_dry_run(scan_path)
        elif choice == "5":
            assert scan_path is not None
            if duplicates_execute(scan_path):
                same_track_done = True
                hash_cleanup_dry_run_done = False
                hash_cleanup_done = False
                final_naming_dry_run_done = False
        elif choice == "6":
            assert scan_path is not None
            final_naming_done = False
            hash_cleanup_dry_run_done = hash_cleanup_dry_run(scan_path)
        elif choice == "7":
            assert scan_path is not None
            if hash_cleanup_execute(scan_path):
                hash_cleanup_done = True
                final_naming_dry_run_done = False
        elif choice == "8":
            assert scan_path is not None
            final_naming_done = False
            final_naming_dry_run_done = final_naming_dry_run(scan_path)
        elif choice == "9":
            assert scan_path is not None
            if final_naming_execute(scan_path):
                final_naming_dry_run_done = False
                final_naming_done = True
        elif choice == "10":
            print("Goodbye.")
            break
        else:
            _print_error("[ERROR] Invalid choice.")


if __name__ == "__main__":
    if not sys.version_info >= (3, 10):
        print("Please run with Python 3.10+.")
        sys.exit(1)
    main_menu()
