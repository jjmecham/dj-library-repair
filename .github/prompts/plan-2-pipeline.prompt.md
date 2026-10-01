---
description: "Planning step 2: derive and prove the stage order of the repair pipeline into plan/02-pipeline.md."
agent: agent
---
Inputs: [INSTRUCTIONS.md](../../INSTRUCTIONS.md), `plan/00-decisions.md`, `plan/01-module-audit.md`. Stop and say so if 00 or 01 is missing.

Write `plan/02-pipeline.md`:
1. A stage table: stage, source module and function it reuses (or "new"), input set, output set, folders written, logs written, confirmation required.
2. For every ordering constraint, a dependency proof: "Stage X must precede Y because Y selects files by <criterion> that X changes" (cite audit lines). Use the conflicts in INSTRUCTIONS.md section 5.
3. Show what goes wrong if adjacent stages are swapped.
4. Show where each stage's results become stale (for example, tag edits change hashes; moves change folder emptiness) and which later stage must re-check them.
5. Map every Jeremy requirement to the stage that satisfies it, and every stage to the requirement or decision that justifies it. A stage with no justification is removed.

Do not add features Jeremy did not ask for. List anything you could not prove as an open question for Jeremy.
