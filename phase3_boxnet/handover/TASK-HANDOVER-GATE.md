# TASK-HANDOVER-GATE: a two-robot hand-over test in MuJoCo (2026-11-25)

## Why
The user decided (2026-11-25 02:00 to 02:01 KST, verbatim): "흠; 걍 각자 하나의 방을 가지면 안되나?", "그러고 문 주변에 두면
서로 넘길 수 있고, 자기 방에 QR이 있어서 목적지가 있는 느낌으로다가", "사실상 BoxNet처럼 가는 거 어떄?", "실제 시뮬이랑
sim2real도 그 방향으로 가게". The task of the whole project becomes BoxNet-like: every robot stays in its own room, boxes
are handed over at a place near the door between two rooms, every room has a QR sign as destination, and the same
layout must later be built with the real robots. Design: `../20261123-plan3/debate/DESIGN-20261125.md` (DRAFT 3 at the
end). Your own reviews: `../20261123-plan3/debate/R16-ASTRA-extracted.md`, `R17-ASTRA-extracted.md` (Q2 and Q3 give the
geometry and the size of this task), `R18-ASTRA-extracted.md` (Q2 to Q4).
Nothing else is built before ONE thing is known: can a robot pick up, from its own room, a box that the robot of the
neighbouring room has put down near the door, and carry it to its room's sign? This task builds the smallest test
that answers it. It does NOT build the three-room scene, the planner adapter or any LLM part.

## Hard limits
- Work only under `20261123-phase3/` : new files in a new folder `handover/` (driver, scorer, scenes, tests) and
  OPT-IN hooks in `exec/` (`exec/harness/`, `exec/scripts/`, `exec/sim/`). Every existing run mode, option default,
  golden file and record must stay byte for byte: the new behaviour is reachable only through new, explicitly named
  options or a new scene field. Do not touch `link/`, `probe3d/`, `tools/`, `cloudrun/`, `scenes/`, `exec-repo/`,
  `video*/`, or anything outside `20261123-phase3/`. Phase-2 folders are read-only.
- No network, no cloud command, no LLM call (the test uses a fixed script, no planner). No git push. Do not commit;
  leave the working tree for the main session.
- You may run MuJoCo locally for SHORT smoke checks only (this server has 2 cores; keep any single run under 20
  minutes of wall time and do not run two at once). The 12 trials are run by the main session.
- No deletion or overwriting of existing files. Standard library plus what `exec/` already imports.

## P1. Scene and geometry (one layout, both wall orientations)
- Two rooms that share a wall with a door opening; robot A may not leave room 1 and robot B may not leave room 2
  (the chassis centre stays in its own room; say exactly how you enforce and how you record a violation).
- A hand-over place NEAR the door that can also be marked on a real floor: a fixed floor spot with a nominal
  position and box orientation. Start from your R17 Q2 geometry (flush mark at the door centre, donor releases about
  0.31 m before it, receiver scans from about 0.80 m and approaches to about 0.20 m). If the present 0.50 m opening
  is too tight, use the wider recessed opening you proposed (about 1.0 to 1.2 m) and say which you chose and why.
  The user's wording is "문 주변" (around the door), so the spot may lie slightly inside one room as long as the
  receiver's chassis stays in its own room; choose ONE variant, do not build several.
- A QR sign (existing sign type and recognition) in the receiver's room as the destination.
- Twelve preselected trials written to a table file: six red and six blue boxes, both hand-over directions (west to
  east and east to west) balanced, both wall orientations, varied robot start poses and box start positions inside
  the donor's room; seeds fixed and listed.

## P2. Behaviour (opt-in)
- Donor: pick the box in its room with the existing approach + grasp policy, carry it to the hand-over spot, release
  it there, back off and park off the receiver's line of sight.
- Receiver: wait in its room until the donor has backed off, scan, pick up THE SAME physical box with the existing
  grasp policy, carry it to the sign of its room and set it down with the existing placement.
- The existing pickup filter that ignores boxes within 0.25 m of the door line, `PUT_DOWN` releasing wherever the
  robot stands, and `pass` driving through the door must be handled by the new opt-in path only.
- One retry of a failed grasp is allowed for each robot (same as the plan for the later experiment); record it.

## P3. Driver, scorer, records
- `python3 -B handover/run_trial.py --trial K --out DIR` runs one trial with a fixed script (no planner, no LLM) and
  writes: the trial definition, a time line of events (pick, release pose of the box: x, y, yaw, tilt; donor clear;
  receiver first sees the box; grasp attempts with outcome; set-down pose relative to the sign), chassis positions
  sampled often enough to prove nobody left its room, wall-clock and simulated seconds, and at least a few camera or
  overhead frames at release, at the receiver's grasp and at set-down (the user asks for pictures).
- `python3 -B handover/score.py DIR...` prints per trial and in total: SUCCESS only if the box was released near the
  spot, the donor cleared, the receiver lifted the same body, the box ended at the receiver's sign, and both chassis
  stayed home; otherwise the FIRST failing stage. Retries counted. "10 of 12" is the gate.
- A command list for the main session: (a) local, one trial at a time, with the expected wall time on this server;
  (b) Cloud Run, using the existing build and dispatch scripts (`../20261118-cloudrun-p2/scripts/`, `cloudrun/`),
  with what has to be changed or added for a two-robot row, the cost estimate, and a dry-run that makes no cloud call.

## P4. Tests and report
- Unit tests without MuJoCo where possible (trial table, room-limit check, scorer on constructed time lines,
  option parsing, defaults unchanged). Run the existing executor checks you can run locally and list them; show that
  the golden files under `exec/` still match.
- `REPORT-HANDOVER-GATE.md`: the layout with numbers and a small top-view sketch (ASCII is fine), what you changed in
  `exec/` (file, function, the opt-in switch), the twelve trials, the commands, what the short local smoke showed
  (honestly: how far it got), risks for the real robots (what on a real floor replaces each simulated assumption),
  and a list "확인 안 됨". Last step: create `review/ASTRA-HANDOVER-GATE.done`.
