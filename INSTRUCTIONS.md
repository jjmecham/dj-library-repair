# Music Folder Repair App — Instructions

Status: **planning phase. No application code may be written until the plan in `plan/` is approved by Jeremy.**

## 1. Goal

One Python app with a guided menu that prompts for a source music folder, copies it to the output, and performs a complete, non-destructive repair on the copy:

- **Complete:** no music is lost. Every audio file in the source is accounted for in the output.
- **Organized:** preserve the source folder structure; put samples in `_SAMPLES` and duplicates in `_DUPLICATES` at the output root. Flattening is a separate function, not the main output layout.
- **Fully logged:** every move, rename, tag edit, skip and failure is written to a log.
- **Rollback:** no separate rollback feature or snapshot is needed. The source remains untouched; restarting means setting aside the output copy and copying from the source again.
- **Output:** `C:\Users\Jeremy\REPAIRED-MUSIC`.
- **Originals intact:** the selected source folder and the three original source scripts are never modified.

## 2. Non-negotiable rules

1. **No assumptions, no drift, no imagination.** Every behavior must come from Jeremy's stated requirements or from verified facts (code that was read, commands that were run). If something is unclear, stop and ask Jeremy.
2. **The source folder is read-only** for the whole run.
3. **Nothing is ever deleted.** Files are moved or copied and never overwritten. The only removal allowed is an empty folder, using a call that can only remove empty folders (`os.rmdir`).
4. **Extensions are never changed,** except in the extension-repair stage, and only when the file's contents prove its type.
5. **Every changing action is previewed and confirmed** before execution. Renames, move batches and tag edits are logged with old and new values.
6. **Every stage is accounted for:** counts and file identities must balance. Record pre-edit hashes and paths; after tag edits, record new hashes as well. Every source file must have one traceable current location in the output.
7. **The reference scripts in `reference/` are read-only** and must never be edited. They are the specification of proven behavior.
8. **Written in Python.** Use `mutagen` for audio duration and tag reads in sample detection. Use required `taglib-sharp` through `pythonnet` for tag handling; the selected approach must retain Windows-visible tags, including RIFF INFO in WAV files, and preserve DJ-software metadata and album art. Tag edits are limited to Title and Name tags; filename normalization may rename files.

## 3. Verified facts (checked 2026-10-01)

| Fact | Value |
|---|---|
| Python | 3.14.7 |
| mutagen | 1.48.1 installed |
| Tag library at `C:\Users\Jeremy\Scripts\lib` | `taglib-sharp.dll` 2.1.0.0 (a **.NET** assembly), plus `policy.2.0.taglib-sharp.dll` and its `.config` |
| Can Python load taglib-sharp? | **Verified 2026-10-01:** `pythonnet` is installed. Load CoreCLR with `pythonnet.load("coreclr")` before importing `clr`; `clr.AddReference(...)` and `import TagLib` then succeed. The default runtime failed to load the DLL. |
| Source selection | The app prompts for the source folder at runtime; it does not hard-code `C:\Users\Jeremy\Music`. `C:\Jeremy\Music` was checked and does not exist. |
| Previously inspected music folder | `C:\Users\Jeremy\Music`: 9,086 files (all types), 35.08 GB, as checked 2026-10-01. This is not the app's preselected source. |
| Free space | C: 246.8 GB, D: 415.1 GB, E: 716.2 GB |
| Output folder | `C:\Users\Jeremy\REPAIRED-MUSIC` (does not exist yet) |

## 4. Source modules (copies in `reference/`; originals untouched)

The details below describe the legacy modules as inspected. They are not, by themselves, the merged app's behavior; the decisions in §5–§7 control where they differ.

### 4.1 `simpleDupe.py` (from `C:\Users\Jeremy\Scripts`)
- **Scope:** recursive. It works **in place** inside the chosen folder.
- **Which files it sees:** only by **extension**: `.mp3 .flac .wav .aac .ogg .m4a .aif .aiff`. A file with a wrong or missing extension is invisible to it.
- **Menu:** 0 folders (ghost/empty), 1–2 samples, 3–4 duplicates, 5 names, 6 validate, R repair, 7 learn, 8 flatten, Q quit.
- **Samples:**
  - Anything 30 seconds or shorter (whole seconds) is a sample, regardless of tags.
  - Files over 30s and up to 60s are scored, threshold 6, and need at least one name, folder, tag-text or file-content signal.
  - Files over 60s are never samples.
  - Your decisions are remembered by hash in `_decisions.json`.
  - Destination: `_SAMPLES\` with the original folder path mirrored inside it.
- **Duplicates:**
  - Matched by MD5 hash, OR by identical Title (ignoring case) plus identical byte size.
  - Keeper: highest (has art, 7 key fields, total tags). On a tie, the first file found is kept.
  - Groups with unreadable tags are skipped.
  - Every move is re-verified with fresh reads.
  - Destination: `_DUPLICATES\` with the original path mirrored.
- **Hash cache:** `_hash_cache.json` at the root. Reused while a file's size and modified time (nanoseconds) are unchanged.
- **Names:** renames only, and only winners from `_duplicates_log.csv`. Strips copy/dupe markers and "(n)". Extension kept exactly. Confirmation required.
- **Validation:** 20 or more runs of 20 random files from `_DUPLICATES`, each checking that an equal-or-better copy remains. Repair (swap or restore) is offered only when a run fails.
- **Learning:** files put back from `_SAMPLES` or `_DUPLICATES`, and files placed into `_SAMPLES` by hand, are remembered by hash.
- **Folder maintenance (port of the ghost script):**
  - `desktop.ini` and `thumbs.db` are moved to `_ARCHIVE\<stamp>\ghost\`; other hidden items are unhidden.
  - Folders are removed only when empty, via `os.rmdir`.
  - Junctions are skipped.
- **Flatten:** copies the remaining tracks to `<parent>\FLATTENED-TRACKS`. A clashing name gets " (n)"; a file already there is detected by hash.
- **Logs:** `_samples_log.csv`, `_duplicates_log.csv`, `_renames_log.csv`, `_folders_log.csv`, `_samples_preview.csv`.

### 4.2 `ghostVSEmptyFolders.ps1` (from `C:\Users\Jeremy\Scripts`)
- **Root is hard-coded** to `C:\Users\Jeremy\Music`.
- **Destructive as written:**
  - deletes `desktop.ini` and `thumbs.db`
  - `Remove-Item -Force` on folders
- Already ported safely into `simpleDupe.py` option 0. **The port, not the script, is the behavior to keep.**

### 4.3 `reassignTypeMusic.py` (from `C:\Users\Jeremy\Scripts\MusicScripts`; its spec is `reference/reassignTypeMusic.Instructions.md`)
- **Scope:** **root-level files only** (non-recursive). It was designed for a flat folder.
- **Stages:**
  1. **Extension repair:** the real type is detected from file contents (mutagen class → extension map). If the corrected name is taken, the file is moved to `_COPIES_`.
  2. **Same-track review:** fuzzy candidate keys built from Name, Filename and Title tags and the filename stem. Non-keepers go to `_FILTERED_`.
  3. **Exact copies:** SHA-256. Extras go to `_REVIEW_`.
  4. **Final naming:** writes Title, Name and Filename tags and renames to the canonical title. If the name is taken, the file goes to `_COPIES_`.
- **Snapshot:** copies the root files into `_SNAPSHOTS_` once, before the first Execute.
- **Ledger:** the tracked total (root files + `_COPIES_` + `_FILTERED_` + `_REVIEW_`) must not change during a stage.

## 5. Decisions for the merged app

These are settled decisions recorded in `plan/00-decisions.md`; that file is authoritative if this summary ever differs.

- Prompt for the source folder at runtime. Copy it to `C:\Users\Jeremy\REPAIRED-MUSIC` and work only on that copy. Preserve the artist/album folder structure; flattening is a separate operation.
- Never modify the source or delete files. Keep track-specific art and sidecar metadata with their audio file. Move unrelated non-audio files to a review folder; its name and exact location remain open.
- Run ghost/empty-folder cleanup first, then content-based extension repair, sample detection, and exact-duplicate review. Cleanup must enumerate hidden and system entries; skip junctions; archive `desktop.ini` and `thumbs.db`; remove folders only with `os.rmdir` when truly empty.
- Use `mutagen` to read duration and tags for sample detection. Follow `plan/sample_detection_prototype.py` for the authoritative rating behavior: score `>= 40` is sample, score `<= 0` is track, and the middle range is ambiguous. Move both sample and ambiguous files to `_SAMPLES`; only tracks stay in the library. If more than 90% of files in a folder score as samples, move the folder as a unit to `_SAMPLES`.
- Do not hash files for sample classification. Hashing is reserved for duplicate detection and accounting.
- Use exact-duplicate checks only; do not use fuzzy/name-normalized matching. Keep the copy with the most complete metadata. Move duplicate copies, unchanged, to the root `_DUPLICATES` folder. Files differing only in musical key or BPM are distinct samples, not duplicates based only on a stripped name.
- Name normalization is a final polish over library files. Do not add text. Derive the original name from the file's own metadata and remove only characters unsupported by that metadata. Rename/write only when normalization is needed. Do not alter DJ-software metadata or album art; tag writes are limited to Title and Name.
- Use `taglib-sharp` through `pythonnet` with CoreCLR for tag handling. Preview and ask for confirmation before any changing action; log old and new values.
- No separate snapshot or rollback feature is required: the source copy is the recovery point.
- Keep the validation step: sample at least 20 runs of 20 random files from `_DUPLICATES`; verify an equal-or-better copy remains in the library. Offer repair only after a failed run.

## 6. Remaining planning questions

Resolve these before finalizing the relevant planning documents. Do not choose defaults without Jeremy's direction or verified research.

1. **Unrelated non-audio destination:** choose the review folder name and location. Track-specific art/sidecars stay with their audio file.
2. **Windows Search integration:** determine whether `kind:music` can be queried reliably from Python and whether the index is present/current. It is optional; content-based detection is the fallback. Explorer Details-view configuration is out of scope; Jeremy sets it manually.
3. **Preview and report fields:** decide the information shown for flagged files and final accounting; prior notes say previews should surface useful music-tag detail, but the report format is not settled.
4. **Duplicate edge case:** confirm that the approved Title-plus-byte-size check cannot merge distinct files that differ only by Key/BPM. Exact hash matches are distinct from name-based/fuzzy matching; do not silently broaden the duplicate rule.

## 7. Proposed stage order (planning draft; document the proof in `plan/02-pipeline.md`)

Each step lists why it sits where it does.

1. **Preflight (read-only):** prompt for the source; verify source/output paths, free space, and tools; inventory files and establish the accounting baseline.
2. **Create the working copy:** copy to `REPAIRED-MUSIC`; verify every copied file against the inventory before continuing.
3. **Folder maintenance:** enumerate all entries, including hidden/system files; archive `desktop.ini` and `thumbs.db`; skip junctions; remove only truly empty folders with `os.rmdir`.
4. **Extension repair:** detect audio type from content and repair extensions only when content proves the type. This precedes any extension-dependent scan.
5. **Samples:** use the authoritative prototype's score and thresholds; classify without hashing. Move samples and ambiguous files to `_SAMPLES`; move a whole folder when more than 90% of its files score as samples.
6. **Exact duplicates:** apply the approved exact-match methods; retain the most complete-metadata copy and move other copies unchanged to `_DUPLICATES`. Do not use fuzzy matching; protect Key/BPM variants.
7. **Non-audio review:** move unrelated non-audio files to the yet-to-be-named review location; keep track-specific art and metadata with their audio file.
8. **Validate:** run the approved random checks on `_DUPLICATES`; offer repair only when a check fails.
9. **Name normalization:** final pass on library files only. Do not rename duplicate files. Resolve filename collisions inside the library; never move a different track out of it.
10. **Final accounting:** re-hash after tag edits, confirm every source file has a traceable output location, perform the final duplicate check, clean up empty folders, and report results.

## 8. Accounting invariants (draft; finalize in `plan/03-safety-and-accounting.md`)

- **Every source audio file remains represented** exactly once as a file in the output: in the library, `_SAMPLES`, `_DUPLICATES`, or another approved destination. Identify it by its inventory path and pre-edit hash; record post-edit hashes when tags change.
- **Track-specific non-audio files stay with their audio file.** Every unrelated non-audio file is accounted for in the approved review destination.
- **Counts balance:** source files equal files accounted for across the library and approved destinations at each stage; document any intentional grouping/move as a unit without losing per-file records.
- **Every audio file in `_DUPLICATES`** has an equal-or-better copy in the library under the approved keeper rule.
- **Every log row has a status;** none are left blank.
- **A stage that fails its invariant stops the workflow.** Nothing further runs until Jeremy decides.

## 9. Planning deliverables (in `plan/`; produced with the prompts in `.github/prompts/`)

1. `plan/01-module-audit.md`: a factual behavior table for each reference module, with line references.
2. `plan/02-pipeline.md`: stage order with a dependency proof, inputs and outputs per stage.
3. `plan/03-safety-and-accounting.md`: invariants, manifest schema, rollback, failure modes.
4. `plan/04-architecture.md`: package layout, what is reused vs rewritten, tag-library strategy, UI.
5. `plan/05-test-plan.md`: fixtures, unit tests, end-to-end tests, acceptance criteria.
6. `plan/00-decisions.md`: Jeremy's answers to §6, dated. **Nothing in 02–05 may contradict this file.**
