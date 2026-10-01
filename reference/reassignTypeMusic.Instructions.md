Apply this workflow to root-level files in the folder selected in the menu. Do not process subfolders.

Use these folders: `_COPIES_` for filename collisions, `_FILTERED_` for confirmed same-track losers, `_REVIEW_` for uncertain matches and byte-identical extras, and `_SNAPSHOTS_` for the initial rollback copy. Never overwrite or permanently delete a file.

Before the first Execute stage, the app snapshots root files and current archive contents once under `_SNAPSHOTS_`; it reuses this snapshot for the rest of that workflow. It cancels the first Execute if a complete snapshot cannot be created or there is insufficient free space.

The tracked total is root-level files plus files in `_COPIES_`, `_FILTERED_`, and `_REVIEW_`. `_SNAPSHOTS_` is excluded because it contains rollback copies. Moving a file between the root and an archive changes the cleaned/root count, but must not change the tracked total.

Menu options and progress ticks are color-coded by stage. Execute shows a single updating `Working... percent` line, without filenames. Each dry run ends with `Total files changed` and `Total files`. After each completed stage, the validation ledger shows before/after root-file counts, audio counts, and the destination archive count; each equation should reconcile before continuing.

## 1. Repair Extensions

Determine each file's audio type from its contents. Add or correct the extension only when the type is recognized. Leave non-audio sidecars and unrecognized files unchanged and report them. If a corrected filename already exists, move the source to `_COPIES_`.

## 2. Review Same-Track Candidates

1. Build temporary comparison values from the `Name`, `Filename`, and `Title` fields. For comparison only, ignore case and harmless punctuation, and remove clearly identifiable track-number prefixes or trailing BPM/key/duration/`Copy` text. Do not edit tags or filenames yet.
2. Treat matching values as candidates, not proof. Compare Artist, duration, and other available details. If fields conflict or the match is uncertain, move the candidate to `_REVIEW_`.
3. Among confirmed matches, keep the file with the most complete useful metadata: Title, Artist, Album, Genre, year, and track number. Use duration and bit rate as supporting details; ignore Serato/rekordbox analysis data when scoring completeness. If tied, keep either.
4. Move confirmed losing files unchanged to `_FILTERED_`. Do not rename files during this stage.

## 3. Remove Exact Copies

1. Hash the audio files still in the selected folder's root after same-track review.
2. Identical hashes mean byte-for-byte copies. Different tags or encodings produce different hashes.
3. Keep one file from each exact-hash group and move the extras unchanged to `_REVIEW_`. Exact copies have identical tags, so metadata-completeness scoring is unnecessary. Do not rename files during this stage.

## 4. Normalize Remaining Names

1. Normalize only the files that remain after both duplicate stages. Use a meaningful Title as the canonical name; if Title is blank, use the filename stem.
2. Remove only clearly identifiable track-number prefixes, parentheses characters, trailing BPM/key/duration text, and trailing `Copy` markers. Preserve meaningful words, numbers, and punctuation. If the intended name is unclear, leave it unchanged for review.
3. Set Title to the canonical name. If a separate Name field exists, make it agree. Update an embedded Filename field only if it exists.
4. Set the filesystem filename to the canonical name plus the extension confirmed from file contents. If that target exists, move the source to `_COPIES_` rather than overwrite it.
5. After all tag and filename changes, compute fresh hashes and check for byte-identical files. Hashes from before tag edits are not comparable because tag edits change file contents.

## Examples

- Keep `Rock da Beat.flac` with Title `Rock Da Beat` if its metadata is best. If `Rock da Beat 110 Am 1m28s.flac` is confirmed to be the same recording, move it unchanged to `_FILTERED_`.
- Keep `T-Shirt.flac` if it is the best-tagged version. Move `T-Shirt 90 Gm 1m30s.flac` unchanged to `_FILTERED_` only after confirming it is the same recording.
- Keep `Herman's Hustle.wav` over the misspelled or analysis-suffixed variants if it is the same recording and has the best metadata. If Title is blank, write `Herman's Hustle` during final normalization.
- If `Black Mona Lisa - Copy.mp3` is the best version, normalize it to `Black Mona Lisa.mp3` and set Title to `Black Mona Lisa`. Move the BPM/key/duration variant unchanged to `_FILTERED_` only after confirming it is the same recording.