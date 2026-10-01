# Jeremy's decisions

Dated entries. Nothing in `plan/02-*` through `plan/05-*` may contradict this file.

## 2026-10-01

### Decision 1: Source path

**Answered (Jeremy, 2026-10-01):** not a fixed/pre-confirmed path — the app prompts for the source folder at runtime. `C:\Users\Jeremy\Music` is not hardcoded as the source; this replaces the open question in `INSTRUCTIONS.md` §6.1.

### Decision 2: Working model

**Answered (Jeremy, 2026-10-01):** option (A) from `INSTRUCTIONS.md` §6.2 — copy the source into `REPAIRED-MUSIC` and work only on the copy. The untouched source is the rollback. Needs ~35GB on C: (246.8GB free, per the verified facts in `INSTRUCTIONS.md` §3), not the ~70GB a snapshot-plus-in-place approach would need.

### Decision 9: Rollback mechanics

**Answered (Jeremy, 2026-10-01):** no dedicated rollback feature is needed — "we don't need it since it will work off of a copy." Because the app only ever works on the copy in `REPAIRED-MUSIC` (Decision 2) and the source is never touched, "rollback" in practice just means: delete/rename aside `REPAIRED-MUSIC` and re-run from the untouched source. No separate undo/rollback mechanism needs to be built. This closes the open question in `INSTRUCTIONS.md` §6.9.

### Decision 10: Workspace name

**Answered (Jeremy, 2026-10-01):** rename to `DJ-Library-Repair` (from `MusicRepairApp`). **Attempted on disk, not yet completed:** `Rename-Item` failed — "The process cannot access the file because it is being used by another process," since the folder is open in VS Code. Needs the folder closed in the editor before the rename can succeed; still named `MusicRepairApp` on disk as of this entry.

### Decision 3: Final layout of REPAIRED-MUSIC

**Answered (Jeremy, 2026-10-01):** `REPAIRED-MUSIC`'s layout is **fully folder-structured** (artist/album folders kept), not flat. Flattening (simpleDupe's existing `FLATTENED-TRACKS` behavior, `INSTRUCTIONS.md` §4.1, §7 step 9, and C10) is a **separate function**, not the primary output layout of this app's run.

### Decision 4: Duplicate method

**Answered (Jeremy, 2026-10-01):** **exact match only** — no name-based/fuzzy candidate matching (resolves `INSTRUCTIONS.md` §6.4 and sidesteps C6's fuzzy-matching risk entirely for this stage). This lines up with the duplicate-detection methods `simpleDupe.py` already has: MD5 hash, and/or identical Title (case-insensitive) + identical byte size (`INSTRUCTIONS.md` §4.1). **Keeper rule:** keep the file with the **most complete metadata** ("most meta") — simplifies `simpleDupe`'s existing cascading keeper score (art → 7 key fields → total tags, §4.1) to "most complete file wins." Jeremy, 2026-10-01: "it should be obvious that one is better than the other two so choose the best" — confirms this is meant to be a clear-cut choice even across a group of 3+ duplicates, not a close call needing extra tie-break rules. Non-keepers are moved to a root `_DUPLICATES` folder (matches the destination `simpleDupe.py` already uses, `INSTRUCTIONS.md` §4.1/§6.9, not a new destination). **Clarified (Jeremy, 2026-10-01):** "don't construe the duplicates comment, that was answering your previous question" — the "choose the best... rename the rest" remark belongs entirely to this duplicate-keeper decision, not to a separate name-normalization rule; no open question remains here. **Further clarified (Jeremy, 2026-10-01):** "no need to rename duplicate files" — non-keepers are moved to `_DUPLICATES` as-is, with no filename/tag renaming applied to them.

### Decision 5: Tag writing permission

**Answered (Jeremy, 2026-10-01):** all music-related metadata and album art must be **retained as-is**, because it is used by Serato DJ Pro and rekordbox (cue points, hot cues, beat grids, crate/waveform data, embedded art, etc. — typically stored in tag frames like Serato's `Markers2`/`Markers_`/analysis data and rekordbox-specific fields). Any tag writing the app does must **not strip or alter** this DJ-software metadata or art.
- Directly relevant to `INSTRUCTIONS.md` **C4** (conflict: `reassign`'s keeper scoring explicitly *ignores* Serato/rekordbox data, while `simpleDupe`'s scoring considers art + key fields). This answer favors preserving that data, which leans toward `simpleDupe`'s approach over `reassign`'s for anything touching tags.
- **Answered (Jeremy, 2026-10-01):** yes, the app may rename filenames and write **Title and Name tags specifically**, but **only when they are not already normalized** (skip a file whose filename/Title/Name already conform to the normalized form — don't touch/re-log files that don't need it). This is narrower than "any tag": only filename + Title + Name are in scope, not arbitrary tag fields, and always subject to the DJ-metadata/art preservation rule above.
- **Stage placement confirmed (Jeremy, 2026-10-01):** "the renaming feature comes as a final polish to the repaired folder" — matches the already-proposed stage order in `INSTRUCTIONS.md` §7 step 10, where name normalization runs after duplicates/samples/layout are settled, not interleaved with those earlier stages. Renaming is a last-pass cleanup over whatever remains in the library at that point.

### Decision 7: What counts as "music" for accounting

Jeremy, 2026-10-01, first answer: "non audio files or files not relating to an audio file get deleted... Art that goes with a track stays with that track. All other metadata that is tied to an audio file must remain with it." **Flagged before recording:** this conflicted with `INSTRUCTIONS.md` §2 rule 3 ("nothing is ever deleted... only empty folders may be removed"), so I asked for explicit confirmation rather than assume an override.

**Resolved (Jeremy, 2026-10-01):** no override — the no-delete rule stands. Non-audio files, and files not relating to any audio file, are **moved to a review folder**, not deleted. So:
- "Music" for the accounting rule = **audio files**, detected by content (consistent with the extension-repair stage's content-based detection, C1).
- Art and any other metadata/sidecar files that belong to a specific track **travel with that track** (not counted/moved separately, not sent to the review folder).
- Anything else non-audio (not tied to any track) is moved to a review folder — name/location not yet specified; needs a decision before `plan/02-pipeline.md` (e.g. a root `_REVIEW_` or `_NON_MUSIC` folder, mirroring structure like `_SAMPLES`/`_DUPLICATES` do).

### Decision 8: Name-normalization rules

**Answered (Jeremy, 2026-10-01):** "do not add anything to the name, only remove special characters and get the original name either from the meta or other tags. The idea is to get the original name for each track and repair it to original state." This is narrower and more conservative than `reassign`'s existing transforms:
- **No additions** — no track-number prefixes, no BPM/key/duration suffixes, nothing appended or inserted. This rejects the part of `reassign`'s behavior that adds/reformats beyond what's already there.
- **Source of truth for the name is the track's own metadata/tags** (Title, or other tags), not an invented or guessed name — the goal is restoring the track's **original** name, not creating a new one.
- **Only special characters are removed** from the result.
- **Resolved (Jeremy, 2026-10-01):** a "special character" is **any character that is not part of the original file/track name** — determined by cross-checking against the track's own metadata (Title, Filename tag, or anywhere else in its tags). If the original name can't be determined that way, the fallback is to **strip all leading characters that don't appear anywhere in the Title, Filename, or other metadata**. This directly avoids `INSTRUCTIONS.md` **C7**'s problem with `reassign`'s normalizer (blind stripping of all parentheses / leading digits-hyphens, which mangles real titles like "99 Luftballons"): under this rule, a leading "99" in "99 Luftballons" would **not** be stripped, because "99" is presumably still part of the Title tag — only characters genuinely absent from the track's own metadata (e.g. a download-site prefix, a stray "_copy", bracketed junk not found in any tag) get removed.

### Decision 6: taglib-sharp requirement level

**Answered (Jeremy, 2026-10-01):** "that is why I provided the tag tool" — taglib-sharp is **required**, not optional or cross-check-only. Jeremy supplied it specifically to handle tag reads/writes correctly, which is also the mechanism for satisfying Decision 5 above (retaining Serato/rekordbox metadata and art untouched) — the concern is that a library unaware of those vendor-specific frames could silently drop them when writing other tags.

**Checked (2026-10-01):** ran `python --version` (3.14.7) and `pip show pythonnet` (not installed, exits non-zero); fetched PyPI's JSON metadata for `pythonnet` — latest release 3.2.0 lists Python 3.11–3.15 support (`requires_python: <3.16,>=3.11`), which covers 3.14.7. So `pythonnet` is **expected to install and work**, resolving the "unverified Python 3.14 support" concern from `INSTRUCTIONS.md` §3 — but it is **not yet installed or runtime-tested** (importing `clr` and actually loading `taglib-sharp.dll` hasn't been tried). That remaining step is implementation work, not a open decision for Jeremy.

**Fully verified (2026-10-01), Decision 6 now closed:** installed `pythonnet` (succeeded). `clr.AddReference(r"C:\Users\Jeremy\Scripts\lib\taglib-sharp.dll")` then `import TagLib` **failed** under the default runtime — `System.IO.FileLoadException`/`NotSupportedException`, because the DLL carries a Windows `Zone.Identifier` (marked as downloaded from the internet) and the legacy .NET Framework runtime pythonnet loads by default on Windows refuses to load it. Running `Unblock-File` on the DLL was tried (with Jeremy's OK) but got `Access to the path ... is denied`. **Working fix, no file modification needed:** call `pythonnet.load("coreclr")` before `import clr` — this loads the CoreCLR runtime instead of .NET Framework/Mono, and `clr.AddReference(...)` + `import TagLib` then succeeds (`TagLib.File` class loads). This is the approach to use in the app: `from pythonnet import load; load("coreclr"); import clr; clr.AddReference(...)`.

### Decision 11: Menu format and interaction style

The app's menu and interaction style follow `simpleDupe.py` (see `INSTRUCTIONS.md` §4.1), not a new design:

- Numbered/lettered menu, one screen, one choice at a time.
- A preview/dry-run step before any destructive or changing action, with Jeremy confirming before execute (the "way it works" in `simpleDupe.py`: preview → confirm → execute → log).
- Renames, moves and tag edits each require confirmation and are logged with old and new values (already a non-negotiable rule in `INSTRUCTIONS.md` §2.5; this decision extends the same pattern to the whole merged app's menu, not just to those three actions).

Answered: the menu is renumbered to reflect the stage order in `INSTRUCTIONS.md` §7, not `simpleDupe.py`'s original numbering. Extension repair must be the first menu item/stage, ahead of ghost-folder cleanup, samples and duplicates. Reason (Jeremy, 2026-10-01): extension repair must run before any stage that selects files by extension, or there are no files to compare — a mislabeled file is invisible to extension-based scanning until its real type is detected (this is `INSTRUCTIONS.md` C1, §5). This matches the proposed stage order in §7, where extension repair (step 4) precedes samples (step 5) and duplicates (step 6).

Ghost-folder cleanup (simpleDupe's item 0) comes first, before extension repair (Jeremy, 2026-10-01). It does not depend on extensions, so this ordering does not conflict with the extension-repair-first rule above. Order so far: 1) ghost-folder cleanup, 2) extension repair, 3) samples, 4) duplicates.

Note (Jeremy, 2026-10-01): a folder that *appears* empty in Windows Explorer is often not actually empty — Explorer's view settings (hidden/system files not shown) are frequently the cause. The ghost-folder/empty-folder check must not trust what Explorer displays; it must enumerate every directory entry itself (including hidden and system files) before deciding a folder is empty enough to remove with `os.rmdir`.

Note (Jeremy, 2026-10-01): running a Windows Explorer search with `kind:music` on a folder surfaces files that don't otherwise appear there (i.e. Explorer's `kind:music` filter uses content/property-based detection, not extension) — switching that search to Details view with music tag columns shown makes it easier to read. Jeremy, 2026-10-01: leverage `kind:music` in the app **if technically feasible**; if not, disregard that part. Either way, Jeremy wants the default view for every folder and subfolder the app examines to be Details view with music-related tag columns shown.

- **Not yet verified:** whether `kind:music` can be run from Python at all. In Explorer this is a Windows Search Index query (the "Kind" property, `System.Kind`). Reusing it from the app would mean querying the Windows Search index (e.g. an ADO/OLE DB query against the `Search.CollatorDSO` provider, or the `search-ms:` protocol), which is a different mechanism from reading file contents directly with mutagen. This must be confirmed as possible (and that the index is present/current on this machine) before it is adopted — not assumed. If it can't be done, the app's own content-based detection (mutagen class → type, per `reassign`'s approach, C1) is the fallback, which already does not depend on the Windows Search index or on extensions.
- Setting a folder's default view to Details with specific columns is normally an Explorer/registry-level setting (e.g. via a folder's `desktop.ini` `[ViewState]`/`PersistMoniker` state, or `IColumnManager`), not something mutagen or plain file I/O controls. **Resolved (Jeremy, 2026-10-01):** out of scope for the app. Jeremy will set the Details view with music tag columns himself in Explorer. The app does not write `desktop.ini` for view state, so there is no conflict with ghost-cleanup archiving `desktop.ini`.

Confirmed (Jeremy, 2026-10-01): viewing tags in the Details view he set up is genuinely helping him review files. This is supporting evidence for keeping tag-based signals (not just filenames/duration) central to sample and duplicate review, and reinforces that the app's own logs/previews should surface the same kind of tag detail for the files it flags (still open, tied to the unanswered report-format question above).

### Decision 12: Validation step is kept

The validation step from `simpleDupe.py` is kept in the merged app, as described in `INSTRUCTIONS.md` §4.1:

- 20 or more runs of 20 random files from `_DUPLICATES`, each run checking that an equal-or-better copy remains in the library.
- Repair (swap or restore) is offered only when a run fails.
- This maps to stage 8, "Validate and repair loop," in the proposed stage order (`INSTRUCTIONS.md` §7).

Note (Jeremy, 2026-10-01), relevant to open Decision 9 (rollback): everything can be undone manually by Jeremy as long as files are only moved, never deleted — consistent with `INSTRUCTIONS.md` §2.3 ("nothing is ever deleted... files are moved or copied"). This lowers the bar for automated rollback tooling: a move is reversible by Jeremy moving the file back, provided its original path is known (the per-file log of old/new values, already required by §2.5, is what makes that possible). Decision 9 itself (what "rollback" means in practice) is still open.

### Decision 13: Sample detection — Jeremy supplied a PowerShell script (2026-10-01), conflict not yet resolved

Jeremy supplied a working PowerShell script that classifies files as samples/tracks by (a) duration via the Windows Shell COM `Details` column, and (b) a name-keyword regex list (loop, oneshot, stab, pad, arp, lead, kick, snare, perc, 808, fx, rise, impact, vox, vocal, chop, dry, wet, bpm, key names, melody, "top loop", kit, pack). He asked to use it, improve it, and incorporate it.

**This conflicts with the sample-detection spec already recorded from `simpleDupe.py` in `INSTRUCTIONS.md` §4.1:**

| | simpleDupe.py (existing spec) | Jeremy's new script |
|---|---|---|
| ≤ a short cutoff | ≤30s = sample, always, regardless of tags/name | <45s = sample if duration signal OR name matches a keyword |
| middle range | 30–60s: **scored**, threshold 6, needs ≥1 of name/folder/tag-text/file-content signal | 45–59s: only classified if a name keyword matches; otherwise neither bucket |
| long cutoff | >60s: never a sample | ≥60s: track, unconditionally (even if the name matches a sample keyword) |
| method | weighted multi-signal score (not just name) | boolean OR over a name-keyword list, plus duration |
| decisions memory | remembered by hash in `_decisions.json` | none (script just prints two lists) |

I have **not** merged these into one rule — doing so silently would be drift. A Python port of Jeremy's script exists for review at `plan/sample_detection_prototype.py` (classification/logging only, no file moves, duration read with `mutagen` instead of the Windows Shell COM object since the app is Python-only per `INSTRUCTIONS.md` §2.8 and `mutagen` is already verified installed). **Open question for Jeremy:** should the final rule be (a) Jeremy's thresholds/keyword-list replacing simpleDupe's scored system entirely, (b) the keyword list added as one more signal inside simpleDupe's existing scored system (keeping the 30/60 cutoffs and the `_decisions.json` memory), or (c) something else? Needs an answer before this stage is implemented or added to `plan/02-pipeline.md`.

Answered (Jeremy, 2026-10-01): "do our absolute best on samples" — resolves the method question toward **(b)/merge**, not a straight replacement: use every available signal (duration cutoffs, the name-keyword list, and simpleDupe's existing folder/tag-text/file-content signals) rather than discarding any of them, since over-flagging a sample is low-cost — it only causes a move, which Jeremy can undo manually (previous note, this file). This is a direction, not a finished spec. Note (Jeremy, 2026-10-01): samples typically have most tags missing compared to full songs. This lines up with simpleDupe's existing scored system, where "total tags" is already one of its signals (`INSTRUCTIONS.md` §4.1, keeper scoring: art → 7 key fields → total tags) — low/missing tag count should count as a signal *toward* "sample," not just a duplicate-keeper signal. This is a new input for the merged scoring, not yet wired into `plan/sample_detection_prototype.py`.

Note (Jeremy, 2026-10-01): the Album a sample belongs to is often named "Pack," "Samples" or "Loops." This is an **Album-tag-text** signal, distinct from the filename-keyword list: `plan/sample_detection_prototype.py`'s keyword list already has "pack" and "loop" but not "sample(s)," "loops" (plural) or "packs" (plural), and none of the keywords are currently checked against the Album tag specifically — only the filename. These gaps need to be fixed before this is wired in: add "sample(s)," "loops" and "packs" to the keyword set, and check Album tag text in addition to filename (simpleDupe's existing "tag-text" signal in its scored system already covers tag text generally, per §4.1).

Note (Jeremy, 2026-10-01): sample filenames within a pack almost always match each other except for minor differences in Key or BPM (e.g. the same sample at different tempos/keys, named near-identically). **This is a caution for duplicate detection, not just sample detection** — it directly touches `INSTRUCTIONS.md` C6 (fuzzy name matching merges different recordings that share a name) and C7 (reassign's normalizer strips BPM/key/parenthetical suffixes). Files that differ only in Key or BPM are **different samples, not duplicates of each other**, even though fuzzy/normalized name matching would treat them as the same. Any merged duplicate-detection logic must not let BPM/Key-stripped name matching alone call these duplicates.

Note (Jeremy, 2026-10-01): additional signals for sample detection —
- Duration too short to be a track (reaffirms the existing duration cutoff signal, no new threshold given).
- Genre tag is often missing on samples — another "missing tag" signal, alongside total tag count (previous note, this file). Jeremy also noted (2026-10-01) genre is *sometimes* present on samples too, so a missing Genre is a weak/contributing signal, not a rule that decides "sample" on its own.
- Filenames/tags containing "one shot(s)" also indicate a sample — `plan/sample_detection_prototype.py`'s keyword list has "oneshot" and "one-shot" but not the spaced form "one shot(s)"; needs adding.

Note (Jeremy, 2026-10-01): confirms the detection approach is a **holistic score across all factors** — duration, name/tag keywords, Album tag text, missing-tag count (including missing Genre), not any single factor deciding "sample" by itself. This supports simpleDupe's existing scored/threshold model (§4.1) over a hard boolean OR rule, and is additional direction for the "still open" questions below, though the exact threshold/weights remain unanswered.

Note (Jeremy, 2026-10-01): instrument names generally (e.g. "snare") are a sample-name signal, not just the specific instrument words already listed. `plan/sample_detection_prototype.py`'s keyword list currently only has "kick," "snare" and "perc" — this is Jeremy flagging that the category should be instrument names broadly (hi-hat, clap, cymbal, tom, bass, guitar, piano, synth, etc.), not a fixed short list. **Exact final word list is still open** — needs Jeremy's review before it's final, so this isn't a complete list to implement yet.

**Still open, needed before `plan/02-pipeline.md`:**
- Exact thresholds: keep simpleDupe's 30/60s cutoffs, Jeremy's 45/60s cutoffs, or a new combined set? **Answered (Jeremy, 2026-10-01):** <30s is **not absolute** — this changes `INSTRUCTIONS.md` §4.1's existing rule, where ≤30s is always a sample "regardless of tags." A <30s file can be overridden back to "track" when several countervailing signals are present together: it belongs to an album that is obviously a real album (not a pack/samples/loops album, per the earlier Album-tag note), it is plausibly a track "intro," its name has no Key in it, its name has no instrument name in it, and it does not match several other same-named files (i.e. it isn't one of a cluster of similarly-named short variants, the way pack samples are).
- **Answered (Jeremy, 2026-10-01):** the "all vs. several conditions" question is resolved as a **confidence score**, not a condition count: combine all available signals (duration, keyword/instrument-name matches, Album tag text, missing-tag count including Genre, matching several same-named files, etc.) into a single confidence percentage, and classify as "sample" at **75% confidence or higher**. Below 75%, classify as "track" (subject to review, since mistakes are low-cost and reversible, per the earlier notes). This replaces simpleDupe's hard threshold-6 point score and Jeremy's script's boolean-OR rule, and applies holistically across the whole duration range, not only the 30–60s middle band.
- **Draft weight table proposed for discussion (2026-10-01), then revised by Jeremy:**

  | Signal | Points |
  |---|---|
  | Duration < 30s | +40 |
  | Filename/tag keyword match, per distinct category, max +30 | +15 each |
  | Instrument name in filename | +15 |
  | Album tag contains pack/samples/loops | +20 |
  | Missing-tag count (scaled), up to | +15 |
  | Missing Genre specifically | +5 |
  | Matches several same-named files differing only by Key/BPM | +15 |
  | Belongs to an obviously real (non-pack) album | −20 |
  | Plausible track "intro" | −15 |
  | No Key in name | −10 |
  | No instrument name in name | −10 |
  | Not part of a same-name cluster | −10 |

  **Jeremy, 2026-10-01: removed the "30–60s" (+10) and "≥60s" (−100) rows.** Duration now only ever contributes via the single <30s bonus; 30s and above, duration contributes **nothing** (neither bonus nor penalty) and classification rests entirely on the non-duration signals. **This is a material change from `INSTRUCTIONS.md` §4.1's existing spec**, where simpleDupe treats >60s as *never* a sample — removing the −100 row means a long file could in principle still reach 75% through other signals alone (e.g. strong keywords + pack album + missing tags + same-name cluster). **Flagging for explicit confirmation, not assuming:** is it intentional that a long (e.g. several-minute) file could now be classified as a sample if its name/album/tag signals are strong enough, with no duration-based ceiling at all?
  Jeremy, 2026-10-01, on the worked example scored exactly 75% (`Lead_Cmin_128bpm.wav`, Album "Synth Loops Pack"): confirmed as "clearly a sample" — the 75%-or-higher cutoff correctly classifies it as a sample; no reweighting of the other rows was requested.

Jeremy, 2026-10-01, supplied a full PowerShell implementation of the weight table (keywords: loop, stab, 808, bpm, key, "one shot", oneshot, shot, melody, kit, pack, "top loop"; instruments: kick, snare, clap, hihat, perc, 808, tom, rim; a cluster-detector that strips BPM/key suffixes from the base filename to group same-sample variants). **Conflicts with the two immediately preceding answers, not yet resolved:**
- It brings back `Duration30to60 = 10` and `DurationOver60 = -100`, which Jeremy had just said to remove ("remove the second and third duration factors. under 30 is all you need").
- It classifies by **raw point total**, not the agreed 75%-confidence percentage: `score >= 40` is "sample," `score <= 0` is "track," and anything in between is a new third bucket, "ambiguous" — this is a different (three-way) classification model than the binary 75%-cutoff rule agreed immediately above.
- It reads duration and tags via the Windows Shell COM object (`$shell.Namespace(...).GetDetailsOf(...)`), the same mechanism as Jeremy's very first script. The sample-detection prototype already in this repo (`plan/sample_detection_prototype.py`) was deliberately changed to use `mutagen` instead, since the app is Python-only (`INSTRUCTIONS.md` §2.8) and doesn't need a COM/Explorer dependency. Not yet confirmed whether Jeremy wants COM kept here specifically or ported to `mutagen` like the rest.
- **Asked Jeremy, not yet answered:** which duration-tier rule stands (just removed, or restored), whether to keep a three-way sample/track/ambiguous split instead of the binary 75% rule, and whether to port tag/duration reads to `mutagen`.

**Resolved (Jeremy, 2026-10-01):** "disregard my comment and use the [rating system] that I just gave you" / "don't combine them." The PowerShell script's rating system is authoritative **as given**, replacing (not merged with) the earlier 75%-confidence model:
- `Duration30to60 = 10` and `DurationOver60 = -100` are **restored** — the earlier "remove them, under 30 is all you need" instruction is superseded.
- Classification is the script's **raw point total with a three-way split**: `score >= 40` → sample, `score <= 0` → track, anything in between → **ambiguous** (a third bucket, for Jeremy's own review). This replaces the 75%-confidence-percentage rule.
- The earlier 75% model and its worked examples (in this file, above) are superseded for this stage — kept in this file only as history of how we got here, not as the current rule.
- **Resolved (Jeremy, 2026-10-01):** sample-detection duration and tag reads use `mutagen`, not Windows Shell COM. This keeps the implementation Python-only and follows `plan/sample_detection_prototype.py`; the PowerShell script remains authoritative for the rating system itself.

Note (Jeremy, 2026-10-01): when an entire folder contains **multiple** files that each fit the sample criteria, the whole folder should be moved as a unit, not decided file-by-file — Jeremy's reasoning: this helps with "individual rating," i.e. folder-level agreement is a more reliable signal than any one file's score, and moving as a unit is also fewer decisions to make/review than scoring every file independently. **Answered (Jeremy, 2026-10-01):**
- Threshold: **over 90%** of a folder's files scoring as "sample" (per the script's `score >= 40` rule, now that the raw-score system is authoritative) triggers moving the entire folder, including any files in it that individually scored below that line.
- Destination: the whole folder moves into `_SAMPLES` as a unit (mirroring the structure simpleDupe's existing single-file moves already use, per `INSTRUCTIONS.md` §4.1).
- Jeremy will review/sort out any individually-misclassified files within a moved folder himself afterward ("I can deal with it from there") — consistent with the earlier "moves are reversible, low-cost to over-flag" notes in this file.
- Confirmed (Jeremy, 2026-10-01): the whole-folder-move rule is **the only rule added on top of** the script's rating system — everything else about per-file scoring is exactly as given in the script (resolved above), nothing further is layered on.

Superseded by the script's rating system (resolved above), kept here only as history: the two "still open" questions that used to follow this point — how a keyword match plugs into scoring, and whether ≥60s is an absolute veto — are both answered directly by the script: a keyword match adds a fixed `KeywordMatch` point value (not a hard override), and `DurationOver60 = -100` is a heavy penalty within the raw-point total, not a separate absolute rule.

**Resolved (Jeremy, 2026-10-01) — disposition of the "ambiguous" bucket:** "when in doubt, move it and I will review it" — ambiguous-scoring files (`0 < score < 40`) are **moved to `_SAMPLES` along with the "sample" bucket**, not left in the library/track output. Jeremy's stated reason: a past run left "a bunch of short tracks in the final result," which he called "an obvious mistake" — i.e. leaving ambiguous/borderline short files behind in the library is the failure mode to avoid, not over-moving to `_SAMPLES` (consistent with the repeated theme in this file: moves are cheap/reversible, leaving true samples in the library is the costly mistake). Net effect: of the three buckets, only `track` (`score <= 0`) stays in the library; both `sample` and `ambiguous` go to `_SAMPLES`.

Note (Jeremy, 2026-10-01): the exact override formula (all conditions vs. "several") doesn't need to be perfect — Jeremy will review files after they're moved to `_SAMPLES` (consistent with the earlier note: moves are reversible, so mistakes are low-cost). **Performance requirement:** do not hash every sample file. Hashing (MD5, per simpleDupe's duplicate matching, §4.1) is for the **duplicate-detection stage**, not sample classification — classification should only use cheap checks (duration via `mutagen`, filename/tag-text keywords, tag presence/count), never a full-file hash, since hashing thousands of sample files would be slow and wasted work. If a hash is later needed (e.g. a sample also turns out to be an exact duplicate), simpleDupe's existing hash cache (`_hash_cache.json`, keyed by size + mtime-ns, §4.1) already avoids recomputing it.

**Final signal list (Jeremy, 2026-10-01): "don't spend too much energy on this"** — the complete, final set of signals to use, no further tuning needed beyond implementing these:
- Length (duration)
- Name (keywords)
- Missing tags
- Neighboring file names (the cluster check)
- **Parent folder name** — new: not just the Album tag, the folder name itself should be checked for pack/sample/loop-style words. Not yet in `plan/sample_detection_prototype.py` (which currently only checks the Album tag); needs adding.
- Music keys present in the name
- Names that are instruments
- Names containing "Loops," "Package," "Tools," "Samples," "Shots" — `plan/sample_detection_prototype.py`'s `KEYWORDS` list has "loop," "pack," "shot," "oneshot" but not "package," "tools," or "sample(s)"; needs adding.
- File names in the dozens or more that are almost identical in the same directory (reinforces the existing cluster check and the >90% whole-folder-move rule; emphasizes it should hold at larger scale, not just 2–3 files).

**Resolved (Jeremy, 2026-10-01):** `plan/sample_detection_prototype.py` (the Python conversion of Jeremy's PowerShell rating script, now including the parent-folder-name check and the expanded keyword/instrument lists) is **the authoritative reference** for the sample-detection stage going forward — "use the code... as the best guide." When `plan/02-pipeline.md`/`plan/04-architecture.md` specify this stage, they should match this file; the narrative notes above remain in this file only as the history of how each part was decided, not as independent specs to reconcile separately.