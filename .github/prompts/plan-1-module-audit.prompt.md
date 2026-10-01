---
description: "Planning step 1: produce a factual, line-referenced behavior audit of the three reference modules into plan/01-module-audit.md."
agent: agent
---
Audit [simpleDupe.py](../../reference/simpleDupe.py), [reassignTypeMusic.py](../../reference/reassignTypeMusic.py), its spec [reassignTypeMusic.Instructions.md](../../reference/reassignTypeMusic.Instructions.md) and [ghostVSEmptyFolders.ps1](../../reference/ghostVSEmptyFolders.ps1). Read-only.

Write `plan/01-module-audit.md` with, per module:
- Every user-reachable operation (menu option → function → line numbers).
- For each: inputs, which files it selects (by extension? by content? recursive or root-only?), what it reads, what it writes or moves, destination folders, logs, confirmations, and failure handling.
- Exact rules and constants (thresholds, regexes, scoring order) quoted from the code.
- Code that is unreachable or never called (it is not specification).
- Places where the code and its written spec disagree.
- Anything destructive (delete, overwrite, tag write, extension change).

Rules: every statement cites file and line. If you cannot confirm a behavior from the code, mark it UNVERIFIED and do not guess. Do not propose design here.
