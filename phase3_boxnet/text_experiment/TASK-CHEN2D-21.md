# TASK-CHEN2D-21: when an answer is cut part-way, use its complete leading steps (2026-11-25)

Context: tasks 1 to 20 are done. Start only after `review/ASTRA-CHEN2D-20.done` exists. Same hard limits (this
folder only, no network, fake model for tests, no real-model batches, never print or copy the key). Everything below
is OPT-IN; defaults stay byte for byte.

Why. The user (2026-11-25 08:10 KST, verbatim): "잘리면, 말 자체가 안 나오나?\n내 생각에 잘리는 거는 정보 손실 정도로
생각해서 앞에 부분만 반영되는 걸 생각했는데". Today an attempt that is cut at the output limit is thrown away whole and
asked again, even when the visible answer already holds complete steps. In the real runs almost every cut happened
inside the reasoning (72 of 74 cut attempts had an empty answer, `../20261124-chen2d-snap-v19/runs/
chen2d-19-first-round-r2`), so this rule will fire rarely; it is added so that the rare part-written answer is
treated the way the user expects: what was written is used, what was not written is lost.

Facts to keep in mind (checked in records): a joint answer (CMAS, GROUP) is a JSON array of steps, each step an
object `robot -> action` (step-major), usually inside a ```json fence
(`../20261124-chen2d-snap-v18/runs/v18-pilot-r2-16k/episodes/3x3_CMAS_static_env0/calls/00001.json`). So a cut loses
the LATER STEPS of every robot, not the later robots.

## P1. `--cut-answer discard|prefix` (default `discard` = today)
With `prefix`, in the matched protocol, for an attempt whose provider finish says cut at the output limit
(`cut_off is True`) and whose visible answer is not blank:
1. Complete step, defined. Read the visible answer with the existing accepted reply shapes (fenced or bare, joint or
   own). A step is complete only when its own JSON value is closed in the text: for a joint answer the step's object
   up to its closing `}`; for an own answer the step's entry up to its closing quote / bracket in whichever own
   shape the parser accepts. The step that was being written when the text ended is dropped whole, for all its
   robots, even if some `robot: action` pairs inside it are complete. Missing closing brackets of the outer array
   and a missing closing fence are tolerated. Text before the first step (prose, fence) is handled as the lenient
   reader handles it today. If the answer's shape cannot be recognised, there are zero complete steps.
2. If there is at least ONE complete step: do NOT retry. The salvaged answer is treated exactly as if the writer
   had replied with only those steps (a short list): the same judging, the same repair path when the first step is
   not doable, the same merge and execution, the same thing shown to later writers in the earlier-lists slot. Do not
   invent padding: use whatever the code does today for a complete reply that has fewer than H steps, and say in the
   report what that is (do the writer's robots idle for the rest of the round, or does the round end earlier?).
3. If there are zero complete steps: nothing changes (retry as today; after the reply attempts are exhausted the
   `--failed-writer` setting decides, including `idle` from task 20).
4. A cut attempt that was salvaged counts as a cut attempt in every existing counter (it WAS cut), and is
   additionally recorded: `cut_answer_salvaged: true`, `salvaged_steps: k`, the visible characters, and the class
   `partial`. The call record says the plan came from a cut attempt. Add a per-round event `writer_cut_prefix` with
   round, structure, speaker, robots covered, steps kept (k of H).

## P2. Measures
- `summarize.py` (and the planning table): per cell, cut attempts split into empty / partial-with-zero-steps /
  partial-salvaged; steps kept and steps not written (H - k) for salvaged answers, as robot-steps
  (steps x robots that writer covers), by structure. Keep "delivered boxes / total boxes" first.
- The fake model gets a way to script a cut attempt with a given visible text, if it has none yet.

## P3. Tests, report
- Tests with the scripted client: a joint answer cut inside step 3 keeps steps 1-2 and is not retried; cut inside
  step 1 retries; an own answer cut after two entries keeps two; a cut inside the fence opener gives zero steps;
  a salvaged first step that is not doable goes through the existing repair; the earlier-lists slot of the next
  writer shows the short list; with `--cut-answer discard` every prompt, record and summary of the existing test
  runs is byte identical; interplay with `--failed-writer idle`.
- Rerun the whole suite; append section "CHEN2D-21" to `REPORT-CHEN2D.md`: the exact definition as implemented,
  what happens to the rest of the round after a short list, the new counters, the exact pilot command for the main
  session (the task-20 pilot command plus `--cut-answer prefix`), test results, and "확인 안 됨".
Last step: create `review/ASTRA-CHEN2D-21.done`.
