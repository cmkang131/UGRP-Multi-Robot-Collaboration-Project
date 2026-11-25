# TASK-CHEN2D: the authors' 2D BoxNet1 with a mid-run change of orders, 4 to 32 robots (2026-11-24)

Why: the user wants a fast 2D experiment "like Chen", up to 32 robots, to see how each communication framework (DMAS, CMAS, HMAS-2, and HMAS-1 since the code has it) reacts when the orders change in the middle of a run, for few robots and for many. No MuJoCo, no Cloud Run. Rule of this project: take the prior method as it is and change only what our question needs.

Source (read-only, do not edit there): `<work>/20261113-l0-planning-env/refs/hmas/` (authors' code of Chen et al., arXiv 2309.15943, MIT licence; `env1-box-arrange.py`, `env1_create.py`, `prompt_env1.py`). Our notes on it: `<work>/20261117-leader-study/PROTOCOLS-FROM-PAPERS.md` section 2 (it lists places where the code and the paper differ; keep the CODE behaviour). The repository has no `LLM.py`; you write it.

Work only inside `<work>/20261124-chen2d/`. Copy the three env1 files here and change the copies. Touch nothing outside this folder. No git push, no gcloud, no deletion outside this folder. You have no network in your sandbox: all your tests use a scripted fake model. The main session runs the real-model smoke and the batches.

## 1. Keep as it is
- BoxNet1: grids 2x2, 2x4, 4x4, 4x8 (4, 8, 16, 32 agents), the four frameworks exactly as the code runs them (DMAS turn-taking with EXECUTE, max 4 rounds; CMAS one call; HMAS-1; HMAS-2 with the exact "I Agree" and the feedback count of env1), the prompts word for word, the syntactic check and its 6 re-prompts, the history method `_w_only_state_action_history` with the 3000-token window, the step limits (30, and 40 for 4x8), the failure labels.
- Environment generator `env_create` as in `create_env1` (five colours, 1 to 3 boxes per colour, each with its own target), but seeded (`random.seed`) so that the same environment files are reused by every framework and both conditions. Write them once to `envs/` and never regenerate silently.

## 2. What you add
### 2.1 LLM.py
- `GPT_response(messages, model_name)` (the signature the code calls; check the call sites) backed by our existing client: import `RealLLM` from `<work>/20261123-phase3/link/brain/llm.py` (read-only import via sys.path; do not copy the key handling, never print or log the key). Model `z-ai/glm-5.3-flash`, temperature 0.0 as in the authors' code, reasoning effort low (the client's default). Set `max_output_tokens` high enough for a 32-agent JSON plan plus reasoning tokens (reasoning counts toward the limit); say what you chose and why. Read the client's limits first (`HARD_EPISODE_CALLS`, `HARD_CAMPAIGN_USD`, `budget_usd`, the campaign ledger, the cache): if a hard constant blocks the batches of section 5, do NOT edit `link/`; report it and wrap around it only in a way the client supports. The response cache must be OFF or keyed so that two repetitions are not silently the same call (state what you did).
- Token counting: `tiktoken` is not installed and cannot be installed. Replace `enc.encode` by a deterministic approximation (for example UTF-8 bytes / 4, rounded up) used only for the history window. For the reported token metric use the real `usage` numbers the API returns (prompt, completion, reasoning, cost). Say this in the report as a deviation.
- A scripted fake model for tests (`--model fake`), with scripts that produce correct plans, wrong plans, non-JSON, endless DMAS dialogue.

### 2.2 The change of orders (`--condition change`; `--condition static` is the authors' task untouched)
- Fires once, right after the first executed step (after state 2 exists, before the second planning iteration).
- One colour A is chosen: of the colours that still have a box, the one with most boxes left, ties by a seeded choice (depends only on the environment seed, so every framework gets the same A when the states agree; record A and the state at the event). One square D is chosen by the seed among squares that hold no target of colour A.
- New rule from then on: boxes of colour A must not be put into target_A any more. They must be brought to square D and put into the drop-off there. Implementation: add the item `dropoff_A` to square D; a box_A in square D gets the extra doable action `move(box_A, dropoff_A)` which removes the box and leaves the drop-off. `move(box_A, target_A)` stays in the doable list exactly as before (it is still physically possible) but it is now a WRONG delivery: the box and that target are removed, the delivery is counted as wrong, and it cannot be undone. Leftover target_A items do not block completion: the completion test counts boxes only.
- How the LLMs learn it: from the event step on, every prompt that contains the current state (central planner, local agents in DMAS / HMAS-1 / HMAS-2, re-prompts) gets the same block right before the current state: `Change of orders (announced after step 1): boxes of colour A must no longer be moved into target_A. Every box_A must be moved to square[D] and put into dropoff_A with move(box_A, dropoff_A). A box_A that is put into target_A now counts as a wrong delivery.` with A and D filled in. The same sentence for everyone. Nothing else in the prompts changes. Before the event the prompts are byte-identical to `static`.
- The syntactic check and `action_from_response` must accept the new action and keep everything else.

### 2.3 Records and metrics (one JSON per episode + one CSV row)
- Authors' metrics: success or failure label, steps, API calls, tokens.
- Ours: `wrong_deliveries`, `correct_deliveries`, `boxes_left`, `strict_success` (no box left and no wrong delivery), event step, A, D, number of box_A left at the event; `first_plan_after_event_wrong` (the first executed plan after the event contains a move of a box_A into target_A), `first_plan_after_event_towards_dropoff` (it moves at least one box_A strictly closer to D or into the drop-off; NA when no box_A can move), steps from the event until the last box_A is in the drop-off (NA if never), calls and wall-clock seconds of the first planning iteration after the event, dialogue or feedback rounds in it, per-episode cost in USD from the API usage, call-ceiling flag.
- Every prompt and response is saved per episode as the authors' code does.

### 2.4 Guards (ours, reported as deviations)
- `--episode-call-ceiling N` (default 300): an episode that reaches it stops with the label `failure over call ceiling`.
- `--max-cost-usd X` for one invocation, from the API's reported cost: when reached, no new episode starts and running ones stop at the next call, everything finished is kept. Also `--max-calls`.
- `--jobs J`: J episodes in parallel (processes). An episode stays sequential inside, as the authors' code is.

### 2.5 Runner
`python3 -B run_chen2d.py --sizes 2x2,4x8 --frameworks CMAS,HMAS-2,DMAS --conditions static,change --envs 0,1,2 --out runs/NAME --jobs 6 --max-cost-usd 2.5 [--model fake]` and `python3 -B summarize.py runs/NAME` (table per size x framework x condition: episodes, success, strict success, mean steps, mean calls, mean tokens, wrong deliveries, first-plan-wrong share, cost; counts next to every share; failure labels counted). Resumable: finished episodes are skipped.

## 3. Tests (offline, fake model)
Static condition with the fake model reproduces the authors' flow (one episode per framework finishes with success); before the event the prompts of `static` and `change` are identical; the event picks the same A and D for every framework given the same state; correct replan = strict success; a plan that puts box_A into target_A after the event = wrong delivery, not undone, no strict success; ceiling, cost cap and resume work; the environment files are identical across frameworks.

## 4. Report
`REPORT-CHEN2D.md`: what you copied and every line-level change to the authors' logic (list them), deviations (token counter, guards, seeds), anything in the authors' code that looks like a bug and that you kept, the client limits you found, test output (last lines), exact commands for: (a) a real-model smoke of 3 episodes (2x2, one per framework, condition change), (b) batch 1 = sizes 2x2 and 4x8, frameworks CMAS, HMAS-2, DMAS, both conditions, envs 0 to 2 (36 episodes), with an estimate of calls. Write "확인 안 됨" for what you did not check. Last step: create the empty file `review/ASTRA-CHEN2D.done`.
