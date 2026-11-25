# TASK-CHEN2D-8: separating "the turn" from "the memory" in DMAS (2026-11-24, after review round 5, `../20261123-plan3/debate/R5b-ASTRA.md` item 1)

Context: tasks 1 to 7 are done (`REPORT-CHEN2D.md`). Same hard limits (this folder only, no network, fake model for tests, no real-model batches). No existing option may change behaviour: batches of version 7 are running from a frozen copy and will be analysed with these tools; every existing test must stay green.

Why: a reviewer will say "you first kept the news from the plan-maker and then showed it, of course it helps". In DMAS the robots can talk anyway, so the question that discriminates is WHEN the notice reaches the others and WHETHER it stays in front of them. In the main batch one DMAS planner read the new destination in a teammate's words at step 5 and still put the box into the old target at step 11 (`../20261124-chen2d-snap-v6/runs/v6-main-2x4/episodes/2x4_DMAS_e1_member_env108`).

## M1. Two new switches, used only with `--speech auto` (reject them with any other speech rule; defaults reproduce today's `auto` byte for byte)
Let R be the robot that was told (the member M under `--tell member`). The text delivered is always the notice word for word; there is never a relay LLM call.
- `--relay-timing immediate | turn` (default immediate).
  - `immediate`: today's behaviour: right after the event is applied, before the first call of the next planning iteration, the notice is put into the inbox of the recipients.
  - `turn`: the notice is put into the recipients' inbox right after R has finished its NEXT regular speaking turn in the framework's own dialogue (DMAS: R's first dialogue turn after the event, whatever R says there, even PROCEED or an EXECUTE). If R has no turn in an iteration (the dialogue ended before its turn), nothing is delivered in that iteration and the wait continues. Record the iteration and the position at which delivery happened, or that it never happened.
- `--relay-display persistent | once` (default persistent).
  - `persistent`: today's behaviour: from delivery on, the message block is in every state-carrying prompt of each recipient until the episode ends.
  - `once`: each recipient sees the message block only in its FIRST regular planning prompt after delivery (its first dialogue turn or planner prompt that contains the current state; re-prompts of that same turn keep it). After that it is no longer shown to that recipient. A recipient that gets no turn for several iterations sees it at its first turn whenever that comes.
- These switches apply to DMAS (and, by the same rules, HMAS-1 dialogue). For CMAS and HMAS-2 `turn` is not defined (a member has no regular turn towards the planner): reject `--relay-timing turn` there with a clear message; `--relay-display once` is allowed for CMAS (the planner sees the block in its first planning prompt after delivery only).
- Text that robots repeat by themselves in the ordinary dialogue is not touched; record it as today (`audit_news.py` already separates direct / relay / dialogue).

## M2. Records
Per episode: relay timing, relay display, delivery iteration and speaker position (or `never`), step of the first wrong delivery of a box of colour A (or none), `delivered_before_first_wrong` (true / false / NA when there was no wrong delivery and no delivery), for every post-event iteration whether the producer of the executed plan had the notice in its prompt and through which path (direct, relay block, dialogue), and the existing outcomes. Summary and `paired.py` accept the two new grouping fields (`--by relay`), and `audit_news.py` reports the table "producer had news x plan respected" split by the four cells.

## M3. Maps
`python3 -B enrol_maps.py --set cause --sizes 2x4 --envs 328-351`: 24 new maps with the same rules and strata as `confirm` (12 first column / 12 other columns, wording irrelevant here but keep the field).

## M4. Tests and report
Tests (fake model): defaults equal version 7 `auto` byte for byte on a saved episode; `turn`: nothing in any recipient prompt before R's turn, everything after it; R without a turn: never delivered, recorded; `once`: block present in exactly one planning prompt per recipient (plus its re-prompts) and absent afterwards; `persistent`: present until the end; rejection of the switches with other speech rules and of `turn` in CMAS; the new record fields on constructed episodes (delivery before / after the first wrong delivery). Append "CHEN2D-8" to `REPORT-CHEN2D.md` with the command for the batch: 2x4, e1, tell member, DMAS, speech auto, the four cells (two timings x two displays), maps 328 to 351 (96 episodes), same technical switches as the confirmation batch, and a call estimate. Last step: create `review/ASTRA-CHEN2D-8.done`.
