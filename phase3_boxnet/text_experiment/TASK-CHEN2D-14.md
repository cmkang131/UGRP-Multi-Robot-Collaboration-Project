# TASK-CHEN2D-14: defects found by the independent review and by the first real multi-step runs (2026-11-24)

Context: tasks 1 to 13 are done. Same hard limits (this folder only, no network, fake model for tests, no real-model batches, nothing under `20261123-phase3/`). Default behaviour of the authors' frameworks at horizon 1 must stay byte for byte. Read first: the independent review `<work>/20261123-plan3/review-neon/REPORT-NEON-1.md` sections B1 to B3 (it cites the exact episodes and code lines), and your own task 13. Where task 13 already fixed an item, say so and add only the missing test.

## G1. Multi-step replies of CMAS and DMAS (lenient mode)
- A reply keyed by step numbers, e.g. `{"1": {...}, "2": {...}}` or `{"step 1": {...}, ...}`, is today wrapped as ONE joint plan, the keys are taken for agent names and the episode ends with Syntactic Error after six misleading feedbacks (real case: `../20261124-chen2d-snap-v12/runs/v12-h5-2048/episodes/4x4_CMAS_static_env3/calls/`). Accept it as the list of plans in key order. Never treat a key that is not an agent name as an agent: such a reply is a format error with feedback that says so.
- DMAS with H > 1: `discuss()` replaces the stored turn whenever a reply contains "EXECUTE", even without a usable plan, so a valid plan from an earlier row is lost; and later rows answer `EXECUTE [{}]` because they read the earlier EXECUTE in the dialogue as already executed (real cases: `v12-h5-8192/episodes/4x4_DMAS_static_env1` and `env3`: 6 of 13 and 5 of 12 rounds empty). Keep the authors' loop for H = 1 untouched. For H > 1: (a) replace the stored plan only when the new reply contains a parsable plan (as the authors' H = 1 path does with `if match:`); (b) an all-empty list from a later speaker does not replace a non-empty plan of the same round; record how often (a) and (b) applied. State both as rules of our multi-step extension.

## G2. OWN (complete what task 13 started)
- Parsing, lenient mode: also accept the strings "null", "None", "none", "" and "wait" as null; a bare `null` or `[]` as all nulls; whitespace variants inside `move( … , … )`; Python-style single-quoted lists; trailing commas; an object element such as `{"action": "move(...)"}`. A format error in entry 2..H must not discard a usable entry 1: keep the entries up to the first unusable one and null the rest; record it.
- Repair budget: per robot, not shared by the round (two repair prompts per robot per round; a robot still unusable afterwards is dropped for the round as in task 13). Robots that have nothing doable and no box can reach them within H steps need not be repaired at all: an unusable reply from such a robot counts as nulls.
- Instruction: add ONE concrete example line of the expected list (same style as the authors' examples for joint plans), and state that null is the JSON literal, not a string.
- What later robots see: only lists that passed the first-entry doable check; a robot whose list was refused or dropped is shown as `null`. During repairs a robot sees the same peer lists it saw on its first turn (no extra information from robots that spoke after it).
- Report these as rules of OWN with the reason for each.

## G3. `--state-position after` with an announcement (conditions e1/e2)
The announcement must move together with the current-state block, and relay insertion must still land directly before the current-state block. Static prompts stay byte-identical to task 12.

## G4. Tests and report
One fake-model test per bullet above, using the real replies quoted in the review as fixtures where they exist. Replay tests: horizon-1 default episodes of CMAS and DMAS byte for byte; the static `--state-position after` prompt byte for byte against task 12. Append "CHEN2D-14" to `REPORT-CHEN2D.md` with a table "defect, real example, fix, test". Last step: create `review/ASTRA-CHEN2D-14.done`.
