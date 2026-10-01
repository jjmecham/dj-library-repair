# Music Repair App — always-on rules

Read `INSTRUCTIONS.md` before any work. `plan/00-decisions.md` holds Jeremy's decisions; it overrides drafts.

- No assumptions, drift or invented behavior. Every claim must come from Jeremy's words, code you read (cite file + line), or a command you ran. If unsure, ask Jeremy; do not pick a default.
- Planning phase: do not write application code until Jeremy approves the plan in `plan/`.
- `reference/` files are read-only specifications. Never edit them.
- The source music folder is read-only. Never delete files. Never overwrite. Only empty folders may be removed, via `os.rmdir`.
- Extensions change only in the content-verified extension-repair stage.
- Renames, move batches and tag edits require confirmation and are logged with old and new values.
- Every stage must balance its file accounting; a failed invariant stops the workflow.
- Python only. Tags must include Windows-visible tags (WAV RIFF INFO). taglib-sharp (`C:\Users\Jeremy\Scripts\lib`) is a .NET DLL; its use depends on decision 6.
- When stating results, report what was verified and what was not.
