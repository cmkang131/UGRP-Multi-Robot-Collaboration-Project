# TASK-CHEN2D-13: OWN replies in near-miss formats must not end an episode (2026-11-24)

Context: tasks 1 to 12 are done (146 tests pass). Same hard limits (this folder only, no network, fake model for tests, no real-model batches, nothing under `20261123-phase3/`). Behaviour of CMAS, DMAS, HMAS-1, HMAS-2 and of every existing option must stay byte for byte; only OWN's reply handling changes.

What happened in the first real run (GLM, 4x4, horizon 1; record `<work>/20261124-chen2d-snap-v12/runs/v12-h1-8192/episodes/4x4_OWN_static_env0/calls/`): robot Agent[0.5, 3.5] answered `[["move(box_purple, square[0.5, 2.5])"]]`, a correct and doable action wrapped in one extra list. The parser refused it, the feedback said only "Your assigned plan is not in the correct json format as before. If your answer is empty dict, …" (the authors' sentence written for joint plans), the robot repeated the same nesting or answered `{"Agent[0.5, 3.5]": ["move(...)"]}`, and after six tries the episode ended with `Syntactic Error` at step 0. That is a formatting artefact of our new structure, not a planning failure.

## F1. Lenient OWN parsing (`--parse lenient`, the default mode of all our runs; `--parse strict` keeps today's behaviour)
Accept, in this order, and record which form was used (`own_reply_form` per call: `list`, `nested`, `self_dict`, `string`, `fenced`):
- a JSON list of H entries (today);
- the same inside a Markdown code fence, or followed/preceded by prose (take the first JSON value that validates, searching after the last "EXECUTE" if present);
- a list whose entries are themselves one-element lists (`[["move(...)"], [null]]`) or a list containing exactly one list of H entries (`[[a1, a2, a3]]`): unwrap;
- an object with exactly one key naming the speaker itself whose value is any accepted list form: unwrap (a key naming another agent stays a refusal, as in task 12);
- for H = 1 only: a bare action string or `null`.
A list shorter than H is padded with nulls; longer than H is cut to H; record both (`own_reply_padded`, `own_reply_cut`).

## F2. Feedback written for OWN
When an OWN reply is still not usable, or its first entry is not doable, the re-prompt must say exactly what was wrong and repeat the format, e.g. "Your reply could not be read as a JSON list of {H} entries. Output only a list like [\"move(box_blue, square[0.5, 1.5])\", null] with {H} entries, each one action string for yourself or null." or "Your first entry {entry} is not in your doable action list {list}. Choose from that list or use null." Keep the authors' feedback sentences for the other frameworks untouched.

## F3. A robot that still fails after the repair limit
Do not end the episode with `Syntactic Error` because ONE robot's own list is unusable: treat that robot's list as all nulls for this round, count it (`own_robots_dropped` per round and per episode), and continue with the other robots' lists. The episode-level label `Syntactic Error` remains for the authors' frameworks. Report this as a rule of OWN (it has no single joint plan whose failure would stop everyone).

## F4. Tests and report
Fake-model tests for every accepted form, for strict mode refusing them, for padding and cutting, for the two feedback texts, and for the dropped-robot rule (episode continues, counters right). Default behaviour of the other frameworks byte for byte (reuse the saved-episode replay tests). `output_demand.py` and `summarize.py` show `own_reply_form` counts and `own_robots_dropped`. Append "CHEN2D-13" to `REPORT-CHEN2D.md`. Last step: create `review/ASTRA-CHEN2D-13.done`.
