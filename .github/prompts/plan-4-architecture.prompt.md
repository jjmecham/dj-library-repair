---
description: "Planning step 4: design the app architecture (packages, reuse vs rewrite, tag-library strategy, menu) into plan/04-architecture.md."
agent: agent
---
Inputs: [INSTRUCTIONS.md](../../INSTRUCTIONS.md), `plan/00`–`plan/03`.

Before designing the tag layer, verify by running commands (read-only):
- Whether `pythonnet` can be installed for the installed Python version. If it can't, say so and do not assume.
- Whether `C:\Users\Jeremy\Scripts\lib\taglib-sharp.dll` loads, and which .NET runtime it targets.
- What mutagen and taglib-sharp each return for the same sample files: ID3, MP4, FLAC, and WAV with RIFF INFO.
Report the evidence. Choose per decision 6.

Write `plan/04-architecture.md`:
1. **Package layout:** one module per pipeline stage, plus shared core modules (manifest, logging, tags, hashing, file operations, UI).
2. **Reuse table:** for each function taken from `reference/`, say whether it is kept as-is, adapted (and why), or rewritten (and why). Cite lines.
3. **One file-operation layer:** every move, copy, rename, rmdir and tag write goes through it, and it enforces the rules: no overwrite, no delete, extension guard, logging, verification after the action.
4. **Menu flow:** stages run in the approved order. Each stage has a dry run and an execute, and later stages are gated until the earlier ones succeed. Use the existing color palette from `reference/simpleDupe.py` (lines with `rgb(`) and the single-line progress counter.
5. **Configuration:** paths and thresholds in one place, with the values Jeremy approved.
6. **Dependencies** with exact versions.

Nothing beyond what the pipeline requires. Open points go to Jeremy.
