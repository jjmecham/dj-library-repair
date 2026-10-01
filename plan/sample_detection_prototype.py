"""Prototype only — for review, not wired into the app yet.

Python port of Jeremy's PowerShell sample/track rating system (2026-10-01),
as recorded in plan/00-decisions.md Decision 13 (raw-point score, resolved
as authoritative over the earlier 75%-confidence model; "don't combine them").

Differences from the PowerShell version, both already decided:
  - duration and tags are read with mutagen instead of the Windows Shell COM
        object, as decided in plan/00-decisions.md Decision 13. This keeps the
        app Python-only (INSTRUCTIONS.md section 2.8) and uses installed mutagen.
  - adds the whole-folder-move rule: if over 90% of a folder's files score
    as "sample," the whole folder is recommended for a single move,
    including any file in it that individually scored below the line.

Still classification/reporting only — no file moves are performed here.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from mutagen import File as MutagenFile

WEIGHTS = {
    "duration_under_30": 40,
    "duration_30_to_60": 10,
    "duration_over_60": -100,
    "keyword_match": 15,
    "instrument_match": 15,
    "album_pack_match": 20,
    "missing_tags_max": 15,
    "missing_genre": 5,
    "cluster_match": 15,
    "real_album": -20,
    "track_intro": -15,
    "no_key_in_name": -10,
    "no_instrument_in_name": -10,
}

KEYWORDS = [
    "loop", "stab", "808", "bpm", "key", "one shot", "oneshot", "shot", "shots",
    "melody", "kit", "pack", "package", "tools", "sample", "samples", "top loop",
    # added by Copilot, 2026-10-01, Jeremy: "add more to the list if you see fit"
    "sfx", "fx", "riser", "impact", "transition", "sweep", "vox", "vocal",
    "chop", "pad", "arp", "stems", "stem", "construction kit", "drum loop",
    "fill", "break", "midi", "preset", "patch",
]
INSTRUMENTS = [
    "kick", "snare", "clap", "hihat", "perc", "808", "tom", "rim",
    # added by Copilot, 2026-10-01 — short/common words here (bass, ride) carry
    # real false-positive risk as plain substrings (e.g. "bass" in "embassy"),
    # same risk the original keyword list already accepts for words like "key"
    "cymbal", "crash", "ride", "synth", "piano", "guitar", "strings",
    "brass", "cowbell", "shaker", "tambourine", "conga", "bongo", "bass",
]

SAMPLE_BUCKET_MIN_SCORE = 40     # score >= this: sample
TRACK_BUCKET_MAX_SCORE = 0       # score <= this: track
FOLDER_MOVE_FRACTION = 0.90      # fraction of a folder's files scoring "sample"

_KEY_PATTERN = re.compile(r"(c|d|e|f|g|a|b)(maj|min|m)", re.IGNORECASE)
_BPM_PATTERN = re.compile(r"\d{2,3}\s?bpm", re.IGNORECASE)
_INSTRUMENT_PATTERN = re.compile("|".join(INSTRUMENTS), re.IGNORECASE)
_PACK_ALBUM_PATTERN = re.compile(r"pack|sample|loop", re.IGNORECASE)
_INTRO_PATTERN = re.compile(r"intro", re.IGNORECASE)


def cluster_base_name(filename: str) -> str:
    base = Path(filename).stem
    base = _BPM_PATTERN.sub("", base)
    base = _KEY_PATTERN.sub("", base)
    return base.strip().lower()


def read_duration_seconds(path: Path):
    try:
        audio = MutagenFile(path)
        if audio is not None and audio.info is not None:
            return float(audio.info.length)
    except Exception:
        pass
    return None


def read_tags(path: Path) -> dict:
    tags = {}
    try:
        audio = MutagenFile(path, easy=True)
    except Exception:
        audio = None
    if audio is not None:
        for key in ("title", "artist", "album", "genre", "date"):
            value = audio.get(key) if hasattr(audio, "get") else None
            if value:
                tags[key] = value[0]
    return tags


@dataclass
class Classification:
    path: Path
    score: int
    bucket: str                     # "sample", "track", "ambiguous"
    reasons: list = field(default_factory=list)


def classify(path: Path, cluster_map: dict) -> Classification:
    score = 0
    reasons = []
    name = path.name
    duration = read_duration_seconds(path)
    tags = read_tags(path)
    album = tags.get("album", "")

    if duration is not None:
        if duration < 30:
            score += WEIGHTS["duration_under_30"]
            reasons.append(f"duration {duration:.1f}s < 30s (+{WEIGHTS['duration_under_30']})")
        elif duration < 60:
            score += WEIGHTS["duration_30_to_60"]
            reasons.append(f"duration {duration:.1f}s in 30-60s (+{WEIGHTS['duration_30_to_60']})")
        else:
            score += WEIGHTS["duration_over_60"]
            reasons.append(f"duration {duration:.1f}s >= 60s ({WEIGHTS['duration_over_60']})")

    for kw in KEYWORDS:
        if kw in name.lower():
            score += WEIGHTS["keyword_match"]
            reasons.append(f"keyword '{kw}' (+{WEIGHTS['keyword_match']})")

    has_instrument = bool(_INSTRUMENT_PATTERN.search(name))
    if has_instrument:
        score += WEIGHTS["instrument_match"]
        reasons.append(f"instrument name matched (+{WEIGHTS['instrument_match']})")

    if _PACK_ALBUM_PATTERN.search(album):
        score += WEIGHTS["album_pack_match"]
        reasons.append(f"album '{album}' looks like a pack (+{WEIGHTS['album_pack_match']})")
    elif album:
        score += WEIGHTS["real_album"]
        reasons.append(f"album '{album}' looks like a real album ({WEIGHTS['real_album']})")

    if _PACK_ALBUM_PATTERN.search(path.parent.name):
        score += WEIGHTS["album_pack_match"]
        reasons.append(f"parent folder '{path.parent.name}' looks like a pack (+{WEIGHTS['album_pack_match']})")

    missing = sum(1 for key in ("genre", "artist", "album", "date") if not tags.get(key))
    missing_points = min(missing * 3, WEIGHTS["missing_tags_max"])
    if missing_points:
        score += missing_points
        reasons.append(f"{missing} missing tag(s) (+{missing_points})")

    if not tags.get("genre"):
        score += WEIGHTS["missing_genre"]
        reasons.append(f"missing genre (+{WEIGHTS['missing_genre']})")

    base = cluster_base_name(name)
    if len(cluster_map.get(base, [])) > 1:
        score += WEIGHTS["cluster_match"]
        reasons.append(f"part of a {len(cluster_map[base])}-file name cluster (+{WEIGHTS['cluster_match']})")

    if _INTRO_PATTERN.search(name):
        score += WEIGHTS["track_intro"]
        reasons.append(f"looks like a track intro ({WEIGHTS['track_intro']})")

    if not _KEY_PATTERN.search(name):
        score += WEIGHTS["no_key_in_name"]
        reasons.append(f"no key in name ({WEIGHTS['no_key_in_name']})")

    if not has_instrument:
        score += WEIGHTS["no_instrument_in_name"]
        reasons.append(f"no instrument name ({WEIGHTS['no_instrument_in_name']})")

    if score >= SAMPLE_BUCKET_MIN_SCORE:
        bucket = "sample"
    elif score <= TRACK_BUCKET_MAX_SCORE:
        bucket = "track"
    else:
        bucket = "ambiguous"

    return Classification(path, score, bucket, reasons)


def build_cluster_map(paths: list) -> dict:
    cluster_map = defaultdict(list)
    for path in paths:
        cluster_map[cluster_base_name(path.name)].append(path)
    return cluster_map


def scan(root: Path):
    all_paths = [p for p in root.rglob("*") if p.is_file()]
    cluster_map = build_cluster_map(all_paths)

    results = [classify(p, cluster_map) for p in all_paths]

    by_folder = defaultdict(list)
    for r in results:
        by_folder[r.path.parent].append(r)

    folder_moves = set()
    for folder, items in by_folder.items():
        if not items:
            continue
        sample_count = sum(1 for r in items if r.bucket == "sample")
        if len(items) > 1 and sample_count / len(items) > FOLDER_MOVE_FRACTION:
            folder_moves.add(folder)

    return results, folder_moves


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\Jeremy\Music")
    results, folder_moves = scan(root)

    samples = [r for r in results if r.bucket == "sample"]
    tracks = [r for r in results if r.bucket == "track"]
    ambiguous = [r for r in results if r.bucket == "ambiguous"]

    print(f"\n=== Folders recommended for whole-folder move (> {FOLDER_MOVE_FRACTION:.0%} sample) ===")
    for folder in sorted(folder_moves):
        print(folder)

    # "when in doubt, move it" (Jeremy, 2026-10-01): ambiguous moves to _SAMPLES
    # alongside sample, for Jeremy's review — only "track" stays in the library.
    print(f"\n=== Move to _SAMPLES: sample (score >= {SAMPLE_BUCKET_MIN_SCORE}), {len(samples)} ===")
    for r in samples:
        print(f"{r.score:4d}  {r.path}  [{'; '.join(r.reasons)}]")

    print(f"\n=== Move to _SAMPLES: ambiguous, for review ({TRACK_BUCKET_MAX_SCORE} < score < {SAMPLE_BUCKET_MIN_SCORE}), {len(ambiguous)} ===")
    for r in ambiguous:
        print(f"{r.score:4d}  {r.path}  [{'; '.join(r.reasons)}]")

    print(f"\n=== Kept in library: track (score <= {TRACK_BUCKET_MAX_SCORE}), {len(tracks)} ===")
    for r in tracks:
        print(f"{r.score:4d}  {r.path}  [{'; '.join(r.reasons)}]")

