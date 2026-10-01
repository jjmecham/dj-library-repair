---
description: "Planning step 3: define accounting invariants, manifest schema, rollback and failure handling into plan/03-safety-and-accounting.md."
agent: agent
---
Inputs: [INSTRUCTIONS.md](../../INSTRUCTIONS.md) sections 2 and 8, `plan/00-decisions.md`, `plan/02-pipeline.md`.

Write `plan/03-safety-and-accounting.md`:
1. **Manifest:** the schema of the per-file inventory taken in preflight (path, size, mtime_ns, content-detected type, hash algorithm and value). Explain how a file is tracked through moves, renames and tag edits; tag edits change the hash, so record both pre- and post-edit hashes.
2. **Invariants per stage:** count and identity checks that must hold before and after, written as equations. Define exactly what counts as "music" per decision 7.
3. **Rollback:** what the snapshot or working copy is, when it is taken, how it is verified (hash every file), how rollback is performed without deleting anything, and the disk space required, computed from the verified sizes.
4. **Failure modes and responses:** for each of these, the detection and the exact app response:
   - interrupted run
   - locked file
   - path too long (over 260 characters)
   - destination exists
   - unreadable tags
   - disk full
   - file changed since the scan
   - junction
5. **Log formats:** one schema covering every action type, with no blank status.

Every operation must be non-destructive. Flag anything in the reference code that violates this (cite lines). Questions go to Jeremy, not to defaults.
