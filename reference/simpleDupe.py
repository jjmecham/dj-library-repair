import csv
import hashlib
import json
import os
import random
import re
import shutil
import struct
import time
import wave
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from mutagen.mp4 import MP4Tags

# Supported music file extensions
MUSIC_EXTENSIONS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".aif", ".aiff"}

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def rgb(r, g, b):
  return f"\033[38;2;{r};{g};{b}m"


WHITE = rgb(255, 255, 255)
RED = rgb(255, 64, 96)
GREEN = rgb(64, 255, 128)
YELLOW = rgb(255, 234, 64)
CYAN = rgb(64, 240, 255)
PEACH = rgb(255, 190, 152)
LIME = rgb(190, 255, 60)
VANILLA = rgb(243, 229, 171)
SAND = rgb(224, 196, 140)
TEAL = rgb(0, 200, 180)
GRAY = rgb(110, 110, 110)
LAVENDER = rgb(200, 170, 255)
SEPARATOR = f"{WHITE}{'=' * 40}{RESET}"


class Progress:
  """Single-line counter that redraws in place."""

  def __init__(self, label, total=None):
    self.label = label
    self.total = total
    self.last = 0.0

  def update(self, n, force=False):
    now = time.monotonic()
    if force or now - self.last >= 0.1:
      self.last = now
      count = f"{n} / {self.total}" if self.total else f"{n}"
      # \r returns to line start, \033[K clears leftovers, so the line updates in place
      print(f"\r{WHITE}{self.label}{RESET}  {CYAN}File count: {count}{RESET}\033[K", end="", flush=True)

  def done(self, n):
    self.update(n, force=True)
    print()

# Title, artist, album, album artist, track, year, genre
ID3_FIELDS = ("TIT2", "TPE1", "TALB", "TPE2", "TRCK", "TDRC", "TCON")
MP4_FIELDS = ("\xa9nam", "\xa9ART", "\xa9alb", "aART", "trkn", "\xa9day", "\xa9gen")
VORBIS_FIELDS = ("title", "artist", "album", "albumartist", "tracknumber", "date", "genre")
FIELD_COUNT = len(ID3_FIELDS)

# ---- Sample filter ----
# Files are scored on many signals; score >= SAMPLE_THRESHOLD is a sample.
SAMPLE_THRESHOLD = 6
SAMPLE_MAX_SECONDS = 60     # longer files are never treated as samples
DJ_MIN_SECONDS = 30         # nothing this short is a usable DJ track
ONE_SHOT_SECONDS = 10
PACK_FOLDER_MIN_FILES = 8
PACK_FOLDER_SHORT_RATIO = 0.7
ALBUM_FOLDER_MIN_FILES = 3
ALBUM_FOLDER_TAGGED_RATIO = 0.7  # share of files in the folder tagged with both artist and album
UNIFORM_LENGTH_TOLERANCE = 0.5   # seconds; every file in the folder within this of each other
SERIES_MIN_FILES = 3
SERIES_RE = re.compile(r"^(.*?\D)[\s_-]*\d{1,3}$")  # leading text + trailing 1-3 digit number
TAG_PACK_RE = re.compile(
  r"(?<![a-z])(samples?|sampler|packs?|kits?|loops?|tools?|fx|sfx|one[\s_-]?shots?)(?![a-z])"
  r"|www\.|https?://|\.(com|net|org|io|co\.uk)(?![a-z])",
  re.IGNORECASE)
BAR_TOLERANCE = 0.02        # fraction of a bar

SIDECAR_EXTENSIONS = {".mid", ".midi", ".rx2", ".rex", ".fxp", ".fxb", ".nmsv",
                      ".adg", ".adv", ".als", ".flp", ".nki", ".sfz"}

# Key between _ or - (e.g. _Am_, -C#m7-); spaces excluded so titles like "I Am" don't match
KEY_RE = re.compile(r"(?<![^_-])[A-G](?:#|b)?(?:maj7|maj|min|m7|m|7|dim|sus[24]?)?(?![^_-])")
BPM_RE = re.compile(r"(?<!\d)(\d{2,3})\s*bpm", re.IGNORECASE)
LEAD_BPM_RE = re.compile(r"^(1\d{2})_")
SOUND_WORD_RE = re.compile(
  r"(?<![a-z])(pad|sub|bass|arp|pluck|perc|shaker|crash|cymbal|rim|808|909|vox|hit|fx|sfx|stab|"
  r"chord|kick|snare|hi[\s_-]?hat|hat|clap|riser|impact|sweep|loop|one[\s_-]?shot|fill|drum|groove)s?(?![a-z])",
  re.IGNORECASE)
NUMBERED_RE = re.compile(r"[A-Za-z_ -]\d{1,3}(?:_[A-Z]{2,4})?$")
PACK_FOLDER_RE = re.compile(
  r"(?<![a-z])(packs?|kits?|samples?|loops?|one[\s_-]?shots?|construction|stems|sfx|fx)(?![a-z])",
  re.IGNORECASE)

TAG_ROLES = {
  "id3": {"title": ("TIT2",), "artist": ("TPE1", "TPE2"), "album": ("TALB",)},
  "mp4": {"title": ("\xa9nam",), "artist": ("\xa9ART", "aART"), "album": ("\xa9alb",)},
  "vorbis": {"title": ("title",), "artist": ("artist", "albumartist"), "album": ("album",)},
}

# Windows Explorer shows WAV Title/Artist/Album from the RIFF LIST/INFO chunk, which mutagen doesn't read
RIFF_INFO_ROLES = {b"INAM": "title", b"IART": "artist", b"IPRD": "album", b"ITRK": "track",
                   b"IPRT": "track", b"ICRD": "date", b"IGNR": "genre", b"ICMT": "comment"}
RIFF_KEY_ROLES = ("title", "artist", "album", "track", "date", "genre")


def _decode_riff_text(raw):
  raw = raw.split(b"\x00", 1)[0]
  try:
    text = raw.decode("utf-8")
  except UnicodeDecodeError:
    text = raw.decode("cp1252", errors="replace")  # Windows writes INFO text in the ANSI code page
  return text.strip()


def read_riff_info(file_path):
  """Returns {role: text} from a WAV's RIFF INFO chunk; empty dict if none or not a WAV."""
  found = {}
  try:
    with open(file_path, "rb") as f:
      header = f.read(12)
      if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        return found
      for _ in range(256):
        chunk = f.read(8)
        if len(chunk) < 8:
          break
        cid, size = chunk[:4], struct.unpack("<I", chunk[4:])[0]
        if cid == b"LIST" and size <= 1_000_000:
          body = f.read(size)
          if size & 1:
            f.read(1)
          if body[:4] != b"INFO":
            continue
          pos = 4
          while pos + 8 <= len(body):
            sub_id = body[pos:pos + 4]
            sub_size = struct.unpack("<I", body[pos + 4:pos + 8])[0]
            role = RIFF_INFO_ROLES.get(sub_id)
            if role and role not in found:
              text = _decode_riff_text(body[pos + 8:pos + 8 + sub_size])
              if text:
                found[role] = text
            pos += 8 + sub_size + (sub_size & 1)
        else:
          f.seek(size + (size & 1), 1)
  except (OSError, struct.error):
    pass
  return found


def get_file_hash(file_path, block_size=65536):
  """Calculates the MD5 hash of a file to detect exact duplicates."""
  hasher = hashlib.md5()
  try:
    with open(file_path, "rb") as f:
      while chunk := f.read(block_size):
        hasher.update(chunk)
    return hasher.hexdigest()
  except IOError:
    return None


class HashCache:
  """Hashes saved in <root>/_hash_cache.json; reused while a file's size and modified time are unchanged."""

  SAVE_EVERY = 500

  def __init__(self, root):
    self.root = root
    self.path = root / "_hash_cache.json"
    self.unsaved = 0
    self.hits = 0
    self.misses = 0
    try:
      with open(self.path, encoding="utf-8") as f:
        loaded = json.load(f)
    except (OSError, ValueError):
      loaded = {}
    # Drop anything not shaped like [size, mtime_ns, md5] so a damaged cache can't feed bad hashes
    self.data = {k: v for k, v in loaded.items()
                 if isinstance(v, list) and len(v) == 3 and isinstance(v[0], int)
                 and isinstance(v[1], int) and isinstance(v[2], str) and len(v[2]) == 32} \
      if isinstance(loaded, dict) else {}

  def _key(self, file_path):
    try:
      return str(file_path.relative_to(self.root))
    except ValueError:
      return str(file_path)

  def get(self, file_path):
    try:
      st = file_path.stat()
    except OSError:
      return None
    key = self._key(file_path)
    entry = self.data.get(key)
    if entry and entry[0] == st.st_size and entry[1] == st.st_mtime_ns:
      self.hits += 1
      return entry[2]
    self.misses += 1
    file_hash = get_file_hash(file_path)
    if file_hash:
      self.data[key] = [st.st_size, st.st_mtime_ns, file_hash]
      self.unsaved += 1
      # Save as we go so an interrupted scan keeps its progress
      if self.unsaved >= self.SAVE_EVERY:
        self.save()
    return file_hash

  def moved(self, src, dest):
    entry = self.data.pop(self._key(src), None)
    if entry:
      self.data[self._key(dest)] = entry
      self.unsaved += 1

  def save(self):
    if not self.unsaved:
      return
    self.data = {k: v for k, v in self.data.items() if (self.root / k).exists()}
    tmp = self.path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(self.data, f)
    os.replace(tmp, self.path)
    self.unsaved = 0

  def report(self):
    print(f"{WHITE}Hash cache:{RESET} {CYAN}{self.hits} reused, {self.misses} new{RESET}")
    self.hits = self.misses = 0


class Decisions:
  """Your decisions, saved in <root>/_decisions.json and keyed by file hash so they survive renames.
  not_sample: put back from _SAMPLES. is_sample: placed in _SAMPLES by you.
  not_duplicate: put back from _DUPLICATES. The latest sample decision for a file replaces the earlier one."""

  KINDS = ("not_sample", "is_sample", "not_duplicate")
  OPPOSITE = {"not_sample": "is_sample", "is_sample": "not_sample"}

  def __init__(self, root):
    self.path = root / "_decisions.json"
    try:
      with open(self.path, encoding="utf-8") as f:
        loaded = json.load(f)
    except (OSError, ValueError):
      loaded = {}
    if not isinstance(loaded, dict):
      loaded = {}
    self.data = {k: loaded.get(k, {}) if isinstance(loaded.get(k), dict) else {} for k in self.KINDS}
    self.unsaved = False

  @property
  def not_sample(self):
    return self.data["not_sample"]

  @property
  def not_duplicate(self):
    return self.data["not_duplicate"]

  @property
  def is_sample(self):
    return self.data["is_sample"]

  def add(self, kind, file_hash, info):
    if file_hash in self.data[kind]:
      return False
    opposite = self.OPPOSITE.get(kind)
    if opposite:
      self.data[opposite].pop(file_hash, None)
    self.data[kind][file_hash] = info
    self.unsaved = True
    return True

  def save(self):
    if not self.unsaved:
      return
    tmp = self.path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(self.data, f, indent=1)
    os.replace(tmp, self.path)
    self.unsaved = False


TEXT_ROLES = {
  "id3": {"title": "TIT2", "artist": "TPE1", "album": "TALB", "track": "TRCK"},
  "mp4": {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "track": "trkn"},
  "vorbis": {"title": "title", "artist": "artist", "album": "album", "track": "tracknumber"},
}


def get_tag_texts(file_path):
  """Title/artist/album/track as text, from the file's tags, then Windows RIFF INFO for WAV."""
  texts = {}
  try:
    audio = MutagenFile(file_path)
  except Exception:
    audio = None
  tags = audio.tags if audio is not None else None
  kind = "id3" if isinstance(tags, ID3) else "mp4" if isinstance(tags, MP4Tags) else "vorbis" if tags is not None else None
  if kind:
    for role, key in TEXT_ROLES[kind].items():
      try:
        if kind == "id3":
          value = str(tags[key]) if key in tags else ""
        elif kind == "mp4":
          raw = tags.get(key)
          value = str(raw[0][0]) if key == "trkn" and raw else str(raw[0]) if raw else ""
        else:
          raw = tags.get(key, [])
          value = str(raw[0]) if raw else ""
      except Exception:
        value = ""
      if value.strip():
        texts[role] = value.strip()
  if file_path.suffix.lower() == ".wav":
    for role, value in read_riff_info(file_path).items():
      if role in ("title", "artist", "album", "track"):
        texts.setdefault(role, value)
  return texts


def get_title(file_path):
  title = get_tag_texts(file_path).get("title")
  return title.lower() if title else None


def get_metadata_score(file_path):
  """Returns (has_art, key_fields, total_tags), or None if the file can't be read.
  Tuples compare left to right: art wins, then the 7 key fields, then total tag count."""
  try:
    audio = MutagenFile(file_path)
  except Exception:
    return None
  if audio is None:
    return None

  tags = audio.tags
  has_art = bool(getattr(audio, "pictures", None))  # FLAC stores art outside tags
  fields = 0
  total = 0

  try:
    if isinstance(tags, ID3):
      fields = sum(1 for k in ID3_FIELDS if k in tags and str(tags[k]).strip())
      has_art = has_art or bool(tags.getall("APIC"))
      total = sum(1 for frame in tags.values() if str(frame).strip())
    elif isinstance(tags, MP4Tags):
      fields = sum(1 for k in MP4_FIELDS if tags.get(k))
      has_art = has_art or bool(tags.get("covr"))
      total = sum(1 for v in tags.values() if v)
    elif tags is not None:
      fields = sum(1 for k in VORBIS_FIELDS if any(str(v).strip() for v in tags.get(k, [])))
      has_art = has_art or bool(tags.get("metadata_block_picture"))
      total = sum(1 for k in tags.keys() if any(str(v).strip() for v in tags.get(k, [])))
  except Exception:
    return None

  if file_path.suffix.lower() == ".wav":
    riff = read_riff_info(file_path)
    fields = max(fields, sum(1 for r in RIFF_KEY_ROLES if r in riff))
    total += len(riff)

  return (has_art, fields, total)


def tag_present(tags, kind, key):
  try:
    if kind == "id3":
      return key in tags and bool(str(tags[key]).strip())
    if kind == "mp4":
      return bool(tags.get(key))
    return any(str(v).strip() for v in tags.get(key, []))
  except Exception:
    return False


def read_audio_info(file_path):
  info = {"seconds": None, "channels": None, "title": False, "artist": False, "album": False, "art": False}
  try:
    audio = MutagenFile(file_path)
  except Exception:
    audio = None

  if audio is not None:
    info["seconds"] = getattr(audio.info, "length", None) or None
    info["channels"] = getattr(audio.info, "channels", None)
    info["art"] = bool(getattr(audio, "pictures", None))
    tags = audio.tags
    if isinstance(tags, ID3):
      kind = "id3"
      info["art"] = info["art"] or bool(tags.getall("APIC"))
    elif isinstance(tags, MP4Tags):
      kind = "mp4"
      info["art"] = info["art"] or bool(tags.get("covr"))
    elif tags is not None:
      kind = "vorbis"
      info["art"] = info["art"] or tag_present(tags, "vorbis", "metadata_block_picture")
    else:
      kind = None
    if kind:
      for role, keys in TAG_ROLES[kind].items():
        info[role] = any(tag_present(tags, kind, k) for k in keys)

  if file_path.suffix.lower() == ".wav":
    riff = read_riff_info(file_path)
    for role in ("title", "artist", "album"):
      info[role] = info[role] or role in riff

  if info["seconds"] is None and file_path.suffix.lower() == ".wav":
    try:
      with wave.open(str(file_path), "rb") as w:
        info["seconds"] = w.getnframes() / w.getframerate()
        info["channels"] = w.getnchannels()
    except Exception:
      pass
  return info


def has_loop_chunk(file_path):
  """True if a WAV has acid/smpl chunks or an AIFF has INST/basc (sampler loop data)."""
  try:
    with open(file_path, "rb") as f:
      header = f.read(12)
      if len(header) < 12:
        return False
      if header[:4] in (b"RIFF", b"RF64") and header[8:12] == b"WAVE":
        endian, wanted = "<", {b"acid", b"smpl"}
      elif header[:4] == b"FORM" and header[8:12] in (b"AIFF", b"AIFC"):
        endian, wanted = ">", {b"INST", b"basc"}
      else:
        return False
      for _ in range(64):
        chunk = f.read(8)
        if len(chunk) < 8:
          return False
        if chunk[:4] in wanted:
          return True
        size = struct.unpack(endian + "I", chunk[4:])[0]
        f.seek(size + (size & 1), 1)
  except (OSError, struct.error):
    pass
  return False


def bpm_from_name(stem):
  m = BPM_RE.search(stem) or LEAD_BPM_RE.search(stem)
  if m and 60 <= int(m.group(1)) <= 200:
    return int(m.group(1))
  return None


def is_bar_aligned(seconds, bpm):
  bars = seconds * bpm / 240  # 4 beats per bar
  return round(bars) >= 1 and abs(bars - round(bars)) <= BAR_TOLERANCE


def key_family_name(stem):
  """Name with key and tempo removed, so key variants of one sample collapse together."""
  name = KEY_RE.sub("", stem)
  name = BPM_RE.sub("", name)
  name = LEAD_BPM_RE.sub("", name)
  return re.sub(r"[\s_-]+", "_", name).strip("_").lower()


def find_samples(target_dir, skip_dirs, hashes, decisions):
  """Returns (path, seconds, score, reasons) for files scoring as samples."""
  print(f"Scanning for samples: {target_dir.resolve()}...\n")

  folders = {}
  listing = Progress("Finding files")
  seen = 0
  for file_path in target_dir.rglob("*"):
    if any(d in file_path.parents for d in skip_dirs) or not file_path.is_file():
      continue
    seen += 1
    listing.update(seen)
    ext = file_path.suffix.lower()
    entry = folders.setdefault(file_path.parent, {"audio": [], "sidecar": False})
    if ext in MUSIC_EXTENSIONS:
      entry["audio"].append(file_path)
    elif ext in SIDECAR_EXTENSIONS:
      entry["sidecar"] = True
  listing.done(seen)

  total_files_scanned = 0
  candidates = []  # [path, seconds, signals, forced]
  all_seconds = {}
  analyzing = Progress("Analyzing", sum(len(e["audio"]) for e in folders.values()))

  for folder, entry in folders.items():
    files = entry["audio"]
    if not files:
      continue
    infos = {}
    for p in files:
      infos[p] = read_audio_info(p)
      total_files_scanned += 1
      analyzing.update(total_files_scanned)

    known = [i["seconds"] for i in infos.values() if i["seconds"] is not None]
    short = sum(1 for s in known if s <= DJ_MIN_SECONDS)
    pack_folder = len(files) >= PACK_FOLDER_MIN_FILES and known and short / len(known) >= PACK_FOLDER_SHORT_RATIO
    # Real albums never have every track the same length; sample packs often do
    uniform = (len(files) >= PACK_FOLDER_MIN_FILES and len(known) == len(files)
               and max(known) - min(known) <= UNIFORM_LENGTH_TOLERANCE and max(known) <= SAMPLE_MAX_SECONDS)
    folder_named = bool(PACK_FOLDER_RE.search(folder.name))
    tag_texts = {p: get_tag_texts(p) for p in files}
    tag_words = {p: any(TAG_PACK_RE.search(tag_texts[p].get(k, "")) for k in ("artist", "album")) for p in files}
    pack_like = pack_folder or uniform or folder_named or any(tag_words.values())
    tagged = sum(1 for i in infos.values() if i["artist"] and i["album"])
    album_folder = (not pack_like and len(files) >= ALBUM_FOLDER_MIN_FILES
                    and tagged / len(files) >= ALBUM_FOLDER_TAGGED_RATIO)

    families = {}
    for p in files:
      if KEY_RE.search(p.stem):
        families.setdefault(key_family_name(p.stem), set()).add(p.stem)

    # Numbered series: same name apart from a trailing number ("EDM Beatloop 124bpm 01" .. "25")
    series = {}
    for p in files:
      m = SERIES_RE.match(p.stem)
      if m:
        series.setdefault(m.group(1).strip(" _-").casefold(), set()).add(p.stem)

    for p in files:
      info = infos[p]
      seconds = info["seconds"]
      all_seconds[p] = seconds
      # Unreadable length: leave it alone rather than guess
      if seconds is None or seconds > SAMPLE_MAX_SECONDS:
        continue

      # (points, reason, is_evidence): evidence = name, folder, tag-text or file-content signal.
      signals = []
      has_key = bool(KEY_RE.search(p.stem))
      family_size = len(families.get(key_family_name(p.stem), ())) if has_key else 0
      bpm = bpm_from_name(p.stem)

      # Length is checked first: nothing this short is a real track, whatever its tags say.
      # Whole seconds, as Windows Explorer shows Length (30.7s displays as 0:30).
      forced = int(seconds) <= DJ_MIN_SECONDS
      if forced:
        signals.append((SAMPLE_THRESHOLD, f"<={DJ_MIN_SECONDS}s (too short for a real track)", True))
      else:
        signals.append((1, f"<={SAMPLE_MAX_SECONDS}s", False))

      if has_loop_chunk(p):
        signals.append((5, "loop data", True))
      if family_size >= 2:
        signals.append((4, f"{family_size} key variants", True))
      m = SERIES_RE.match(p.stem)
      series_size = len(series.get(m.group(1).strip(" _-").casefold(), ())) if m else 0
      if series_size >= SERIES_MIN_FILES:
        signals.append((3, f"numbered series of {series_size}", True))
      if bpm and is_bar_aligned(seconds, bpm):
        signals.append((3, "bar length", True))
      if bpm or has_key:
        signals.append((2, "bpm/key in name", True))
      if SOUND_WORD_RE.search(p.stem):
        signals.append((1, "sound word", True))
      if NUMBERED_RE.search(p.stem):
        signals.append((1, "numbered", True))
      if uniform:
        signals.append((5, "identical lengths in folder", True))
      if pack_folder:
        signals.append((3, "pack folder", True))
      if folder_named:
        signals.append((2, "folder name", True))
      if entry["sidecar"]:
        signals.append((2, "sidecar files", True))
      if tag_words[p]:
        signals.append((3, "pack words in artist/album tag", True))

      # Tags are weighed after length. Artists are sometimes on samples, albums rarely, both together seldom.
      has_title, has_artist, has_album = info["title"], info["artist"], info["album"]
      if has_artist and has_album:
        signals.append((-3, "has artist + album", False))
      elif has_album:
        signals.append((-2, "has album", False))
      elif has_artist:
        signals.append((-1, "has artist", False))
      elif has_title:
        signals.append((1, "no artist/album", False))
      else:
        signals.append((2, "no tags", False))
      if not info["art"]:
        signals.append((1, "no art", False))
      if p.suffix.lower() in {".wav", ".aif", ".aiff"}:
        signals.append((1, "wav/aiff", False))
      if info["channels"] == 1:
        signals.append((1, "mono", False))
      if album_folder:
        signals.append((-3, "in tagged album folder", False))

      candidates.append([p, seconds, signals, forced])

  analyzing.done(total_files_scanned)

  def score(c):
    return sum(points for points, _, _ in c[2])

  def is_flagged(c):
    return c[3] or (score(c) >= SAMPLE_THRESHOLD and any(ev for _, _, ev in c[2]))

  # Exact copies of flagged files elsewhere (e.g. samples dropped into an artist folder).
  # Name + size only narrows the search; the file hash must match to count.
  flagged_by_key = {}
  for c in candidates:
    if is_flagged(c):
      flagged_by_key.setdefault((c[0].name.lower(), c[0].stat().st_size), []).append(c[0])
  for c in candidates:
    if is_flagged(c):
      continue
    others = flagged_by_key.get((c[0].name.lower(), c[0].stat().st_size))
    if others:
      own_hash = hashes.get(c[0])
      if own_hash and any(hashes.get(o) == own_hash for o in others):
        c[2].append((6, "exact copy of flagged file", True))

  flagged = [(c[0], c[1], score(c), [r for _, r, _ in c[2]])
             for c in candidates if is_flagged(c)]

  # Files you placed in _SAMPLES yourself are remembered by hash and always suggested
  if decisions.is_sample:
    already = {f[0] for f in flagged}
    sizes = {info.get("size") for info in decisions.is_sample.values()}
    for p, seconds in all_seconds.items():
      if p not in already and p.stat().st_size in sizes:
        file_hash = hashes.get(p)
        if file_hash in decisions.is_sample:
          flagged.append((p, seconds if seconds is not None else 0.0, SAMPLE_THRESHOLD, ["you marked this as a sample"]))

  # Anything you previously put back from _SAMPLES is never suggested again (matched by hash)
  samples = []
  remembered = 0
  for s in flagged:
    file_hash = hashes.get(s[0])
    if file_hash and file_hash in decisions.not_sample:
      remembered += 1
    else:
      samples.append(s)
  hashes.save()
  if remembered:
    print(f"{GREEN}Not suggested because you put them back before: {remembered}{RESET}")

  samples.sort(key=lambda s: str(s[0]).lower())
  return samples, total_files_scanned


def write_samples_csv(samples, target_dir, csv_path, dest_root=None):
  with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(["original_path", "new_path", "seconds", "score", "reasons"])
    for file_path, seconds, score, reasons in samples:
      rel = file_path.relative_to(target_dir)
      new_path = dest_root / rel if dest_root else ""
      writer.writerow([str(rel), str(new_path), f"{seconds:.1f}", score, "; ".join(reasons)])


def append_log(csv_path, header, rows):
  """Appends to a CSV log, writing the header only when the file is new."""
  is_new = not csv_path.exists()
  csv_path.parent.mkdir(parents=True, exist_ok=True)
  # BOM only at the start of a new file so Excel reads it as UTF-8
  with open(csv_path, "a", newline="", encoding="utf-8-sig" if is_new else "utf-8") as f:
    writer = csv.writer(f)
    if is_new:
      writer.writerow(header)
    writer.writerows(rows)


def preview_samples(samples, target_dir):
  by_folder = {}
  for file_path, _, _, _ in samples:
    by_folder.setdefault(file_path.parent.relative_to(target_dir), 0)
    by_folder[file_path.parent.relative_to(target_dir)] += 1
  for folder, count in sorted(by_folder.items(), key=lambda kv: str(kv[0]).lower()):
    print(f"  {count:5}  {folder}")
  csv_path = target_dir / "_samples_preview.csv"
  write_samples_csv(samples, target_dir, csv_path)
  print(f"\nFull per-file list with scores and reasons: {csv_path}\n")


def move_samples(samples, target_dir, samples_dir):
  moved = 0
  stamp = time.strftime("%Y-%m-%d %H:%M:%S")
  log_path = samples_dir / "_samples_log.csv"
  header = ["time", "status", "moved_from", "moved_to", "seconds", "score", "reasons"]
  moving = Progress("Moving samples", len(samples))
  for n, (file_path, seconds, score, reasons) in enumerate(samples, 1):
    dest = samples_dir / file_path.relative_to(target_dir)
    if not file_path.exists():
      status = "skipped: file no longer exists"
    elif dest.exists():
      status = "skipped: destination already exists"
    else:
      try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(file_path), str(dest))
        moved += 1
        status = "moved"
      except Exception as e:
        status = f"failed: {e}"
    if status != "moved":
      print(f"\n{RED}{file_path.name}: {status}{RESET}")
    # One row per file, written immediately, so an interrupted run still has a complete log
    append_log(log_path, header, [[stamp, status, str(file_path.relative_to(target_dir)),
                                   str(dest.relative_to(target_dir)), f"{seconds:.1f}", score, "; ".join(reasons)]])
    moving.update(n)
  moving.done(len(samples))
  print(f"{WHITE}Log:{RESET} {log_path}")
  return moved


def print_sample_summary(title, total_files_scanned, samples, moved, samples_dir):
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{title:^40}{RESET}")
  print(SEPARATOR)
  print(f"Total music files scanned : {total_files_scanned}")
  if moved is None:
    print(f"Samples that would move   : {len(samples)}")
  else:
    print(f"Samples moved             : {moved} of {len(samples)}")
    print(f"Samples folder            : {samples_dir.resolve()}")
  print(SEPARATOR)


def find_duplicate_groups(target_dir, skip_dirs, hashes, decisions):
  """Groups files matching by hash OR by (title, size)."""
  files = []
  parent = []
  first_by_hash = {}
  first_by_title = {}
  total_files_scanned = 0
  kept_by_you = 0

  def find(i):
    while parent[i] != i:
      parent[i] = parent[parent[i]]
      i = parent[i]
    return i

  def union(a, b):
    parent[find(a)] = find(b)

  print(f"Scanning directory: {target_dir.resolve()}...\n")

  music_files = []
  listing = Progress("Finding files")
  for file_path in target_dir.rglob("*"):
    if any(d in file_path.parents for d in skip_dirs):
      continue
    if file_path.is_file() and file_path.suffix.lower() in MUSIC_EXTENSIONS:
      music_files.append(file_path)
      listing.update(len(music_files))
  listing.done(len(music_files))

  hashing = Progress("Hashing", len(music_files))
  try:
    for file_path in music_files:
      total_files_scanned += 1
      hashing.update(total_files_scanned)
      file_hash = hashes.get(file_path)

      if not file_hash:
        continue
      # You put this file back from _DUPLICATES before: leave it out of duplicate matching entirely
      if file_hash in decisions.not_duplicate:
        kept_by_you += 1
        continue

      idx = len(files)
      files.append(file_path)
      parent.append(idx)

      if file_hash in first_by_hash:
        union(idx, first_by_hash[file_hash])
      else:
        first_by_hash[file_hash] = idx

      title = get_title(file_path)
      if title:
        title_key = (title, file_path.stat().st_size)
        if title_key in first_by_title:
          union(idx, first_by_title[title_key])
        else:
          first_by_title[title_key] = idx
  finally:
    hashes.save()
  hashing.done(total_files_scanned)
  hashes.report()
  if kept_by_you:
    print(f"{GREEN}Left out because you put them back before: {kept_by_you}{RESET}")

  groups = {}
  for idx in range(len(files)):
    groups.setdefault(find(idx), []).append(files[idx])

  plan = []
  for group in groups.values():
    if len(group) < 2:
      continue
    scores = {f: get_metadata_score(f) for f in group}
    # Never pick a keeper when any copy's tags can't be read; that group is left for you
    if any(s is None for s in scores.values()):
      plan.append((None, group, scores))
      continue
    keeper = max(group, key=scores.__getitem__)
    plan.append((keeper, group, scores))

  return plan, total_files_scanned


def files_to_move(plan):
  return sum(len(group) - 1 for keeper, group, _ in plan if keeper is not None)


def fmt_score(score):
  if score is None:
    return "tags unreadable"
  has_art, fields, total = score
  return f"art: {'yes' if has_art else 'no '} | fields: {fields}/{FIELD_COUNT} | tags: {total:>2}"


def preview_plan(plan, target_dir):
  for n, (keeper, group, scores) in enumerate(plan, 1):
    if keeper is None:
      print(f"Group {n}:  {YELLOW}SKIPPED - a copy's tags could not be read, nothing will be moved{RESET}")
    else:
      print(f"Group {n}:")
    for file_path in group:
      action = "----" if keeper is None else "KEEP" if file_path == keeper else "move"
      print(f"  {action}  [{fmt_score(scores[file_path])}]  {file_path.relative_to(target_dir)}")
    print()


DUP_LOG_HEADER = ["time", "status", "moved_from", "moved_to", "kept", "match",
                  "moved_art", "moved_fields", "moved_tags", "kept_art", "kept_fields", "kept_tags"]


def direct_match(a_path, a_hash, a_title, b_path, b_hash, b_title):
  """Returns 'same hash', 'title+size', or None, using values read just now."""
  if a_hash and a_hash == b_hash:
    return "same hash"
  if a_title and a_title == b_title and a_path.stat().st_size == b_path.stat().st_size:
    return "title+size"
  return None


def apply_plan(plan, target_dir, dup_dir, hashes, decisions):
  """Moves non-keepers, re-checking each one against the files on disk right now.
  The scan may be minutes or days old, so nothing from it is trusted blindly."""
  moved = 0
  stamp = time.strftime("%Y-%m-%d %H:%M:%S")
  log_path = dup_dir / "_duplicates_log.csv"
  total = files_to_move(plan)
  moving = Progress("Moving duplicates", total)
  attempted = 0

  def score_cols(score):
    if score is None:
      return ["", "", ""]
    return ["yes" if score[0] else "no", score[1], score[2]]

  for keeper, group, _ in plan:
    if keeper is None:
      continue
    keeper_ok = keeper.exists()
    k_hash = k_title = k_score = None
    if keeper_ok:
      # Fresh reads, not the cache: tags can change without changing size or timestamp
      k_hash, k_title, k_score = get_file_hash(keeper), get_title(keeper), get_metadata_score(keeper)
    for file_path in group:
      if file_path == keeper:
        continue
      dest = dup_dir / file_path.relative_to(target_dir)
      match = ""
      d_score = k_score_now = None
      if not keeper_ok:
        status = "skipped: kept copy no longer exists"
      elif not file_path.exists():
        status = "skipped: file no longer exists"
      elif dest.exists():
        status = "skipped: destination already exists"
      else:
        d_hash, d_title, d_score = get_file_hash(file_path), get_title(file_path), get_metadata_score(file_path)
        k_score_now = k_score
        match = direct_match(file_path, d_hash, d_title, keeper, k_hash, k_title)
        if match is None:
          status = "skipped: no longer matches kept copy"
        elif d_hash in decisions.not_duplicate:
          status = "skipped: you chose to keep this file"
        elif d_score is None or k_score is None:
          status = "skipped: tags unreadable"
        elif d_score > k_score:
          status = "skipped: this copy now has more metadata than the kept copy"
        else:
          try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file_path), str(dest))
            hashes.moved(file_path, dest)
            moved += 1
            status = "moved"
          except Exception as e:
            status = f"failed: {e}"
      if status != "moved":
        print(f"\n{RED}{file_path.name}: {status}{RESET}")
      append_log(log_path, DUP_LOG_HEADER,
                 [[stamp, status, str(file_path.relative_to(target_dir)), str(dest.relative_to(target_dir)),
                   str(keeper.relative_to(target_dir)), match or ""] + score_cols(d_score) + score_cols(k_score_now)])
      attempted += 1
      moving.update(attempted)
  moving.done(attempted)
  hashes.save()
  print(f"{WHITE}Log:{RESET} {log_path}")
  return moved


def print_summary(title, total_files_scanned, plan, moved, dup_dir):
  to_move = files_to_move(plan)
  skipped = sum(1 for keeper, _, _ in plan if keeper is None)
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{title:^40}{RESET}")
  print(SEPARATOR)
  print(f"Total music files scanned : {total_files_scanned}")
  print(f"Duplicate groups          : {len(plan)}")
  if skipped:
    print(f"{YELLOW}Groups skipped (unreadable): {skipped}{RESET}")
  if moved is None:
    print(f"Files that would move     : {to_move}")
  else:
    print(f"Duplicates moved          : {moved} of {to_move}")
    print(f"Duplicates folder         : {dup_dir.resolve()}")
  print(SEPARATOR)


def grade(pct):
  if pct == 100:
    return GREEN, "best copy remains"
  if pct >= 95:
    return GREEN, "excellent"
  if pct >= 80:
    return YELLOW, "good"
  if pct >= 60:
    return PEACH, "fair"
  return RED, "poor"


def run_line(label, passed, total, missing, worse, unreadable=0):
  pct = passed * 100 / total
  color, word = grade(pct)
  filled = round(pct / 5)
  bar = f"{color}{'█' * filled}{DIM}{'░' * (20 - filled)}{RESET}"
  extra = f"  {DIM}missing {missing}, worse {worse}, unreadable {unreadable}{RESET}" if passed < total else ""
  return f"  {WHITE}{label:<8}{RESET}{bar}  {color}{BOLD}{pct:5.1f}%{RESET}  {color}{passed:>2}/{total}  {word}{RESET}{extra}"


def validate_duplicates(target_dir, dup_dir, skip_dirs, history, hashes, pending, sample_size=20):
  """Spot-checks random files in _DUPLICATES: an equal-or-better copy must still be in the library."""
  MIN_VALIDATION_RUNS = 20
  dup_files = []
  finding = Progress("Finding duplicates")
  if dup_dir.is_dir():
    for p in dup_dir.rglob("*"):
      if p.is_file() and p.suffix.lower() in MUSIC_EXTENSIONS:
        dup_files.append(p)
        finding.update(len(dup_files))
  finding.done(len(dup_files))

  if not dup_files:
    print(f"{YELLOW}Nothing in {dup_dir} to validate.{RESET}")
    return

  answer = input(f"{VANILLA}{BOLD}How many runs? (minimum 20, Enter = 20):{RESET} ").strip()
  runs = max(MIN_VALIDATION_RUNS, int(answer)) if answer.isdigit() else MIN_VALIDATION_RUNS

  # Any match must be the same size (same hash, or the title+size rule), so index by size
  by_size = {}
  indexing = Progress("Indexing library")
  indexed = 0
  for p in target_dir.rglob("*"):
    if any(d in p.parents for d in skip_dirs):
      continue
    if p.is_file() and p.suffix.lower() in MUSIC_EXTENSIONS:
      by_size.setdefault(p.stat().st_size, []).append(p)
      indexed += 1
      indexing.update(indexed)
  indexing.done(indexed)

  # Files get re-checked across runs, so remember the expensive reads
  cache = {}

  def facts(p):
    if p not in cache:
      cache[p] = (hashes.get(p), get_title(p), get_metadata_score(p))
    return cache[p]

  for r in range(1, runs + 1):
    # Fresh OS randomness each run: independent draws, nothing seeded or carried between runs
    picks = random.SystemRandom().sample(dup_files, min(sample_size, len(dup_files)))
    passed = missing = worse = unreadable = 0
    failures = []
    checking = Progress(f"Validating run {r}/{runs}", len(picks))
    for n, dup in enumerate(picks, 1):
      dup_hash, dup_title, dup_score = facts(dup)
      best = None
      unreadable_match = False
      for cand in by_size.get(dup.stat().st_size, []):
        cand_hash, cand_title, cand_score = facts(cand)
        if cand_hash == dup_hash or (dup_title and cand_title == dup_title):
          if cand_score is None:
            unreadable_match = True
          elif best is None or cand_score > best[1]:
            best = (cand, cand_score)
      if dup_score is None or (best is None and unreadable_match):
        unreadable += 1
        failures.append(f"    {YELLOW}CHECK{RESET} {dup.relative_to(dup_dir)}  {YELLOW}tags unreadable, compare by hand{RESET}")
      elif best is None:
        missing += 1
        pending[dup] = ("missing", None)
        failures.append(f"    {RED}FAIL{RESET}  {dup.relative_to(dup_dir)}  {RED}no matching copy left in the library{RESET}")
      elif best[1] < dup_score:
        worse += 1
        pending[dup] = ("worse", best[0])
        failures.append(f"    {RED}FAIL{RESET}  {dup.relative_to(dup_dir)}  {DIM}[{fmt_score(dup_score)}]{RESET}\n"
                        f"          {RED}kept copy is worse:{RESET} {best[0].relative_to(target_dir)}  {DIM}[{fmt_score(best[1])}]{RESET}")
      else:
        passed += 1
        pending.pop(dup, None)
      checking.update(n)
    checking.done(len(picks))

    history.append((passed, len(picks), missing, worse, unreadable))
    print(run_line(f"Run {len(history)}", passed, len(picks), missing, worse, unreadable))
    for line in failures:
      print(line)

  hashes.save()
  hashes.report()

  pcts = [h[0] * 100 / h[1] for h in history]
  avg = sum(pcts) / len(pcts)
  avg_color, avg_word = grade(avg)
  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'VALIDATION HISTORY':^40}{RESET}")
  print(SEPARATOR)
  print(f"{WHITE}Duplicates in folder: {len(dup_files)}   Files per run: {min(sample_size, len(dup_files))}{RESET}")
  for i, h in enumerate(history, 1):
    print(run_line(f"Run {i}", *h))
  print(SEPARATOR)
  print(f"  {WHITE}Average {RESET}{avg_color}{BOLD}{avg:5.1f}%  {avg_word}{RESET}   "
        f"{WHITE}Best{RESET} {max(pcts):.0f}%   {WHITE}Worst{RESET} {min(pcts):.0f}%   {WHITE}Runs{RESET} {len(history)}")
  print(SEPARATOR)


def flatten_library(target_dir, flat_dir, skip_dirs):
  """Copies every remaining track into flat_dir with no subfolders. Originals are untouched."""
  tracks = []
  finding = Progress("Finding tracks")
  for p in target_dir.rglob("*"):
    if any(d in p.parents for d in skip_dirs):
      continue
    if p.is_file() and p.suffix.lower() in MUSIC_EXTENSIONS:
      tracks.append(p)
      finding.update(len(tracks))
  finding.done(len(tracks))

  if not tracks:
    print(f"{YELLOW}No tracks found to flatten.{RESET}")
    return

  needed = sum(p.stat().st_size for p in tracks)
  free = shutil.disk_usage(flat_dir.parent).free
  print(f"{WHITE}Space needed:{RESET} {needed / 1e9:.2f} GB   {WHITE}Free:{RESET} {free / 1e9:.2f} GB")
  if needed > free:
    print(f"{RED}Not enough free space. Nothing was copied.{RESET}")
    return

  confirm = input(f"{YELLOW}Copy {len(tracks)} track(s) to {flat_dir}? (y/n):{RESET} ").strip().lower()
  if confirm != "y":
    print(f"{RED}Cancelled.{RESET}")
    return

  flat_dir.mkdir(exist_ok=True)
  copied = skipped = renamed = failed = 0
  copying = Progress("Copying", len(tracks))
  for n, src in enumerate(tracks, 1):
    dest = flat_dir / src.name
    i = 2
    src_hash = None
    already_there = False
    try:
      # A same-named file only counts as already copied if its contents are identical
      while dest.exists():
        if src_hash is None:
          src_hash = get_file_hash(src)
        if src_hash is not None and get_file_hash(dest) == src_hash:
          already_there = True
          break
        dest = flat_dir / f"{src.stem} ({i}){src.suffix}"
        i += 1
      if already_there:
        skipped += 1
      else:
        shutil.copy2(src, dest)
        copied += 1
        if i > 2:
          renamed += 1
    except Exception as e:
      failed += 1
      print(f"\n{RED}Failed to copy {src.name}: {e}{RESET}")
    copying.update(n)
  copying.done(len(tracks))

  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'FLATTEN COMPLETE':^40}{RESET}")
  print(SEPARATOR)
  print(f"Tracks found              : {len(tracks)}")
  print(f"Copied                    : {copied}")
  print(f"Renamed (name clash)      : {renamed}")
  print(f"Already in folder         : {skipped}  (identical contents)")
  print(f"Failed                    : {failed}")
  print(f"Flattened folder          : {flat_dir.resolve()}")
  print(SEPARATOR)


class NoRepairNeeded(Exception):
  pass


def repair_failures(target_dir, dup_dir, pending, hashes):
  """Worse keeper: swap it with the better copy in _DUPLICATES. Missing: restore the copy to the library."""
  print()
  for dup, (kind, kept) in pending.items():
    if kind == "worse":
      print(f"  {GREEN}swap{RESET}     restore {dup.relative_to(dup_dir)}")
      print(f"           {DIM}retire  {kept.relative_to(target_dir)}{RESET}")
    else:
      print(f"  {GREEN}restore{RESET}  {dup.relative_to(dup_dir)}  {DIM}(no copy left in library){RESET}")
  print()
  confirm = input(f"{YELLOW}Repair {len(pending)} failed duplicate(s)? (y/n):{RESET} ").strip().lower()
  if confirm != "y":
    print(f"{RED}Cancelled.{RESET}")
    return

  stamp = time.strftime("%Y-%m-%d %H:%M:%S")
  log_path = dup_dir / "_duplicates_log.csv"
  fixed = 0
  total = len(pending)
  repairing = Progress("Repairing", total)
  for n, (dup, (kind, kept)) in enumerate(list(pending.items()), 1):
    original = target_dir / dup.relative_to(dup_dir)
    rows = []
    try:
      if not dup.exists():
        raise FileNotFoundError("no longer in _DUPLICATES")
      if original.exists():
        raise FileExistsError(f"{original.relative_to(target_dir)} is already taken")
      if kind == "worse":
        if not kept.exists():
          raise FileNotFoundError(f"kept copy {kept.relative_to(target_dir)} is gone")
        # Re-check with fresh reads: both must still match, and the kept copy must still be worse
        if direct_match(dup, get_file_hash(dup), get_title(dup), kept, get_file_hash(kept), get_title(kept)) is None:
          raise ValueError("the two copies no longer match")
        d_score, k_score = get_metadata_score(dup), get_metadata_score(kept)
        if d_score is None or k_score is None:
          raise ValueError("tags unreadable")
        if not d_score > k_score:
          raise NoRepairNeeded("kept copy is no longer worse")
        retired = dup_dir / kept.relative_to(target_dir)
        if retired.exists():
          raise FileExistsError(f"{retired.relative_to(target_dir)} is already taken")
        retired.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(kept), str(retired))
        hashes.moved(kept, retired)
        rows.append([stamp, "repair: retired worse copy", str(kept.relative_to(target_dir)),
                     str(retired.relative_to(target_dir)), str(original.relative_to(target_dir)), ""])
      original.parent.mkdir(parents=True, exist_ok=True)
      shutil.move(str(dup), str(original))
      hashes.moved(dup, original)
      rows.append([stamp, "repair: restored better copy" if kind == "worse" else "repair: restored missing copy",
                   str(dup.relative_to(target_dir)), str(original.relative_to(target_dir)),
                   str(original.relative_to(target_dir)), ""])
      del pending[dup]
      fixed += 1
    except NoRepairNeeded as e:
      rows.append([stamp, f"repair not needed: {e}", str(dup.relative_to(target_dir)), "", "", ""])
      del pending[dup]
    except Exception as e:
      rows.append([stamp, f"repair failed: {e}", str(dup.relative_to(target_dir)), "", "", ""])
      print(f"\n{RED}Could not repair {dup.name}: {e}{RESET}")
    append_log(log_path, DUP_LOG_HEADER, rows)
    repairing.update(n)
  repairing.done(total)
  hashes.save()

  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'REPAIR COMPLETE':^40}{RESET}")
  print(SEPARATOR)
  print(f"Repaired                  : {fixed}")
  print(f"Could not repair          : {len(pending)}")
  print(f"Log                       : {log_path}")
  print(SEPARATOR)


def read_log(log_path):
  if not log_path.exists():
    return []
  with open(log_path, encoding="utf-8-sig", newline="") as f:
    return list(csv.DictReader(f))


def learn_from_returns(target_dir, samples_dir, dup_dir, hashes, decisions):
  """Finds files you moved back out of _SAMPLES / _DUPLICATES and remembers them by hash.
  A file counts as 'put back' only when its _SAMPLES/_DUPLICATES copy is gone and a file
  is again at its exact original path."""
  results = {}
  for kind, log_path, memory in (("samples", samples_dir / "_samples_log.csv", "not_sample"),
                                 ("duplicates", dup_dir / "_duplicates_log.csv", "not_duplicate")):
    latest = {}
    for row in read_log(log_path):
      if row.get("status") == "moved":
        latest[row["moved_from"]] = row  # later rows win, so a re-move after a return counts as moved
    still, returned, elsewhere = [], [], []
    for src, row in latest.items():
      if (target_dir / row["moved_to"]).exists():
        still.append(row)
      elif (target_dir / src).exists():
        returned.append(row)
      else:
        elsewhere.append(row)
    learned = 0
    for row in returned:
      file_hash = hashes.get(target_dir / row["moved_from"])
      if file_hash and decisions.add(memory, file_hash, {
          "path": row["moved_from"], "learned": time.strftime("%Y-%m-%d %H:%M:%S"),
          "score": row.get("score", ""), "reasons": row.get("reasons", ""), "kept": row.get("kept", "")}):
        learned += 1
    results[kind] = {"still": still, "returned": returned, "elsewhere": elsewhere, "learned": learned}

  # Audio files in _SAMPLES that no log row put there were placed by you: remember them as samples
  logged_dests = {row["moved_to"].casefold() for row in read_log(samples_dir / "_samples_log.csv")
                  if row.get("status") == "moved"}
  added, added_learned = [], 0
  if samples_dir.is_dir():
    for p in samples_dir.rglob("*"):
      if p.is_file() and p.suffix.lower() in MUSIC_EXTENSIONS \
          and str(p.relative_to(target_dir)).casefold() not in logged_dests:
        added.append(p)
        file_hash = hashes.get(p)
        if file_hash and decisions.add("is_sample", file_hash, {
            "path": str(p.relative_to(target_dir)), "size": p.stat().st_size,
            "learned": time.strftime("%Y-%m-%d %H:%M:%S")}):
          added_learned += 1
  results["samples"]["added"] = added
  results["samples"]["added_learned"] = added_learned
  decisions.save()
  decisions.save()
  hashes.save()
  return results


def report_learning(results, target_dir):
  s = results["samples"]
  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'SAMPLES: WHAT YOU PUT BACK':^40}{RESET}")
  print(SEPARATOR)
  print(f"Still in _SAMPLES         : {len(s['still'])}")
  print(f"Put back by you           : {len(s['returned'])}  {GREEN}(newly remembered: {s['learned']}){RESET}")
  print(f"Moved elsewhere / deleted : {len(s['elsewhere'])}  {DIM}(not learned from: original path is empty){RESET}")
  print(f"Placed in _SAMPLES by you : {len(s['added'])}  {GREEN}(newly remembered: {s['added_learned']}){RESET}")

  if s["returned"]:
    # Which signals fired on files you put back vs files you left in _SAMPLES
    def signal_names(row):
      return {re.sub(r"^\d+ ", "", r.strip()) for r in row.get("reasons", "").split(";") if r.strip()}
    back = [signal_names(r) for r in s["returned"]]
    stayed = [signal_names(r) for r in s["still"]]
    names = sorted(set().union(*back, *stayed))
    print()
    print(f"  {WHITE}{'signal':<28}{'put back':>9}{'stayed':>9}{'put-back rate':>15}{RESET}")
    rows = []
    for name in names:
      b = sum(name in x for x in back)
      k = sum(name in x for x in stayed)
      rows.append((b / (b + k) if b + k else 0, name, b, k))
    for rate, name, b, k in sorted(rows, reverse=True):
      color = RED if rate >= 0.5 else YELLOW if rate >= 0.2 else GREEN
      print(f"  {name:<28}{b:>9}{k:>9}{color}{rate * 100:>14.0f}%{RESET}")
    print(f"  {DIM}High put-back rate = that signal is flagging files you consider real music.{RESET}")
    print()
    print(f"  {WHITE}Files you put back (they will not be suggested again):{RESET}")
    for row in s["returned"]:
      print(f"    {PEACH}score {row.get('score', '?'):>2}{RESET}  {row['moved_from']}  {DIM}[{row.get('reasons', '')}]{RESET}")

  d = results["duplicates"]
  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'DUPLICATES: WHAT YOU PUT BACK':^40}{RESET}")
  print(SEPARATOR)
  print(f"Still in _DUPLICATES      : {len(d['still'])}")
  print(f"Put back by you           : {len(d['returned'])}  {GREEN}(newly remembered: {d['learned']}){RESET}")
  print(f"Moved elsewhere / deleted : {len(d['elsewhere'])}")
  for row in d["returned"]:
    print(f"    {PEACH}kept both{RESET}  {row['moved_from']}  {DIM}(was matched to {row.get('kept', '?')} by {row.get('match', '?')}){RESET}")
  print(SEPARATOR)


# ---- Name normalization (winners only) ----
WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
COPY_PREFIX_RE = re.compile(r"^copy(\s*\(\d+\))?\s+of\s+", re.IGNORECASE)
COPY_SUFFIX_RES = [
  re.compile(r"\s*-\s*copy(\s*\(\d+\))?$", re.IGNORECASE),       # "Song - Copy", "Song - Copy (2)"
  re.compile(r"[\s_]+copy(\s*\(\d+\))?$", re.IGNORECASE),        # "Song copy", "Song_copy"
  re.compile(r"\s*\(copy\)$", re.IGNORECASE),                    # "Song (copy)"
  re.compile(r"[\s_-]+dup(e|licate)?[\s_-]*\d*$", re.IGNORECASE),  # "Song__dup001", "Song - dupe", "Song duplicate"
]
NUMBER_SUFFIX_RE = re.compile(r"\s*\((\d+)\)$")                  # "Song (1)" as Windows names copies


def tidy(text):
  return re.sub(r"\s+", " ", text).strip(" ._-")


def strip_copy_markers(stem, title):
  """Removes copy/dupe markers. '(n)' is only removed when the Title tag doesn't itself end in '(n)'."""
  out = COPY_PREFIX_RE.sub("", stem)
  changed = True
  while changed:
    changed = False
    for pattern in COPY_SUFFIX_RES:
      new = pattern.sub("", out)
      if new != out:
        out, changed = new, True
    m = NUMBER_SUFFIX_RE.search(out)
    if m and not (title and NUMBER_SUFFIX_RE.search(title)):
      out, changed = out[:m.start()], True
  return tidy(out)


def comparable(text):
  return re.sub(r"[^0-9a-z]+", "", text.casefold())


def safe_stem(text):
  """Makes a tag value usable as a Windows file name; returns '' if it can't be done cleanly."""
  text = tidy(WINDOWS_INVALID.sub("-", text))
  if not text or text.upper() in WINDOWS_RESERVED or len(text) > 180:
    return ""
  return text


def winners_from_log(target_dir, dup_dir, skip_dirs):
  """Kept copies recorded in _duplicates_log.csv that are still in the library."""
  winners = set()
  for row in read_log(dup_dir / "_duplicates_log.csv"):
    status = row.get("status", "")
    rel = row.get("kept") if status == "moved" else row.get("moved_to") if status == "repair: restored better copy" else None
    if rel:
      p = target_dir / rel
      if p.is_file() and not any(d in p.parents for d in skip_dirs):
        winners.add(p)
  return sorted(winners, key=lambda p: str(p).lower())


def plan_renames(winners):
  """Returns (auto, review): auto = name only loses copy markers/extra spaces and agrees with the Title tag
  (or there is no Title); review = needs your choice."""
  auto, review = [], []
  checking = Progress("Checking winner names", len(winners))
  for n, p in enumerate(winners, 1):
    checking.update(n)
    tags = get_tag_texts(p)
    title = tags.get("title")
    clean_title = strip_copy_markers(title, None) if title else ""
    cleaned = strip_copy_markers(p.stem, clean_title)
    if cleaned == p.stem:
      continue  # already clean
    options = []
    if cleaned and safe_stem(cleaned) == cleaned:
      options.append(("filename without copy markers", cleaned))
    if clean_title and safe_stem(clean_title):
      options.append(("Title tag", safe_stem(clean_title)))
      if tags.get("artist") and safe_stem(f"{tags['artist']} - {clean_title}"):
        options.append(("Artist - Title tags", safe_stem(f"{tags['artist']} - {clean_title}")))
    seen, unique = set(), []
    for label, stem in options:
      if stem.casefold() not in seen:
        seen.add(stem.casefold())
        unique.append((label, stem))
    title_agrees = not clean_title or comparable(clean_title) in comparable(cleaned)
    if cleaned and safe_stem(cleaned) == cleaned and title_agrees:
      auto.append((p, cleaned, "copy markers / spacing removed" + ("; matches Title" if clean_title else "; no Title tag"), tags))
    elif unique:
      review.append((p, unique, tags))
  checking.done(len(winners))
  return auto, review


def rename_one(src, new_stem, reason, target_dir, hashes, log_path, title):
  """Renames src to new_stem + its exact original extension. Never overwrites, never deletes."""
  stamp = time.strftime("%Y-%m-%d %H:%M:%S")
  dest = src.with_name(new_stem + src.suffix)  # src.suffix is kept byte-for-byte
  try:
    if not src.is_file():
      raise FileNotFoundError("file no longer exists")
    case_only = dest.exists() and dest.samefile(src)
    if dest.exists() and not case_only:
      raise FileExistsError(f"{dest.name} already exists")
    if dest.suffix != src.suffix:
      raise ValueError("extension would change")
    size = src.stat().st_size
    os.rename(src, dest)  # os.rename refuses to replace an existing file on Windows
    if not dest.is_file() or dest.stat().st_size != size or (not case_only and src.exists()):
      raise RuntimeError("rename could not be verified; check both names by hand")
    hashes.moved(src, dest)
    status = "renamed"
  except Exception as e:
    status = f"skipped: {e}"
  append_log(log_path, ["time", "status", "old_path", "new_path", "reason", "title_tag"],
             [[stamp, status, str(src.relative_to(target_dir)), str(dest.relative_to(target_dir)), reason, title or ""]])
  return status


def normalize_winner_names(target_dir, dup_dir, skip_dirs, hashes):
  winners = winners_from_log(target_dir, dup_dir, skip_dirs)
  if not winners:
    print(f"{YELLOW}No kept duplicates found in the log. Move duplicates first.{RESET}")
    return
  auto, review = plan_renames(winners)
  log_path = target_dir / "_renames_log.csv"

  # Two renames must never land on the same name
  claimed = {str(p).casefold() for p in winners}
  def free_target(src, stem):
    key = str(src.with_name(stem + src.suffix)).casefold()
    return key == str(src).casefold() or key not in claimed

  if not auto and not review:
    print(f"{GREEN}All {len(winners)} winner names are already clean.{RESET}")
    return

  renamed = skipped = 0
  if auto:
    print()
    print(f"{WHITE}{BOLD}Safe renames{RESET} {DIM}(only copy markers / extra spaces removed, extension unchanged){RESET}")
    for p, stem, reason, tags in auto:
      print(f"  {PEACH}{p.name}{RESET}\n    {LIME}-> {stem}{p.suffix}{RESET}  {DIM}[{reason}]{RESET}")
    answer = input(f"{YELLOW}Type RENAME to rename these {len(auto)} file(s), anything else skips them:{RESET} ").strip()
    if answer == "RENAME":
      progress = Progress("Renaming", len(auto))
      for n, (p, stem, reason, tags) in enumerate(auto, 1):
        if not free_target(p, stem):
          status = "skipped: another rename already uses that name"
        else:
          status = rename_one(p, stem, reason, target_dir, hashes, log_path, tags.get("title"))
        if status == "renamed":
          renamed += 1
          claimed.discard(str(p).casefold())
          claimed.add(str(p.with_name(stem + p.suffix)).casefold())
        else:
          skipped += 1
          print(f"\n{RED}{p.name}: {status}{RESET}")
        progress.update(n)
      progress.done(len(auto))
    else:
      skipped += len(auto)
      print(f"{RED}Safe renames skipped.{RESET}")

  if review:
    print()
    print(f"{WHITE}{BOLD}Needs your choice{RESET} {DIM}({len(review)} file(s); s = skip, q = stop reviewing){RESET}")
    for i, (p, options, tags) in enumerate(review, 1):
      print()
      print(f"  {WHITE}{i}/{len(review)}{RESET}  {PEACH}{p.relative_to(target_dir)}{RESET}")
      print(f"      {DIM}Title: {tags.get('title', '-')} | Artist: {tags.get('artist', '-')} | "
            f"Album: {tags.get('album', '-')} | Track: {tags.get('track', '-')}{RESET}")
      for k, (label, stem) in enumerate(options, 1):
        print(f"      {CYAN}{k}{RESET}  {stem}{p.suffix}  {DIM}({label}){RESET}")
      answer = input(f"      {VANILLA}Choose 1-{len(options)}, s or q:{RESET} ").strip().lower()
      if answer == "q":
        skipped += len(review) - i + 1
        break
      if not answer.isdigit() or not 1 <= int(answer) <= len(options):
        skipped += 1
        continue
      label, stem = options[int(answer) - 1]
      if not free_target(p, stem):
        status = "skipped: another rename already uses that name"
      else:
        status = rename_one(p, stem, f"your choice: {label}", target_dir, hashes, log_path, tags.get("title"))
      if status == "renamed":
        renamed += 1
        claimed.discard(str(p).casefold())
        claimed.add(str(p.with_name(stem + p.suffix)).casefold())
        print(f"      {GREEN}renamed{RESET}")
      else:
        skipped += 1
        print(f"      {RED}{status}{RESET}")

  hashes.save()
  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'NAME NORMALIZATION':^40}{RESET}")
  print(SEPARATOR)
  print(f"Winners checked           : {len(winners)}")
  print(f"Renamed                   : {renamed}")
  print(f"Skipped                   : {skipped}")
  print(f"Log                       : {log_path}")
  print(SEPARATOR)


# ---- Folder maintenance (ghost / empty folders) ----
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400  # junctions / symlinks: never entered, never removed


def _attributes(path):
  try:
    return os.stat(path, follow_symlinks=False).st_file_attributes
  except (OSError, AttributeError):
    return 0


def _hidden_or_system(path):
  return bool(_attributes(path) & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def scan_folders(target_dir, keep_dirs):
  """Returns (ghost, empty).
  ghost: folders Explorer shows as empty but that hold hidden/system files (desktop.ini, Thumbs.db...). Never touched.
  empty: folders with no files anywhere inside them, hidden or not. Only these can be removed."""
  files_below = {}
  ghost, empty = [], []
  scanning = Progress("Scanning folders")
  n = 0
  for dirpath, dirnames, filenames in os.walk(target_dir, topdown=False, followlinks=False):
    d = Path(dirpath)
    n += 1
    scanning.update(n)
    count = len(filenames)
    for name in dirnames:
      sub = d / name
      # A junction/symlink or anything not scanned is treated as holding files, so its parent is never removed
      count += 1 if _attributes(sub) & FILE_ATTRIBUTE_REPARSE_POINT else files_below.get(sub, 1)
    files_below[d] = count
    if d == target_dir or d in keep_dirs or _attributes(d) & FILE_ATTRIBUTE_REPARSE_POINT:
      continue
    if count == 0:
      empty.append(d)
    elif filenames and all(_hidden_or_system(d / f) for f in filenames) \
        and all(_hidden_or_system(d / x) for x in dirnames):
      ghost.append((d, sorted(filenames)))
  scanning.done(n)
  return ghost, empty


FOLDER_LOG_HEADER = ["time", "action", "path", "detail"]
GHOST_JUNK = {"desktop.ini", "thumbs.db"}  # moved to _ARCHIVE, never deleted


def _set_attributes(path, attrs):
  import ctypes
  # 0x80 = FILE_ATTRIBUTE_NORMAL, required when no other attribute is left
  if not ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs or 0x80):
    raise OSError(f"could not change attributes of {path.name}")


def show_ghost_folders(target_dir, ghost):
  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'GHOST FOLDERS':^40}{RESET}")
  print(SEPARATOR)
  print(f"{DIM}Look empty in Explorer but hold hidden/system files.{RESET}")
  for d, names in ghost:
    print(f"  {PEACH}{d.relative_to(target_dir)}{RESET}  {DIM}[{', '.join(names)}]{RESET}")
  print(f"{WHITE}Ghost folders:{RESET} {len(ghost)}")


def show_empty_folders(target_dir, empty):
  print()
  print(SEPARATOR)
  print(f"{VANILLA}{BOLD}{'TRULY EMPTY FOLDERS':^40}{RESET}")
  print(SEPARATOR)
  print(f"{DIM}No files anywhere inside, hidden or not.{RESET}")
  for d in sorted(empty, key=lambda p: str(p).casefold()):
    print(f"  {LAVENDER}{d.relative_to(target_dir)}{RESET}")
  print(f"{WHITE}Empty folders:{RESET} {len(empty)}")


def fix_ghost_folders(target_dir, ghost):
  """desktop.ini / thumbs.db are moved to _ARCHIVE (not deleted); other hidden items are unhidden;
  a folder left with nothing in it is removed."""
  show_ghost_folders(target_dir, ghost)
  if not ghost:
    return
  print(f"\n{DIM}desktop.ini and thumbs.db go to _ARCHIVE\\<date-time>\\ghost\\, other hidden items are made visible,"
        f" and a folder that ends up with nothing in it is removed.{RESET}")
  if input(f"{YELLOW}Type FIX to fix these {len(ghost)} ghost folder(s), anything else leaves them:{RESET} ").strip() != "FIX":
    print(f"{RED}Nothing changed.{RESET}")
    return

  log_path = target_dir / "_folders_log.csv"
  stamp = time.strftime("%Y-%m-%d %H:%M:%S")
  archive = target_dir / "_ARCHIVE" / time.strftime("%Y-%m-%d_%H%M%S") / "ghost"
  archived = unhidden = removed = 0
  fixing = Progress("Fixing ghost folders", len(ghost))
  for n, (d, _) in enumerate(ghost, 1):
    rows = []
    for item in sorted(d.iterdir()):
      rel = item.relative_to(target_dir)
      try:
        attrs = _attributes(item)
        if attrs & FILE_ATTRIBUTE_REPARSE_POINT:
          rows.append([stamp, "skipped", str(rel), "junction/symlink left alone"])
        elif item.is_file() and item.name.casefold() in GHOST_JUNK:
          dest = archive / rel
          if dest.exists():
            raise FileExistsError(f"{dest} already exists")
          dest.parent.mkdir(parents=True, exist_ok=True)
          os.rename(item, dest)  # same drive: a move, never a copy or delete
          archived += 1
          rows.append([stamp, "archived", str(rel), str(dest.relative_to(target_dir))])
        elif attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM):
          _set_attributes(item, attrs & ~(FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))
          unhidden += 1
          rows.append([stamp, "unhidden", str(rel), f"previous attributes 0x{attrs:X}"])
      except OSError as e:
        rows.append([stamp, "skipped", str(rel), str(e)])
        print(f"\n{RED}{rel}: {e}{RESET}")
    try:
      if not any(d.iterdir()):
        os.rmdir(d)  # only succeeds on an empty folder
        removed += 1
        rows.append([stamp, "removed empty folder", str(d.relative_to(target_dir)), ""])
    except OSError as e:
      rows.append([stamp, "skipped", str(d.relative_to(target_dir)), str(e)])
    append_log(log_path, FOLDER_LOG_HEADER, rows)
    fixing.update(n)
  fixing.done(len(ghost))
  print(f"{GREEN}Archived {archived} junk file(s), unhid {unhidden} item(s), removed {removed} now-empty folder(s).{RESET}")
  print(f"{WHITE}Log:{RESET} {log_path}")


def remove_empty_folders(target_dir, empty):
  show_empty_folders(target_dir, empty)
  if not empty:
    return
  if input(f"{YELLOW}Type REMOVE to remove these {len(empty)} empty folder(s), anything else leaves them:{RESET} ").strip() != "REMOVE":
    print(f"{RED}Nothing removed.{RESET}")
    return
  log_path = target_dir / "_folders_log.csv"
  stamp = time.strftime("%Y-%m-%d %H:%M:%S")
  removed = 0
  removing = Progress("Removing empty folders", len(empty))
  # Deepest first, so a parent is only tried after its empty children are gone
  for n, d in enumerate(sorted(empty, key=lambda p: len(p.parts), reverse=True), 1):
    try:
      if any(d.iterdir()):
        raise OSError("no longer empty")
      os.rmdir(d)  # os.rmdir can only remove an empty folder; it cannot delete files
      status = "removed"
      removed += 1
    except OSError as e:
      status = f"skipped: {e}"
      print(f"\n{RED}{d.relative_to(target_dir)}: {status}{RESET}")
    append_log(log_path, FOLDER_LOG_HEADER, [[stamp, status, str(d.relative_to(target_dir)), ""]])
    removing.update(n)
  removing.done(len(empty))
  print(f"{GREEN}Removed {removed} empty folder(s).{RESET}  {WHITE}Log:{RESET} {log_path}")


def folder_maintenance(target_dir, keep_dirs):
  """Folder menu. Rescans before every action so it always works on the folder as it is now."""
  while True:
    print()
    print(SEPARATOR)
    print(f"{VANILLA}{BOLD}{'FOLDER MAINTENANCE':^40}{RESET}")
    print(SEPARATOR)
    menu_line("1", PEACH, "Ghost", "Show ghost folders  (nothing changed)")
    menu_line("2", SAND, "Ghost", "Fix ghost folders  (asks first)")
    menu_line("3", LAVENDER, "Empty", "Show truly empty folders  (nothing changed)")
    menu_line("4", TEAL, "Empty", "Remove truly empty folders  (asks first)")
    menu_line("B", RED, "Back", "Return to main menu")
    print(SEPARATOR)
    choice = input(f"{VANILLA}{BOLD}Choose an option:{RESET} ").strip().upper()
    if choice == "B":
      return
    if choice not in {"1", "2", "3", "4"}:
      print(f"{RED}Invalid choice.{RESET}")
      continue
    ghost, empty = scan_folders(target_dir, set(keep_dirs))
    if choice == "1":
      show_ghost_folders(target_dir, ghost)
    elif choice == "2":
      fix_ghost_folders(target_dir, ghost)
    elif choice == "3":
      show_empty_folders(target_dir, empty)
    elif choice == "4":
      remove_empty_folders(target_dir, empty)


def menu_line(num, color, group, action, group_color=WHITE):
  print(f"  {color}{BOLD}{num}{RESET}  {group_color}{group:<11}{RESET}{color}{action}{RESET}")


def main():
  os.system("")  # enables ANSI colors in older Windows consoles
  music_directory = input(f"{VANILLA}{BOLD}Enter the path to your music folder:{RESET} ").strip().strip('"')
  target_dir = Path(music_directory).resolve()

  if not target_dir.is_dir():
    print(f"{RED}Error: '{music_directory}' is not a valid directory.{RESET}")
    return

  dup_dir = target_dir / "_DUPLICATES"
  samples_dir = target_dir / "_SAMPLES"
  if target_dir.parent == target_dir:
    print(f"{RED}Pick a folder, not a drive root: FLATTENED-TRACKS is created next to the folder.{RESET}")
    return
  flat_dir = target_dir.parent / "FLATTENED-TRACKS"
  skip_dirs = (dup_dir, samples_dir)
  hashes = HashCache(target_dir)
  decisions = Decisions(target_dir)
  plan = None
  samples = None
  validation_history = []
  pending_repairs = {}  # dup path -> ("worse", kept path) or ("missing", None)
  total_files_scanned = 0
  total_sample_scanned = 0

  def learn_quietly():
    results = learn_from_returns(target_dir, samples_dir, dup_dir, hashes, decisions)
    new = results["samples"]["learned"] + results["samples"]["added_learned"] + results["duplicates"]["learned"]
    if new:
      print(f"{GREEN}Learned from your changes: {results['samples']['learned']} sample(s) put back, "
            f"{results['samples']['added_learned']} sample(s) added by you, "
            f"{results['duplicates']['learned']} duplicate(s) put back. Use option 7 to see why.{RESET}")

  while True:
    duplicates_done = any(r.get("status") == "moved" for r in read_log(dup_dir / "_duplicates_log.csv"))
    flatten_blockers = []
    if not validation_history:
      flatten_blockers.append("validation not run yet")
    if pending_repairs:
      flatten_blockers.append(f"{len(pending_repairs)} unrepaired fail(s)")

    print()
    print(SEPARATOR)
    menu_line("0", LAVENDER, "Folders", "Ghost / empty folder maintenance  (run first)")
    menu_line("1", LIME, "Samples", "Find likely samples  (nothing is moved)")
    menu_line("2", PEACH, "Samples", "Move suggested samples to _SAMPLES")
    menu_line("3", TEAL, "Duplicates", "Hash remaining files, suggest duplicates  (nothing is moved)")
    menu_line("4", SAND, "Duplicates", "Move suggested duplicates to _DUPLICATES")
    if duplicates_done:
      menu_line("5", VANILLA, "Names", "Normalize names of winning files  (asks before every rename)")
    else:
      menu_line("5", GRAY, "Names", "Normalize names of winning files  (move duplicates first)", GRAY)
    menu_line("6", CYAN, "Validate", "20+ runs of 20 random duplicates")
    if pending_repairs:
      menu_line("R", GREEN, "Repair", f"Fix {len(pending_repairs)} failed duplicate(s) found by validation")
    menu_line("7", LIME, "Learn", "Recheck what you put back from _SAMPLES / _DUPLICATES and why")
    if flatten_blockers:
      menu_line("8", GRAY, "Flatten", f"Copy remaining tracks to {flat_dir}  ({'; '.join(flatten_blockers)})", GRAY)
    else:
      menu_line("8", YELLOW, "Flatten", f"Copy remaining tracks to {flat_dir}")
    menu_line("Q", RED, "Quit", "")
    print(SEPARATOR)
    choice = input(f"{VANILLA}{BOLD}Choose an option:{RESET} ").strip().upper()

    if choice == "0":
      folder_maintenance(target_dir, (samples_dir, dup_dir, target_dir / "_ARCHIVE"))

    elif choice == "1":
      learn_quietly()
      samples, total_sample_scanned = find_samples(target_dir, skip_dirs, hashes, decisions)
      preview_samples(samples, target_dir)
      print_sample_summary("SAMPLES DRY RUN COMPLETE", total_sample_scanned, samples, None, samples_dir)

    elif choice == "2":
      if samples is None:
        learn_quietly()
        samples, total_sample_scanned = find_samples(target_dir, skip_dirs, hashes, decisions)
      if not samples:
        print(f"{GREEN}No samples found.{RESET}")
        continue
      confirm = input(f"{YELLOW}Move {len(samples)} file(s) to {samples_dir}? (y/n):{RESET} ").strip().lower()
      if confirm != "y":
        print(f"{RED}Cancelled.{RESET}")
        continue
      moved = move_samples(samples, target_dir, samples_dir)
      print()
      print_sample_summary("SAMPLES MOVED", total_sample_scanned, samples, moved, samples_dir)
      samples = None
      plan = None  # library changed, duplicate results are stale

    elif choice == "3":
      learn_quietly()
      plan, total_files_scanned = find_duplicate_groups(target_dir, skip_dirs, hashes, decisions)
      preview_plan(plan, target_dir)
      print_summary("DRY RUN COMPLETE", total_files_scanned, plan, None, dup_dir)

    elif choice == "4":
      # Reuse the dry-run results if there are any, otherwise scan now; every move is re-verified anyway
      if plan is None:
        learn_quietly()
        plan, total_files_scanned = find_duplicate_groups(target_dir, skip_dirs, hashes, decisions)
      to_move = files_to_move(plan)
      if to_move == 0:
        print(f"{GREEN}No duplicates found.{RESET}")
        continue
      confirm = input(f"{YELLOW}Move {to_move} file(s) to {dup_dir}? (y/n):{RESET} ").strip().lower()
      if confirm != "y":
        print(f"{RED}Cancelled.{RESET}")
        continue
      moved = apply_plan(plan, target_dir, dup_dir, hashes, decisions)
      print()
      print_summary("SCAN & CLEAN COMPLETE", total_files_scanned, plan, moved, dup_dir)
      plan = None
      samples = None

    elif choice == "5":
      if not duplicates_done:
        print(f"{YELLOW}Move duplicates first (option 4); only winning files are renamed.{RESET}")
        continue
      normalize_winner_names(target_dir, dup_dir, skip_dirs, hashes)
      plan = None
      samples = None

    elif choice == "6":
      validate_duplicates(target_dir, dup_dir, skip_dirs, validation_history, hashes, pending_repairs)

    elif choice == "R" and pending_repairs:
      repair_failures(target_dir, dup_dir, pending_repairs, hashes)
      plan = None

    elif choice == "7":
      report_learning(learn_from_returns(target_dir, samples_dir, dup_dir, hashes, decisions), target_dir)

    elif choice == "8":
      if flatten_blockers:
        print(f"{YELLOW}{BOLD}Flatten is not ready:{RESET}")
        for reason in flatten_blockers:
          print(f"  {YELLOW}- {reason}{RESET}")
        print(f"{DIM}Run Validate (and Repair if offered) first so bad tracks don't end up in FLATTENED-TRACKS.{RESET}")
        if input(f"{RED}Type FLATTEN to continue anyway:{RESET} ").strip() != "FLATTEN":
          print(f"{RED}Cancelled.{RESET}")
          continue
      flatten_library(target_dir, flat_dir, skip_dirs)

    elif choice == "Q":
      break

    else:
      print(f"{RED}Invalid choice.{RESET}")


if __name__ == "__main__":
  main()