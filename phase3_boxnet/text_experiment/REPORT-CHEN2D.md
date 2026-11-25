# Chen BoxNet1 with an order change after step 1

The runner supports 4, 8, 16 and 32 robots with CMAS, DMAS, HMAS-1 and HMAS-2. On the 2×2 reference map, each framework reproduced the upstream static episode, including every message, response, executed plan and state under the specified history-token approximation. On the requested 36-episode batch design, the correct scripted model achieved strict success in 36/36 episodes with 1,010 scripted calls. Real GLM behavior, billed cost and latency are **확인 안 됨**. [Test log](review/offline-tests.txt) · [Batch table](review/offline-batch1-summary.txt) · [Independent recount of saved traces](review/offline-audit.txt)

On seed 0 of the 2×2 grid, the first action left three orange boxes. All four frameworks received the same order to use the drop-off at `square[0.5, 1.5]`. The correct CMAS script completed the last orange delivery three steps after the event and delivered all 12 boxes correctly. Under the script that continued following the old orders, the first post-event plan delivered an orange box to its old target. The episode finished with nine correct deliveries, three irreversible wrong deliveries, zero boxes left, the authors’ `success` label and `strict_success=false`. [Correct episode](review/offline-batch1/episodes/2x2_CMAS_change_env0/episode.json) · [Wrong-delivery episode](review/offline-wrong/episodes/2x2_CMAS_change_env0/episode.json)

## Commands for the main session

Run these commands from `<work>/20261124-chen2d`. The three-episode smoke uses seed 0, the change condition and a $0.25 invocation cap. The 36-episode batch uses two sizes, three frameworks, two conditions and three seeds. Each output directory owns its campaign ledger across resumes. The shared client's **$1.50 campaign ceiling** takes precedence over the example's $2.50 invocation cap.

**Real-model smoke, three episodes**

```bash
python3 -B run_chen2d.py \
  --sizes 2x2 --frameworks CMAS,HMAS-2,DMAS --conditions change --envs 0 \
  --model z-ai/glm-5.3-flash --out runs/glm-smoke --jobs 1 \
  --episode-call-ceiling 300 --max-calls 900 --max-cost-usd 0.25
python3 -B summarize.py runs/glm-smoke
```

**Real-model batch 1, 36 episodes**

```bash
python3 -B run_chen2d.py \
  --sizes 2x2,4x8 --frameworks CMAS,HMAS-2,DMAS --conditions static,change --envs 0,1,2 \
  --model z-ai/glm-5.3-flash --out runs/glm-batch1 --jobs 6 \
  --episode-call-ceiling 300 --max-calls 10800 --max-cost-usd 2.5
python3 -B summarize.py runs/glm-batch1
```

**Call estimate.** The scripted smoke took 7 CMAS, 27 HMAS-2 and 14 DMAS calls, 48 total. Batch 1 has a 1,010-call planning estimate if GLM takes the same steps, every reviewer agrees and DMAS emits a valid `EXECUTE` at its first opportunity in each row. A full DMAS round takes 32 turns on 4×8. At that rate, the 300-call ceiling interrupts the tenth planning iteration even with one round per iteration. Six workers can plan and record different episodes concurrently. The client admits one outstanding **paid** request per shared ledger, so the six workers take turns making those requests.

| Scripted batch 1 | CMAS calls | HMAS-2 calls | DMAS calls | Total |
|---|---:|---:|---:|---:|
| 2×2, 18 episodes | 35 | 128 | 70 | 233 |
| 4×8, 18 episodes | 78 | 387 | 312 | 777 |
| Both sizes | 113 | 515 | 382 | 1,010 |

The experiment allows at most 10,800 attempts across the 36 episodes at the default episode ceiling. Repairs, objections, delayed agreement, episode failures and dollar guards can change the observed call count. The scripted batch's $1.010 is a fixture value used to exercise the guards. [Episode CSV](review/offline-batch1/episodes.csv) · [Invocation log](review/offline-batch1.log)

## Provenance and changes to the authors’ code

The three copies came from the local Chen reference tree. Project notes identify the upstream snapshot as `multi-agent-framework@024221d36d520db67a8ee4e19f755789056255fa`, corresponding to arXiv 2309.15943. The distribution includes Yongchao Chen's MIT license. The local snapshot contains no `LLM.py`. [Reference tree](<work>/20261113-l0-planning-env/refs/hmas) · [Project notes, section 2](<work>/20261117-leader-study/PROTOCOLS-FROM-PAPERS.md) · [License](LICENSE)

| Upstream file | SHA-256 of the read-only input |
|---|---|
| `env1-box-arrange.py` | `8ca608415701e94febc9868f0dbc5b914e0d86933fa65c8335c7efd0a08106ff` |
| `env1_create.py` | `66a6135480372e6a7c0297bcffb6fed321fc5734829f422ea6ca3dbb49058926` |
| `prompt_env1.py` | `1d130732b2e311970a5463d7406770a021a8196b6384ef08eee9bbdd21809445` |

The table maps each edit to the original line numbers. The unified diff includes every changed line, including removed prints, imports and the two import-time entry points. Reapplying it to fresh local copies reproduced all three delivered files byte-for-byte. [Full line-level diff](review/chen2d-upstream.diff) · [SHA-256 of the running implementation](review/offline-batch1/run.json)

| Original file and lines | Delivered lines | Change |
|---|---|---|
| `env1-box-arrange.py` 1–29 | 1–32 | Use explicit imports. The caller supplies a verified initial state, result directory, framework, model and episode recorder. The default history is the selected upstream batch setting. The four authors’ result directories and initial state snapshot are created as before. |
| Same, 39–105, 126–145, 171–205 | 34–95, 117–136, 158–192 | Start a clock at each iteration. Record the DMAS/HMAS-1 round at each loop entry and the HMAS-2 round when a reviewer is selected. Pass the optional announcement into the four active prompt builders. Speaker and reviewer selection, message construction and checks retain their positions. |
| Same, 108–123 | 97–115 | A brace-free first central reply used to reference an unbound variable. Record the existing author label `Hallucination of wrong plan` for this exception case. A bare central `Out of tokens` is recorded with the token-limit label. Later brace-free central replies retain the upstream previous-plan behavior. |
| Same, 40–43, 46, 67, 78, 89, 106, 114, 127, 161–167, 172, 221, 239, 245–246 | Corresponding planning and execution blocks | Remove diagnostic console prints. Full messages, replies, applied actions and execution feedback are kept on disk. The no-feedback print/pass branch has no remaining work. |
| Same, 120, 123, 229, 232, 267 | 112, 115, 215, 218, 254 | Return the label to the recording wrapper. It owns the scalar files, JSON and CSV. |
| Same, 226–254 | 212–242 | Stop the planning timer before applying the selected plan. Record successful physical actions, save the authors’ next-state file, then apply the one-time event and give the updated state to the next iteration. Execution errors of type `ValueError`, `TypeError`, `KeyError` or `IndexError` retain the hallucination label. |
| Same, 256–295 | 243–254 and `run_chen2d.py` | Count boxes for the change condition. Static retains the all-item count. Preserve the last-iteration label test. Replace the import-time hard-coded HMAS-2 sweep and path placeholders with the CLI and per-episode recorder. |
| `env1_create.py` 3–13 | 3–11 | Import only the required prompt/model functions, use `re.error`, and replace imports used by the destructive directory writer with local persistence helpers. |
| Same, 32–37, 53–58, 65–70 | 30–38, 53–61, 67–75 | Add the drop-off action to the central, other-agent and own-agent action lists when the matching box and drop-off share a square. Original target actions keep their order and availability. |
| Same, 101–110, 119–127 | 105–117, 123–130, 136–139 | Accept a box at its matching drop-off and keep the new site stationary. Remove syntax-check prints. The six-call feedback loop, its message text and the original target check remain. |
| Same, 135–162 | 142–174 | Accept an optional applied-action list, remove only a box on drop-off, and append an action after its transition succeeds. A wrong target delivery uses the original two-item removal. The recorder classifies it using the active order. |
| Same, 164–212 | 176–226 | Keep the `env_create` draw sequence. Replace recursive deletion, regeneration and import-time generation with seeded, locked, write-once storage and a digest manifest. |
| `prompt_env1.py` 1–6, 48/55, 103/113/123/131, 191/200/210/218, 291/301/311/319, 390/400/410/418, 476/486/496/504 | 1–9 and the corresponding sizing expressions | Import the model function and exception explicitly. Replace each `len(enc.encode(text))` with `ceil(UTF-8 byte length / 4)` using integer arithmetic. Keep the original strict `< 3000` history inclusion test. |
| Same, 81/98/147, 157/166/226, 354/364/427, 454/465/514 | 84/101/150, 160/169/229, 357/367/430, 457/468/517 | Insert one optional string immediately before the first current-state heading in both the sizing template and final template for each active framework. The empty string preserves static prompt bytes. A syntax or HMAS-2 re-prompt carries the original annotated turn through the upstream message history. |

## Environment, scoring and records

The runner seeds the authors’ generator with the integer passed in `--envs`. Each color has one to three boxes and exactly as many targets. Twelve input files cover seeds 0–2 on all four sizes. Subsequent invocations read and check each registered digest. A changed or missing registered file produces an error. Every framework and condition on a size/seed pair reads the same bytes. [Environment manifest](envs/manifest.json) · [Generator and persistence](env1_create.py)

After executing step 1, the runner saves `pg_state2.json` and counts the remaining boxes by color. A fresh `random.Random(env_seed)` chooses among the lexically sorted maximum-count colors, then among eligible squares in coordinate order. The JSON records the pre-announcement state and the state with the drop-off. The latter feeds planning and subsequent state history. If step 1 already clears all boxes, the order has no eligible color and the event fields are null. [Intervention and scoring](episode.py)

- `steps` counts executed plans, including an empty joint plan. `authors_env_action_times` also counts an unfinished final planning iteration. Correct and wrong delivery counts follow actual removals. Strict success requires zero boxes left and zero wrong deliveries.
- `first_plan_after_event_wrong` examines the selected plan that actually reaches execution. `first_plan_after_event_towards_dropoff` uses applied actions and Manhattan distance. Placing a box into the drop-off also qualifies. With an eligible box on these grids, at least one approach or drop is physically possible. An unobserved first execution or an inapplicable movement measure is null.
- `steps_to_last_dropoff` counts executed steps after the event until every box of the diverted color that was present at the event has entered its drop-off. Any irreversible wrong delivery of one of those boxes makes this measure null.
- `post_event_calls`, `post_event_planning_seconds` and `post_event_rounds` describe the first planning iteration after the event, including a partial iteration if a guard intervenes. Timing uses a monotonic wall clock and includes prompt construction, waiting for admission and calls. A resumed partial iteration accumulates active time. CMAS has zero dialogue rounds. HMAS-2 has one pass when it has reviewers. Partial DMAS/HMAS-1 rounds count on entry.
- Each `episodes/<id>/episode.json` contains the metrics, event, final state, issued plan and applied actions by step. Numbered `calls/*.json` preserve every original role/content message, raw reply, step, round and usage. They also retain local turns overwritten in the upstream per-step prompt file. The authors’ state, prompt, selected-response, dialogue and three scalar/text outputs are available alongside the trace. The real client also writes its own request/settlement records.
- `episodes.csv` has one row per recorded episode. The summary lists planned, recorded and interrupted counts. Success shares use terminal episodes. First-plan-wrong shares use observed post-event executions. Means and workload totals include consumed work in partial episodes. Each share shows its numerator and denominator. Unknown token or cost totals display as NA. [Runner](run_chen2d.py) · [Summarizer](summarize.py)

## Model transport, usage and limits

The bridge imports `RealLLM` from the read-only Phase 3 client. Its SHA-256 was `2b9c5dda01817ad4d3889efcf4f845505bd8c1b21333081c9ce566e323a7dcad`. The route uses `z-ai/glm-5.3-flash`, temperature 0.0 and the client's default low reasoning effort. I chose **8,192 completion tokens** for visible JSON and internal reasoning together. A representative 32-entry plan occupies 1,824 visible UTF-8 bytes. The output allowance leaves space for reasoning and dialogue. Adequacy for actual GLM replies is **확인 안 됨**. [Bridge](LLM.py) · [Client source](<work>/20261123-phase3/link/brain/llm.py)

| Client or runner setting | Effect on this experiment |
|---|---|
| Client input interface | `RealLLM.call` accepts one string and sends one API user message. The adapter writes each original turn verbatim under a `[system]`, `[user]` or `[assistant]` text heading, in order. The call trace separately preserves the original structured messages. This is a transport deviation from native chat roles. `response_format=None` allows dialogue, exact agreement text and JSON through the same interface. |
| Episode and retry guards | Client `HARD_EPISODE_CALLS=600`. The runner defaults to 300, applies the lower real limit and keeps the Nth reply when it stops with `failure over call ceiling`. That unfinished iteration has no executed plan. A zero client retry window gives one HTTP attempt per author call. Syntax repairs remain independent author calls. |
| Campaign budget | Client `HARD_CAMPAIGN_USD=1.5` clamps `budget_usd` to $1.50. All real workers and resumes share `OUT/campaign-calls.jsonl`. The client reserves before sending, persists settlements, honors stricter historical caps, and refuses unresolved costs or reservations. Two qualifying authentication/quota errors can also halt the ledger. |
| Invocation guards | `--max-calls` and `--max-cost-usd` cover one invocation across processes. Before a request, the runner checks remaining funds against the client's reservation formula. A guard can therefore stop just below the requested dollar cap. Actual usage settles the call. If a failed attempt has only the client's reservation charge, the guard uses that charge and the API-reported cost field stays unknown. An unresolved settlement stops new requests. |
| Client project guard and input bound | Before its first paid request the client checks the existing project spend guard against provider key usage. Its configured limit is clamped to $10 in the inspected source. Current remaining allowance is **확인 안 됨**. The default conservative input bound is 71,024, tested against UTF-8 bytes plus 1,024 framing units. The client's GLM routing price ceilings are $0.10/M input and $0.20/M completion in the inspected source. |
| Response cache | The temperature-zero client exposes `cache_dir`. Each new logical request receives a fresh temporary directory inside its episode. Equal prompts within an episode, across conditions, or in another repetition therefore reach the transport independently. The directory is removed after that call. |
| Reported tokens and cost | Real metrics use the client's API usage fields for prompt tokens, completion tokens, reasoning tokens and cost. `tokens` sums prompt and completion. Reasoning is already included in completion. Missing fields stay null. `known_reported_cost_usd` and `guard_cost_usd` expose partial reporting and conservative charges. The UTF-8 approximation affects only the history window. |
| Resume | Completed outcomes, including episode-ceiling failures, are skipped. Invocation interruptions can resume with a new invocation budget in the same output directory. The worker reconstructs the same episode from its saved replies, checking its step, round and full messages before admitting the next new request. The prefix keeps its original usage and call numbers. An unresolved pending call requires inspection. An output directory records its model, script, ceiling, and protocol hashes to prevent incompatible resumes. |

## Upstream behavior preserved

- DMAS and HMAS-1 break only the inner column loop after an accepted `EXECUTE`. Later rows can still speak and replace the plan. DMAS can accept the first speaker without polling every agent. After four full rounds of `PROCEED`, DMAS executes `{}` and consumes an environment step. HMAS-1 retains the central proposal without a replacement. Its outer loop can also finish on a braced local reply without `EXECUTE`, with the central plan intact.
- HMAS-2 reviews only agents whose exact grid key appears in the central plan. It compares whole response strings with `I Agree`. Punctuation or whitespace triggers dissent. At most one round of objections goes to the central planner, with no second local review. The revised-plan checker receives the full returned text even when a braced substring was extracted.
- CMAS omits state/action history in its upstream branch. The other frameworks keep a suffix of state/action pairs using the BoxNet1 3,000-unit history window. Large current states and the dialogue already accumulated within a step can themselves exceed that window.
- The validator ignores action strings its movement regex does not match, accepts an empty plan, normalizes coordinate keys and checks adjacency without checking destination membership. A listed item such as a target can satisfy its original square-transfer rule. Execution uses dictionary order against a progressively updated copy. The new drop-off site is explicitly stationary.
- The sixth syntactic re-prompt is issued and counted, then the loop returns `Syntactic Error` without validating that last reply. Malformed braced JSON raises before the authors’ JSON-repair text. The wrapper records that exception under `Hallucination of wrong plan`, keeping the raw reply. On later central iterations a brace-free answer may reuse the previous selected plan.
- Completion on the final allowed iteration still receives `failure over query time limit`. Offline fixtures reproduced this with all boxes delivered on step 30 of 2×2 and step 40 of 4×8. The independently defined strict-success flag is true in those two fixtures.

## Offline verification

```bash
python3 -B -m unittest -v test_chen2d.py
python3 -B run_chen2d.py --sizes 2x2,4x8 --frameworks CMAS,HMAS-2,DMAS \
  --conditions static,change --envs 0,1,2 --out review/offline-batch1 \
  --jobs 6 --max-cost-usd 2.5 --model fake
python3 -B summarize.py review/offline-batch1
```

The reference test loads the original functions without their destructive top-level drivers and supplies the same history approximation and fake replies. For seed 0, all four static episodes took nine steps. CMAS used 9 calls, DMAS 18, HMAS-1 23 and HMAS-2 30. The tests also cover wrong and correct deliveries, non-JSON, the six syntax repairs, exact agreement, endless DMAS dialogue, all four sizes, unchanged inputs, parallel admission, and resume without rebilling. A scripted HTTP transport exercised the actual client's request builder, cache and reservation ledger without a network connection. Its scripted 503 case kept the conservative charge separate from unreported API usage. [Test source](test_chen2d.py) · [Full output](review/offline-tests.txt)

The test run exited with code 0 and ended with the following output.

```text
----------------------------------------------------------------------
Ran 13 tests in 15.559s

OK
```

The 36-episode fake run and its summarizer also exited 0. Its 339 executed steps have 1,010 corresponding scripted call records. All 18 static/change pairs had identical first-iteration message lists. For each of six size/seed maps, the three frameworks agreed on the first executed state and the resulting event. The audit independently recounted the drop-off metrics from the applied actions. SHA-256 of the frozen environment manifest is `8e0266d961ec8e305d3e14f882d4ca21d59560625c8ca260c0ae974aab402351`. SHA-256 of the episode CSV is `1996855279e511ef341f42cd52d82eda0dd7fb4902e83d6f616510fc102a8b36`. [Saved audit](review/offline-audit.txt) · [Batch results](review/offline-batch1/episodes.csv)

## CHEN2D-2

Protocol version `66ed69dbe6aa` passed 27 offline tests. In the scripted batch, e1 fired in all 54 assigned episodes. In 45 of them the selected colour had already been delivered. Only the nine 4×8 seed-1 episodes still had a box to reroute. All 54 contribute to the results below. Real-model outcomes, billed costs, and live request overlap for this revision are **확인 안 됨**. [Offline test output](review/chen2d-2/offline-tests.txt) · [Batch comparison](review/chen2d-2/batch1-summary.txt) · [Trace recount](review/chen2d-2/offline-audit.txt)

### Commands for the main session

Run both commands from `<work>/20261124-chen2d`. Each uses a fresh version-2 output path. Repeating a command with the same output path resumes its saved episodes.

**Real-model smoke, three episodes.** All three frameworks use 2×2 seed 0, e1, and the broadcast announcement. The scripted equivalents used 9 CMAS, 30 HMAS-2 and 18 DMAS calls, 57 in total.

```bash
python3 -B run_chen2d.py \
  --sizes 2x2 --frameworks CMAS,HMAS-2,DMAS --conditions e1 --tell all \
  --envs 0 --parse lenient --model z-ai/glm-5.3-flash \
  --out runs/glm-smoke-v2 --jobs 3 --episode-call-ceiling 300 \
  --max-calls 900 --max-cost-usd 0.25
python3 -B summarize.py runs/glm-smoke-v2
```

**Real-model batch 1, 72 episodes.** Each size, framework and seed has one static episode and three e1 episodes. The invocation can admit up to 21,600 calls within its $2.50 cap. Each episode also has the client's $1.50 ledger ceiling.

```bash
python3 -B run_chen2d.py \
  --sizes 2x2,4x8 --frameworks CMAS,HMAS-2,DMAS --conditions static,e1 \
  --tell all,leader,member --envs 0,1,2 --parse lenient --model z-ai/glm-5.3-flash \
  --out runs/glm-batch1-v2 --jobs 6 --episode-call-ceiling 300 \
  --max-calls 21600 --max-cost-usd 2.5
python3 -B summarize.py runs/glm-batch1-v2
```

### Map assignment and event timing

Each frozen `envN.json` has a sibling `envN.event.json` with its initial-map SHA-256, seed, e1 colour and square `A,D`, static reference length `S`, e1 trigger step, e2 colour and square `A2,D2`, leader `L` and member `M`. New maps get the same treatment at generation. All 12 existing maps have enrolled assignments. The frozen map manifest retains its original SHA-256, `8e0266d961ec8e305d3e14f882d4ca21d59560625c8ca260c0ae974aab402351`. The reader verifies each enrolled input before use. [Seed-0 assignment](envs/2x2/env0.event.json) · [Event manifest](envs/events-manifest.json)

The reference planner chooses joint actions from the state at the start of each step. Each square's robot can move one box. For co-located boxes it chooses the shortest remaining distance to a matching target, breaking ties by box name and target coordinates. It deposits a box at distance zero. Otherwise it chooses the lowest-coordinate adjacent square on a shortest path. It recomputes after each joint step. The generator executes every reference plan with the authors’ action rules. Tests also checked every chosen action against the displayed doable list and submitted each joint plan to the strict checker. The e1 trigger is `ceil(S/2)`, clamped to 2 through half the grid's step limit. `--event-step N` overrides the e1 schedule for tests. On 2×2 seed 0, `S=9` and the announcement follows executed step 5. [Reference planner](map_events.py) · [Map enrollment and action rules](env1_create.py)

- **e1.** The seeded draw chooses a map colour and a square initially free of that colour's target. At the trigger, the episode records how many affected boxes remain and adds the drop-off. The announcement gives the new destination and the wrong-delivery rule. A robot sees the drop-off command in the doable list for a square containing both items. The old target action stays physically possible and counts as a wrong delivery. If zero affected boxes remain, the event still produces the announcement, sets `event_fired` and `event_nothing_to_change`, and supplies the notice on subsequent eligible turns. An episode finishing on the trigger step retains the notice in its event record.
- **e2.** The destination is drawn from squares at least two Manhattan units from every initial target of the selected colour. If none qualify, the draw uses squares maximizing distance to the nearest such target. The first applied delivery of that colour triggers e2 after the joint step. If several qualify together, the first in the authors’ execution order is cancelled. Its target stays consumed, its delivery credit is reversed, and one visibly renamed box returns at the delivery square. Only that box can use the new drop-off. The other same-colour boxes retain their target actions. State snapshots include the intervention, and the event record retains both sides of the change. An episode with no qualifying delivery sets `event_not_fired`. [Episode transitions and scoring](episode.py) · [Saved e2 example](review/chen2d-2/e2/episodes/2x2_CMAS_e2_all_env0/episode.json)

### Recipients and measurements

The seeded robots differ and keep their identities across frameworks on a map. The central planner is robot L in CMAS, HMAS-1 and HMAS-2. Its prompt keeps the authors’ wording. DMAS uses its usual speakers. With `all`, the same announcement appears immediately before the current state on every planner, dialogue and review turn after the event. With `leader` or `member`, it appears only on the selected robot's turns. Syntactic re-prompts inherit the original speaker's prompt. HMAS-2 central revisions inherit the central prompt and the feedback that reviewers actually wrote. All robots receive the usual shared state and doable actions. [Framework loops and recipient selection](env1-box-arrange.py) · [Prompt templates](prompt_env1.py)

HMAS-2 reviews only robot keys present in the central proposal. A member absent from that proposal has no review turn. In CMAS with `member`, there is no member turn and no path for the notice to reach the planner. DMAS and HMAS-1 retain in-step dialogue. HMAS-2 retains its in-step feedback path. The default history method does not replay earlier steps’ dialogue. A test traced a member’s distinctive feedback phrase to the same-step central revision and checked its absence from the next step’s planner prompt. [Recipient and feedback tests](test_chen2d_v2.py)

Each call records its robot, role, direct-notice flag and parser-rescue flag. Each episode records told turns per recipient, including zero-turn recipients. The iteration trace names the told robots whose replies contained the drop-off identifier, “drop-off” or “Change of orders”, case-insensitively. The episode reports a first-iteration mention flag, the count of later mentioning iterations, and how many of those executed a respecting plan. For scoring, an executed plan respects the order when it sends at least one affected box strictly closer or into the drop-off and issues no wrong delivery. Wrong delivery and progress also have separate fields. With no affected box available, progress and respect are NA. For e2, the episode also records the trigger step, whether the first executed plan advanced the returned box, and steps to its drop-off. The latency is NA if the box never arrives. [Episode CSV](review/chen2d-2/batch1/episodes.csv) · [e2 CSV](review/chen2d-2/e2/episodes.csv)

The table groups by size, framework, condition and tell policy. Static contributes one episode per map and framework. Boolean shares use all recorded episodes in the group, including interrupted, unfired and nothing-to-change episodes. An undefined first-plan measure contributes to the denominator and has an explicit NA count. Conditional means, such as time to the returned delivery, show the observed count out of all episodes. Planned and recorded counts expose episodes that never started. Run manifests bind the short code version to the hashes of 12 source files. The summarizer checks the version on every episode, rejects version-one results and refuses to combine runs with different versions or settings. [Summarizer](summarize.py) · [Versioned run manifest](review/chen2d-2/batch1/run.json)

### Plan extraction, spending limits and resume

`--parse lenient` is the default. At a plan-extraction site it tries the JSON decoder at successive opening braces, starting at the last `EXECUTE` when present. The checker receives canonical JSON for the first dictionary, preserving key order for execution. If a checker reply has no dictionary, it uses the authors’ format-feedback sentence within their six-re-prompt loop. The other extraction sites retain their original no-match paths. The sixth repair call still consumes the last slot under the authors’ loop boundary. `--parse strict` preserves the original greedy extraction and full-reply checker behavior. Tests compared strict static episodes with the upstream code for all four frameworks. [Parser](plan_parse.py) · [Upstream parity tests](test_chen2d.py)

The tests contain the exact frozen DMAS replies 00011 and 00012 and HMAS-2 reply 00017. In DMAS, 00011 causes a legitimate action repair. Strict parsing then raises on the `EXECUTE` prefix of 00012. In HMAS-2, strict parsing raises on the greedy match spanning two dictionaries. Lenient parsing recovers the two intended plans. Each affected reply receives one rescue flag even when both the extractor and checker see it. The episode sums the flags and the summary reports the share of episodes with a rescue. [Frozen reply fixtures and tests](test_chen2d_v2.py)

Each episode owns `episodes/<episode_id>/campaign-calls.jsonl`. A separate invocation file tracks settled calls, reported cost, conservative charges and in-flight reservations. Workers hold its file lock during admission and settlement and release it during transport. A request waits if another worker’s outstanding reservation temporarily occupies its call or dollar allowance. A settled episode-budget refusal frees its invocation reservation. On resume, the runner replays the saved prefix with its original usage, call numbers, recipients and rescue flags. An unresolved pending numbered call requires inspection before replay. The scripted transport test observed two worker processes inside the request function together, with two invocation reservations and a separate client reservation in each episode ledger. [Client bridge](LLM.py) · [Shared counters](limits.py) · [Transport and resume tests](test_chen2d_v2.py)

### Offline results

| Batch 1 condition and recipients | Episodes | Event fired | Nothing to change | Strict success | Wrong deliveries | Scripted calls |
|---|---:|---:|---:|---:|---:|---:|
| Static | 18 | — | — | 18/18 | 0 | 501 |
| e1, all | 18 | 18 | 15 | 18/18 | 0 | 480 |
| e1, leader | 18 | 18 | 15 | 17/18 | 1 | 492 |
| e1, member | 18 | 18 | 15 | 15/18 | 3 | 501 |
| **Total** | **72** | **54** | **45** | **68/72** | **4** | **1,974** |

All 72 episodes received the authors’ success label. The four wrong deliveries explain the four strict failures. On a separate 2×2 seed-0 e2 run, all four frameworks cancelled the first blue delivery at step 1 and delivered the returned box three steps later. All four achieved strict success. Replaying the saved actions reproduced all 709 state transitions across the two runs. The API prices and latencies of a live model cannot be inferred from the scripted calls. [Batch table](review/chen2d-2/batch1-summary.txt) · [e2 table](review/chen2d-2/e2-summary.txt) · [Recount and artifact hashes](review/chen2d-2/offline-audit.txt)

The test command and both scripted runs exited 0. The fake batch used a $22 fixture cap for its 21,600-call ceiling. Its measured fixture cost was $1.974. [Full test output](review/chen2d-2/offline-tests.txt) · [Batch log](review/chen2d-2/batch1.log) · [e2 log](review/chen2d-2/e2.log)

```bash
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest -v test_chen2d.py test_chen2d_v2.py
```

```text
----------------------------------------------------------------------
Ran 27 tests in 55.956s

OK
```

## CHEN2D-3

**All 54 scripted e1 episodes had a box to reroute when the event fired.** The previous batch had 45 empty interventions in 54 episodes. In a separate scripted HTTP test, the client recovered from a cut-off reply on its second attempt and executed the plan. Three consecutive cutoffs produced `failure output limit` and charged all three attempts to the episode and invocation. Protocol `0bd42cf7f6e1` passed 36 offline tests. Live-model recovery, billing and latency for this revision are **확인 안 됨**. [Batch recount](review/chen2d-3/offline-audit.txt) · [Scripted HTTP evidence](review/chen2d-3/scripted-transport.json) · [Test output](review/chen2d-3/offline-tests.txt)

### The 12 enrolled maps

At enrolment the static reference planner plays the map to completion. The e1 assignment uses the state immediately **after** the scheduled joint action. It selects a colour with the most boxes left, using the seed to break ties. It draws D among squares that initially lack the selected colour’s target and lack its box in the reference event state. If every initially target-free square holds such a box at that step, those target-free squares form the fallback pool. Each sidecar records the counts for all colours, the selected count, the clamped step and whether it needed lowering. All 12 maps used the clamped step. A one-step test map exercised the lower bound by firing at step zero, when its last box was still present. [Assignment code](map_events.py) · [Example sidecar](envs/2x2/env0.event.json)

The coordinates in the leader and member columns identify the robots assigned to those squares. For e1, M operates the square where the new drop-off opens, and the seed selects L among the other robots. For e2, L2 is drawn at enrolment from all robots. The episode records M when the rejected delivery reveals the return square. Static episodes use the e1 leader identity. [Event handling](episode.py)

| Grid | Seed | e1 A | e1 D | Event step | Reference boxes of A left | e1 L | e1 M | e2 A2 | First reference delivery of A2 | e2 L2 |
|---|---:|---|---|---:|---:|---|---|---|---:|---|
| 2×2 | 0 | red | [0.5, 0.5] | 5 | 2 | [1.5, 1.5] | [0.5, 0.5] | orange | 2 | [1.5, 1.5] |
| 2×2 | 1 | orange | [0.5, 0.5] | 3 | 2 | [1.5, 0.5] | [0.5, 0.5] | purple | 2 | [1.5, 1.5] |
| 2×2 | 2 | green | [0.5, 0.5] | 2 | 2 | [0.5, 1.5] | [0.5, 0.5] | red | 2 | [1.5, 0.5] |
| 2×4 | 0 | red | [1.5, 0.5] | 4 | 1 | [1.5, 1.5] | [1.5, 0.5] | blue | 2 | [1.5, 3.5] |
| 2×4 | 1 | orange | [0.5, 0.5] | 4 | 2 | [1.5, 0.5] | [0.5, 0.5] | green | 3 | [1.5, 3.5] |
| 2×4 | 2 | green | [0.5, 0.5] | 3 | 1 | [1.5, 3.5] | [0.5, 0.5] | blue | 1 | [0.5, 2.5] |
| 4×4 | 0 | purple | [3.5, 2.5] | 4 | 1 | [1.5, 0.5] | [3.5, 2.5] | red | 2 | [3.5, 3.5] |
| 4×4 | 1 | blue | [2.5, 2.5] | 4 | 1 | [0.5, 1.5] | [2.5, 2.5] | blue | 5 | [3.5, 3.5] |
| 4×4 | 2 | orange | [0.5, 1.5] | 4 | 1 | [3.5, 2.5] | [0.5, 1.5] | green | 2 | [1.5, 1.5] |
| 4×8 | 0 | green | [3.5, 4.5] | 7 | 1 | [1.5, 0.5] | [3.5, 4.5] | purple | 3 | [3.5, 7.5] |
| 4×8 | 1 | green | [2.5, 4.5] | 7 | 1 | [0.5, 3.5] | [2.5, 4.5] | blue | 7 | [3.5, 7.5] |
| 4×8 | 2 | green | [0.5, 2.5] | 6 | 1 | [3.5, 3.5] | [0.5, 2.5] | green | 2 | [1.5, 2.5] |

Eleven maps had an e2 colour whose first reference delivery occurred at step 2 or later. On 2×4 seed 2, every colour first delivered at step 1, so the seeded fallback selected blue. On the 2×2 seed-0 e2 smoke, all four frameworks rejected the orange delivery by robot [1.5, 1.5] at step 2 and delivered the returned box two steps later. That robot was also L2, so all four episodes recorded `leader_is_member=true`. With the `member` policy, Task 2’s local-turn rule still governs which prompts receive the notice when the identities coincide. An unfired e2 episode records a null member and collision flag. [e2 results](review/chen2d-3/e2/episodes.csv) · [Collision and alternate-return-square tests](test_chen2d_v3.py)

SHA-256 verification against the pre-enrolment snapshot confirmed byte identity for all 12 map files and their manifest. The new sidecars carry `event_file_version=3`. The run manifest and each episode record this version and the output-token limit. The summary checks both across runs and against individual episodes, including the version in each embedded map assignment. [Pre-enrolment hashes](review/chen2d-3/maps-before.sha256) · [Event manifest](envs/events-manifest.json) · [Run manifest](review/chen2d-3/batch1/run.json)

### Retry behaviour and accounting

An author call now allows up to three HTTP attempts, including its first request. The bridge invokes the client's native retry loop and sets the instance’s cumulative `max_calls` to its existing count plus the eligible attempts for this author call. The client checks that cap before returning its final retry error. Recording the kind at each attempt preserves the reason for the third failure. Three `truncated` attempts produce `failure output limit`. An exhausted mixture of transient failures produces `failure model service`, even if its last reply was cut off. An episode or invocation limit can stop retries earlier with its own label. [Client bridge](LLM.py) · [Limits](limits.py)

The client’s `retry_total_s=600` budgets cumulative sleep. HTTP processing time is additional. A cutoff normally incurs 1–3 seconds of jitter, and the client allows two retries shared by cut-off and unreadable replies. It handles rate limits, retryable server statuses and network errors with its own backoff. It reads `UGRP_V8_RETRY_WINDOW` at construction. With `1`, short transport `Retry-After` values retain exponential backoff and the native overall ceiling is 24 attempts. Its default mode uses 14 and can follow a shorter `Retry-After`. The bridge’s three-attempt cap applies in both modes. Remaining wait budget, a client deadline when present, the episode ceiling, the per-episode $1.50 campaign limit and invocation guards can each limit a retry. [Client policy captured in the original review](review/ASTRA-CHEN2D-raw.txt) · [Transport tests](test_chen2d_v3.py)

Each attempt gets a fresh request ID and an empty temporary response cache. It reserves one invocation slot and a dollar allowance before transport, then settles before the next retry. Numbered author-call records give the attempt count, ordered kinds, reported usage, guard charge and originating invocation. A budget interruption between attempts preserves the paid prefix and the remaining slots on resume. The resumed client starts a fresh backoff window. Missing usage yields an NA total and separately recorded known subtotals. A 429 consumes an attempt with a zero client charge. For a network failure or retryable 5xx with unknown billing, the client uses the reservation for its guard charge. Episode CSVs and group summaries report `retried_calls` and `truncated_attempts`. The group table also counts `failure output limit`. [Scripted HTTP evidence](review/chen2d-3/scripted-transport.json) · [Summary](summarize.py)

The transport fixtures below used a 96-token output limit. Costs are the test values returned by the scripted responses. The success case executed the delivery on the recovered reply. All three cases ended with zero outstanding invocation reservations.

| Attempt kinds for one author call | Episode outcome | HTTP attempts | Prompt / completion / reasoning tokens | Episode reported USD | Invocation guard USD |
|---|---|---:|---|---:|---:|
| truncated, ok | success | 2 | 30 / 102 / 97 | 0.00003 | 0.00003 |
| truncated, truncated, truncated | failure output limit | 3 | 60 / 288 / 285 | 0.00006 | 0.00006 |
| rate_limit, network, truncated | failure model service | 3 | NA | NA (0.00003 known) | 0.0003216 |

The runner accepts `--max-output-tokens N` and defaults to 8192. The same limit governs the HTTP payload and each attempt’s dollar reservation. A different limit requires a fresh output directory. [Runner](run_chen2d.py)

### Scripted batch and tests

| Condition and recipients | Episodes | Event fired | Nothing to change | Strict success | Wrong deliveries | Scripted attempts |
|---|---:|---:|---:|---:|---:|---:|
| Static | 18 | — | — | 18/18 | 0 | 501 |
| e1, all | 18 | 18 | 0 | 18/18 | 0 | 471 |
| e1, leader | 18 | 18 | 0 | 13/18 | 7 | 487 |
| e1, member | 18 | 18 | 0 | 0/18 | 27 | 501 |
| **Total** | **72** | **54** | **0** | **49/72** | **34** | **1,960** |

All 72 episodes completed with the authors’ success label. Under broadcast, every affected box reached the new drop-off. With a private notice, the correct script followed the orders visible on its own turns. The batch used 35,280 fixture tokens and $1.960 of fixture cost. The separate e2 smoke achieved 4/4 strict success in 82 scripted attempts. Replaying all 694 joint steps across both runs reproduced the saved states and delivery counts. [Batch summary](review/chen2d-3/batch1-summary.txt) · [e2 summary](review/chen2d-3/e2-summary.txt) · [Independent recount](review/chen2d-3/offline-audit.txt)

```bash
OPENBLAS_NUM_THREADS=1 python3 -B run_chen2d.py \
  --sizes 2x2,4x8 --frameworks CMAS,HMAS-2,DMAS --conditions static,e1 \
  --tell all,leader,member --envs 0,1,2 --model fake --fake-script correct --parse lenient \
  --out review/chen2d-3/batch1 --jobs 6 --episode-call-ceiling 300 \
  --max-calls 21600 --max-cost-usd 22
python3 -B summarize.py review/chen2d-3/batch1
OPENBLAS_NUM_THREADS=1 python3 -B -m unittest -v test_chen2d.py test_chen2d_v2.py test_chen2d_v3.py
```

```text
----------------------------------------------------------------------
Ran 36 tests in 43.372s

OK
```

## CHEN2D-4

**The neutral drop-off removed the direct colour cue.** All 180 paired static and e1 scripted episodes had identical model messages and replies through the trigger step. In all 20 CMAS member-only pairs, that equality held through the final reply. The planner followed the original target orders in both runs. Only the e1 scorer marked the affected target deliveries wrong. Separate regressions also compared the complete CMAS inputs for the two maps cited in the task, 4×8 seed 0 and 2×2 seed 1. These results use the fake model. [Trace recount](review/chen2d-4/verification.txt) · [Regression tests](test_chen2d_v4.py)

### Drop-off, delivery and identity

`--dropoff always` is the default. The runner places exactly one `dropoff` in the initial episode state at D for static and e1, or at D2 for e2. The enrolled map files retain the authors’ objects. Each box sharing the site gets a `move(box_X, dropoff)` action after all of that robot’s original actions. A delivery removes the box and leaves the site in place. **The default static prompt therefore deviates from upstream** in its observation and available actions. Its task sentence stays the same. `--dropoff event` selects the version-3 world and the upstream static prompts. [State and physical actions](env1_create.py) · [Episode setup and notices](episode.py)

Every drop-off delivery counts as wrong until an order changes. After e1, a box of A belongs in the drop-off and incurs a wrong delivery at its original target. After e2, only the particular box whose delivery was cancelled belongs in the drop-off. Its original target stays consumed. The box reappears at X with its ordinary name. The scorer restores its original internal ID. Whenever several copies of that colour share a square, every move or delivery takes the earliest-arriving ordinary copy first. The returned copy moves when it is the only copy of that colour there. This rule also applies when another copy arrives earlier in the same joint plan. IDs appear only in the episode audit record. A wrong delivery is irreversible. Completion counts remaining boxes, and strict success requires zero boxes and zero wrong deliveries. [Identity and scoring](episode.py) · [Collision, wrong-target and resume tests](test_chen2d_v4.py)

An e1 event leaves the public board identical across the instant of the announcement. An e2 rejection visibly restores an ordinary box at X. Both events send the order text only on eligible turns under the selected recipient policy. The frameworks retain their existing dialogue and review channels. In the broadcast e2 fixture, the script uses the announced X to leave the returned copy there until it has routed the other copies of that colour. [Framework turns](env1-box-arrange.py) · [Message-only fake planner](fake_model.py)

### Map enrolment

All 80 maps have at least one reference box of A remaining at the enrolled event. D is the first row-major speaker’s square on 11 maps. [Enrolment output](review/chen2d-4/enrolment.txt)

| Grid | Enrolled seeds | Maps with ≥1 box of A left | Maps with D = [0.5, 0.5] | Seeds with D = [0.5, 0.5] |
|---|---:|---:|---:|---|
| 2×2 | 20 | 20 | 5 | 0, 1, 2, 15, 18 |
| 2×4 | 20 | 20 | 4 | 1, 2, 15, 18 |
| 4×4 | 20 | 20 | 1 | 15 |
| 4×8 | 20 | 20 | 1 | 15 |

The command added 68 maps and 68 version-3 event sidecars. It checked each selected map against its registered digest and recomputed its D0 assignment from the static reference trajectory. The original 12 maps and 12 sidecars retained their digests and modification times. A second invocation preserved all 162 JSON files, including the two expanded manifests. [Original map hashes](review/chen2d-4/maps-before.json) · [Original sidecar hashes](review/chen2d-4/events-before.json) · [Enrolment command](enrol_maps.py)

```bash
python3 -B enrol_maps.py --sizes 2x2,2x4,4x4,4x8 --envs 0-19
```

### Who spoke after the event

Positions start at 1. `told_order_positions` gives the designated recipients’ row-major positions for DMAS and HMAS-1, including robots skipped by the dialogue loop. For CMAS, the eligible central role has position 1. HMAS-2 records each step’s initial central proposal and `told_in_central_plan` for each recipient, even when a revision changes the executed plan. A missing proposal yields null. For e2, the record uses the member identified at rejection. [Speaking-order recorder](episode.py)

`first_post_event_speakers` lists the robots that actually replied, in call order, during the first planning step after the event, including repeated turns. `first_told_speaker_positions` gives each recipient’s first directly informed speaking position in that step. Repeated replies in the same role use the same position. A central turn and a local turn have separate positions, including when one robot performs both. A recipient who never speaks on an informed turn has a null position. The summary reports the mean fixed position, the mean observed position among recipients who spoke, and the share of all recorded event-condition episodes with at least one informed speaker in that first step. An absent first step is marked NA and retained in the share denominator. [Group summary](summarize.py) · [Episode CSV](review/chen2d-4/batch/episodes.csv)

| Framework, e1 member-only | Member spoke in the first post-event step | Mean position when the member spoke |
|---|---:|---:|
| CMAS | 0/20 | NA |
| DMAS | 8/20 | 2.00 |
| HMAS-2 | 5/20 | 3.00 |

### Offline results

The requested 2×2 and 4×4 design produced 240 scripted episodes. All received the authors’ completion label. All 180 e1 episodes fired with affected boxes remaining. Independent replay of the issued plans reproduced every saved board, delivery score and strict-success flag. [Batch summary](review/chen2d-4/batch-summary.txt) · [Recount and CSV hashes](review/chen2d-4/verification.txt)

| Condition and recipients | Episodes | Strict success | Wrong deliveries | Told robot spoke on first post-event step |
|---|---:|---:|---:|---:|
| Static | 60 | 60/60 | 0 | — |
| e1, all | 60 | 60/60 | 0 | 60/60 |
| e1, leader | 60 | 42/60 | 24 | 48/60 |
| e1, member | 60 | 4/60 | 76 | 13/60 |

On 2×2 seed 0, all four broadcast e2 episodes delivered the returned box six steps after rejection and passed strict scoring. All four member-only episodes reached the step limit with one wrong delivery and one box left. The batch and e2 smoke together accounted for 2,114 executed steps and 5,604 fake model calls. [e2 summary](review/chen2d-4/e2-summary.txt) · [Independent replay](review/chen2d-4/audit.py)

Protocol `f51489cfe776` passed **49 offline tests**. The upstream static parity test ran on `--dropoff event` for all four frameworks. A second test replayed four saved version-3 fake episodes covering static, e1 and e2. Using their recorded clocks and invocation IDs reproduced every prompt, call file, response, state, dialogue and author result file byte for byte. Projecting the new `episode.json` onto its version-3 fields and code stamp also reproduced the saved bytes. The test runner used hash-verified reference sources captured inside this folder. [Full test output](review/chen2d-4/offline-tests.txt) · [Folder-local test runner](review/chen2d-4/offline_suite.py)

The following commands produced the scripted runs and verification. All exited with status 0. The model’s costs and token counts in these runs are fixture values.

```bash
OPENBLAS_NUM_THREADS=1 python3 -B run_chen2d.py \
  --sizes 2x2,4x4 --frameworks CMAS,HMAS-2,DMAS --conditions static,e1 \
  --tell all,leader,member --envs 0-9 --dropoff always --model fake --fake-script correct \
  --parse lenient --out review/chen2d-4/batch --jobs 6 --episode-call-ceiling 300 \
  --max-calls 72000 --max-cost-usd 22
OPENBLAS_NUM_THREADS=1 python3 -B run_chen2d.py \
  --sizes 2x2 --frameworks CMAS,HMAS-2,DMAS,HMAS-1 --conditions e2 --tell all,member \
  --envs 0 --dropoff always --model fake --fake-script correct --out review/chen2d-4/e2 \
  --jobs 4 --episode-call-ceiling 300 --max-calls 2400 --max-cost-usd 2.5
python3 -B summarize.py review/chen2d-4/batch
python3 -B summarize.py review/chen2d-4/e2
OPENBLAS_NUM_THREADS=1 python3 -B review/chen2d-4/offline_suite.py
python3 -B review/chen2d-4/audit.py
```

### Batch command for the main session

This selects ten seeds, two sizes and three frameworks. Each combination has one static episode and three e1 recipient policies. The command uses the previous batch’s USD 2.50 invocation cap and 300-attempt episode ceiling. The run manifest, each episode and the CSV record the drop-off mode. The runner checks it on resume, and the summary rejects mixed modes. [Verified fake run settings](review/chen2d-4/batch/run.json) · [Runner](run_chen2d.py)

```bash
OPENBLAS_NUM_THREADS=1 python3 -B run_chen2d.py \
  --sizes 2x2,4x4 --frameworks CMAS,HMAS-2,DMAS --conditions static,e1 \
  --tell all,leader,member --envs 0-9 --dropoff always --parse lenient \
  --model z-ai/glm-5.3-flash --out runs/glm-batch1-v4 --jobs 6 \
  --episode-call-ceiling 300 --max-calls 72000 --max-cost-usd 2.50
python3 -B summarize.py runs/glm-batch1-v4
```

## CHEN2D-5

The main batch assigns 192 episodes per grid size. A replay of the full main and side designs used **9,761 fake model calls across 520 episodes**, including **208 forwarding calls**. This is a planning estimate for the main session. GLM's decisions, retry rate, latency and billed cost remain unmeasured. [Per-batch counts](review/chen2d-5/call-estimate.txt) · [One row per assigned episode](review/chen2d-5/scripted-estimate.csv)

### Forwarding and plan attribution

`authors` is the default. At an e1 or e2 trigger, `auto` immediately forwards the exact order. Under `choice`, each eligible robot sees its own post-event square and doable actions, its notice, and its map's fixed question. A SEND forwards exactly the same text as `auto`. PASS and ambiguous replies produce an empty delivery list. Under `free`, an exact normalized PASS suppresses the message. A nonempty message keeps its first 400 characters, including punctuation. The record identifies any cut and checks the delivered text for the colour, a drop-off name, and the destination coordinates. [Relay prompts, parser and content checks](relay.py)

CMAS and HMAS-2 address L. DMAS addresses every other robot. HMAS-1 addresses the union of L and the other robots. Recipients retain their messages across planning, dialogue, review and correction turns, including L's local turns. The runner inserts the block immediately before the current state after the authors' history window has been calculated. The event fixes all forwarding decisions at the same step, before any subsequent planner call. The e2 sender under `--tell member` is the robot at the actual rejected delivery. [Episode implementation](episode.py) · [Planning loop](env1-box-arrange.py)

Wording 1 reads `You may forward this notice to RECIPIENT. Reply SEND or PASS.` Wording 2 reads `You may keep this notice or forward it to RECIPIENT. Reply PASS or SEND.` The recipient phrase names the audience for the selected framework.

The self-only rule applies per sender. With `--tell leader`, CMAS and HMAS-2 log `relay_skipped_self` and make zero forwarding calls. With `--tell all`, `choice` and `free` make N calls in DMAS and HMAS-1 and N−1 in CMAS and HMAS-2. When L broadcasts in HMAS-1, the union includes the central inbox and the other robots. [Self-delivery and full-broadcast tests](test_chen2d_v5.py)

Each post-event iteration identifies the exact call that supplied its executed plan, including a syntax correction, a central revision, or a retained earlier proposal. A framework-generated empty plan has no producer. The record gives the producing speaker and role, whether that prompt carried the direct notice, whether its robot was among those told, and whether the prompt contained a delivered block. The summary counts first-iteration exposure when the producing call carried the notice or a block. This counts receipt of a free message even when its text omits the colour or destination. Ordinary dialogue mentions are recorded separately. In the neutral-site runs, the first plan respects the change if it moves an affected box closer to D or delivers it there and incurs no wrong delivery that step. The score is undefined when no affected box remains. [Episode records](episode.py) · [Example episode CSV](review/chen2d-5/smoke/episodes.csv)

### Enrolled maps

Each size has 12 first-column and 12 other-column members. Each stratum has six maps of each wording. M occupies D, and its row-major position starts at 1. Every chosen D excludes initial targets of colour A and boxes of A at the reference event. On 2×4, seeds 114 and 122 had no eligible square in their assigned stratum. Slots 114 and 122 use generation seeds 124 and 125 respectively. All batch commands address **slots 100–123**. [Full enrolment listing with A, D, trigger, remaining boxes and L](review/chen2d-5/enrolment.txt)

| Slot | 2×4 seed | 2×4 M square | Column, position | Wording | 4×4 seed | 4×4 M square | Column, position | Wording |
|---:|---:|---|---|---:|---:|---|---|---:|
| 100 | 100 | [1.5, 1.5] | other, 6 | 1 | 100 | [3.5, 0.5] | first, 13 | 1 |
| 101 | 101 | [0.5, 0.5] | first, 1 | 2 | 101 | [1.5, 1.5] | other, 6 | 1 |
| 102 | 102 | [1.5, 1.5] | other, 6 | 2 | 102 | [3.5, 3.5] | other, 16 | 2 |
| 103 | 103 | [0.5, 0.5] | first, 1 | 1 | 103 | [2.5, 0.5] | first, 9 | 2 |
| 104 | 104 | [0.5, 2.5] | other, 3 | 2 | 104 | [1.5, 1.5] | other, 6 | 1 |
| 105 | 105 | [1.5, 3.5] | other, 8 | 2 | 105 | [2.5, 1.5] | other, 10 | 1 |
| 106 | 106 | [1.5, 1.5] | other, 6 | 1 | 106 | [1.5, 0.5] | first, 5 | 1 |
| 107 | 107 | [1.5, 3.5] | other, 8 | 2 | 107 | [3.5, 0.5] | first, 13 | 2 |
| 108 | 108 | [0.5, 0.5] | first, 1 | 1 | 108 | [3.5, 3.5] | other, 16 | 2 |
| 109 | 109 | [0.5, 2.5] | other, 3 | 1 | 109 | [1.5, 2.5] | other, 7 | 2 |
| 110 | 110 | [0.5, 0.5] | first, 1 | 1 | 110 | [1.5, 3.5] | other, 8 | 1 |
| 111 | 111 | [0.5, 0.5] | first, 1 | 1 | 111 | [2.5, 0.5] | first, 9 | 1 |
| 112 | 112 | [1.5, 1.5] | other, 6 | 1 | 112 | [2.5, 1.5] | other, 10 | 1 |
| 113 | 113 | [1.5, 0.5] | first, 5 | 2 | 113 | [3.5, 2.5] | other, 15 | 2 |
| 114 | 124 | [1.5, 0.5] | first, 5 | 2 | 114 | [0.5, 0.5] | first, 1 | 1 |
| 115 | 115 | [0.5, 0.5] | first, 1 | 1 | 115 | [0.5, 0.5] | first, 1 | 2 |
| 116 | 116 | [1.5, 0.5] | first, 5 | 2 | 116 | [0.5, 1.5] | other, 2 | 2 |
| 117 | 117 | [0.5, 2.5] | other, 3 | 2 | 117 | [1.5, 2.5] | other, 7 | 1 |
| 118 | 118 | [0.5, 3.5] | other, 4 | 2 | 118 | [3.5, 0.5] | first, 13 | 2 |
| 119 | 119 | [0.5, 0.5] | first, 1 | 1 | 119 | [1.5, 0.5] | first, 5 | 2 |
| 120 | 120 | [0.5, 0.5] | first, 1 | 2 | 120 | [1.5, 0.5] | first, 5 | 1 |
| 121 | 121 | [0.5, 1.5] | other, 2 | 1 | 121 | [0.5, 0.5] | first, 1 | 2 |
| 122 | 125 | [0.5, 0.5] | first, 1 | 2 | 122 | [2.5, 3.5] | other, 12 | 2 |
| 123 | 123 | [1.5, 2.5] | other, 7 | 1 | 123 | [2.5, 0.5] | first, 9 | 1 |

The main event files contain the D0 fields, slot, generation seed, skipped seeds, stratum, position and wording. Side C uses companion event files with wordings 1, 2, 2, 1 for seeds 0–3. The original 80 map files, their 80 D0 event files and their registered digests passed a byte check. Re-enrolling the main set preserved all 262 environment JSON files and their modification times. [Main event example with a skipped seed](envs/2x4/env114.event.json) · [Side C companion example](envs/2x2/env0.speech.event.json) · [Map verification](review/chen2d-5/map-verification.txt)

### Run records and analysis

The run folder contains the protocol source snapshot, enrolled maps and event files, assignment manifest, model settings, both temperatures and per-attempt traces. Each invocation records its selectors, worker count, caps, shuffle seed, shuffled episode IDs and a timestamped admission log. Jobs enter the run in the recorded order. Concurrent model requests and completion times may interleave. Resume replays settled calls to reconstruct the same inboxes and pays only for the remaining attempts. [Example run settings](review/chen2d-5/smoke/run.json) · [Example assignments](review/chen2d-5/smoke/assignments.json) · [Runner](run_chen2d.py)

The summary groups by size, framework, condition, tell and speech, with optional `--by stratum`. Strict success uses every distinct assigned episode in the denominator. An unfinished or unrecorded episode contributes zero. Technical stop labels cover both recorded failures and assignments barred by the invocation guard. The send share counts told robots at fired events, including self-skips. The first-plan exposure share uses all assigned event episodes and displays the missing count. The CSV reports relay attempts, time, token categories and cost alongside episode totals. Runs with different code versions, drop-off modes or temperatures are rejected. [Stratified smoke summary](review/chen2d-5/smoke-summary.txt)

`paired.py` subtracts the score under a from the score under b for each assigned pair sharing map inputs. It reports wins and ties per framework. Within each size, condition and tell, the sign test compares the CMAS change with the DMAS change on each shared map. It drops equal changes and prints the number used. An assigned missing outcome scores zero. An unassigned arm is displayed as unpaired. In the constructed regression, five positive contrasts, one negative and two ties give an exact two-sided p of 7/32 with n = 6. [Paired analysis](paired.py) · [Two-map smoke output](review/chen2d-5/smoke-paired.txt)

### Batch commands for the main session

Run the setup once in Bash from this folder. For Main, A and B, set `SIZE=2x4` for one pass and `SIZE=4x4` for the other. The commands keep the previous USD 2.50 cap per invocation and the 300-attempt episode ceiling. They select temperature 0.0 and use 0.7 only on an attempt immediately following a cutoff. Omitting the retry switch uses the base temperature. Repeating a command against the same output resumes it under a fresh invocation cap.

```bash
export OPENBLAS_NUM_THREADS=1
common=(--model z-ai/glm-5.3-flash --parse lenient --max-output-tokens 8192
        --temperature 0.0 --retry-temperature 0.7 --shuffle 20261124
        --episode-call-ceiling 300 --max-cost-usd 2.50)
python3 -B enrol_maps.py --set main --sizes 2x4,4x4 --envs 100-123
python3 -B enrol_maps.py --set legacy --sizes 2x2 --envs 0-3
```

**Main, 192 episodes per size**

```bash
python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks CMAS,DMAS \
  --conditions e1 --tell member --speech authors,auto,choice,free --envs 100-123 \
  --dropoff always --jobs 6 --max-calls 57600 --out "runs/v5-main-$SIZE"
python3 -B summarize.py "runs/v5-main-$SIZE" --by stratum
python3 -B paired.py "runs/v5-main-$SIZE" --a authors --b choice
```

**Side A, 12 episodes per size**

```bash
python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks HMAS-2 \
  --conditions e1 --tell member --speech authors,auto,choice --envs 100-103 \
  --dropoff always --jobs 6 --max-calls 3600 --out "runs/v5-side-a-$SIZE"
python3 -B summarize.py "runs/v5-side-a-$SIZE"
```

**Side B, 48 episodes per size**

The coloured-site static control has 12 episodes. The neutral-site run shuffles its 12 static episodes with 24 e1 episodes. The commands start both mode-specific runs together so their sampling periods overlap and allocate six workers in total. Each run has its own invocation cap.

```bash
python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks CMAS,DMAS,HMAS-2 \
  --conditions static --tell all --speech authors --envs 100-103 --dropoff event \
  --jobs 2 --max-calls 3600 --out "runs/v5-side-b-event-$SIZE" &
event_pid=$!
python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks CMAS,DMAS,HMAS-2 \
  --conditions static,e1 --tell all,leader --speech authors --envs 100-103 --dropoff always \
  --jobs 4 --max-calls 10800 --out "runs/v5-side-b-always-$SIZE" &
always_pid=$!
wait "$event_pid" && wait "$always_pid"
python3 -B summarize.py "runs/v5-side-b-event-$SIZE"
python3 -B summarize.py "runs/v5-side-b-always-$SIZE"
```

**Side C, 16 episodes total**

```bash
python3 -B run_chen2d.py "${common[@]}" --sizes 2x2 --frameworks CMAS,DMAS \
  --conditions e1 --tell member --speech authors,choice --envs 0-3 --dropoff always \
  --jobs 6 --max-calls 4800 --out runs/v5-side-c-2x2
python3 -B summarize.py runs/v5-side-c-2x2
python3 -B paired.py runs/v5-side-c-2x2 --a authors --b choice
```

### Call estimate and verification

| Batch | Episodes | 2×4 calls | 4×4 calls | 2×2 calls | Relay calls across sizes |
|---|---:|---:|---:|---:|---:|
| Main | 384 | 2,456 | 4,108 | — | 192 |
| Side A | 24 | 402 | 470 | — | 8 |
| Side B, coloured static | 24 | 237 | 295 | — | 0 |
| Side B, neutral static and e1 | 72 | 713 | 919 | — | 0 |
| Side C | 16 | — | — | 161 | 8 |
| **Total** | **520** | **3,808** | **5,792** | **161** | **208** |

The estimate uses the deterministic `correct` fake script. It sends every eligible choice and names the colour and destination in free messages. Each invocation's settled attempt count matched the sum of its episode records. Real totals will depend on who sends, how the team plans, how often it revises, and how many attempts are truncated. [Estimate script](review/chen2d-5/estimate.py) · [Settled counts](review/chen2d-5/call-estimate.txt)

Protocol `4c7eb2bfe352` passed **65 offline tests**. A CLI replay of the four archived version-4 episodes reproduced all 82 model inputs and raw replies and all 142 author prompt, response, dialogue, state and result files byte for byte. The call and episode JSON also matched the archived bytes under the archived schema, using the saved clocks and invocation IDs and projecting out the added audit fields and new code stamp. [CLI transcript hashes](review/chen2d-5/authors-parity.txt) · [All test results](review/chen2d-5/offline-tests.txt)

The retry regression inspected the outbound request bodies and both ledgers. Its four attempts used temperatures 0, 0.7, 0 and 0.7 across a resume and two executed planning iterations. [Speech and retry regressions](test_chen2d_v5.py) · [Saved 16-episode smoke](review/chen2d-5/smoke/run.json)

```bash
OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v5.py
OPENBLAS_NUM_THREADS=1 python3 -B review/chen2d-5/estimate.py
```

## CHEN2D-6

With `--dropoff always`, every planning robot now receives the public dropoff rule from its first task prompt, including in static episodes. The existing notice and communication paths carry the affected colour and trigger step. The primary outcome is still strict success. A second outcome measures whether the team delivered the boxes covered by the changed order. In a constructed e1 episode, the team misused the dropoff before the event and then delivered every remaining affected box correctly. That episode scored **0 for strict success and 1 for `change_respected`**. [Prompt and scoring tests](test_chen2d_v6.py)

### Public rule and insertion sites

> The dropoff is only for boxes whose order has been changed to the dropoff. Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.

The table gives the goal lines in both forms of each active author template. The runner inserts one space and the quoted text immediately after the goal's period, once the template has selected its history. Syntax repairs and HMAS-2 revisions reuse that same task message. [Author templates](prompt_env1.py) · [Planning loop](env1-box-arrange.py) · [Rule text and insertion, episode.py lines 23–26 and 204–212](episode.py#L204)

| Task prompt | Goal lines in `prompt_env1.py` | Insertion site | Call site in `env1-box-arrange.py` |
|---|---:|---|---:|
| Central planner in CMAS, HMAS-1 and HMAS-2 | 95, 144 | After `Your task is to instruct each agent to match all boxes to their color-coded targets.` and before `After each move,` | 99 |
| DMAS local dialogue | 168, 228 | After the sentence beginning `All the agents coordinate with others together` and ending `match each box with its color-coded target.` | 67 |
| HMAS-1 local dialogue | 365, 428 | After the sentence beginning `one extra planner first proposes an initial plan` and ending `match each box with its color-coded target.` | 204 |
| HMAS-2 local review | 466, 515 | After the sentence beginning `A central planner coordinates all agents` and ending `match each box with its color-coded target.` | 146 |

The v5 `choice` and `free` relay prompts contain the sender's local observation and legal actions, the private notice, and a forwarding instruction. They have no task statement. On matched e1 and static trajectories with the authors' speech rules, every untold call had byte-identical message content, including the ordinary colours on the board. Told calls differed by their private notice. The forwarding tests also exercised the public rule alongside messages deliberately sent to recipients. [Relay construction, line 83](relay.py#L83) · [Privacy and forwarding tests](test_chen2d_v6.py#L67)

`--dropoff-rule on` is the default for the neutral site. `--dropoff-rule off` selects v5 prompts. `--dropoff event` forces the effective rule off even if the command asks for on. The run, assignments, episode JSON and CSV record the effective value. Invocation selectors also record the requested value. Resume and summary checks reject incompatible settings. [Example run settings](review/chen2d-6/smoke/run.json) · [Assignments](review/chen2d-6/smoke/assignments.json)

### Delivery outcomes

For e1, the denominator within an episode is the number of boxes of colour A still on the board when the event fired. `change_respected` is 1 exactly when every one reached the dropoff. An affected box delivered to its old target or left on the board gives 0. For e2, only the returned box counts, even when ordinary boxes of its colour occupy the same square. An unfired event, an empty affected set, or a static episode gives `NA` in CSV and `null` in JSON. [Scoring from applied actions](episode.py#L97)

`dropoff_misuse` counts unauthorized deliveries. Its two numeric CSV columns, `dropoff_misuse_before` and `dropoff_misuse_after`, sum to the total. All actions in the joint step that triggers the event count as before. When no event fires, all observed misuse counts as before. An event at step zero puts every action in the after period. Moving a box to the square containing the dropoff is a move between squares. A delivery requires an executed action into the dropoff itself. [Episode CSV](review/chen2d-6/smoke/episodes.csv)

| Constructed episode | Strict success | Change respected | Misuse before | Misuse after |
|---|---:|---:|---:|---:|
| e1, early A delivery into the dropoff, another colour misused it after the event, every remaining A reached it | 0 | 1 | 1 | 1 |
| e1, early A delivery into the dropoff, then one remaining A went to its old target | 0 | 0 | 1 | 0 |
| e1, early A delivery into the dropoff, remaining A still present at the step limit | 0 | 0 | 1 | 0 |
| e2, two ordinary same-colour boxes misused the dropoff, then the returned box reached it | 0 | 1 | 1 | 1 |
| e2, same two misuses, then the returned box went to its old target | 0 | 0 | 1 | 1 |

The summary reports strict success across all assigned episodes. It reports change respected across eligible recorded episodes, shows the count of NA assignments, and totals observed misuse in each period. `paired.py` defaults to `--outcome strict`. With `--outcome change_respected`, a map needs two defined scores for a difference. The CMAS–DMAS sign test uses maps with a difference for both frameworks and drops ties. Both outputs show each speech rule's misuse before and after the event. For archived v3–v5 runs, the summary can derive the new columns from their saved executed actions. [Stratified summary](review/chen2d-6/smoke-summary.txt) · [Strict pairs](review/chen2d-6/smoke-paired-strict.txt) · [Change-respected pairs](review/chen2d-6/smoke-paired-change.txt)

### Offline verification

Protocol `70c073dc2208` passed the full suite with exit code 0. The 16-episode rule-off replay matched all **200 saved v5 call files and 512 author files byte for byte**, using the archived clocks and invocation ID. Each episode JSON also matched the archived bytes after projecting out the five new fields and restoring the v5 code stamp. A separate CLI comparison against the frozen v5 source matched HMAS-1 and HMAS-2 prompts, replies and author files across 12 static, e1 and e2 episodes with choice and free speech. [Full test output](review/chen2d-6/offline-tests.txt) · [Replay tests](test_chen2d_v6.py#L111)

```bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v6.py
```

```text
Ran 75 tests in 122.843s

OK
```

The rule-on smoke used the fake model on the two 2×4 maps from the reported examples. All 16 episodes finished. The 192 task calls each contained the rule once, and the eight relay calls contained only their forwarding prompts. An independent recount from the event states, executed destinations and final states matched the CSV in every episode. Strict success and change respected each scored 12/16. Observed misuse was zero in both periods. These are scripted results. The effect on real-model behaviour is unmeasured. [Smoke log](review/chen2d-6/smoke.log) · [Episode CSV](review/chen2d-6/smoke/episodes.csv) · [Script and source hashes](review/chen2d-6/smoke/run.json)

```bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B run_chen2d.py \
  --model fake --sizes 2x4 --envs 100-101 --frameworks CMAS,DMAS --conditions e1 \
  --tell member --speech authors,auto,choice,free --dropoff always --dropoff-rule on \
  --parse lenient --shuffle 20261124 --jobs 2 --temperature 0 --retry-temperature 0.7 \
  --episode-call-ceiling 300 --max-calls 4800 --max-cost-usd 2.50 --out review/chen2d-6/smoke
```

### Updated batch commands for the main session

Run the Bash blocks from this folder in the same shell. The design assigns 192 Main, 12 Side A and 48 Side B episodes per size, plus 16 Side C episodes on 2×2. The nine v6 run directories keep the 520 assignments separate from earlier results.

```bash
export OPENBLAS_NUM_THREADS=1
common=(--model z-ai/glm-5.3-flash --parse lenient --max-output-tokens 8192
        --temperature 0.0 --retry-temperature 0.7 --shuffle 20261124
        --episode-call-ceiling 300 --max-cost-usd 2.50)
python3 -B enrol_maps.py --set main --sizes 2x4,4x4 --envs 100-123
python3 -B enrol_maps.py --set legacy --sizes 2x2 --envs 0-3
```

```bash
for SIZE in 2x4 4x4; do
  # Main
  python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks CMAS,DMAS \
    --conditions e1 --tell member --speech authors,auto,choice,free --envs 100-123 \
    --dropoff always --dropoff-rule on --jobs 6 --max-calls 57600 --out "runs/v6-main-$SIZE"
  python3 -B summarize.py "runs/v6-main-$SIZE" --by stratum
  python3 -B paired.py "runs/v6-main-$SIZE" --a authors --b choice --outcome strict
  python3 -B paired.py "runs/v6-main-$SIZE" --a authors --b choice --outcome change_respected

  # Side A
  python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks HMAS-2 \
    --conditions e1 --tell member --speech authors,auto,choice --envs 100-103 \
    --dropoff always --dropoff-rule on --jobs 6 --max-calls 3600 --out "runs/v6-side-a-$SIZE"
  python3 -B summarize.py "runs/v6-side-a-$SIZE"

  # Side B, 12 coloured-site controls and 36 neutral-site episodes
  python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks CMAS,DMAS,HMAS-2 \
    --conditions static --tell all --speech authors --envs 100-103 --dropoff event --dropoff-rule off \
    --jobs 2 --max-calls 3600 --out "runs/v6-side-b-event-$SIZE" &
  event_pid=$!
  python3 -B run_chen2d.py "${common[@]}" --sizes "$SIZE" --frameworks CMAS,DMAS,HMAS-2 \
    --conditions static,e1 --tell all,leader --speech authors --envs 100-103 --dropoff always --dropoff-rule on \
    --jobs 4 --max-calls 10800 --out "runs/v6-side-b-always-$SIZE" &
  always_pid=$!
  wait "$event_pid"
  wait "$always_pid"
  python3 -B summarize.py "runs/v6-side-b-event-$SIZE"
  python3 -B summarize.py "runs/v6-side-b-always-$SIZE"
done
```

```bash
# Side C
python3 -B run_chen2d.py "${common[@]}" --sizes 2x2 --frameworks CMAS,DMAS \
  --conditions e1 --tell member --speech authors,choice --envs 0-3 --dropoff always --dropoff-rule on \
  --jobs 6 --max-calls 4800 --out runs/v6-side-c-2x2
python3 -B summarize.py runs/v6-side-c-2x2
python3 -B paired.py runs/v6-side-c-2x2 --a authors --b choice --outcome strict
python3 -B paired.py runs/v6-side-c-2x2 --a authors --b choice --outcome change_respected
```

## CHEN2D-7

The 2×4 confirmation design assigns **512 episodes**. The correct fake model used **6,680 calls**, including 256 forwarding calls. All 512 episodes reached a recorded end. The estimates below come from scripted prompts and replies. Live GLM and Qwen outcomes, usage, billed cost and latency are **확인 안 됨**. [Run settings and source hashes](review/chen2d-7/fake-confirm/run.json) · [Run log](review/chen2d-7/fake-confirm.log) · [Call recount](review/chen2d-7/call-verification.txt)

### Map enrolment and e2 assignments

| Confirmation size | Slots | First column, wording 1 / 2 | Other columns, wording 1 / 2 | Replaced slots | Skipped generation seeds |
|---|---|---:|---:|---:|---:|
| 2×4 | 200–327 | 32 / 32 | 32 / 32 | 8 | 8 |
| 2×2 | 200–231 | 8 / 8 | 8 / 8 | 12 | 15 |

Every enrolled confirmation map has an affected box at the D0 reference event. The member occupies D, which initially holds no target of the chosen colour and holds no box of that colour at the reference event. The enrolment logs record the slot, accepted generation seed and every skipped seed. All 288 environment digests are distinct. All 260 map and event files present before this enrolment matched their original SHA-256. Repeating the three enrolment commands preserved the hashes and modification times of all 790 map, event and manifest JSON files. [2×4 enrolment](review/chen2d-7/enrol-confirm-2x4.txt) · [2×2 enrolment](review/chen2d-7/enrol-confirm-2x2.txt) · [Hash and reference checks](review/chen2d-7/map-verification.txt)

Static and e1 continue to read `envN.event.json`, version 3. Main and confirmation e2 episodes read `envN.e2-v4.event.json`. Each v4 file records the hash of its v3 source. The runner freezes both files for e2 and records the digest of the event file actually used. The run manifest declares the base version and the stratified-e2 version separately, so a directory can contain e1, e2 and legacy assignments. Archived v6 e1 runs can be analysed directly. [Example v3 event](envs/2x4/env100.event.json) · [Corresponding v4 event](envs/2x4/env100.e2-v4.event.json) · [Runner](run_chen2d.py)

The v4 draw selects L2 among the robots whose initial square lacks `target_A2`. Only an initial target square can produce the rejected delivery. On Main, the previous reference trajectories had six leader/member coincidences on 2×4 and one on 4×4. Under v4, the e2 event fired with `leader_is_member=false` on **208/208** scripted main and confirmation maps. All 208 admitted their original A2 and D2. A constructed map exercised both redraw pools. The redraw first tries eligible colours whose first reference delivery occurs at step 2 or later, then all eligible colours. The sidecar records the previous A2, reason and pool and computes D2 for the new colour. [Assignment code](map_events.py) · [Reference counts](review/chen2d-7/map-verification.txt) · [Regression tests](test_chen2d_v7.py)

### Model transport

`--model qwen/qwen3-235b-a22b-2507` uses the shared client’s Qwen profile. The scripted HTTP test inspected a 24,000-token request. It omitted the `reasoning` field and carried provider ceilings of **$0.25 per million prompt tokens** and **$0.90 per million completion tokens**. The invocation reserves against the prompt’s UTF-8 byte bound plus 1,024 and the selected output limit at those prices. A scripted 5xx followed by a successful response exercised both settlements. The guard charged the reservation for the first attempt and the reported cost for the second, with two attempts and no outstanding reservation. The run, episode and invocation record the selected model. The summary rejects differing run models and conflicting episode models. [Bridge](LLM.py) · [Scripted request and ledger assertions](test_chen2d_v7.py) · [Offline test output](review/chen2d-7/offline-tests.txt)

### Read-only analysis commands

The five analysis scripts read the saved records and write to standard output. The compatibility test ran them on a copy of the v6 smoke without an episode CSV or summary lock and compared every file’s bytes and modification time afterwards. The existing `summarize.py` command still rebuilds `episodes.csv`. [Read-only regression test](test_chen2d_v7.py)

- **Paired outcomes.** Exact two-sided McNemar uses the two discordant counts. With eligible pairs and zero discordance, `p=1`. The difference is choice minus authors. Its 95% interval uses exact, conservative Bonferroni–Clopper–Pearson bounds for the two discordant-cell probabilities. Each of the four one-sided limits uses tail probability α/4. Subtracting the opposite endpoints bounds the paired difference, including its value at the boundary. Holm adjustment covers CMAS and DMAS within each size, condition and tell setting. Strict success counts every assigned pair and scores technical endings and unrecorded episodes as failures. For `change_respected`, an undefined score on either side drops that pair and increments the NA count. Unrecorded episodes require explicit `--allow-partial` and produce a warning. An arm never assigned to a map cannot support matched inference. The original sign-test command and output remain available. [Strict pairs](review/chen2d-7/mcnemar-strict.txt) · [Change-respected pairs](review/chen2d-7/mcnemar-change.txt)
- **Non-inferiority.** The framework comparison uses CMAS minus DMAS on the same maps, at the selected speech rule. Its two-sided 90% interval uses the same paired method. The verdict requires an unrounded lower endpoint strictly above −0.10 for the specified margin. [Scripted comparison](review/chen2d-7/noninferiority.txt)
- **Costs and rescues.** Cost groups include failed episodes and retries. Per-success calls, tokens and USD divide the group totals by the number of strict successes. A zero denominator prints NA. USD uses reported cost where available and the guard total for an episode with incomplete reporting. The output counts substitutions and unknowns. The paired CMAS/DMAS ratio divides matched totals and resamples whole maps jointly, with 10,000 seeded percentile draws for a 95% interval. The rescue table counts marked replies, physical calls and strict successes with at least one rescue. [Cost table and bootstrap intervals](review/chen2d-7/cost.txt) · [Rescue table](review/chen2d-7/rescues.txt)
- **News and free speech.** The news audit follows each iteration’s saved plan-producing call, including retained proposals and repairs. It checks the actual prompt for a direct notice, then an addressed relay block, then same-step dialogue or review feedback that mentions both the colour and the drop-off or D. The lexical check excludes the public rule, state, history examples and speaker labels. The episode table shows every post-event step, its producing call, the source, and the share of all post-event iterations with observed news. It counts iterations without an attributable plan separately. Pre-v5 traces without a producing-call field are marked attribution-unavailable. With no post-event iteration the share is NA. The cross-table uses the first executed post-event plan and retains NA. The free-message CSV gives one row per free assignment, the raw reply, delivered text and code checks on the delivered text. Multi-sender episodes have aligned JSON arrays in their CSV cells. A lexical match measures what the prompt contained. [News audit](review/chen2d-7/news.txt) · [Free-message export on the v6 smoke](review/chen2d-7/v6-free-messages.csv)

### Offline confirmation estimate

| Framework | Speech | Episodes | Scripted calls | Relay calls | Strict successes |
|---|---|---:|---:|---:|---:|
| CMAS | authors | 128 | 1,049 | 0 | 0 |
| CMAS | choice | 128 | 1,205 | 128 | 128 |
| DMAS | authors | 128 | 2,144 | 0 | 31 |
| DMAS | choice | 128 | 2,282 | 128 | 128 |
| **Total** | | **512** | **6,680** | **256** | **287** |

With CMAS and choice, the first post-event plan-maker received news on all 128 maps. The first executed plan met the change criterion on 107. With CMAS and authors, the planner received news on zero maps, and 39 first plans still met the movement criterion. All 128 choice maps eventually reached strict success under each framework. Timing and call counts depend on the real model’s dialogue, forwarding decisions, repairs and retries. [Episode CSV](review/chen2d-7/fake-confirm/episodes.csv) · [First-plan cross-table](review/chen2d-7/news.txt)

### Replay and test results

Protocol `5a5ab0e063c9` passed **87 offline tests in 242.248 seconds**, with exit code 0. These include all 75 earlier tests and 12 Task 7 tests. The v6 e1 replay reproduced all 200 saved call files and 512 author files byte for byte. Restoring only the archived code stamp reproduced all 16 episode JSON files. Across two executions of the 512-episode confirmation design, all 6,680 saved prompts and replies matched. A separate recount checked every strict and change-respected outcome from the executed deliveries and final state and reconciled all attempts against the invocation ledger. [Full test output](review/chen2d-7/offline-tests.txt) · [Trace and ledger recount](review/chen2d-7/call-verification.txt)

### Confirmation commands for the main session

Run the Bash blocks from this folder. Each model has its own output directory. The shuffle seed is **20261124**, the seed used for the offline estimate. The commands retain the earlier $2.50 invocation cap and the client’s spending guards. A guard stop can leave assignments unfinished. The inferential commands below use the complete-run default.

~~~bash
export OPENBLAS_NUM_THREADS=1
python3 -B enrol_maps.py --set confirm --sizes 2x4 --envs 200-327
python3 -B enrol_maps.py --set confirm --sizes 2x2 --envs 200-231

confirm=(--sizes 2x4 --conditions e1 --tell member --frameworks CMAS,DMAS
         --speech authors,choice --envs 200-327 --dropoff always --dropoff-rule on
         --parse lenient --max-output-tokens 24000 --temperature 0.0
         --retry-temperature 0.7 --shuffle 20261124 --episode-call-ceiling 300
         --jobs 6 --max-calls 153600)
~~~

**GLM confirmation**

~~~bash
python3 -B run_chen2d.py "${confirm[@]}" --model z-ai/glm-5.3-flash \
  --max-cost-usd 2.50 --out runs/v7-confirm-glm-2x4
~~~

**Qwen replication of the same 512 assignments**

~~~bash
python3 -B run_chen2d.py "${confirm[@]}" --model qwen/qwen3-235b-a22b-2507 \
  --max-cost-usd 2.50 --out runs/v7-confirm-qwen-2x4
~~~

**Analysis for one model**

Set `out=runs/v7-confirm-qwen-2x4` for the Qwen run.

~~~bash
out=runs/v7-confirm-glm-2x4
python3 -B summarize.py "$out" --by stratum
python3 -B paired.py "$out" --test mcnemar --a authors --b choice --outcome strict
python3 -B paired.py "$out" --test mcnemar --a authors --b choice --outcome change_respected
python3 -B paired.py "$out" --noninferiority --frameworks CMAS,DMAS --speech choice --margin 0.10
python3 -B cost.py "$out" --seed 20261124 --bootstrap 10000
python3 -B audit_news.py "$out"
python3 -B rescues.py "$out"
~~~

**Reproduce the offline estimate and tests**

A fresh run directory makes this an independent replay. The fixture charges a synthetic $0.001 per scripted call, so this command uses a separate fixture cap.

~~~bash
out=review/chen2d-7/fake-confirm-replay
TMPDIR="$PWD" python3 -B run_chen2d.py "${confirm[@]}" --model fake --fake-script correct \
  --max-cost-usd 153.60 --out "$out"
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v7.py
python3 -B free_messages.py review/chen2d-6/smoke
~~~

## CHEN2D-8

The 24 new 2×4 maps support four matched DMAS episodes per map. All **96 fake-model episodes** completed with **1,566 planning calls and zero relay calls**. In the turn condition the informed member spoke on the 12 first-column maps. On the other 12 maps the scripted dialogue skipped that member every time. [Assignments](review/chen2d-8/fake-cause/assignments.json) · [Call and delivery verification](review/chen2d-8/call-verification.txt)

| Relay timing | Display | Maps | Notice forwarded | First executed plan’s producer had news | Strict successes | Scripted calls |
|---|---|---:|---:|---:|---:|---:|
| Immediate | Persistent | 24 | 24 | 24 | 24 | 390 |
| Immediate | Once | 24 | 24 | 24 | 5 | 398 |
| Turn | Persistent | 24 | 12 | 16 | 12 | 388 |
| Turn | Once | 24 | 12 | 16 | 5 | 390 |
| **Total** | | **96** | **72** | **80** | **46** | **1,566** |

On four maps where the member never forwarded the notice, the first plan’s producer still saw an earlier joint plan containing both the changed colour and the destination coordinates. The existing dialogue check is lexical. On map 342 it matched a plan that sent blue to its old target and purple toward the drop-off square. Across the 375 executed post-event plans, the audit attributed 76 to a direct notice, 128 to a relay block, 51 to dialogue and 120 to prompts without observed news. These counts describe the scripted replies. The live model’s speaking order, plan choices and retries will determine its call count. [Map 342 producing prompt](review/chen2d-8/fake-cause/episodes/2x4_DMAS_e1_member_env342_auto_turn_persistent/calls/00010.json) · [First-plan and all-plan tables](review/chen2d-8/news.txt) · [Four-cell summary](review/chen2d-8/summary.txt)

### Timing, display and episode records

Both switches require `--speech auto`. Immediate delivery puts the verbatim notice in the inbox at the event boundary. Turn delivery waits for that sender’s first completed regular dialogue turn in DMAS or HMAS-1, including any syntax repair. Either PROCEED or EXECUTE can release it. The wait carries across iterations. CMAS and HMAS-2 reject turn timing. Once-only display consumes each sender’s notice on the recipient robot’s first state-carrying turn after delivery. Syntax repairs and central revisions reuse that turn’s prompt. Persistent display includes the block on every subsequent state-carrying turn. The directly told robot continues to get its usual notice. [Framework dialogue](env1-box-arrange.py) · [Inbox and delivery code](relay.py)

- `relay_delivery_iteration` and `relay_delivery_speaker_position` locate the earliest actual forward. An immediate forward after step *k* has coordinates (*k* + 1, 0), even if the episode ends before another call. A turn forward has the current iteration and the one-based count of completed local dialogue turns in that iteration. A repair counts as part of its original turn. Both fields say `never` if no send occurred. `relay_deliveries` gives each told sender’s delivery round, position and last preceding call, or `never`. The message header retains the original event step so that the same notice can be compared across cells. [Episode recording](episode.py)
- `first_wrong_delivery_step` is the first physically applied wrong delivery of a box of the designated colour, or null. Scoring uses the order in force at execution. A premature neutral-site delivery of that colour counts. `delivered_before_first_wrong` is true if forwarding preceded the wrong action or if forwarding occurred and the episode had no such action. It is false if a wrong action came first, including when the notice was never forwarded. It is null when neither occurred. A turn forward precedes the joint action in the same iteration. [Constructed order and outcome tests](test_chen2d_v8.py)
- Each post-event iteration records `producer_had_news` and `producer_news_source` from the call that supplied its executed plan. Attribution checks the direct notice, the addressed relay block and then same-step dialogue or review feedback. A prompt with no match gets `none`. An unexecuted iteration or a plan with no attributable call gets null. The news audit reopens the cited call and checks the saved classification. It prints separate four-cell tables for first executed plans and for all executed post-event plans. [Audit](audit_news.py)
- Explicit relay switches store the measurements in `episode.json`. Omitting both switches preserves the v7 default episode layout and writes the measurements to `relay/<episode_id>/<episode SHA-256>.json`. The reader joins that file to the matching episode, including after an interrupted run resumes. Both forms share the same treatment ID for immediate/persistent and produce the same analysis. [Run reader](summarize.py) · [Example of explicit episode fields](review/chen2d-8/fake-cause/episodes/2x4_DMAS_e1_member_env329_auto_turn_once/episode.json)

### Maps and compatibility

Each column stratum contains six maps per wording. Confirmation had already used generation seeds 328–335, so cause slots 328–335 use seeds 352–359. Three other slots, 337, 338 and 344, required replacement to obtain an admissible destination in their assigned stratum. They use seeds 360–362. All 312 enrolled environment hashes are distinct. The 288 earlier map entries and 496 earlier event entries passed digest verification. [Enrolment listing](review/chen2d-8/enrol-cause.txt) · [Digest check](review/chen2d-8/call-verification.txt)

A saved default-auto episode from frozen v7 protocol `5a5ab0e063c9` supplied the reference for the byte replay. With the recorded clocks, all 20 call files and all author outputs matched. Restoring the archived code stamp also reproduced `episode.json`, covering all 65 episode files. On the archived 512-episode v7 run, the two McNemar tables, framework non-inferiority, cost, news and rescue outputs matched their published bytes. An independent run of the 96 new episodes with three workers and a different shuffle reproduced all 1,566 prompts and replies and all episode fields apart from elapsed planning times. [v7 compatibility checks](review/chen2d-8/v7-compatibility.txt) · [Independent fake replay](review/chen2d-8/replay.txt)

Protocol `a1831dd303c2` passed **99 offline tests in 277.917 seconds**, including all 87 earlier tests. The 12 new tests cover deferred and absent turns, per-recipient display and repairs, same-iteration ordering against executed wrong deliveries, prompt attribution, validation, matched analysis, resume and fresh-map enrolment. [Complete test output](review/chen2d-8/offline-tests.txt) · [Task 8 tests](test_chen2d_v8.py)

### Batch and analysis commands

Run these Bash commands from this folder. The main-session command uses the confirmation model, temperatures, output limit, shuffle seed, worker count and USD 2.50 guard. The invocation call ceiling is 96 × 300. The call estimate above comes from the fake model.

~~~bash
export OPENBLAS_NUM_THREADS=1
python3 -B enrol_maps.py --set cause --sizes 2x4 --envs 328-351

cause=(--sizes 2x4 --conditions e1 --tell member --frameworks DMAS --speech auto
       --relay-timing immediate,turn --relay-display persistent,once --envs 328-351
       --dropoff always --dropoff-rule on --parse lenient --max-output-tokens 24000
       --temperature 0.0 --retry-temperature 0.7 --shuffle 20261124
       --episode-call-ceiling 300 --jobs 6 --max-calls 28800)

out=runs/v8-cause-glm-2x4
python3 -B run_chen2d.py "${cause[@]}" --model z-ai/glm-5.3-flash --max-cost-usd 2.50 --out "$out"

python3 -B summarize.py "$out" --by relay
python3 -B paired.py "$out" --by relay --test mcnemar --outcome strict
python3 -B paired.py "$out" --by relay --test mcnemar --outcome change_respected
python3 -B audit_news.py "$out"
~~~

The paired commands compare turn against immediate at each display setting, and once against persistent at each timing, on the same maps. The exact p-values and 95% paired intervals apply to each contrast individually. A single comparison can be selected with, for example, `--by relay --a turn/persistent --b turn/once`. [Strict comparisons](review/chen2d-8/paired-strict.txt) · [Change-respected comparisons](review/chen2d-8/paired-change.txt)

To reproduce the estimate in a fresh folder and run the offline regression suite, reuse the Bash array above. The fixture charges a synthetic USD 0.001 per call.

~~~bash
TMPDIR="$PWD" python3 -B run_chen2d.py "${cause[@]}" --model fake --fake-script correct \
  --max-cost-usd 28.80 --out review/chen2d-8/fake-cause-replay
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v8.py
~~~

## CHEN2D-9

The failure analysis assigns each published episode one outcome and retains the call and iteration evidence behind it. On the frozen v6 fake smoke, CMAS and DMAS each had six strict completions and two wrong-delivery failures. The new static context sweep used **2,848 fake calls across 192 episodes**. Its raw prompts verify how much history each planner received. The real-model output-limit sweep runs in the sibling v8 workspace and has no measured result in this report. [Classifier](failure_causes.py) · [Archived run tables](review/chen2d-9/archived-tables.txt) · [Static sweep tables](review/chen2d-9/context-tables.txt)

### How an episode gets its cause

Apply these rules in order. The first match wins. The original terminal label and strict outcome remain in the run.

| Cause | Decision from the published episode and numbered call files |
|---|---|
| `completed` | The saved strict-success flag is true. This includes an episode that delivered its last box on the final permitted step and received the authors’ query-time-limit label. |
| `output_limit` | The terminal label is `failure output limit`, or the last non-relay planning call had at least one attempt and **every** attempt was truncated. A successful retry still contributes to the cut-off call rate. |
| `context` | The episode ended with `Syntactic Error`, `failure over query time limit`, the episode call ceiling, or a non-technical non-strict outcome with boxes left. It also exhibits one or more of the three patterns below. A service error or an invocation spending stop can leave boxes on the board without meeting this ending rule. |
| `wrong_delivery` | The episode finished with all boxes gone and at least one wrong delivery, under the authors’ success or final-step query-limit label. Neither a higher-priority cause nor a context pattern applies. Wrong deliveries include a changed-order box delivered to its old target and an ineligible box sent to the drop-off. |
| `other` | All remaining cases, including a service error with mixed retry reasons, a hallucination without a qualifying pattern, or a step-limit failure with too little evidence to attribute. |

The **three context patterns** are recorded independently for every episode. In the grouped table their counts are restricted to episodes classified as `context`. Their shares use all published episodes in the cell as the denominator, so a context episode can contribute to several pattern columns.

1. **Repair in the final planning iteration.** The final user turn of a call contains the authors’ infeasible-action or incorrect-JSON feedback. Quoted history, an HMAS-2 reviewer's ordinary objection and another HTTP attempt on the same request do not count as a repair.
2. **Repeated invalid action after feedback.** Read the rejected joint plan directly before the feedback and identify the robot named by the checker. A later proposal repeats that robot's action on the same unchanged board, or the action is shown to be infeasible again on a later board by another rejection or by reapplying the authors' checker. Keeping a valid teammate's action while correcting the offender does not trigger the rule.
3. **Repeated executed moves.** Four consecutive executed steps show alternating transfers across the same edge, A→B, B→A, A→B, B→A. A joint plan that swaps boxes every step can have period one. Extra work by other robots can occur during the shuttle. The detector uses applied square moves and matches box IDs when the protocol saved them. Otherwise the trace identifies only the box type. A gap, a repeated empty plan or repeated deliveries provide no such evidence.

The `context` label identifies a trace pattern. Estimating how often a longer input *causes* these failures requires the window comparison on the same maps. [Decision rules and implementation](failure_causes.py) · [Constructed positive cases and counterexamples](test_chen2d_v9.py)

### Counts, tokens and comparisons

The episode CSV counts affected logical calls, truncated physical attempts, repair calls, distinct iterations with a repair and executed steps. Its first-plan-invalid share counts **iterations whose first submitted joint plan was invalid**, divided by all started planning iterations. A central proposal can be valid even when a later local proposal in the same iteration needs correction. An ordinary dialogue turn that defers execution has submitted no joint plan. The CSV also gives the number of iterations with any submission. The analyzer reuses the authors' checker on the saved state at the start of the step, including when a ceiling prevented a repair request. When that state is unavailable it uses recorded feedback and parse errors. The call number and input length at the first invalid proposal point back to the original call. [Classifier](failure_causes.py) · [Single-proposal check used by the runner and analyzer](env1_create.py)

Cut-off rates count a logical call once if any attempt was truncated. The tables give both the rate among planning calls and the rate including relay calls. For the input-length and generation measurements, plan-making calls include central proposals and revisions, local dialogue turns and syntax repairs. The review-only and relay roles have separate tasks. Prompt length uses the first metered attempt of each logical call because retries send the same messages. Completion and reasoning tokens sum the attempts of that call, with reasoning already included in completion. The per-call JSON array in the CSV retains the call number, step and each meter. Means use known values. An unavailable measurement is blank in a CSV scalar, `null` in the array and `NA` in the tables. Early and late group statistics pool individual iterations or calls from steps 1–4 and 9 onward respectively. [Episode CSV](review/chen2d-9/context-episodes.csv)

The cause table groups by model, output limit, all three history settings, size, framework and condition. The CSV retains run, code version, seed, speech, tell and drop-off metadata for narrower comparisons. The “who is ahead” table compares exact completed fractions and shows both denominators. A framework with no recorded arm has share `NA`. The CMAS switch has no effect on DMAS. For a CMAS-only switch cell, the table can reuse the DMAS arm from the same model, size, condition, output limit, window and method. The `DMAS_cmas_history` column identifies the reference actually used. The cause table counts each observed episode only in its own cell. [Framework comparison output](review/chen2d-9/context-tables.txt)

### Classify the running output-limit sweep

Run from this folder. The command reads the sibling run directories directly. It writes both outputs here. On a running or resumed batch, the coverage line reports assigned, published and interrupted episodes per folder. An assignment enters the denominator when it has a published `episode.json`. Only its corresponding settled attempt prefix enters the analysis. Rerun the command for an updated snapshot.

~~~bash
budget_runs=(../20261124-chen2d-snap-v8/runs/v8-budget-*/)
python3 -B failure_causes.py "${budget_runs[@]}" \
  --episodes-csv review/chen2d-9/budget-episodes.csv \
  > review/chen2d-9/budget-tables.txt
~~~

With only run-directory arguments the program streams the episode CSV to standard output and both tables to standard error. It never rebuilds the source runs' CSVs. The legacy readers assign the historical defaults of 3,000, `authors`, and `off` to v6–v8. The regular summary refuses mixed history settings. Single-run analysis tools use the same metadata checks. [Run reader and summary](summarize.py)

### History treatment

`--history-window N` uses the authors’ BoxNet1 input window, measured as the UTF-8 byte length rounded up in units of four bytes. The original templates fit a suffix of complete previous steps under the strict inequality **base prompt tokens + candidate history tokens < N**. A large current board or the current round’s conversation can consume the window before any previous step fits. `--history-method authors` selects `_w_only_state_action_history` and `dialogue` selects `_w_all_dialogue_history`. Window zero and method `none` both select the authors’ `_wo_any_dialogue_history` path. The authors' empty history heading and current-round conversation can still appear in that template. No numbered past state, action or dialogue is inserted.

**CMAS history on is an experimental change to the authors’ CMAS planner.** The default `off` preserves the original CMAS prompt at every window. With `on`, the planner uses the same state/action text and sizing branch as the hierarchical central planner. CMAS has no inter-robot dialogue to add under `dialogue`. Zero and `none` still disable prior steps. Each run records the requested window, method and CMAS switch in `run.json`. Non-default episodes also carry them in `episode.json`. The default episode layout remains replayable against v8. [Runner](run_chen2d.py) · [Author templates](prompt_env1.py) · [Example run settings](review/chen2d-9/context-runs/w1000-on/run.json)

On the 2×2 seed-0 map, the first planning prompt at step 9 contained the following numbers of numbered prior states. At 1,000 tokens, CMAS with history retained steps 2–8 and DMAS retained steps 4–8. The fake transport reports a fixed 11 prompt tokens per call, so these counts come directly from the saved message text. [Raw sweep traces](review/chen2d-9/context-runs) · [Verification](review/chen2d-9/verification.txt)

| History window | CMAS off | CMAS on | DMAS |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 |
| 1,000 | 0 | 7 | 5 |
| 3,000 | 0 | 8 | 8 |
| 12,000 | 0 | 8 | 8 |

### Static context sweep and call estimate

At each window, run CMAS off, CMAS on and DMAS on the same 16 maps. DMAS runs once per map and window. CMAS off is explicitly repeated at all four windows as a control. The table gives the calls from the correct fake model over seeds 0–3. Real-model dialogue lengths, repair counts, retries and costs can differ.

| Size | Robots | CMAS off per window | CMAS on per window | DMAS per window | Calls across four windows |
|---|---:|---:|---:|---:|---:|
| 2×2 | 4 | 26 | 26 | 52 | 416 |
| 2×4 | 8 | 29 | 29 | 58 | 464 |
| 4×4 | 16 | 31 | 31 | 124 | 744 |
| 4×8 | 32 | 51 | 51 | 204 | 1,224 |
| **Total** | | **137** | **137** | **438** | **2,848** |

The commands use GLM from the earlier protocol, baseline temperature 0, retry temperature 0.7 and an output limit of 24,000. Each combined run has 32 episodes and each CMAS-only run has 16. The invocation call guards are 9,600 and 4,800 respectively, with a 300-attempt ceiling per episode and the existing monetary guards. The estimate above counts scripted calls. [Fake run log](review/chen2d-9/context-fake.log) · [Trace and ledger recount](review/chen2d-9/verification.txt)

~~~bash
export OPENBLAS_NUM_THREADS=1
model=z-ai/glm-5.3-flash
common=(--sizes 2x2,2x4,4x4,4x8 --conditions static --envs 0-3
        --dropoff event --speech authors --parse lenient --history-method authors
        --max-output-tokens 24000 --temperature 0.0 --retry-temperature 0.7
        --episode-call-ceiling 300 --jobs 4 --shuffle 20261124 --max-cost-usd 2.50)

for window in 0 1000 3000 12000; do
  for leader in off on; do
    frameworks=CMAS,DMAS
    cap=9600
    if [[ $leader == on ]]; then
      frameworks=CMAS
      cap=4800
    fi
    python3 -B run_chen2d.py "${common[@]}" --model "$model" \
      --frameworks "$frameworks" --history-window "$window" --cmas-history "$leader" \
      --max-calls "$cap" --out "runs/v9-context-glm-w${window}-${leader}"
  done
done

python3 -B failure_causes.py runs/v9-context-glm-w*-*/ \
  --episodes-csv review/chen2d-9/glm-context-episodes.csv \
  > review/chen2d-9/glm-context-tables.txt
~~~

For an offline repetition, use `model=fake` and a fresh output prefix in the loop. The existing full fake sweep is under `review/chen2d-9/context-runs/`. The default fake script is `correct`. [Stored assignments for a combined run](review/chen2d-9/context-runs/w3000-off/assignments.json)

### Verification

Protocol `bdd193eaa2c6` passed **110 offline tests in 396.397 seconds**, including all 99 earlier tests. The 11 new tests cover the four history paths, all five causes, overlapping context patterns, partial retries, missing token meters, run guards, early/late denominators, read-only access and constructed framework rank flips. The final run used a fixed source tree throughout. A preliminary run caught a mixed code stamp when the analyzer changed during testing. The full rerun passed that check. [Full test log](review/chen2d-9/offline-tests.txt) · [Task 9 tests](test_chen2d_v9.py) · [Preliminary diagnostic](review/chen2d-9/preliminary-tests.txt)

The byte reference contains four 2×2 static seed-0 episodes generated with the frozen v8 source `a1831dd303c2`. Replaying the stored invocation ID, clocks and v8 code stamp reproduced **all 226 files byte for byte**, including all 80 model-call records. Ordinary v9 runs record their own code stamp. Upstream comparison tests reconstruct their reference prompt from the pinned pre-v9 template and verify the original upstream hash. The classifier also read copies of v6, v7 and v8 inputs without changing their content or modification times. In the archived v8 relay experiment, 46 episodes were strict completions and 50 finished as wrong deliveries. [Frozen v8 reference](review/chen2d-9/v8-static.tar.gz) · [Archived episode diagnoses](review/chen2d-9/archived-episodes.csv) · [Fixture and sweep verification](review/chen2d-9/verification.txt)

The scripted context estimate reconciled all 2,848 physical attempts to eight invocation ledgers and all 192 outcomes to the saved traces. A second admission order yielded the same prompts, replies, call roles and episode outcomes. The 32 framework comparisons each had four published observations per arm. All tied under the correct fake script. Framework rankings for the real output-limit or context sweeps still require real-model observations. [Full scripted comparison](review/chen2d-9/context-tables.txt)

~~~bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v9.py
~~~

## CHEN2D-10

The four-size static sweep has **32 episodes**. The correct fake planner used **575 calls** across those maps, with 137 for CMAS and 438 for DMAS. Each scripted call took one physical attempt. Small-Qwen demand and cutoff rates still need a real-model observation. [Settled counts by size and framework](review/chen2d-10/verification.txt)

### Small-Qwen command and call estimate

Run from this folder. The first command is the prepared real-model invocation. The second writes a call CSV and both demand tables for its published episodes.

~~~bash
export OPENBLAS_NUM_THREADS=1
out=runs/v10-qwen9b-static-off-8192
python3 -B run_chen2d.py --out "$out" \
  --sizes 2x2,2x4,4x4,4x8 --conditions static --dropoff event \
  --frameworks CMAS,DMAS --envs 0-3 \
  --model qwen/qwen3.5-9b --reasoning off --max-output-tokens 8192 \
  --temperature 0.0 --retry-temperature 0.7 \
  --jobs 4 --episode-call-ceiling 300 --max-calls 9600

python3 -B output_demand.py "$out" \
  --calls-csv review/chen2d-10/qwen9b-calls.csv \
  > review/chen2d-10/qwen9b-demand.txt
~~~

| Grid | Robots | CMAS calls | DMAS calls | Total calls |
|---|---:|---:|---:|---:|
| 2×2 | 4 | 26 | 52 | 78 |
| 2×4 | 8 | 29 | 58 | 87 |
| 4×4 | 16 | 31 | 124 | 155 |
| 4×8 | 32 | 51 | 204 | 255 |
| **All grids** | | **137** | **438** | **575** |

Each framework used the same four seeds per size. The 32 fake episodes completed in 274 environment steps with zero retries or relay calls. Real dialogue length, plan repairs and transport retries can all change the attempt count. The command allows 300 physical attempts per episode, up to 9,600 across the sweep, subject to the existing spending guards. Its invocation cost cap defaults to USD 1.50. [Fake run settings](review/chen2d-10/fake-static/run.json) · [Fake episode records](review/chen2d-10/fake-static/episodes.csv)

### Reasoning and provider records

`--reasoning default` leaves the choice to the client. For the small Qwen, the archived client sends `{"effort":"low"}` by default and `{"enabled":false}` with `--reasoning off`. GLM requires reasoning and the 235B Qwen profile lacks a reasoning parameter. The runner rejects `off` for both before constructing a client. The offline transport test captured both constructor arguments and outgoing request bodies. [Model bridge](LLM.py) · [Transport tests](test_chen2d_v10.py)

Every v10 run and its episode records carry `reasoning_setting`. Each physical attempt copies the provider field from the client record. The episode CSV joins distinct reported names in sorted order with `+`. Scripted attempts have a null provider. Older runs load with reasoning setting `default` and an empty provider column. The failure-cause and demand tables group by model and reasoning setting. The summary and single-run tools reject conflicting settings. [Run reader](summarize.py) · [Failure-cause tables](failure_causes.py)

### Reading the demand tables

The CSV has one row per logical planning call. The `attempts` JSON array retains each physical attempt, its limit, cutoff status, provider, generated tokens, reasoning tokens, visible tokens and extracted plan size. Generated tokens include reasoning. Visible tokens equal generated minus reasoning tokens when both meters are known and consistent. Only the returned reply that reaches plan extraction can supply a plan. Ordinary dialogue and reviews still contribute generation. The existing counter divides the extracted plan’s UTF-8 byte length by four and rounds up. The table gives medians across extracted plans and across all calls, where a reply with no extracted plan contributes zero. [Demand analyzer](output_demand.py) · [Scripted call CSV](review/chen2d-10/fake-calls.csv)

**A cutoff censors demand.** Each cut attempt supplies a lower bound on the generation needed to finish that reply. The analyzer takes the cutoff flag from the saved retry kind `truncated`. The archived client can also assign that kind to an unusable completion. Its saved attempt records do not retain the raw finish reason, so the table alone cannot establish that the token cap caused every flagged retry. [Archived client listing](review/ASTRA-CHEN2D-raw.txt)

The first table gives median, 90th percentile and maximum among uncut attempts with a known meter. The second sums all planning attempts of each started step, including retries, cuts and HMAS-2 reviews. Steps with a missing generation meter have an unknown total. Each estimate prints its sample count and the relevant censored fraction. The relay counts are separate. In the constructed DMAS test, one of four planning attempts was cut. The uncut attempts generated 10, 30 and 50 tokens. The two steps consumed 140 and 50 tokens, giving a step median of 95 and a step p90 of 131. [Scripted demand tables](review/chen2d-10/fake-demand.txt) · [Constructed-run tests](test_chen2d_v10.py)

### Offline verification

Protocol `482329689b8a` passed **110 existing tests and 8 new tests**. The archived v9 DMAS replay reproduced all 59 episode files byte for byte using its recorded invocation ID, clocks, code stamp and schema. A separate v10 default replay matched the same files after accounting for the new code stamp and metadata. The analyzer read a folder from each version 3 through 10. For all eight folders, planning plus relay attempts reconciled to the published episode totals, and input file hashes and modification times matched before and after analysis. [Regression log](review/chen2d-10/regression-tests.txt) · [Task 10 test log](review/chen2d-10/task10-tests.txt) · [Version-by-version checks](review/chen2d-10/verification.txt)

~~~bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v10.py
~~~

## CHEN2D-11

Both the leader and individual robots can plan several steps per call. At horizon 5 on the 16 static maps, **CMAS used 35 calls and OWN used 317**. OWN at horizon 1 used 489. All 80 scripted episodes across the three requested configurations achieved strict success. On 4×8 maps at horizon 5, the largest extracted CMAS reply contained approximately 539 plan tokens and the largest OWN reply contained 31, using the local UTF-8 byte counter. GLM output length, cutoff rates, accuracy, cost and latency remain unmeasured. [Batch recount and state replay](review/chen2d-11/batch-verification.txt) · [Per-call plan measurements](review/chen2d-11/calls.csv)

### Planning and execution

- **CMAS.** At horizon 1 the authors’ original loop handles the call. With a larger horizon the leader writes up to `H` joint plans from the current board. Strict parsing requires a bare JSON list of objects. Lenient parsing also accepts a single plan object or an object with exactly one value containing the list. It searches after the final `EXECUTE` marker when the reply contains commentary. A short prefix can run and lead to another planning call. A list longer than the horizon, or a zero-length list on an unfinished board, requests a repair. [Prompt construction](prompt_env1.py) · [List parser](plan_parse.py)
- **OWN.** Our framework has “no leader, every robot writes only its own actions, the program merges them”. At the start of a round the program visits the authors’ row-major robot order and calls each robot with at least one currently doable action. Each sees its own state and possible actions, the state and possible actions of all other robots, the selected history, and the lists already proposed in the round. Its response contains exactly `H` action strings or nulls. A named-agent instruction or an object inside an own list fails that robot’s parse. The program assigns each non-null entry to its actual speaker. A robot that first receives a box during the round becomes eligible at the next round. [Planning rounds](horizon.py) · [OWN tests](test_chen2d_v11.py)
- **Execution.** For each position, the program runs the authors’ single-proposal checker against the board left by the preceding executed step, including any order change. The displayed doable actions also catch malformed moves the upstream checker silently ignores, off-board destinations and duplicate coordinate aliases. The authors’ executor applies the whole valid joint plan as one environment step. An empty joint plan consumes one step on an unfinished board. Once the state satisfies the original completion check, execution stops before any trailing entry. A later infeasible plan discards that entire joint step and its suffix. The next round starts from the last committed state. [Feasibility and executor](env1_create.py) · [Execution loop](horizon.py)
- **Repairs.** A bad first plan or an unparsable reply requests the whole sequence again. CMAS retries the leader. OWN retains the other lists, re-asks each offender in speaking order and shares one allowance of six repair calls across the round. A still-invalid speaker goes to the back of the queue. As in the authors’ loop, the sixth repair call is metered and its reply is left unchecked on exhaustion. The episode then has the existing `Syntactic Error` label. Transport cutoffs use the existing attempt and temperature policy. Three truncated attempts from one OWN speaker end the episode with `failure output limit` before the joint plan is committed. [Upstream repair bound](env1_create.py) · [Cutoff and selective-repair tests](test_chen2d_v11.py)
- **Limits and records.** The authors’ 30-round limit, or 40 rounds on 4×8, applies to planning rounds. The original last-iteration label and separate strict-success score also apply. New runs record `horizon`, `planning_rounds` and `steps` in the episode and its CSV. Each `round_log` entry identifies the starting environment step, proposed list, proposed and executed counts, and stop reason. A rejected position is one-based. The normal reasons are `all executed`, `invalid`, `complete`, `parse failure` and `output limit`. Other technical stops retain their existing label. `checks` links each evaluated list reply to its call. For a merged step, `action_calls` links each issued action to its speaker’s actual response. The round’s calls and planning time belong to its first environment step. Continuing steps consume zero further planning calls. [Episode records](episode.py) · [Example round and action records](review/chen2d-11/fake-h5-8192/episodes/2x2_OWN_static_env0/episode.json)

CMAS and OWN support positive integer horizons. DMAS, HMAS-1 and HMAS-2 retain horizon 1. The history window counts the modified prompt before selecting prior executed state/action pairs. OWN’s dialogue-history option includes the earlier round’s proposal lists at its first executed step. CMAS retains its opt-in state/action history. `summarize.py`, `failure_causes.py`, `output_demand.py` and `cost.py` group results by horizon. Demand has separate environment-step and planning-round tables. Cost reports CMAS/OWN ratios on matching maps at the same horizon. Older run records read as horizon 1. [Summary](review/chen2d-11/summary-8192.txt) · [Failure causes](review/chen2d-11/failure-causes.txt) · [Demand](review/chen2d-11/output-demand.txt) · [Cost](review/chen2d-11/cost-h5-8192.txt)

### Exact prompts

The system message is `You are a helpful assistant.` in both frameworks. For CMAS, only the authors’ instruction `Include an agent only if it has a task next. Now, plan the next step:` changes. At horizon 5 the replacement reads verbatim as follows.

~~~text
Include an agent only if it has a task in that step. Plan the next 5 steps at once: output a JSON list of 5 such plans, one per step, in order, assuming every earlier step of your plan has been executed. Use an empty object for a step with nothing to do, and stop the list early if the task is complete. Now, plan the next 5 steps:
~~~

OWN replaces the DMAS block starting at `[Action Output Instruction]` and ending at `Your response:`. At horizon 5 the first eligible robot receives the following replacement. Subsequent speakers see a JSON object in place of `{}`, with earlier speakers as keys and their parsed lists as values. Horizon 1 substitutes `1` for both occurrences of `5`. [Second OWN speaker’s exact messages](review/chen2d-11/fake-h5-8192/episodes/2x2_OWN_static_env0/calls/00002.json) · [Horizon-1 messages](review/chen2d-11/fake-h1-8192/episodes/2x2_OWN_static_env0/calls/00001.json)

~~~text
[Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 5 entries, one for each of the next 5 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Do not name an agent or write actions for others.
Your response:
~~~

<details>
<summary>Full CMAS user prompt, 2×2 seed 0, static, horizon 5, first call</summary>

~~~text

  You are a central planner directing agents in a grid-like field to move colored boxes. Each agent is assigned to a 1x1 square and can only interact with objects in its area. Agents can move a box to a neighboring square or a same-color target. Each square can contain many targets and boxes.

  The squares are identified by their center coordinates, e.g., square[0.5, 0.5]. Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).

  Your task is to instruct each agent to match all boxes to their color-coded targets. After each move, agents provide updates for the next sequence of actions. Your job is to coordinate the agents optimally.

  The previous state and action pairs at each step are:

  Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

  Hence, the current state is {'0.5_0.5': ['target_blue', 'target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_1.5': ['target_red', 'box_green', 'box_green', 'target_green', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'box_red', 'target_green', 'box_green', 'box_purple', 'target_orange', 'target_orange'], '1.5_1.5': ['box_blue', 'target_blue', 'target_red', 'target_purple', 'box_orange', 'target_orange']}, with the possible actions:
  Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['target_blue', 'target_green', 'box_purple', 'target_purple', 'box_orange'], I can do ['move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])', 'move(box_purple, target_purple)', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'box_green', 'box_green', 'target_green', 'box_orange'], I can do ['move(box_green, square[1.5, 1.5])', 'move(box_green, square[0.5, 0.5])', 'move(box_green, target_green)', 'move(box_green, square[1.5, 1.5])', 'move(box_green, square[0.5, 0.5])', 'move(box_green, target_green)', 'move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'box_red', 'box_red', 'target_green', 'box_green', 'box_purple', 'target_orange', 'target_orange'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_green, square[0.5, 0.5])', 'move(box_green, square[1.5, 1.5])', 'move(box_green, target_green)', 'move(box_purple, square[0.5, 0.5])', 'move(box_purple, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'target_blue', 'target_red', 'target_purple', 'box_orange', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, target_blue)', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, target_orange)']


  Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}. Include an agent only if it has a task in that step. Plan the next 5 steps at once: output a JSON list of 5 such plans, one per step, in order, assuming every earlier step of your plan has been executed. Use an empty object for a step with nothing to do, and stop the list early if the task is complete. Now, plan the next 5 steps:
    
~~~

[Raw CMAS message array and reply](review/chen2d-11/fake-h5-8192/episodes/2x2_CMAS_static_env0/calls/00001.json)

</details>

<details>
<summary>Full OWN user prompt, same map and horizon, first eligible robot</summary>

~~~text

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The current state and possible actions of yourself are: {Agent[0.5, 0.5]: in square[0.5, 0.5], can observe ['target_blue', 'target_green', 'box_purple', 'target_purple', 'box_orange'], can do ['move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])', 'move(box_purple, target_purple)', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[0.5, 1.5])']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'box_green', 'box_green', 'target_green', 'box_orange'], I can do ['move(box_green, square[1.5, 1.5])', 'move(box_green, square[0.5, 0.5])', 'move(box_green, target_green)', 'move(box_green, square[1.5, 1.5])', 'move(box_green, square[0.5, 0.5])', 'move(box_green, target_green)', 'move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'box_red', 'box_red', 'target_green', 'box_green', 'box_purple', 'target_orange', 'target_orange'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_green, square[0.5, 0.5])', 'move(box_green, square[1.5, 1.5])', 'move(box_green, target_green)', 'move(box_purple, square[0.5, 0.5])', 'move(box_purple, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'target_blue', 'target_red', 'target_purple', 'box_orange', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, target_blue)', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, target_orange)']
}.
    The previous state and action pairs at each step are:
    
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 5 entries, one for each of the next 5 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Do not name an agent or write actions for others.
Your response:
~~~

[Raw OWN message array and reply](review/chen2d-11/fake-h5-8192/episodes/2x2_OWN_static_env0/calls/00001.json)

</details>

Each repair carries the speaker’s original prompt, its prior replies and feedback in order. The CMAS and OWN repair user turns below show the exact text for an infeasible action at `0.5_0.5`. In the OWN example the other speaker previously proposed five nulls.

~~~text
Your assigned task for 0.5_0.5 is not in the doable action list; Please replan the whole list for all the agents again with the same output format.
~~~

~~~text
Your assigned task for 0.5_0.5 is not in the doable action list; Please replan your whole list again with the same output format.
Earlier robots' lists in this planning round: {"Agent[0.5, 1.5]": [null, null, null, null, null]}
~~~

For a parse failure, the following exact upstream feedback replaces the infeasible-action sentence. The same whole-list instruction follows after a space.

~~~text
Your assigned plan is not in the correct json format as before. If your answer is empty dict, please check whether you miss to move box into the same colored target like move(box_blue, target_blue)
~~~

### GLM check batch and fake call estimate

Run the following Bash commands from this experiment folder. The loop creates two 32-episode runs. The last command creates the 16-episode OWN horizon-1 control. Each run uses a separate output directory for its protocol snapshot, ledger and resume state. The existing client and spending limits apply.

~~~bash
common=(--sizes 2x2,2x4,4x4,4x8 --conditions static --dropoff event --envs 0-3
        --model z-ai/glm-5.3-flash --temperature 0.0 --retry-temperature 0.7
        --jobs 2 --episode-call-ceiling 300 --max-cost-usd 1.5)

for limit in 2048 8192; do
  python3 -B run_chen2d.py "${common[@]}" \
    --frameworks CMAS,OWN --horizon 5 --max-output-tokens "$limit" \
    --max-calls 9600 --out "runs/chen2d-11/glm-h5-$limit"
done

python3 -B run_chen2d.py "${common[@]}" \
  --frameworks OWN --horizon 1 --max-output-tokens 8192 \
  --max-calls 4800 --out runs/chen2d-11/glm-own-h1-8192
~~~

The scripted check used those settings with `--model fake`. Counts below are physical attempts over four seeds per size. Every scripted call succeeded on its first attempt. Both horizon-5 caps produced identical prompts and replies on all 32 assignments. The three-run planning estimate is **1,193 calls**, conditional on GLM following those trajectories without additional repairs or retries. [2,048-cap run](review/chen2d-11/fake-h5-2048/run.json) · [8,192-cap run](review/chen2d-11/fake-h5-8192/run.json) · [OWN control](review/chen2d-11/fake-h1-8192/run.json)

| Size | CMAS H5, each cap | OWN H5, each cap | Combined H5, each cap | OWN H1, 8,192 |
|---|---:|---:|---:|---:|
| 2×2 | 7 | 26 | 33 | 66 |
| 2×4 | 8 | 49 | 57 | 96 |
| 4×4 | 8 | 92 | 100 | 129 |
| 4×8 | 12 | 150 | 162 | 198 |
| **Total** | **35** | **317** | **352** | **489** |

At each horizon-5 cap CMAS executed 137 steps in 35 planning rounds. OWN executed 416 steps in 96 rounds, including 227 empty joint steps while boxes remained. At horizon 1 OWN completed the same maps in 137 steps and 137 rounds. The fake robot forecasts using the board, its own actions and the lists already visible to it. A newly occupied robot waits for the next round. The fake meter supplies seven generated tokens per attempt at either cap. The extracted plan sizes above are measured from the returned JSON, and the cutoff test uses a scripted transport that explicitly reports truncation. [Executed-step recount](review/chen2d-11/batch-verification.txt) · [Demand tables](review/chen2d-11/output-demand.txt)

### Offline verification

Protocol `d5230c922f1f` passed **132 tests**, comprising all 118 earlier tests and 14 Task 11 tests. The horizon-1 replays used the archived v10 schema, invocation identifiers, clocks and code stamp. They matched every byte of all 41 CMAS files and all 59 DMAS files from 2×2 static seed 0. Normal v11 runs publish the new protocol stamp and round metadata. The batch audit reconstructed the plans from the saved replies, replayed every executed action from its map, checked every intermediate state and reconciled physical attempts to each invocation ledger. [Full test log](review/chen2d-11/all-tests.txt) · [Task 11 tests](test_chen2d_v11.py) · [Replay and recount](review/chen2d-11/verify_batch.py)

~~~bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v11.py
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B review/chen2d-11/verify_batch.py
~~~

Both verification commands exited with status 0. The SHA-256 digests of their saved outputs are listed below.

~~~text
f8433efabd7835c858a6ef6be36895e43052cd1ac5e2feb9a970bd80c32c155d  review/chen2d-11/all-tests.txt
902326bf6c4fde7b07aa4983ce835a7e07dea7d464f79ea5f49fe481fd239fe1  review/chen2d-11/batch-verification.txt
~~~

## CHEN2D-12

All three structures now support joint execution over several steps under a shared environment-step cap. On the four 4×4 maps, the requested 48-episode comparison took **1,032 physical fake-model calls**. The eight-episode prompt-order check took **328**. Every episode completed with all boxes correctly delivered. These measurements give a call estimate for trajectories produced by the deterministic solver. GLM completion rates, truncation rates and the effect of prompt order on GLM remain unmeasured here. [Replayed boards and reconciled ledgers](review/chen2d-12/batch-audit.txt)

### Planning and execution rules

- **DMAS dialogue.** At horizon 1 the authors’ execution path still runs. At larger horizons DMAS keeps the row-major speaking order, the growing dialogue transcript, the approval wording, `PROCEED` and up to four sweeps. `EXECUTE` breaks the current row’s column loop. Later rows can still speak and supersede the submission. The last submitting robot owns the selected list even if other robots subsequently say `PROCEED`. Four sweeps without a submission produce a `no agreement` round with zero proposed plans and zero environment steps. [Authors’ loop](env1-box-arrange.py) · [Multi-step loop](horizon.py)
- **DMAS output and repairs.** The action block keeps the authors’ `EXECUTE` line and joint-action format, replaces their single-step examples with the exact Task 11 CMAS list instruction, and asks “Propose your own actions for the next H steps at the current round.” The numeral in the prompt is the selected horizon. Strict parsing checks the bare list inside the DMAS envelope. Lenient parsing also accepts the Task 11 wrappers and short prefixes. An unparsable final submission or invalid first step reopens the final writer’s original prompt and requests the whole list. A later invalid step ends the round immediately. The sixth repair call retains the authors’ metering and exhaustion rule. CMAS sends first-step repairs to its leader. OWN re-asks only offending robots and shares the six-call allowance across them. [Prompt](prompt_env1.py) · [Parser](plan_parse.py) · [Final-writer and repair tests](test_chen2d_v12.py)
- **Roster.** At horizons above 1 a joint plan can assign any robot a later action. OWN now calls **every robot** once in row-major order before repairs. A robot can return an all-null list or plan to forward a box it will receive. Task 11 filtered OWN speakers using their doable actions at round start. That filter still applies at horizon 1. The relay fixture moves a red box through two initially idle robots and delivers it on the third step of one planning round. [Roster and merge](horizon.py) · [Relay fixture](test_chen2d_v12.py)
- **Physical steps.** Each nonempty joint step is checked as a whole against the live board before any action is committed. At horizons above 1 an empty joint step on an unfinished board increments `empty_steps_skipped`. It leaves the board, event clock and state/action history at the same step. A later nonempty entry can still execute in that round. The entire empty suffix is counted. Task 11 charged empty entries as environment steps. Horizon 1 keeps its original execution behavior. [Execution and history](horizon.py)
- **Limits.** The default retains the authors’ 30 planning iterations, or 40 on 4×8, with the Task 11 interpretation of an iteration as a planning round. The optional `--max-env-steps N` caps committed environment steps across all three structures and can stop inside a list. Zero permits zero steps. An unfinished board at the explicit cap receives `failure over environment step limit`. Completion on the cap is credited. The original last-iteration label and the separate strict-success score remain available. For the 4×4 comparison below, **30** gives H1 and H5 the same move budget as the authors’ 4×4 single-step bound. [Runner](run_chen2d.py) · [Cap and resume tests](test_chen2d_v12.py)

### Measurements and prompt order

Each published run records the selected horizon, environment cap and requested state position. Episodes and assignments also record the effective state position. Both the episode and each planning round record a stop reason, `plans_proposed`, `effective_steps`, `empty_steps_skipped` and `discarded_steps`. The proposal count is the length of the selected joint list after repairs. Individual turns and superseded replies remain in the call files. An effective step has at least one applied action. For a rejected second entry in a three-entry list, `discarded_steps` is 2, counting the rejected step and its unexecuted suffix. `untried_steps_after_invalid` is 1. Entries left over at completion or the environment cap contribute zero to both discard counts. [Round records](episode.py) · [Counter definitions](planning_metrics.py)

The comparison tables use all started planning rounds for the median, including rounds with zero effective steps. Effective steps per model call divides the group’s total effective steps by its total physical calls, including discussion, repairs, retries and any relay calls. Completed episodes use strict success, including a strict completion on the authors’ last allowed iteration. Output-limit, syntactic-error, iteration-limit and environment-cap endings have separate counts. The `cut_*` columns count truncated physical attempts, including recovered attempts. The `output_limit_*` columns count terminal episodes by the cut call’s role. Repair takes precedence over the original speaker’s role. On a terminal DMAS cut, the final speaker is the last attempted speaker. The missing reply leaves its intended content unknown. Episode cut records retain the call number, round and robot. [Planning table](review/chen2d-12/comparison.txt) · [Demand table](review/chen2d-12/output-demand.txt) · [Call CSV](review/chen2d-12/comparison-calls.csv)

For DMAS and OWN, `--state-position after` moves the two current-state sentences together to the end of the selected history, immediately before “Please learn from previous steps.” The default `before` preserves the old prompt bytes. The CMAS template already presents the current state after its history. Its effective setting is recorded as `ignored` for both the default and an explicit `after`. An explicit CMAS-only request for `before` is refused. In a mixed invocation the option applies to DMAS and OWN. With `--history-method none`, all three omit past state/action pairs. DMAS speakers still see the current discussion and OWN speakers see the earlier lists from the same round. [Prompt templates](prompt_env1.py) · [Byte comparisons](test_chen2d_v12.py)

The summary, demand and failure tables group by the requested state position. Use `summarize.py --by planning` to compare several output limits in one table. The ordinary summary retains its existing compatibility guard. The failure table counts syntactic endings and splits iteration-limit episodes by the existing four-executed-step back-and-forth test. Repairs and repeated rejected actions remain visible alongside that split. These are observations of executed moves and model replies. An attribution to stale state still requires inspecting the prompt and state. [Grouped causes](review/chen2d-12/failure-causes.txt) · [Episode classifications](review/chen2d-12/failure-episodes.csv)

### Three-structure GLM check

Run the following Bash commands from this folder. Each output directory fixes one horizon and output limit. The outer loop finishes seeds 0 and 1 across all four configurations before extending them to seeds 2 and 3. Each stage assigns six episodes.

~~~bash
(
  set -e
  common=(--model z-ai/glm-5.3-flash --sizes 4x4 --conditions static --dropoff event
          --frameworks CMAS,DMAS,OWN --max-env-steps 30 --history-method none
          --temperature 0.0 --retry-temperature 0.7 --jobs 2
          --episode-call-ceiling 300 --max-calls 1800 --max-cost-usd 1.5)
  for seeds in 0-1 2-3; do
    for h in 1 5; do
      for limit in 2048 8192; do
        python3 -B run_chen2d.py "${common[@]}" --envs "$seeds" --horizon "$h" \
          --max-output-tokens "$limit" --out "runs/chen2d-12/glm-h$h-$limit"
      done
    done
  done
)
python3 -B summarize.py --by planning runs/chen2d-12/glm-h*
python3 -B output_demand.py runs/chen2d-12/glm-h* --calls-csv runs/chen2d-12/glm-comparison-calls.csv
~~~

Physical fake-model calls per output limit were as follows. Both limits produced byte-identical message arrays and replies on all 24 matched assignments. The estimates across both limits are **518 calls** for seeds 0–1 and **514** for seeds 2–3. [Stage totals and input checks](review/chen2d-12/batch-audit.txt)

| Horizon | Seeds | CMAS | DMAS | OWN | All three per output limit |
|---:|---|---:|---:|---:|---:|
| 1 | 0–1 | 15 | 60 | 68 | 143 |
| 5 | 0–1 | 4 | 16 | 96 | 116 |
| 1 | 2–3 | 16 | 64 | 61 | 141 |
| 5 | 2–3 | 4 | 16 | 96 | 116 |

At either output limit, the following counts cover all four seeds. OWN at H5 proposed 60 joint steps. It executed 47, skipped 8 empty entries and reached completion before the remaining 5 entries. Every fake attempt returned on its first try. A separate scripted-transport test exercises recovery from a truncated repair reply and counts 3 effective steps over 10 physical calls. [Demand measurements](review/chen2d-12/output-demand.txt) · [Retry fixture](test_chen2d_v12.py)

| Structure | Horizon | Planning rounds | Effective steps | Median effective steps per round | Effective steps per physical call |
|---|---:|---:|---:|---:|---:|
| CMAS | 1 | 31 | 31 | 1 | 1.000 |
| DMAS | 1 | 31 | 31 | 1 | 0.250 |
| OWN | 1 | 31 | 31 | 1 | 0.240 |
| CMAS | 5 | 8 | 31 | 4.5 | 3.875 |
| DMAS | 5 | 8 | 31 | 4.5 | 0.969 |
| OWN | 5 | 12 | 47 | 4 | 0.245 |

### DMAS prompt-order GLM check

This one-step command uses the authors’ state/action history over a 100,000-token window and the original size-specific iteration limits. It uses the same static maps, event-style dropoff and temperatures. The offline check found all prior executed state/action pairs in the reordered prompts. It took 124 scripted calls on 4×4 and 204 on 4×8. [Prompt-order run](review/chen2d-12/fake-order-after/run.json) · [Recount](review/chen2d-12/batch-audit.txt)

~~~bash
python3 -B run_chen2d.py --model z-ai/glm-5.3-flash --sizes 4x4,4x8 \
  --conditions static --dropoff event --envs 0-3 --frameworks DMAS --horizon 1 \
  --max-output-tokens 8192 --history-method authors --history-window 100000 \
  --state-position after --temperature 0.0 --retry-temperature 0.7 --jobs 2 \
  --episode-call-ceiling 300 --max-calls 2400 --max-cost-usd 1.5 \
  --out runs/chen2d-12/glm-order-after
python3 -B failure_causes.py runs/chen2d-12/glm-order-after \
  --episodes-csv runs/chen2d-12/glm-order-episodes.csv
~~~

### Offline verification

The published fake runs used the GLM command settings above with `--model fake` and outputs under `review/chen2d-12/`. The audit reconstructed the selected plans from raw replies, replayed every executed action from its enrolled map, checked each saved board and reconciled the physical attempts to the stage ledgers. The two reporting tools produced identical planning-outcome tables over the 48 comparison episodes. [Audit program](review/chen2d-12/verify_batch.py) · [Audit output](review/chen2d-12/batch-audit.txt)

~~~bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v12.py
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B review/chen2d-12/verify_batch.py
~~~

Protocol `93e201336bd9` passed **146 tests** with network connections disabled in the offline harness. The original 132 tests passed on the Task 11 baseline. The final suite runs those 132 cases and 14 new ones. Four Task 11 cases have updated expectations for the required all-robot roster, empty-step accounting and DMAS horizon eligibility. The H1 byte replay still matches all 41 archived CMAS files and all 59 archived DMAS files. An additional read of the archived H5 OWN runs recovered 189 effective steps from 416 charged steps, including 227 historical empty executions. [Baseline log](review/chen2d-12/baseline-tests.txt) · [Final test log](review/chen2d-12/all-tests.txt) · [Task 12 tests](test_chen2d_v12.py)

Both verification commands exited with status 0. Their saved outputs have the following SHA-256 digests.

~~~text
6addadf5841c90654bd8dbe2d717d8cca0ad66de714cb7da54e9dc1d2d3e4b1f  review/chen2d-12/all-tests.txt
da7f5060ff4b03d470ca6cebcdb9d02f7c4649f97957f50b19066840343585a6  review/chen2d-12/batch-audit.txt
~~~

## CHEN2D-13

On the enrolled 4×4 static map, seed 0, the fake model returned the reported `[["move(box_purple, square[0.5, 2.5])"]]` for `Agent[0.5, 3.5]`. OWN accepted its first reply and moved the purple box onto the target square. In the same round, `Agent[1.5, 0.5]` delivered a green box. A third robot, `Agent[3.5, 1.5]`, gave seven unreadable replies and contributed one null. The fixture ended at its configured one-step limit after eight initial calls and six repairs. [First raw reply](review/chen2d-13/registered-map/episodes/4x4_OWN_static_env0/calls/00001.json) · [Executed plans and final board](review/chen2d-13/registered-map/episodes/4x4_OWN_static_env0/episode.json)

### Accepted OWN replies

| Per-call `own_reply_form` | Accepted input under `--parse lenient` | Calls in the 4×4 fixture |
|---|---|---:|
| `list` | A plain JSON list of action strings or nulls | 3 |
| `nested` | One list around the action list, or one singleton list around each entry | 1 |
| `self_dict` | A single key naming the speaker, with a flat or nested action list | 1 |
| `string` | At H = 1, a quoted or standalone action string, or JSON `null` | 1 |
| `fenced` | A flat list extracted from Markdown, surrounding prose or an `EXECUTE` reply | 1 |

Lenient parsing selects the first complete outer value with an accepted shape, starting after the last `EXECUTE` in surrounding text. A foreign agent key or a multi-key object fails the ownership check. Wrapped nested lists, self-keyed objects and scalars keep their structural label when embedded in prose. The parser validates every submitted entry before padding a short list with trailing nulls or cutting a long list to H. The independent Boolean flags `own_reply_padded` and `own_reply_cut` each fired once in the fixture. Strict parsing requires a plain JSON list of exactly H valid entries. [Parser](plan_parse.py) · [Per-call CSV](review/chen2d-13/calls.csv)

### Repairs and dropped robots

A format repair tells the speaker the required list length and gives a full-length example. A feasibility repair quotes the first entry, lists that robot’s current doable actions, and offers null. Both prompts repeat the own-list format and show the peer lists. The example uses an action available to that speaker, or all nulls when it has none. [Recorded format repair](review/chen2d-13/registered-map/episodes/4x4_OWN_static_env0/calls/00009.json) · [Exact feedback tests](test_chen2d_v13.py)

OWN merges separately authored lists. In both parse modes, robots needing repair share six calls per planning round. OWN checks the sixth reply. Each still-unresolved robot contributes H nulls for that round, and the other robots’ accepted lists proceed to execution. A dropped robot can participate again in the next round. If every entry is null, H = 1 charges its ordinary empty step and longer horizons skip the empty entries. The round records `own_robots_dropped`, and the episode sums that count across rounds. The authors’ joint-plan repair loops retain their episode-level `Syntactic Error` outcome. [Planning loop](horizon.py)

The two reporting tools count forms per logical call, including repairs. A parsed list with an infeasible first action still has a form. A format refusal or a call stopped before parsing has a null form and contributes no form count. Older OWN episodes show `NA` for the unrecorded measurements. Both tools reported the seven parsed replies above and one dropped robot. [Planning summary](review/chen2d-13/summary.txt) · [Output demand](review/chen2d-13/output-demand.txt)

### Offline verification

The Task 12 baseline passed all 146 tests before editing. Two earlier OWN assertions now check the required feedback and the all-robots-dropped outcome. The new fake-model tests exercise every form in lenient and strict mode, foreign-agent and malformed values, the last repair, repeated drops, interruption and resume, and both reporting commands. [Baseline log](review/chen2d-13/baseline-tests.txt) · [Task 13 tests](test_chen2d_v13.py)

The existing saved-episode replays cover CMAS, DMAS, HMAS-1 and HMAS-2. An additional H5 replay against Task 12 matched every byte of 25 CMAS files and 39 DMAS files using the archived clocks and protocol stamp. The current reporting commands also reproduced the Task 12 output bytes on its 4×4 and 4×8 DMAS prompt-order runs. [H5 replay](review/chen2d-13/h5-replay.txt) · [Reporting comparison](review/chen2d-13/author-reports.txt)

~~~bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v13.py
~~~

Protocol `c66110927114` passed **155 offline tests**, including all four authors’ framework replays. The suite used folder-local references, fake replies and scripted transports with network connections disabled. [Final test log](review/chen2d-13/all-tests.txt)

## CHEN2D-14

The independent review found that the 4×4 H5 DMAS runs lost 6 of 13 rounds on env1 and 5 of 12 on env3 to empty submissions. It also traced six CMAS repair prompts on env3 to a reply whose keys were step numbers. Those counts describe the original model runs. The tests below use scripted replies to verify which proposal the repaired runner actually executes. Where the review gives only a reply shape, the fixture fills it with actions from its test board. [Independent review, B1–B3](../20261123-plan3/review-neon/REPORT-NEON-1.md)

| defect | real example | fix | test |
|---|---|---|---|
| CMAS and DMAS mistook step keys for robots | In `v12-h5-2048/4x4_CMAS_static_env3`, the repair told the model that the task for `1` was infeasible. | Lenient parsing orders numbered plans numerically, including keys such as `step 1`. It checks every joint plan’s keys against the board roster before checking actions. A format repair names the unknown key. | [Step 10 before step 2 on the wire](test_chen2d_v14.py#L37) · [Unknown names in first and later entries](test_chen2d_v14.py#L54) |
| A later DMAS `EXECUTE` could erase a parsable plan | B1 identified the marker-only overwrite in the discussion loop. | **Multi-step rule 1.** Keep the stored proposal and its writer when a later submission cannot be parsed. If every submission fails to parse, the last submitting writer receives the format repair. A parsable first action can still require a feasibility repair. | [Marker-only reply](test_chen2d_v14.py#L79) · [Original writer gets the repair](test_chen2d_v14.py#L106) · [Interrupted sweep and resume](test_chen2d_v14.py#L113) |
| A later DMAS speaker could replace outstanding work with empty steps | The 8192-token env1 and env3 traces contained `EXECUTE\n[{}]` and lists of five empty objects. | **Multi-step rule 2.** Once a proposal contains an action anywhere in its list, a later all-empty list cannot displace it in that round. Another nonempty submission can replace it. Each new round starts with no stored plan. | [Short, full-length and zero-length empty replies, plus round reset](test_chen2d_v14.py#L91) |
| OWN rejected common waits and action spellings | B3 found string `"null"` on all four H5 maps, bare `null` in env3 call 4, `[]` in env0 call 1 and an action object on H1 env3. It also identified whitespace and quoting variants in code. | Lenient OWN accepts the five requested wait strings, bare `null` at any horizon, whitespace in moves, single-quoted lists, trailing commas and single-key action elements. These spellings resolve to the same own action or wait. Task 13 already handled `[]`, nested lists, self-keyed lists, short-list padding and standalone moves at H1. | [Wait spellings and strict refusals](test_chen2d_v14.py#L143) · [Action spellings](test_chen2d_v14.py#L154) · [Both quoted purple-box replies on the enrolled map](test_chen2d_v14.py#L189) |
| One bad OWN entry could discard a usable first move | B1 linked whole-list refusals to the H5 env0 and env1 failures. | Keep the usable prefix in lenient mode and fill from the first malformed position through H with nulls. Later actions may depend on the missing move. An unusable first entry still needs repair when the robot can participate. | [Failures at positions 2, 3 and 5, raw reply and issued action](test_chen2d_v14.py#L170) |
| OWN robots shared a repair budget | Seven robots needed repairs in round 3 of `v12-h5-2048/4x4_OWN_static_env0`. | Each robot gets up to two repair prompts per round in either parse mode. Both replies are checked. A robot still unusable contributes no actions for the round, so its peers can execute. Task 13 introduced dropping and next-round re-entry. | [Seven robots receive two attempts each](test_chen2d_v14.py#L202) · [Re-entry and interrupted repairs](test_chen2d_v13.py) |
| Repairs could be spent on a robot no box could reach | B3 records an idle robot returning an empty list and another replying in prose. The distance boundary is a constructed case. | If a robot has no doable action and every box is more than H grid moves away at round start, an unusable reply contributes H waits immediately. A box at exactly H still makes the robot eligible for repair. This preserves possible handoffs. | [Distances H, H+1 and 6 on a 4×4 board](test_chen2d_v14.py#L218) |
| The initial OWN instruction lacked a list example | B3 found repeated nesting on H1 and quoted waits on H5. | Show one concrete list of exactly H entries and identify `null` as the unquoted JSON literal. At H2 the example is `["move(box_blue, square[0.5, 1.5])", null]`. | [Example text, length and JSON types at H1, H2 and H5](test_chen2d_v14.py#L234) |
| OWN showed infeasible plans to peers and gave early speakers extra information during repairs | B1 found that infeasible first moves remained visible, format refusals disappeared, and re-prompts included later speakers. | Show a robot’s list only after its first entry passes the doable check. Show a refusal or drop as JSON `null`. An accepted all-wait plan remains a list. Every repair reuses the peer view from that speaker’s first turn, including any refusals visible then. | [Exact views on initial turns, both repairs and saved dialogue](test_chen2d_v14.py#L244) |
| With state after history, the order-change notice stayed before history | B2 reproduced the misplaced notice for e1 and e2. | Move the announcement with the current state. Insert any delivered relay directly before the live state heading, including when earlier dialogue quotes that heading. | [e1/e2, DMAS/OWN and H1/H5](test_chen2d_v14.py#L285) · [Quoted heading and once-only relay](test_chen2d_v14.py#L261) |

DMAS records actual prevented replacements in `dmas_unparsable_overwrites_prevented` and `dmas_empty_overwrites_prevented` per round and per episode. The selected writer and call number identify the proposal used for execution or repair. OWN records the first discarded position, counted from 1, in the call’s `own_reply_invalid_position`. The episode sums such calls in `own_prefixes_kept`. It also reports `own_unreachable_skipped` separately from robots exhausted after two repairs in `own_robots_dropped`. The 16-robot fixture made 16 initial calls and 14 repair calls. Five of the seven repaired robots supplied a usable move on their second try, and two were dropped. Historical demand reports use the parsing rules recorded for their run. [Round implementation](horizon.py) · [Call measurements](output_demand.py) · [Comparison tables](planning_metrics.py)

### Offline verification

The horizon-1 replay uses the archived invocation IDs, clocks, schema and protocol stamp. It compares every file in both default 2×2 static episodes, 41 CMAS files and 59 DMAS files. The separate Task 12 prompt-order replay compares all 328 rendered model prompts and all 82 saved prompt files across eight static DMAS episodes on 4×4 and 4×8 boards. OWN’s new action instruction also appears in static OWN episodes. [Horizon-1 replay](test_chen2d_v11.py#L60) · [Task 12 prompt replay](test_chen2d_v14.py#L310)

~~~bash
TMPDIR="$PWD" PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v14.py
~~~

In a 2×2 H5 fake run with a one-step cap, DMAS retained one proposal after an empty reply. OWN retained four prefixes, each ending immediately before entry 2. Both reporting commands, the episode CSV and the episode JSON agreed on the counters. Running the current demand analyzer on the archived Task 13 fixture also reproduced all 6,938 call-CSV bytes and all 3,301 report bytes. [Reconciliation](review/chen2d-14/verification.txt)

Protocol `5fdcc9bb98a5` passed **173 offline tests**, including **18 Task 14 tests**. The Task 13 baseline passed all 155 tests. Earlier OWN repair, visibility and prompt-order assertions now check the Task 14 rules. The authors’ horizon-1 runner has the same source hash as Task 13, and both byte replays passed. All execution used the fake model or scripted transports with network connections disabled. [Baseline](review/chen2d-14/baseline-tests.txt) · [Task 14 tests](review/chen2d-14/task14-tests.txt) · [Full regression suite](review/chen2d-14/all-tests.txt)

## CHEN2D-15

The same-state reading probe is ready for the main session. On six finished GLM episodes, the offline run asked all **36 states × 3 callers × 4 arms = 432** questions once. Resuming with a zero-call budget used **0** further calls. In the separate map calibration, all 144 boards were solved at both horizons. A matched 32-robot OWN example took 37 steps on a board the scripted joint planner solved in 24. [Probe evidence](review/chen2d-15/verification.json) · [Matched episodes at the 30-step cap](review/chen2d-15/matched-scaled/episodes.csv) · [Longer OWN run](review/chen2d-15/matched-headroom/episodes.csv)

### P0. Work per robot

`python3 -B enrol_maps.py --sizes 2x2,2x4,4x4,4x8 --envs 0-11 --boxes-per-robot 0.5` registers the first scaled family. Substitute 1 or 2 for the other two families. The runner selects one with `--map-set scaled:R`. A positive decimal rate gives `max(1, round(R × rows × columns))` boxes, with ties rounded to even. Each of the five existing colours gets the quotient on division by five. The remainder goes in blue, red, green, purple, orange order. For every box the generator independently draws one source square and one matching target square using the seeded generator. Delivery consumes a target, so a larger team gets more target instances in those same five colours. Cells may still hold multiple items. [Generator and registry](map_sets.py) · [Enrolment](enrol_maps.py)

Each rate has its own map, event and hash manifests in `envs-scaled/r<R>/`. Scaled events use the unstratified v3 assignment. New runner episodes, assignments and CSVs carry `map_set`, `boxes_per_robot` and the **initial** `box_count`. The rate is null in legacy JSON and blank in its CSV. A summary cell groups by the map family, which includes the canonical rate. Archived runs are read as legacy. The historical 45 boards regenerated byte for byte. The larger existing local registry also verified against its manifests, with 312 board files and 544 event files. [Registry checks](review/chen2d-15/verify_evidence.py) · [Map tests](test_chen2d_v15_maps.py)

Solvability also follows from the placement and move rules. Each delivery removes one box and one matching target. As long as a box remains, a matching target exists on the connected grid. During any stretch without a delivery, the reference solver moves boxes one square closer to a nearest matching target. With the targets fixed, the sum of those distances decreases at each such step. Another delivery must therefore occur, and only finitely many deliveries are needed. [Reference planner](map_events.py)

Each range below covers twelve seeds, 0–11. At H1 the number of rounds equals the physical steps. At H5 the scripted joint writer rendered a plan from its prompt, the parser read it, and the executor applied each entry. Every intermediate board at both horizons matched the independent reference trajectory. The legacy allowance is 30 rounds, or 40 on 4×8. The last column applies a separate cap of 30 **physical steps**. Headroom is the minimum over the twelve seeds. [All 288 per-map measurements](review/chen2d-15/scaled-map-measurements.json) · [Measurement code](scaled_map_measurements.py)

| R | Size | Boxes per map | Steps at H1 and H5 | H1 rounds | H5 rounds | Spare legacy rounds, H1 / H5 | Spare steps at cap 30 |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.5 | 2x2 | 2 | 2–4 | 2–4 | 1 | 26 / 29 | 26 |
| 0.5 | 2x4 | 4 | 3–7 | 3–7 | 1–2 | 23 / 28 | 23 |
| 0.5 | 4x4 | 8 | 5–10 | 5–10 | 1–2 | 20 / 28 | 20 |
| 0.5 | 4x8 | 16 | 11–16 | 11–16 | 3–4 | 24 / 36 | 14 |
| 1 | 2x2 | 4 | 2–6 | 2–6 | 1–2 | 24 / 28 | 24 |
| 1 | 2x4 | 8 | 4–10 | 4–10 | 1–2 | 20 / 28 | 20 |
| 1 | 4x4 | 16 | 6–13 | 6–13 | 2–3 | 17 / 27 | 17 |
| 1 | 4x8 | 32 | 9–19 | 9–19 | 2–4 | 21 / 36 | 11 |
| 2 | 2x2 | 8 | 5–9 | 5–9 | 1–2 | 21 / 28 | 21 |
| 2 | 2x4 | 16 | 7–14 | 7–14 | 2–3 | 16 / 27 | 16 |
| 2 | 4x4 | 32 | 12–21 | 12–21 | 3–5 | 9 / 25 | 9 |
| 2 | 4x8 | 64 | 17–25 | 17–25 | 4–5 | 15 / 35 | 5 |

The reference planner fits the common 30-step cap in every calibration cell. The own-actions writer can take a different route. On `scaled:2/4x8/env0` at H5 the matched scripted OWN team hit 30 steps with 3 of 64 boxes left. With a 60-step ceiling and a 600-call ceiling, the same team finished in **37 steps, 10 rounds and 320 calls**. The joint writer finished the same board in **24 steps, 5 rounds and 5 calls**. If the main comparison needs extra room for the distributed writer, one workload-based option is to multiply the largest reference step count in each size/rate cell by 1.5, round up to a multiple of five, and use a floor of 30. That gives 40 steps for the 4×8, R=2 cell and 35 for 4×4, R=2. Apply each environment cap to both structures, use one common round cap across sizes, and disclose the effective call cap. This is a proposal based on scripted workloads. The rate selection remains open. [30-step trace](review/chen2d-15/matched-scaled/episodes/4x8_OWN_static_env0/episode.json) · [37-step trace](review/chen2d-15/matched-headroom/episodes/4x8_OWN_static_env0/episode.json)

### P1 and P1b. Same-state reading and fairness

The probe accepts episode folders, run folders or an `episodes` folder. It selects from finished records with a complete execution log. Step 1 is excluded. From the remaining saved boards with at least one doable action it selects evenly spaced indices including the endpoints, up to K per episode. K=1 uses the middle eligible board. A final solved board has no eligible caller. A final actionable board after a stopped episode can be selected even when no robot executed a further action. Selection happens once for all callers and arms. [Probe](probe_reading.py) · [State and prompt tests](test_chen2d_v15_probe.py)

The leader writes the whole joint plan. Both OWN callers are the **last row-major robot with a doable action** on the saved board. `own_first` gives that robot an empty dictionary. `own_last` gives the same robot the lists of all row-major predecessors, including the idle ones. The executor’s applied actions supply the first entries. Origin coordinates identify the robot, a coordinate destination becomes `square[row, col]`, and a delivery keeps its target or dropoff string. An idle predecessor receives null. All subsequent entries through H are null. The state-action history uses the source’s saved joint responses and board states in their original step order. This preserves the distinction between an issued plan in history and a physically applied move in a peer list.

The two full-history arms contain exactly the same pairs. The native CMAS before variant transposes the existing state and history blocks, including their separators. `none`, `last1` and `all_after` use the same state-after layout. Empty history retains the same heading. `last1` retains the true source step number. Each caller keeps its task, current board, author assignment, layout choice, direct order notice when addressed, and dropoff rule across the corresponding amount comparisons. No earlier source dialogue is added to the state-action history. The six proposed source episodes are static and have no private relay traffic. Counts include the number of active robots and distinct doable choices. For the leader, `caller_doable_actions` spans all the robots whose actions it writes. `robot_local_doable_actions` separately describes its assigned square.

The checker reads the first joint entry or the selected robot's first individual entry. A null OWN entry and an empty joint object propose zero actions. Every named joint entry is checked, including off-board coordinates and malformed values in a readable joint plan. The rejection count uses the environment’s checker and current doable-action lists. Exact repeats and boxes absent from their previous square are counted only among rejected actions. For OWN, `peer_box_name_overlap` counts a first-entry box label also named by an earlier writer. `conflict_earlier_box` counts physically identifiable duplicate claims, either a unique live box at the peer’s origin or an identifiable one-step handoff from the caller to that peer. Two robots can legally move two blue boxes in different squares in the same step.

The probe saves the exact system/user messages, user prompt file, reply file, single-attempt record, finish reason or raw length flag, and token meters. A transported cutoff keeps the partial text when the client supplies it. Unknown finish evidence remains unknown. The one-attempt client uses temperature 0, the same per-transport reservation and settlement as the episode runner, and an 8,192-token default. `--shuffle` seeds admission order and `--jobs` controls concurrent cells. Guards are per invocation. Refusals before transport remain unasked. A durable completed cell reuses its saved reply after interruption. The summary counts asked states, readable plans, wrong plans among readable plans, token medians and cutoffs. Paired wrong-only-A, wrong-only-B, both and neither counts use states with readable plans in both arms. Missing arms and nonplans have their own denominators. [432 fake responses](review/chen2d-15/probe/results.jsonl) · [Cell and paired counts](review/chen2d-15/probe/summary.json)

#### Wording audit and the optional style ablation

These are the literal deletion spans in the rendered prompts. The short fragments occur inside role, goal or output sentences. All board observations, history pairs and peer data keep their original text. The single-step CMAS example ends with the malformed `move...}.` in the original. Removing it also removes the leader's only worked JSON example at H1.

**Leader**, H=1

```text
 in a grid-like field to move colored boxes
Each agent is assigned to a 1x1 square and can only interact with objects in its area.
Agents can move a box to a neighboring square or a same-color target.
The squares are identified by their center coordinates, e.g., square[0.5, 0.5].
Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).
After each move, agents provide updates for the next sequence of actions.
Your job is to coordinate the agents optimally.
Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}.
Now, plan the next step:
```

**OWN (both callers)**, H=1

```text
, stationed on a 1x1 square in a grid playground
You can only interact with objects in your square.
Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)).
All the agents coordinate with others together to come out a plan and 
only 
, using the move syntax above
Write null as the unquoted JSON literal.
Do not name an agent or write actions for others.
Your response:
Example#1: ["move(box_blue, square[0.5, 1.5])"]
```

The final leader cue at H>1 is `Now, plan the next H steps:`. The OWN example contains one blue move and H − 1 nulls. The two deletion lists above instantiate both strings for the specified horizon.

Three other differences matter when reading the legacy comparison.

- The role and goal are written as “You are a central planner directing agents in a grid-like field to move colored boxes.” and “Your task is to instruct each agent to match all boxes to their color-coded targets.” OWN reads “You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground.” and “All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.” The ablation retains the writer identity and delivery goal.
- CMAS repeats a raw board dictionary in “Hence, the current state is {board}, with the possible actions:”. OWN labels “The current state and possible actions of yourself are: {local}.” and “The current states and possible actions of all other agents are: {others}.” Native observation lines use “I am in”, “I can observe”, “I can do” for the whole board, and “in”, “can observe”, “can do” for the local OWN observation. These data-bearing blocks and native newlines stay in the style ablation. Matched uses the same row-major board for both.
- CMAS keeps “Include an agent only if it has a task next.” At H>1 it requests a list of joint objects, allows an empty object and early completion, and assumes earlier steps executed. OWN keeps its earlier-list heading, “Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.” and the JSON-list length, action-string and idle-null contract. The full output-format sentences appear in the unaltered prompts below. Both callers use “Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.”

The D2 review measured DMAS. Its “Think step-by-step about the task and the previous dialogue history. Carefully check and correct them if they made a mistake.” and “Respond very concisely but informatively, and do not repeat what others have said. Discuss with others to come up with the best plan.” are replaced by the OWN output instruction before rendering. Neither probe caller receives them or the two DMAS EXECUTE examples. OWN's “Output only a JSON list” is its remaining explicit output-only instruction. The probe preserves the JSON type/length and removes the output-only qualifier in the stripped OWN prompt.

In matched mode both callers receive the same examples and brevity instruction. The corresponding style ablation removes exactly these two shared sentences.

```text
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).
Respond concisely.
```

State N is the saved board before step N. Public history uses saved states and the source's issued joint response for each earlier executed transition, with original step numbers. For peer lists and repeats, the physical executor's applied_actions are authoritative. Each applied (origin, box, destination) becomes one move for Agent[origin], with coordinates rendered as square[row, col]. Every row-major predecessor gets that move or null at entry one and H − 1 trailing nulls. A final actionable board with no executed next step gives every predecessor null. own_first uses the same robot with {}.

The literal retained and deleted output wording can also be checked together at H5. The OWN example uses an empty peer dictionary.

**CMAS, H5**

~~~text
Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}. Include an agent only if it has a task in that step. Plan the next 5 steps at once: output a JSON list of 5 such plans, one per step, in order, assuming every earlier step of your plan has been executed. Use an empty object for a step with nothing to do, and stop the list early if the task is complete. Now, plan the next 5 steps:
~~~

**OWN, H5**

~~~text
[Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 5 entries, one for each of the next 5 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])", null, null, null, null]
Your response:
~~~


#### Main-session command

The archived source run is `../20261124-chen2d-snap-v12/runs/v12-order-after`. All six records report a finished, strict GLM completion. The table gives the saved episode folder and selected one-based steps. [Source episode hashes](review/chen2d-15/verification.json)

| Episode folder | Executed steps | Six selected steps |
|---|---:|---|
| 2x4_DMAS_static_env0 | 10 | 2, 4, 5, 7, 8, 10 |
| 2x4_DMAS_static_env1 | 11 | 2, 4, 6, 7, 9, 11 |
| 4x4_DMAS_static_env0 | 11 | 2, 4, 6, 7, 9, 11 |
| 4x4_DMAS_static_env1 | 12 | 2, 4, 6, 8, 10, 12 |
| 4x8_DMAS_static_env0 | 13 | 2, 4, 6, 9, 11, 13 |
| 4x8_DMAS_static_env1 | 15 | 2, 5, 7, 10, 12, 15 |

Run from this folder in Bash. A full fresh invocation requests **432 physical attempts**. The call and dollar guards still apply. The fake verification used the identical selection, ordering seed, concurrency and output limit.

```bash
source_dir=../20261124-chen2d-snap-v12/runs/v12-order-after/episodes
printf -v episode_dirs '%s,' "$source_dir"/{2x4,4x4,4x8}_DMAS_static_env{0,1}
python3 -B probe_reading.py --episodes "${episode_dirs%,}" --per-episode 6 \
  --callers leader,own_first,own_last --arms none,last1,all_before,all_after \
  --horizon 1 --protocol authors --model z-ai/glm-5.3-flash --max-output-tokens 8192 \
  --shuffle 20261124 --jobs 2 --max-calls 432 --max-cost-usd 1.5 \
  --out runs/chen2d-15/reading-authors-h1
python3 -B probe_reading.py --summarize runs/chen2d-15/reading-authors-h1
```

For a matched-wording comparison use `--protocol matched`. For the literal style ablation add `--strip-style`. Each separate treatment uses a fresh output directory and requests its own 432 attempts. An interrupted invocation can resume in its original directory with new invocation guards.

#### Twelve exact native prompts on one saved board

These are the wire strings reconstructed from the actual fake-run call records for `2x4_DMAS_static_env0`, step 4, H1. They include the common system message. Every panel has its own byte digest and its original message array in the accompanying file. [Machine-readable prompts and SHA-256](review/chen2d-15/example-messages.json)

<details>
<summary>leader · none</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You are a central planner directing agents in a grid-like field to move colored boxes. Each agent is assigned to a 1x1 square and can only interact with objects in its area. Agents can move a box to a neighboring square or a same-color target. Each square can contain many targets and boxes.

    The squares are identified by their center coordinates, e.g., square[0.5, 0.5]. Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).

    Your task is to instruct each agent to match all boxes to their color-coded targets. After each move, agents provide updates for the next sequence of actions. Your job is to coordinate the agents optimally.

    The previous state and action pairs at each step are:
    
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    Hence, the current state is {'0.5_0.5': [], '0.5_1.5': ['target_green'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': [], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange', 'box_red'], '1.5_2.5': ['box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red']}, with the possible actions:
    Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], I can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']


    Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}. Include an agent only if it has a task next. Now, plan the next step:
      
~~~

</details>

<details>
<summary>leader · last1</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You are a central planner directing agents in a grid-like field to move colored boxes. Each agent is assigned to a 1x1 square and can only interact with objects in its area. Agents can move a box to a neighboring square or a same-color target. Each square can contain many targets and boxes.

    The squares are identified by their center coordinates, e.g., square[0.5, 0.5]. Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).

    Your task is to instruct each agent to match all boxes to their color-coded targets. After each move, agents provide updates for the next sequence of actions. Your job is to coordinate the agents optimally.

    The previous state and action pairs at each step are:
    State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    Hence, the current state is {'0.5_0.5': [], '0.5_1.5': ['target_green'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': [], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange', 'box_red'], '1.5_2.5': ['box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red']}, with the possible actions:
    Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], I can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']


    Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}. Include an agent only if it has a task next. Now, plan the next step:
      
~~~

</details>

<details>
<summary>leader · all_before</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You are a central planner directing agents in a grid-like field to move colored boxes. Each agent is assigned to a 1x1 square and can only interact with objects in its area. Agents can move a box to a neighboring square or a same-color target. Each square can contain many targets and boxes.

    The squares are identified by their center coordinates, e.g., square[0.5, 0.5]. Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).

    Your task is to instruct each agent to match all boxes to their color-coded targets. After each move, agents provide updates for the next sequence of actions. Your job is to coordinate the agents optimally.

    Hence, the current state is {'0.5_0.5': [], '0.5_1.5': ['target_green'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': [], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange', 'box_red'], '1.5_2.5': ['box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red']}, with the possible actions:
    Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], I can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']


    The previous state and action pairs at each step are:
    State1: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_2.5': ['box_green', 'box_green', 'target_green'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'target_green', 'box_green'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_blue', 'box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action1: {"Agent[1.5, 0.5]": "move(box_green, target_green)", "Agent[1.5, 2.5]": "move(box_blue, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, target_green)", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])"}

State2: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_blue', 'box_orange'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action2: {"Agent[1.5, 0.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])", "Agent[0.5, 2.5]": "move(box_blue, square[1.5, 2.5])", "Agent[0.5, 3.5]": "move(box_orange, square[1.5, 3.5])", "Agent[1.5, 2.5]": "move(box_orange, square[1.5, 3.5])"}

State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}. Include an agent only if it has a task next. Now, plan the next step:
      
~~~

</details>

<details>
<summary>leader · all_after</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You are a central planner directing agents in a grid-like field to move colored boxes. Each agent is assigned to a 1x1 square and can only interact with objects in its area. Agents can move a box to a neighboring square or a same-color target. Each square can contain many targets and boxes.

    The squares are identified by their center coordinates, e.g., square[0.5, 0.5]. Actions are like: move(box_red, target_red) or move(box_red, square[0.5, 0.5]).

    Your task is to instruct each agent to match all boxes to their color-coded targets. After each move, agents provide updates for the next sequence of actions. Your job is to coordinate the agents optimally.

    The previous state and action pairs at each step are:
    State1: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_2.5': ['box_green', 'box_green', 'target_green'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'target_green', 'box_green'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_blue', 'box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action1: {"Agent[1.5, 0.5]": "move(box_green, target_green)", "Agent[1.5, 2.5]": "move(box_blue, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, target_green)", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])"}

State2: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_blue', 'box_orange'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action2: {"Agent[1.5, 0.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])", "Agent[0.5, 2.5]": "move(box_blue, square[1.5, 2.5])", "Agent[0.5, 3.5]": "move(box_orange, square[1.5, 3.5])", "Agent[1.5, 2.5]": "move(box_orange, square[1.5, 3.5])"}

State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    Hence, the current state is {'0.5_0.5': [], '0.5_1.5': ['target_green'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': [], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange', 'box_red'], '1.5_2.5': ['box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red']}, with the possible actions:
    Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], I can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']


    Specify your action plan in this format: {"Agent[0.5, 0.5]":"move(box_blue, square[0.5, 1.5])", "Agent[1.5, 0.5]":"move...}. Include an agent only if it has a task next. Now, plan the next step:
      
~~~

</details>

<details>
<summary>own_first · none</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The previous state and action pairs at each step are:
    
    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_first · last1</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The previous state and action pairs at each step are:
    State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_first · all_before</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    The previous state and action pairs at each step are:
    State1: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_2.5': ['box_green', 'box_green', 'target_green'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'target_green', 'box_green'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_blue', 'box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action1: {"Agent[1.5, 0.5]": "move(box_green, target_green)", "Agent[1.5, 2.5]": "move(box_blue, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, target_green)", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])"}

State2: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_blue', 'box_orange'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action2: {"Agent[1.5, 0.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])", "Agent[0.5, 2.5]": "move(box_blue, square[1.5, 2.5])", "Agent[0.5, 3.5]": "move(box_orange, square[1.5, 3.5])", "Agent[1.5, 2.5]": "move(box_orange, square[1.5, 3.5])"}

State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_first · all_after</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The previous state and action pairs at each step are:
    State1: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_2.5': ['box_green', 'box_green', 'target_green'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'target_green', 'box_green'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_blue', 'box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action1: {"Agent[1.5, 0.5]": "move(box_green, target_green)", "Agent[1.5, 2.5]": "move(box_blue, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, target_green)", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])"}

State2: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_blue', 'box_orange'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action2: {"Agent[1.5, 0.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])", "Agent[0.5, 2.5]": "move(box_blue, square[1.5, 2.5])", "Agent[0.5, 3.5]": "move(box_orange, square[1.5, 3.5])", "Agent[1.5, 2.5]": "move(box_orange, square[1.5, 3.5])"}

State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_last · none</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The previous state and action pairs at each step are:
    
    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [null], "Agent[0.5, 1.5]": [null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])"], "Agent[0.5, 3.5]": [null], "Agent[1.5, 0.5]": [null], "Agent[1.5, 1.5]": ["move(box_purple, square[0.5, 1.5])"], "Agent[1.5, 2.5]": ["move(box_blue, square[1.5, 3.5])"]}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_last · last1</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The previous state and action pairs at each step are:
    State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [null], "Agent[0.5, 1.5]": [null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])"], "Agent[0.5, 3.5]": [null], "Agent[1.5, 0.5]": [null], "Agent[1.5, 1.5]": ["move(box_purple, square[0.5, 1.5])"], "Agent[1.5, 2.5]": ["move(box_blue, square[1.5, 3.5])"]}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_last · all_before</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    The previous state and action pairs at each step are:
    State1: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_2.5': ['box_green', 'box_green', 'target_green'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'target_green', 'box_green'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_blue', 'box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action1: {"Agent[1.5, 0.5]": "move(box_green, target_green)", "Agent[1.5, 2.5]": "move(box_blue, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, target_green)", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])"}

State2: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_blue', 'box_orange'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action2: {"Agent[1.5, 0.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])", "Agent[0.5, 2.5]": "move(box_blue, square[1.5, 2.5])", "Agent[0.5, 3.5]": "move(box_orange, square[1.5, 3.5])", "Agent[1.5, 2.5]": "move(box_orange, square[1.5, 3.5])"}

State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [null], "Agent[0.5, 1.5]": [null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])"], "Agent[0.5, 3.5]": [null], "Agent[1.5, 0.5]": [null], "Agent[1.5, 1.5]": ["move(box_purple, square[0.5, 1.5])"], "Agent[1.5, 2.5]": ["move(box_blue, square[1.5, 3.5])"]}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

<details>
<summary>own_last · all_after</summary>

~~~text
[system]
You are a helpful assistant.

[user]

    You're a box-moving agent in a multi-agent system, stationed on a 1x1 square in a grid playground. You can only interact with objects in your square. Squares are denoted by their center coordinates (e.g., square[0.5, 0.5]), and actions involve moving boxes to targets or nearby squares, represented by colors (e.g., move(box_red, target_red)). Each square can contain many targets and boxes.
    All the agents coordinate with others together to come out a plan and achieve the goal: match each box with its color-coded target.
    The previous state and action pairs at each step are:
    State1: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple', 'box_orange'], '0.5_2.5': ['box_green', 'box_green', 'target_green'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red', 'target_green', 'box_green'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_blue', 'box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action1: {"Agent[1.5, 0.5]": "move(box_green, target_green)", "Agent[1.5, 2.5]": "move(box_blue, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, target_green)", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])"}

State2: {'0.5_0.5': ['target_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_blue', 'box_orange'], '0.5_3.5': ['target_red', 'box_orange'], '1.5_0.5': ['box_blue', 'box_red'], '1.5_1.5': ['box_red', 'box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_orange'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange']}
Action2: {"Agent[1.5, 0.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])", "Agent[0.5, 2.5]": "move(box_blue, square[1.5, 2.5])", "Agent[0.5, 3.5]": "move(box_orange, square[1.5, 3.5])", "Agent[1.5, 2.5]": "move(box_orange, square[1.5, 3.5])"}

State3: {'0.5_0.5': ['target_blue', 'box_blue'], '0.5_1.5': ['target_green', 'box_purple', 'target_purple'], '0.5_2.5': ['box_green', 'box_orange'], '0.5_3.5': ['target_red'], '1.5_0.5': ['box_red'], '1.5_1.5': ['box_purple', 'target_orange', 'target_orange'], '1.5_2.5': ['box_red', 'box_blue'], '1.5_3.5': ['target_blue', 'target_red', 'target_purple', 'target_orange', 'box_orange', 'box_orange']}
Action3: {"Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 2.5]": "move(box_red, square[1.5, 3.5])", "Agent[0.5, 0.5]": "move(box_blue, target_blue)", "Agent[0.5, 1.5]": "move(box_purple, target_purple)", "Agent[1.5, 3.5]": "move(box_orange, target_orange)"}


    The current state and possible actions of yourself are: {Agent[1.5, 3.5]: in square[1.5, 3.5], can observe ['target_blue', 'target_red', 'target_purple', 'box_orange', 'box_red'], can do ['move(box_orange, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_red, square[0.5, 3.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_red, target_red)']
}.
    The current states and possible actions of all other agents are: {Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_green'], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])', 'move(box_orange, square[1.5, 2.5])', 'move(box_orange, square[0.5, 1.5])', 'move(box_orange, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_purple', 'target_orange', 'target_orange', 'box_red'], I can do ['move(box_purple, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_blue'], I can do ['move(box_blue, square[0.5, 2.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[1.5, 3.5])']
}.
    Please learn from previous steps. Not purely repeat the actions but learn why the state changes or remains in a dead loop. Avoid being stuck in action loops.

    
    [Own Action Output Instruction]
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [null], "Agent[0.5, 1.5]": [null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])"], "Agent[0.5, 3.5]": [null], "Agent[1.5, 0.5]": [null], "Agent[1.5, 1.5]": ["move(box_purple, square[0.5, 1.5])"], "Agent[1.5, 2.5]": ["move(box_blue, square[1.5, 3.5])"]}
Avoid conflicts with these lists. Write actions only for yourself. Assume your own earlier entries have been executed.
Output only a JSON list of 1 entries, one for each of the next 1 steps in order. Each entry must be one action string for yourself, using the move syntax above, or null if you have nothing to do in that step. Write null as the unquoted JSON literal. Do not name an agent or write actions for others.
Example#1: ["move(box_blue, square[0.5, 1.5])"]
Your response:
~~~

</details>

### P1c. Matched episode protocol

`run_chen2d.py --protocol matched` selects CMAS and OWN by default. At any positive H they use a common role-neutral task, the same row-major observations and doable actions, action examples, brevity instruction, and JSON-format sentences. The role assignment selects a joint entry or an individual entry. OWN alone receives earlier speakers’ lists, frozen as of that writer’s first turn even during repair. Every robot speaks in row-major order at every matched horizon. Transport retries and author repairs are distinct. [Shared template](matched_protocol.py) · [Round execution](horizon.py)

The two complete H1 prompts below use the same saved board as the twelve panels, all history, state after, and the actual previous speakers for OWN. Bold text marks the only differences. The system message, input material outside the peer list, and output-format sentences are byte-identical. [Exact matched messages](review/chen2d-15/example-matched.json)

<table>
<thead><tr><th>CMAS leader</th><th>OWN last active robot</th></tr></thead>
<tbody><tr><td><pre><code>[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:
State1: {&#x27;0.5_0.5&#x27;: [&#x27;target_blue&#x27;], &#x27;0.5_1.5&#x27;: [&#x27;target_green&#x27;, &#x27;box_purple&#x27;, &#x27;target_purple&#x27;, &#x27;box_orange&#x27;], &#x27;0.5_2.5&#x27;: [&#x27;box_green&#x27;, &#x27;box_green&#x27;, &#x27;target_green&#x27;], &#x27;0.5_3.5&#x27;: [&#x27;target_red&#x27;, &#x27;box_orange&#x27;], &#x27;1.5_0.5&#x27;: [&#x27;box_blue&#x27;, &#x27;box_red&#x27;, &#x27;target_green&#x27;, &#x27;box_green&#x27;], &#x27;1.5_1.5&#x27;: [&#x27;box_red&#x27;, &#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;], &#x27;1.5_2.5&#x27;: [&#x27;box_blue&#x27;, &#x27;box_orange&#x27;], &#x27;1.5_3.5&#x27;: [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;target_orange&#x27;]}
Action1: {&quot;Agent[1.5, 0.5]&quot;: &quot;move(box_green, target_green)&quot;, &quot;Agent[1.5, 2.5]&quot;: &quot;move(box_blue, square[0.5, 2.5])&quot;, &quot;Agent[0.5, 2.5]&quot;: &quot;move(box_green, target_green)&quot;, &quot;Agent[0.5, 1.5]&quot;: &quot;move(box_orange, square[0.5, 2.5])&quot;}

State2: {&#x27;0.5_0.5&#x27;: [&#x27;target_blue&#x27;], &#x27;0.5_1.5&#x27;: [&#x27;target_green&#x27;, &#x27;box_purple&#x27;, &#x27;target_purple&#x27;], &#x27;0.5_2.5&#x27;: [&#x27;box_green&#x27;, &#x27;box_blue&#x27;, &#x27;box_orange&#x27;], &#x27;0.5_3.5&#x27;: [&#x27;target_red&#x27;, &#x27;box_orange&#x27;], &#x27;1.5_0.5&#x27;: [&#x27;box_blue&#x27;, &#x27;box_red&#x27;], &#x27;1.5_1.5&#x27;: [&#x27;box_red&#x27;, &#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;], &#x27;1.5_2.5&#x27;: [&#x27;box_orange&#x27;], &#x27;1.5_3.5&#x27;: [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;target_orange&#x27;]}
Action2: {&quot;Agent[1.5, 0.5]&quot;: &quot;move(box_blue, square[0.5, 0.5])&quot;, &quot;Agent[1.5, 1.5]&quot;: &quot;move(box_red, square[1.5, 2.5])&quot;, &quot;Agent[0.5, 2.5]&quot;: &quot;move(box_blue, square[1.5, 2.5])&quot;, &quot;Agent[0.5, 3.5]&quot;: &quot;move(box_orange, square[1.5, 3.5])&quot;, &quot;Agent[1.5, 2.5]&quot;: &quot;move(box_orange, square[1.5, 3.5])&quot;}

State3: {&#x27;0.5_0.5&#x27;: [&#x27;target_blue&#x27;, &#x27;box_blue&#x27;], &#x27;0.5_1.5&#x27;: [&#x27;target_green&#x27;, &#x27;box_purple&#x27;, &#x27;target_purple&#x27;], &#x27;0.5_2.5&#x27;: [&#x27;box_green&#x27;, &#x27;box_orange&#x27;], &#x27;0.5_3.5&#x27;: [&#x27;target_red&#x27;], &#x27;1.5_0.5&#x27;: [&#x27;box_red&#x27;], &#x27;1.5_1.5&#x27;: [&#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;], &#x27;1.5_2.5&#x27;: [&#x27;box_red&#x27;, &#x27;box_blue&#x27;], &#x27;1.5_3.5&#x27;: [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;target_orange&#x27;, &#x27;box_orange&#x27;, &#x27;box_orange&#x27;]}
Action3: {&quot;Agent[1.5, 0.5]&quot;: &quot;move(box_red, square[1.5, 1.5])&quot;, &quot;Agent[1.5, 2.5]&quot;: &quot;move(box_red, square[1.5, 3.5])&quot;, &quot;Agent[0.5, 0.5]&quot;: &quot;move(box_blue, target_blue)&quot;, &quot;Agent[0.5, 1.5]&quot;: &quot;move(box_purple, target_purple)&quot;, &quot;Agent[1.5, 3.5]&quot;: &quot;move(box_orange, target_orange)&quot;}


Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe [&#x27;target_green&#x27;], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe [&#x27;box_green&#x27;, &#x27;box_orange&#x27;], I can do [&#x27;move(box_green, square[1.5, 2.5])&#x27;, &#x27;move(box_green, square[0.5, 1.5])&#x27;, &#x27;move(box_green, square[0.5, 3.5])&#x27;, &#x27;move(box_orange, square[1.5, 2.5])&#x27;, &#x27;move(box_orange, square[0.5, 1.5])&#x27;, &#x27;move(box_orange, square[0.5, 3.5])&#x27;]
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe [&#x27;target_red&#x27;], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [&#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;, &#x27;box_red&#x27;], I can do [&#x27;move(box_purple, square[0.5, 1.5])&#x27;, &#x27;move(box_purple, square[1.5, 0.5])&#x27;, &#x27;move(box_purple, square[1.5, 2.5])&#x27;, &#x27;move(box_red, square[0.5, 1.5])&#x27;, &#x27;move(box_red, square[1.5, 0.5])&#x27;, &#x27;move(box_red, square[1.5, 2.5])&#x27;]
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe [&#x27;box_blue&#x27;], I can do [&#x27;move(box_blue, square[0.5, 2.5])&#x27;, &#x27;move(box_blue, square[1.5, 1.5])&#x27;, &#x27;move(box_blue, square[1.5, 3.5])&#x27;]
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;box_orange&#x27;, &#x27;box_red&#x27;], I can do [&#x27;move(box_orange, square[0.5, 3.5])&#x27;, &#x27;move(box_orange, square[1.5, 2.5])&#x27;, &#x27;move(box_red, square[0.5, 3.5])&#x27;, &#x27;move(box_red, square[1.5, 2.5])&#x27;, &#x27;move(box_red, target_red)&#x27;]

<strong>Write a joint entry for every step, choosing the actions of all robots.</strong>
Return a JSON list for the next 1 steps in execution order.
Use a joint object mapping each acting Agent[row, col] to its action string, with {} for an idle step. Use one action string or the JSON literal null for an individual entry. Assume the earlier entries have been executed. Return only the list.
Respond concisely.</code></pre></td><td><pre><code>[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:
State1: {&#x27;0.5_0.5&#x27;: [&#x27;target_blue&#x27;], &#x27;0.5_1.5&#x27;: [&#x27;target_green&#x27;, &#x27;box_purple&#x27;, &#x27;target_purple&#x27;, &#x27;box_orange&#x27;], &#x27;0.5_2.5&#x27;: [&#x27;box_green&#x27;, &#x27;box_green&#x27;, &#x27;target_green&#x27;], &#x27;0.5_3.5&#x27;: [&#x27;target_red&#x27;, &#x27;box_orange&#x27;], &#x27;1.5_0.5&#x27;: [&#x27;box_blue&#x27;, &#x27;box_red&#x27;, &#x27;target_green&#x27;, &#x27;box_green&#x27;], &#x27;1.5_1.5&#x27;: [&#x27;box_red&#x27;, &#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;], &#x27;1.5_2.5&#x27;: [&#x27;box_blue&#x27;, &#x27;box_orange&#x27;], &#x27;1.5_3.5&#x27;: [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;target_orange&#x27;]}
Action1: {&quot;Agent[1.5, 0.5]&quot;: &quot;move(box_green, target_green)&quot;, &quot;Agent[1.5, 2.5]&quot;: &quot;move(box_blue, square[0.5, 2.5])&quot;, &quot;Agent[0.5, 2.5]&quot;: &quot;move(box_green, target_green)&quot;, &quot;Agent[0.5, 1.5]&quot;: &quot;move(box_orange, square[0.5, 2.5])&quot;}

State2: {&#x27;0.5_0.5&#x27;: [&#x27;target_blue&#x27;], &#x27;0.5_1.5&#x27;: [&#x27;target_green&#x27;, &#x27;box_purple&#x27;, &#x27;target_purple&#x27;], &#x27;0.5_2.5&#x27;: [&#x27;box_green&#x27;, &#x27;box_blue&#x27;, &#x27;box_orange&#x27;], &#x27;0.5_3.5&#x27;: [&#x27;target_red&#x27;, &#x27;box_orange&#x27;], &#x27;1.5_0.5&#x27;: [&#x27;box_blue&#x27;, &#x27;box_red&#x27;], &#x27;1.5_1.5&#x27;: [&#x27;box_red&#x27;, &#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;], &#x27;1.5_2.5&#x27;: [&#x27;box_orange&#x27;], &#x27;1.5_3.5&#x27;: [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;target_orange&#x27;]}
Action2: {&quot;Agent[1.5, 0.5]&quot;: &quot;move(box_blue, square[0.5, 0.5])&quot;, &quot;Agent[1.5, 1.5]&quot;: &quot;move(box_red, square[1.5, 2.5])&quot;, &quot;Agent[0.5, 2.5]&quot;: &quot;move(box_blue, square[1.5, 2.5])&quot;, &quot;Agent[0.5, 3.5]&quot;: &quot;move(box_orange, square[1.5, 3.5])&quot;, &quot;Agent[1.5, 2.5]&quot;: &quot;move(box_orange, square[1.5, 3.5])&quot;}

State3: {&#x27;0.5_0.5&#x27;: [&#x27;target_blue&#x27;, &#x27;box_blue&#x27;], &#x27;0.5_1.5&#x27;: [&#x27;target_green&#x27;, &#x27;box_purple&#x27;, &#x27;target_purple&#x27;], &#x27;0.5_2.5&#x27;: [&#x27;box_green&#x27;, &#x27;box_orange&#x27;], &#x27;0.5_3.5&#x27;: [&#x27;target_red&#x27;], &#x27;1.5_0.5&#x27;: [&#x27;box_red&#x27;], &#x27;1.5_1.5&#x27;: [&#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;], &#x27;1.5_2.5&#x27;: [&#x27;box_red&#x27;, &#x27;box_blue&#x27;], &#x27;1.5_3.5&#x27;: [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;target_orange&#x27;, &#x27;box_orange&#x27;, &#x27;box_orange&#x27;]}
Action3: {&quot;Agent[1.5, 0.5]&quot;: &quot;move(box_red, square[1.5, 1.5])&quot;, &quot;Agent[1.5, 2.5]&quot;: &quot;move(box_red, square[1.5, 3.5])&quot;, &quot;Agent[0.5, 0.5]&quot;: &quot;move(box_blue, target_blue)&quot;, &quot;Agent[0.5, 1.5]&quot;: &quot;move(box_purple, target_purple)&quot;, &quot;Agent[1.5, 3.5]&quot;: &quot;move(box_orange, target_orange)&quot;}


Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [], I can do []
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe [&#x27;target_green&#x27;], I can do []
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe [&#x27;box_green&#x27;, &#x27;box_orange&#x27;], I can do [&#x27;move(box_green, square[1.5, 2.5])&#x27;, &#x27;move(box_green, square[0.5, 1.5])&#x27;, &#x27;move(box_green, square[0.5, 3.5])&#x27;, &#x27;move(box_orange, square[1.5, 2.5])&#x27;, &#x27;move(box_orange, square[0.5, 1.5])&#x27;, &#x27;move(box_orange, square[0.5, 3.5])&#x27;]
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe [&#x27;target_red&#x27;], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [], I can do []
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [&#x27;box_purple&#x27;, &#x27;target_orange&#x27;, &#x27;target_orange&#x27;, &#x27;box_red&#x27;], I can do [&#x27;move(box_purple, square[0.5, 1.5])&#x27;, &#x27;move(box_purple, square[1.5, 0.5])&#x27;, &#x27;move(box_purple, square[1.5, 2.5])&#x27;, &#x27;move(box_red, square[0.5, 1.5])&#x27;, &#x27;move(box_red, square[1.5, 0.5])&#x27;, &#x27;move(box_red, square[1.5, 2.5])&#x27;]
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe [&#x27;box_blue&#x27;], I can do [&#x27;move(box_blue, square[0.5, 2.5])&#x27;, &#x27;move(box_blue, square[1.5, 1.5])&#x27;, &#x27;move(box_blue, square[1.5, 3.5])&#x27;]
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe [&#x27;target_blue&#x27;, &#x27;target_red&#x27;, &#x27;target_purple&#x27;, &#x27;box_orange&#x27;, &#x27;box_red&#x27;], I can do [&#x27;move(box_orange, square[0.5, 3.5])&#x27;, &#x27;move(box_orange, square[1.5, 2.5])&#x27;, &#x27;move(box_red, square[0.5, 3.5])&#x27;, &#x27;move(box_red, square[1.5, 2.5])&#x27;, &#x27;move(box_red, target_red)&#x27;]

<strong>Write an individual entry for every step, choosing only the action of Agent[1.5, 3.5].</strong>
<strong>Earlier robots&#x27; lists in this planning round: {&quot;Agent[0.5, 0.5]&quot;: [null], &quot;Agent[0.5, 1.5]&quot;: [null], &quot;Agent[0.5, 2.5]&quot;: [&quot;move(box_green, square[0.5, 1.5])&quot;], &quot;Agent[0.5, 3.5]&quot;: [null], &quot;Agent[1.5, 0.5]&quot;: [null], &quot;Agent[1.5, 1.5]&quot;: [&quot;move(box_purple, square[0.5, 1.5])&quot;], &quot;Agent[1.5, 2.5]&quot;: [&quot;move(box_blue, square[1.5, 3.5])&quot;]}</strong>
Return a JSON list for the next 1 steps in execution order.
Use a joint object mapping each acting Agent[row, col] to its action string, with {} for an idle step. Use one action string or the JSON literal null for an individual entry. Assume the earlier entries have been executed. Return only the list.
Respond concisely.</code></pre></td></tr></tbody>
</table>

Both writers receive the same public executed state/action suffix. `--history-method none` or `--history-window 0` disables past pairs. In matched mode `authors` and `dialogue` both use those public pairs. Earlier private deliberations would give different historical inputs. The matched token window applies to the serialized pairs using the existing byte-based history estimator and its strict boundary. A longer list of earlier speakers cannot shrink that window. Both writers honor `--state-position before|after`. Matched CMAS uses these settings directly, independent of the legacy `--cmas-history` switch.

Each writer gets **one initial reply plus up to two repair replies per round**, including the final allowed repair in the check. The repair instruction and diagnostic wording are shared. A persistently unusable OWN writer is excluded by name and its entries contribute no move. A leader with an unusable joint plan stops the round. The log records every check, logical repairs by writer, physical repair attempts, and excluded robots. Future joint entries are checked on their execution board. A nonempty valid prefix may already have executed before a later rejection. Empty steps count as zero useful actions.

Each physical attempt retains generated and reasoning tokens and provider finish evidence, including the native reason when available. Four mutually exclusive round counts appear in the episode, CSV and summary. An exhausted required logical call with confirmed length termination on every attempt stops the round. Otherwise an ambiguous attempt makes the round unknown. A first-attempt length termination followed by a successful retry counts as recovered. Rounds with known finish evidence and no length terminations count as no cutoff. A no-transport round has unknown cutoff status. The matched client uses raw provider evidence for an output-limit ending. The generated-token limit includes reasoning, and an unreported meter remains missing.

The matched defaults are **30 environment steps, 30 planning rounds at every size, and 300 physical attempts per episode**. Set them with `--max-env-steps`, `--max-planning-rounds` and `--episode-call-ceiling`. The run file records the ceilings up front, including the effective physical cap when the real client imposes a smaller hard ceiling. Completion on the last allowed action counts. The final labels `environment step ceiling`, `planning round ceiling` and `episode call ceiling` identify the exact boundary. An unfinished board held at an invocation guard can resume.

A 32-robot OWN round needs **32 initial logical calls** at H1 or H5. If every writer needs both repairs, that reaches **96 logical calls**. With the existing three-attempt maximum the upper bound is **288 physical attempts** for such a round, before any separate optional relay calls. A 300-attempt cap covers nine complete repair-free, retry-free rounds and 12 speakers of a tenth. The five joint-writer rounds and ten OWN rounds in the worked 4×8 example illustrate the separate cost of whole-team completion.

`first_blocked_round`, `first_blocked_cause` and `first_blocked_stage` record the first round with no executable action, even if later replanning succeeds. They distinguish confirmed output limit, unusable replies after repairs, not-doable actions, a ceiling, all-idle proposals and service/unknown cases. A ceiling reached after a productive round records that boundary and its stage. A zero ceiling before planning records round 0. Strict completion requires no boxes left and no wrong deliveries. Per-cell physical calls, prompt tokens and generated tokens sum every recorded episode and retry, including interrupted and failed episodes. Each total is divided by the number of strict completions. A zero denominator prints `no completion`, and an unknown contributing token meter keeps its total unknown. [Matched summary with denominators](review/chen2d-15/matched-summary.txt)

### P2 and P3. Verification

The folder-local harness passed **205/205 tests**, covering all 173 earlier cases and 32 Task 15 cases. The focused suite also passed **32/32**. Tests compared every byte of the 41-file CMAS and 59-file DMAS historical H1 episodes, the saved prompts for eight state-order episodes (328 calls, 82 prompt files), and the Task 13 demand output (3,301 bytes) and call CSV (6,938 bytes). The independent artifact check verified all 160 historical board/event digests in the frozen Task 5 list. Scripted HTTP tests exercised a partial length termination, unknown evidence, recovered and exhausted retries, accounting, guards and crash recovery without paying a second attempt. The live gateway was never invoked. [Full test log](review/chen2d-15/all-tests.txt) · [Focused test log](review/chen2d-15/task15-tests.txt) · [Archived replay](review/chen2d-15/replay/output-demand.txt)

The 432 H1 fake calls produced 432 readable plans, 0 plans with a rejected action and 0 cutoffs. In each of the 12 cells the denominators were 36 asked and 36 readable. All 18 paired comparisons had 36/36 in the neither-wrong category. The fake client reports fixed 11-token prompts and 7-token completions, so these medians exercise the reporting path. A second H5 smoke tested all 12 cells in each of four combinations of native/matched wording and full/stripped style, with 48/48 readable first entries. The independent audit also reconciled three strict completions and one environment-ceiling ending in the four-episode scaled smoke. [H5 check](review/chen2d-15/probe-h5-check.json) · [Per-episode evidence](review/chen2d-15/verification.json)

Two development-suite passes overlapped edits to versioned source. They exposed report-column compatibility and rejected mixed code hashes. The final logs above use the corrected grouping and frozen episode protocol. The preliminary logs and early smoke traces are archived separately. [Development evidence](review/chen2d-15/development-evidence.tar.gz)

```bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v14.py \
  test_chen2d test_chen2d_v{2..14} test_chen2d_v15_{maps,matched,cli,probe,probe_exec}
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B scaled_map_measurements.py \
  --rates 0.5,1,2 --sizes 2x2,2x4,4x4,4x8 --envs 0-11 \
  --out review/chen2d-15/scaled-map-measurements.json
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B review/chen2d-15/verify_evidence.py
```

| Verified artifact | SHA-256 |
|---|---|
| [all-tests.txt](review/chen2d-15/all-tests.txt) | e284bc0ecb03ff96e0aa48f896ff28156bf3f98d03f2cd5059004dce222da25d |
| [scaled-map-measurements.json](review/chen2d-15/scaled-map-measurements.json) | 8e234e00b07efb6e3811f1a8bc5641fe6dcc6e5fe3c2c60bd6266891d7aefe09 |
| [probe/results.jsonl](review/chen2d-15/probe/results.jsonl) | 425d4af65e1cb6c64abe65b5f443ebea040c939ae267afae893f7f22da1fd368 |
| [example-messages.json](review/chen2d-15/example-messages.json) | 91b879e9af96aa7f9dd606a659fa44068d1bafc59ca96bf9efe4a0d3038bb734 |
| [example-matched.json](review/chen2d-15/example-matched.json) | 1876e6a1b8ba7ce297caa4ec44394b541c37cff36e64938b1b446adb24ff4394 |
| [verification.json](review/chen2d-15/verification.json) | a58cff59457923ba3f11dc19ad18614e1701d162332b3a7904189c91bcf618eb |

### 확인 안 됨

- These runs measured the scripted writer and offline transports. The live model’s reading-load effect, cutoff rates, token medians, routing, billing and completion rates require the main session’s run.
- The six source episodes cover one static successful GLM cohort. The size of any effect on other sources, unsuccessful episodes, private communications or scaled boards remains unmeasured.
- The board can contain indistinguishable copies of a colour. Peer name overlap is observable, while the physical identity of some alleged conflicts remains ambiguous.
- The headroom example covers one distributed 32-robot, 64-box episode. Performance under another seed, model, rate or budget remains open. No experimental rate has been selected.

## CHEN2D-16

A matched planner can now assign one call to a rectangular sub-team with `--frameworks GROUP --group-size G`. At any positive horizon, each block has one writer and the executor combines their plans. At G = 1 the entire message sequence and merged plans matched OWN byte for byte with the fake model. At G = team size they matched CMAS, including its choice of speaker. The cross-border test delivered a box in one planning round when the receiving leader spoke second and in two rounds when it spoke first. [Endpoint and handover tests](test_chen2d_v16.py) · [Both executed handovers](review/chen2d-16/handover.json)

### The partition on each grid

The table gives every valid G and its block height × width. Blocks start in the upper left. For zero-based cell (r, c), on a board of width C with block shape h × w, its one-based block number is `1 + (r // h) * (C // w) + c // w`. Leaders speak in that order. Members within a block are listed in row-major order. The top-left robot speaks for an intermediate block. The whole-board endpoint uses the map’s assigned CMAS speaker, including L2 for e2. Each writer submits its block’s actions directly to the executor. [All 46 ordered partitions with robot names](review/chen2d-16/partitions.json)

| Grid | G and corresponding block shape |
|---|---|
| 2×2 | 1 (1×1), 2 (1×2), 4 (2×2) |
| 2×4 | 1 (1×1), 2 (1×2), 4 (2×2), 8 (2×4) |
| 4×4 | 1 (1×1), 2 (1×2), 4 (2×2), 8 (2×4), 16 (4×4) |
| 4×8 | 1 (1×1), 2 (1×2), 4 (2×2), 8 (2×4), 16 (4×4), 32 (4×8) |
| 2×8 | 1 (1×1), 2 (1×2), 4 (2×2), 8 (2×4), 16 (2×8) |
| 4×6 | 1 (1×1), 2 (1×2), 3 (1×3), 4 (2×2), 6 (2×3), 12 (4×3), 24 (4×6) |
| 6×6 | 1 (1×1), 2 (1×2), 3 (1×3), 4 (2×2), 6 (2×3), 9 (3×3), 12 (2×6), 18 (3×6), 36 (6×6) |
| 8×8 | 1 (1×1), 2 (1×2), 4 (2×2), 8 (2×4), 16 (4×4), 32 (4×8), 64 (8×8) |

<details><summary>Block numbers on every grid at every valid G</summary>

Each entry identifies the writer for that square. The first row of each matrix is the top row of the board.

**2×2**

```text
G = 1 (1×1)
 1  2
 3  4

G = 2 (1×2)
 1  1
 2  2

G = 4 (2×2)
 1  1
 1  1

```

**2×4**

```text
G = 1 (1×1)
 1  2  3  4
 5  6  7  8

G = 2 (1×2)
 1  1  2  2
 3  3  4  4

G = 4 (2×2)
 1  1  2  2
 1  1  2  2

G = 8 (2×4)
 1  1  1  1
 1  1  1  1

```

**4×4**

```text
G = 1 (1×1)
 1  2  3  4
 5  6  7  8
 9 10 11 12
13 14 15 16

G = 2 (1×2)
 1  1  2  2
 3  3  4  4
 5  5  6  6
 7  7  8  8

G = 4 (2×2)
 1  1  2  2
 1  1  2  2
 3  3  4  4
 3  3  4  4

G = 8 (2×4)
 1  1  1  1
 1  1  1  1
 2  2  2  2
 2  2  2  2

G = 16 (4×4)
 1  1  1  1
 1  1  1  1
 1  1  1  1
 1  1  1  1

```

**4×8**

```text
G = 1 (1×1)
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
17 18 19 20 21 22 23 24
25 26 27 28 29 30 31 32

G = 2 (1×2)
 1  1  2  2  3  3  4  4
 5  5  6  6  7  7  8  8
 9  9 10 10 11 11 12 12
13 13 14 14 15 15 16 16

G = 4 (2×2)
 1  1  2  2  3  3  4  4
 1  1  2  2  3  3  4  4
 5  5  6  6  7  7  8  8
 5  5  6  6  7  7  8  8

G = 8 (2×4)
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 3  3  3  3  4  4  4  4
 3  3  3  3  4  4  4  4

G = 16 (4×4)
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2

G = 32 (4×8)
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1

```

**2×8**

```text
G = 1 (1×1)
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16

G = 2 (1×2)
 1  1  2  2  3  3  4  4
 5  5  6  6  7  7  8  8

G = 4 (2×2)
 1  1  2  2  3  3  4  4
 1  1  2  2  3  3  4  4

G = 8 (2×4)
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2

G = 16 (2×8)
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1

```

**4×6**

```text
G = 1 (1×1)
 1  2  3  4  5  6
 7  8  9 10 11 12
13 14 15 16 17 18
19 20 21 22 23 24

G = 2 (1×2)
 1  1  2  2  3  3
 4  4  5  5  6  6
 7  7  8  8  9  9
10 10 11 11 12 12

G = 3 (1×3)
 1  1  1  2  2  2
 3  3  3  4  4  4
 5  5  5  6  6  6
 7  7  7  8  8  8

G = 4 (2×2)
 1  1  2  2  3  3
 1  1  2  2  3  3
 4  4  5  5  6  6
 4  4  5  5  6  6

G = 6 (2×3)
 1  1  1  2  2  2
 1  1  1  2  2  2
 3  3  3  4  4  4
 3  3  3  4  4  4

G = 12 (4×3)
 1  1  1  2  2  2
 1  1  1  2  2  2
 1  1  1  2  2  2
 1  1  1  2  2  2

G = 24 (4×6)
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1

```

**6×6**

```text
G = 1 (1×1)
 1  2  3  4  5  6
 7  8  9 10 11 12
13 14 15 16 17 18
19 20 21 22 23 24
25 26 27 28 29 30
31 32 33 34 35 36

G = 2 (1×2)
 1  1  2  2  3  3
 4  4  5  5  6  6
 7  7  8  8  9  9
10 10 11 11 12 12
13 13 14 14 15 15
16 16 17 17 18 18

G = 3 (1×3)
 1  1  1  2  2  2
 3  3  3  4  4  4
 5  5  5  6  6  6
 7  7  7  8  8  8
 9  9  9 10 10 10
11 11 11 12 12 12

G = 4 (2×2)
 1  1  2  2  3  3
 1  1  2  2  3  3
 4  4  5  5  6  6
 4  4  5  5  6  6
 7  7  8  8  9  9
 7  7  8  8  9  9

G = 6 (2×3)
 1  1  1  2  2  2
 1  1  1  2  2  2
 3  3  3  4  4  4
 3  3  3  4  4  4
 5  5  5  6  6  6
 5  5  5  6  6  6

G = 9 (3×3)
 1  1  1  2  2  2
 1  1  1  2  2  2
 1  1  1  2  2  2
 3  3  3  4  4  4
 3  3  3  4  4  4
 3  3  3  4  4  4

G = 12 (2×6)
 1  1  1  1  1  1
 1  1  1  1  1  1
 2  2  2  2  2  2
 2  2  2  2  2  2
 3  3  3  3  3  3
 3  3  3  3  3  3

G = 18 (3×6)
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1
 2  2  2  2  2  2
 2  2  2  2  2  2
 2  2  2  2  2  2

G = 36 (6×6)
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1
 1  1  1  1  1  1

```

**8×8**

```text
G = 1 (1×1)
 1  2  3  4  5  6  7  8
 9 10 11 12 13 14 15 16
17 18 19 20 21 22 23 24
25 26 27 28 29 30 31 32
33 34 35 36 37 38 39 40
41 42 43 44 45 46 47 48
49 50 51 52 53 54 55 56
57 58 59 60 61 62 63 64

G = 2 (1×2)
 1  1  2  2  3  3  4  4
 5  5  6  6  7  7  8  8
 9  9 10 10 11 11 12 12
13 13 14 14 15 15 16 16
17 17 18 18 19 19 20 20
21 21 22 22 23 23 24 24
25 25 26 26 27 27 28 28
29 29 30 30 31 31 32 32

G = 4 (2×2)
 1  1  2  2  3  3  4  4
 1  1  2  2  3  3  4  4
 5  5  6  6  7  7  8  8
 5  5  6  6  7  7  8  8
 9  9 10 10 11 11 12 12
 9  9 10 10 11 11 12 12
13 13 14 14 15 15 16 16
13 13 14 14 15 15 16 16

G = 8 (2×4)
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 3  3  3  3  4  4  4  4
 3  3  3  3  4  4  4  4
 5  5  5  5  6  6  6  6
 5  5  5  5  6  6  6  6
 7  7  7  7  8  8  8  8
 7  7  7  7  8  8  8  8

G = 16 (4×4)
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 1  1  1  1  2  2  2  2
 3  3  3  3  4  4  4  4
 3  3  3  3  4  4  4  4
 3  3  3  3  4  4  4  4
 3  3  3  3  4  4  4  4

G = 32 (4×8)
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 2  2  2  2  2  2  2  2
 2  2  2  2  2  2  2  2
 2  2  2  2  2  2  2  2
 2  2  2  2  2  2  2  2

G = 64 (8×8)
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1
 1  1  1  1  1  1  1  1

```

</details>

G = 4 uses two rows and two columns. G = 8 uses two rows and four columns, so the runner rejects G = 8 on 4×6. For other intermediate sizes, the implementation chooses the tiling rectangle with the smallest difference between side lengths, then the one with fewer rows. The run file records the ordered blocks, shape and expected caller count for every compatible grid at the requested G. The assignment manifest identifies the selected grids and seeds. The invocation ledger records admissions. An invalid request lists the valid sizes for its grid before map enrolment. The CLI help lists all eight grids. [Partition implementation](matched_protocol.py) · [Example run file](review/chen2d-16/g4/run.json) · [Assignments](review/chen2d-16/g4/assignments.json)

| Robots | Initial calls at G = 1 (OWN) | G = 4 | G = 8 | G = all (CMAS) |
|---:|---:|---:|---:|---:|
| 16 | 16 | 4 | 2 | 1 |
| 32 | 32 | 8 | 4 | 1 |

Each number counts the writers in one complete initial sweep. A round records the scheduled count in `callers_per_round` and the distinct planning writers actually reached in `callers_reached`. A cutoff or ceiling can end the sweep early. Repairs, transport retries and optional relay calls add work. [Round and per-writer accounting](planning_metrics.py)

### What each leader reads and writes

Each writer sees the whole current board and its doable actions, the selected public history of executed states and actions, and the state position chosen with `--state-position`. Matched history uses the same window and method for all three structures. Announcements and relays use the physical speaker’s inbox. A block leader sees the accepted lists from earlier leaders in this round under the same heading as OWN. The goal, examples, output-format text and brevity instruction are shared. Only the writer assignment and the earlier-speaker material vary. [Matched template](matched_protocol.py) · [Round execution](horizon.py)

An intermediate writer is asked for H joint objects keyed by its robots. Every step is checked for membership using the CMAS joint-list parser with the block’s coordinates as the allowed set. Lenient CMAS forms such as one joint object, a wrapped list and numbered steps work here. Both parsing modes accept a shorter joint list. A missing tail contributes idle steps to the H-step merge. The first step must pass the current doable-action check in its entirety. A valid list becomes visible to later writers under its leader’s name. An unreadable list, a foreign robot key or an invalid first step exposes JSON `null` for that writer. An accepted idle step is `{}`. G = 1 uses the OWN individual-entry grammar and its existing lenient forms. G = all uses CMAS’s original joint-list length and execution rules. [Shared parser](plan_parse.py) · [Saved second-leader call](review/chen2d-16/g4/episodes/4x4_GROUP-g4_static_env0/calls/00002.json)

After the initial sweep, each writer whose submission failed gets up to two repair calls. Repairs use the original board and peer view. Both replies are checked. A successful repair enters the merge. A block still in error after the last repair contributes zero actions, and each of its robots appears in `dropped_robots`. At the CMAS endpoint, exhausting the sole writer’s repairs ends the episode under the existing CMAS rule. For multiple writers, the executor combines accepted entries by step, skips idle steps and checks the resulting joint move against the state at that step. A later invalid joint step discards the remaining suffix and triggers replanning if budget remains. Each issued action identifies its author’s accepted call. [Repair, dropped-block and later-step regressions](test_chen2d_v16.py)

On the 2×4 handover board, the left leader planned for the robot at [0.5, 1.5] to send its red box to [0.5, 2.5] at step 1. The right block started with zero robots able to act. Its leader read the left block’s accepted list and scheduled delivery to the red target at step 2. The merged actions came from calls 1 and 2. With the direction reversed, the receiving leader spoke before the sender. It first saw the incoming box on the next board, and the executed actions came from calls 2 and 3. Both runs used H = 5 and the ordinary text-driven fake solver. [Calls, peer lists and executed actions](review/chen2d-16/handover.json)

Every GROUP logical call records `framework`, `group_size`, `callers_per_round`, the assigned robot names, `robots_assigned` and `assigned_robots_with_doable_actions`. The last count measures how many assigned robots had at least one legal action on the current board. It also covers repairs and cutoffs. Relay calls have zero planning assignments. The matched transport records each physical attempt’s finish evidence, generated tokens and reasoning tokens. The episode keeps the round cutoff classes, the first blocked round, cause and stage, and the final end label. The default ceilings are 30 executed steps, 30 planning rounds and 300 physical calls per episode, subject to the client’s effective limit. [Call recording](LLM.py) · [Example episode](review/chen2d-16/g4/episodes/4x8_GROUP-g4_static_env0/episode.json)

### Three full prompts on the same 4×4 board at H = 5

These are the first-round wire messages on the static scaled:1 map, seed 0, with the board before history. The middle column shows the second block leader, the top-left robot of the upper-right 2×2 block. The OWN column uses that same physical robot, its third caller. CMAS has one caller. Bold marks the complete differing lines, including the earlier lists actually visible when each spoke. The linked call records retain the original whitespace and unmarked messages. [CMAS call 1](review/chen2d-16/g4/episodes/4x4_CMAS_static_env0/calls/00001.json) · [GROUP call 2](review/chen2d-16/g4/episodes/4x4_GROUP-g4_static_env0/calls/00002.json) · [OWN call 3](review/chen2d-16/g4/episodes/4x4_OWN_static_env0/calls/00003.json)

<table>
<thead><tr><th>Matched CMAS</th><th>GROUP, G = 4, second leader</th><th>Matched OWN, same robot</th></tr></thead>
<tbody><tr><td><pre><code>[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets. The dropoff is only for boxes whose order has been changed to the dropoff. Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_orange'], I can do ['move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['box_blue', 'target_orange'], I can do ['move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red', 'target_green', 'target_purple'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_red', 'box_red', 'target_green'], I can do ['move(box_red, square[0.5, 0.5])', 'move(box_red, square[2.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[2.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [], I can do []
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['target_red', 'target_purple'], I can do []
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe [], I can do []
Agent[2.5, 0.5]: I am in square[2.5, 0.5], I can observe ['target_blue', 'box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 0.5])', 'move(box_green, square[3.5, 0.5])', 'move(box_green, square[2.5, 1.5])', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[3.5, 0.5])', 'move(box_orange, square[2.5, 1.5])']
Agent[2.5, 1.5]: I am in square[2.5, 1.5], I can observe ['box_blue', 'target_red', 'box_green'], I can do ['move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[3.5, 1.5])', 'move(box_blue, square[2.5, 0.5])', 'move(box_blue, square[2.5, 2.5])', 'move(box_green, square[1.5, 1.5])', 'move(box_green, square[3.5, 1.5])', 'move(box_green, square[2.5, 0.5])', 'move(box_green, square[2.5, 2.5])']
Agent[2.5, 2.5]: I am in square[2.5, 2.5], I can observe ['target_green', 'box_purple'], I can do ['move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[3.5, 2.5])', 'move(box_purple, square[2.5, 1.5])', 'move(box_purple, square[2.5, 3.5])']
Agent[2.5, 3.5]: I am in square[2.5, 3.5], I can observe ['box_red', 'box_purple'], I can do ['move(box_red, square[1.5, 3.5])', 'move(box_red, square[3.5, 3.5])', 'move(box_red, square[2.5, 2.5])', 'move(box_purple, square[1.5, 3.5])', 'move(box_purple, square[3.5, 3.5])', 'move(box_purple, square[2.5, 2.5])']
Agent[3.5, 0.5]: I am in square[3.5, 0.5], I can observe ['box_blue', 'target_blue'], I can do ['move(box_blue, square[2.5, 0.5])', 'move(box_blue, square[3.5, 1.5])', 'move(box_blue, target_blue)']
Agent[3.5, 1.5]: I am in square[3.5, 1.5], I can observe ['target_blue', 'target_purple'], I can do []
Agent[3.5, 2.5]: I am in square[3.5, 2.5], I can observe ['target_orange'], I can do []
Agent[3.5, 3.5]: I am in square[3.5, 3.5], I can observe ['box_blue', 'target_blue', 'box_purple', 'box_orange', 'dropoff'], I can do ['move(box_blue, square[2.5, 3.5])', 'move(box_blue, square[3.5, 2.5])', 'move(box_blue, target_blue)', 'move(box_purple, square[2.5, 3.5])', 'move(box_purple, square[3.5, 2.5])', 'move(box_orange, square[2.5, 3.5])', 'move(box_orange, square[3.5, 2.5])', 'move(box_blue, dropoff)', 'move(box_purple, dropoff)', 'move(box_orange, dropoff)']

Earlier executed state and action pairs:

<b>Write a joint entry for every step, choosing the actions of all robots.</b>
Return a JSON list for the next 5 steps in execution order.
Use a joint object mapping each acting Agent[row, col] to its action string, with {} for an idle step. Use one action string or the JSON literal null for an individual entry. Assume the earlier entries have been executed. Return only the list.
Respond concisely.</code></pre></td><td><pre><code>[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets. The dropoff is only for boxes whose order has been changed to the dropoff. Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_orange'], I can do ['move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['box_blue', 'target_orange'], I can do ['move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red', 'target_green', 'target_purple'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_red', 'box_red', 'target_green'], I can do ['move(box_red, square[0.5, 0.5])', 'move(box_red, square[2.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[2.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [], I can do []
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['target_red', 'target_purple'], I can do []
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe [], I can do []
Agent[2.5, 0.5]: I am in square[2.5, 0.5], I can observe ['target_blue', 'box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 0.5])', 'move(box_green, square[3.5, 0.5])', 'move(box_green, square[2.5, 1.5])', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[3.5, 0.5])', 'move(box_orange, square[2.5, 1.5])']
Agent[2.5, 1.5]: I am in square[2.5, 1.5], I can observe ['box_blue', 'target_red', 'box_green'], I can do ['move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[3.5, 1.5])', 'move(box_blue, square[2.5, 0.5])', 'move(box_blue, square[2.5, 2.5])', 'move(box_green, square[1.5, 1.5])', 'move(box_green, square[3.5, 1.5])', 'move(box_green, square[2.5, 0.5])', 'move(box_green, square[2.5, 2.5])']
Agent[2.5, 2.5]: I am in square[2.5, 2.5], I can observe ['target_green', 'box_purple'], I can do ['move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[3.5, 2.5])', 'move(box_purple, square[2.5, 1.5])', 'move(box_purple, square[2.5, 3.5])']
Agent[2.5, 3.5]: I am in square[2.5, 3.5], I can observe ['box_red', 'box_purple'], I can do ['move(box_red, square[1.5, 3.5])', 'move(box_red, square[3.5, 3.5])', 'move(box_red, square[2.5, 2.5])', 'move(box_purple, square[1.5, 3.5])', 'move(box_purple, square[3.5, 3.5])', 'move(box_purple, square[2.5, 2.5])']
Agent[3.5, 0.5]: I am in square[3.5, 0.5], I can observe ['box_blue', 'target_blue'], I can do ['move(box_blue, square[2.5, 0.5])', 'move(box_blue, square[3.5, 1.5])', 'move(box_blue, target_blue)']
Agent[3.5, 1.5]: I am in square[3.5, 1.5], I can observe ['target_blue', 'target_purple'], I can do []
Agent[3.5, 2.5]: I am in square[3.5, 2.5], I can observe ['target_orange'], I can do []
Agent[3.5, 3.5]: I am in square[3.5, 3.5], I can observe ['box_blue', 'target_blue', 'box_purple', 'box_orange', 'dropoff'], I can do ['move(box_blue, square[2.5, 3.5])', 'move(box_blue, square[3.5, 2.5])', 'move(box_blue, target_blue)', 'move(box_purple, square[2.5, 3.5])', 'move(box_purple, square[3.5, 2.5])', 'move(box_orange, square[2.5, 3.5])', 'move(box_orange, square[3.5, 2.5])', 'move(box_blue, dropoff)', 'move(box_purple, dropoff)', 'move(box_orange, dropoff)']

Earlier executed state and action pairs:

<b>Write a joint entry for every step, choosing actions only for ["Agent[0.5, 2.5]", "Agent[0.5, 3.5]", "Agent[1.5, 2.5]", "Agent[1.5, 3.5]"].</b>
<b>Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [{"Agent[0.5, 0.5]": "move(box_orange, square[0.5, 1.5])", "Agent[0.5, 1.5]": "move(box_blue, square[0.5, 0.5])", "Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])"}, {"Agent[0.5, 0.5]": "move(box_blue, square[1.5, 0.5])", "Agent[0.5, 1.5]": "move(box_orange, target_orange)", "Agent[1.5, 0.5]": "move(box_red, square[1.5, 1.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])"}, {"Agent[1.5, 0.5]": "move(box_blue, square[2.5, 0.5])", "Agent[1.5, 1.5]": "move(box_red, square[1.5, 2.5])"}, {}, {}]}</b>
Return a JSON list for the next 5 steps in execution order.
Use a joint object mapping each acting Agent[row, col] to its action string, with {} for an idle step. Use one action string or the JSON literal null for an individual entry. Assume the earlier entries have been executed. Return only the list.
Respond concisely.</code></pre></td><td><pre><code>[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets. The dropoff is only for boxes whose order has been changed to the dropoff. Putting any other box into the dropoff counts as a wrong delivery, and a wrong delivery cannot be undone.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_orange'], I can do ['move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['box_blue', 'target_orange'], I can do ['move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['box_green', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[0.5, 3.5])']
Agent[0.5, 3.5]: I am in square[0.5, 3.5], I can observe ['target_red', 'target_green', 'target_purple'], I can do []
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_red', 'box_red', 'target_green'], I can do ['move(box_red, square[0.5, 0.5])', 'move(box_red, square[2.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[2.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [], I can do []
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['target_red', 'target_purple'], I can do []
Agent[1.5, 3.5]: I am in square[1.5, 3.5], I can observe [], I can do []
Agent[2.5, 0.5]: I am in square[2.5, 0.5], I can observe ['target_blue', 'box_green', 'box_orange'], I can do ['move(box_green, square[1.5, 0.5])', 'move(box_green, square[3.5, 0.5])', 'move(box_green, square[2.5, 1.5])', 'move(box_orange, square[1.5, 0.5])', 'move(box_orange, square[3.5, 0.5])', 'move(box_orange, square[2.5, 1.5])']
Agent[2.5, 1.5]: I am in square[2.5, 1.5], I can observe ['box_blue', 'target_red', 'box_green'], I can do ['move(box_blue, square[1.5, 1.5])', 'move(box_blue, square[3.5, 1.5])', 'move(box_blue, square[2.5, 0.5])', 'move(box_blue, square[2.5, 2.5])', 'move(box_green, square[1.5, 1.5])', 'move(box_green, square[3.5, 1.5])', 'move(box_green, square[2.5, 0.5])', 'move(box_green, square[2.5, 2.5])']
Agent[2.5, 2.5]: I am in square[2.5, 2.5], I can observe ['target_green', 'box_purple'], I can do ['move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[3.5, 2.5])', 'move(box_purple, square[2.5, 1.5])', 'move(box_purple, square[2.5, 3.5])']
Agent[2.5, 3.5]: I am in square[2.5, 3.5], I can observe ['box_red', 'box_purple'], I can do ['move(box_red, square[1.5, 3.5])', 'move(box_red, square[3.5, 3.5])', 'move(box_red, square[2.5, 2.5])', 'move(box_purple, square[1.5, 3.5])', 'move(box_purple, square[3.5, 3.5])', 'move(box_purple, square[2.5, 2.5])']
Agent[3.5, 0.5]: I am in square[3.5, 0.5], I can observe ['box_blue', 'target_blue'], I can do ['move(box_blue, square[2.5, 0.5])', 'move(box_blue, square[3.5, 1.5])', 'move(box_blue, target_blue)']
Agent[3.5, 1.5]: I am in square[3.5, 1.5], I can observe ['target_blue', 'target_purple'], I can do []
Agent[3.5, 2.5]: I am in square[3.5, 2.5], I can observe ['target_orange'], I can do []
Agent[3.5, 3.5]: I am in square[3.5, 3.5], I can observe ['box_blue', 'target_blue', 'box_purple', 'box_orange', 'dropoff'], I can do ['move(box_blue, square[2.5, 3.5])', 'move(box_blue, square[3.5, 2.5])', 'move(box_blue, target_blue)', 'move(box_purple, square[2.5, 3.5])', 'move(box_purple, square[3.5, 2.5])', 'move(box_orange, square[2.5, 3.5])', 'move(box_orange, square[3.5, 2.5])', 'move(box_blue, dropoff)', 'move(box_purple, dropoff)', 'move(box_orange, dropoff)']

Earlier executed state and action pairs:

<b>Write an individual entry for every step, choosing only the action of Agent[0.5, 2.5].</b>
<b>Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_orange, square[0.5, 1.5])", null, null, null, null], "Agent[0.5, 1.5]": ["move(box_blue, square[0.5, 0.5])", "move(box_orange, target_orange)", null, null, null]}</b>
Return a JSON list for the next 5 steps in execution order.
Use a joint object mapping each acting Agent[row, col] to its action string, with {} for an idle step. Use one action string or the JSON literal null for an individual entry. Assume the earlier entries have been executed. Return only the list.
Respond concisely.</code></pre></td></tr></tbody>
</table>

### Reading probe

`group_first` and `group_last` select the same last block in speaking order with at least one robot able to act on the saved board. Its representative may be idle. The first view receives an empty peer dictionary. The last view receives one list per preceding leader. Its first joint object contains that block’s physically executed moves at the source step, keyed by the issuing robots. The remaining entries are empty joint steps. These source-derived lists are counterfactual probe inputs. In an episode the peer lists come from the writers’ actual proposals. The judge applies the block’s key restriction, checks all proposed first-step actions and looks for conflicts with actions in earlier blocks. The result includes the active count in the block and on the whole board. At the two endpoints the probe uses the original individual or central prompt and reply grammar. [Probe implementation](probe_reading.py) · [G = 4 probe cells](review/chen2d-16/probe-g4/results.jsonl) · [G = 8 probe cells](review/chen2d-16/probe-g8/results.jsonl)

### Fairness points for review

- Every writer reads the whole board. As G falls, the board and history are sent more often. Later writers also read longer peer lists. Compare physical calls, prompt tokens and generated tokens, including failed episodes and retries.
- A fixed row-major order favors handovers to later speakers. Reversing the transfer direction can cost a planning round even when the box and target are one square apart. The shape and orientation of the blocks determine how many routes cross boundaries.
- Episodes call idle writers. The two group probe arms deliberately sample an active block. Compare active robots per assigned block, box density and seed when interpreting either result.
- Every writer has two repair chances. The team-wide number of chances grows with the number of writers. One bad entry can cost an entire block’s plan, and another writer may already have planned against its initial refusal.
- Larger blocks produce more output per call and can hit the output limit. Smaller blocks spend the episode call allowance faster. With 32 singleton writers, four complete initial sweeps cost 128 calls before repairs, retries or relays. Compare end labels, first blocked causes and strict completions alongside costs.
- Private messages go to the physical robot. Changing G can move a notified robot out of a speaking role. The static comparison below holds the map fixed and removes that source of variation. For changed-order episodes, check the actual speaker’s announcement and inbox.
- The smoke uses one seed per size. Its scripted model has fixed accounting of 11 prompt tokens and 7 generated tokens per successful call. Those totals verify the accounting path. Live reading cost and output demand require measured token counts.

### Offline results

All **218 tests passed**, comprising the 205 earlier tests and 13 for CHEN2D-16. The partition test checked the ordered membership of every block in all 46 grid/size combinations and refused all other integer sizes from zero through one past the board area. The public runner also exercised 2×8, 4×6, 6×6 and 8×8 on temporary scaled maps. The repair tests covered a partly valid first step, an out-of-block key in a future step, survival of another block’s work, a successful final repair, a full block drop and a later invalid joint step. A folder-local scripted transport supplied recovered and exhausted cutoffs. The ceiling tests included an interrupted first sweep. [Full test log](review/chen2d-16/all-tests.txt) · [Focused test log](review/chen2d-16/task16-tests.txt) · [Task 16 tests](test_chen2d_v16.py)

The default replay compared five native writers and the two matched writers on the 2×2 static seed-0 map against the frozen Task 15 source. It compared every episode file, the assignment manifest and the CSV, with fixed clocks and invocation identity and only the source-version string normalized. A separate replay reproduced all 21 CMAS files and 36 OWN files in the saved Task 15 matched episodes byte for byte using their recorded clocks and version. The earlier suite also replayed the historical CMAS/DMAS H1 trees, the eight DMAS state-order episodes and archived prompts for all four original frameworks. The runner and probe retained their original default selections. [Default and archived replay tests](test_chen2d_v16.py) · [Frozen Task 15 source](review/chen2d-15/matched-scaled/source)

The eight comparison episodes below used the same scaled:1 seed-0 maps, H = 5, a four-round cap and a 20-step cap. They made **262 physical fake calls**. Five episodes completed strictly. Each matched cell retains the total from all its episodes and prints `no completion` when its strict-completion denominator is zero. [Planning and token tables](review/chen2d-16/planning-summary.txt) · [Recount from physical attempts](review/chen2d-16/verification.json)

| Grid | Writer | G | Rounds | Executed steps | Calls | Prompt tokens | Generated tokens | End label |
|---|---|---:|---:|---:|---:|---:|---:|---|
| 4×4 | OWN | 1 | 4 | 13 | 64 | 704 | 448 | planning round ceiling |
| 4×4 | GROUP | 4 | 3 | 10 | 12 | 132 | 84 | success |
| 4×4 | GROUP | 8 | 2 | 10 | 4 | 44 | 28 | success |
| 4×4 | CMAS | 16 | 2 | 8 | 2 | 22 | 14 | success |
| 4×8 | OWN | 1 | 4 | 17 | 128 | 1,408 | 896 | planning round ceiling |
| 4×8 | GROUP | 4 | 4 | 20 | 32 | 352 | 224 | environment step ceiling |
| 4×8 | GROUP | 8 | 4 | 18 | 16 | 176 | 112 | success |
| 4×8 | CMAS | 32 | 4 | 18 | 4 | 44 | 28 | success |

Four additional endpoint replays checked **198 paired wire prompts and replies** on those two maps. G = 1 matched all 64 and 128 OWN calls. G = all matched all 2 and 4 CMAS calls. The serialized merged plans, saved prompt files, issued responses, state files and dialogue files matched for each pair. The probe used four saved states, two active-block views and four history arms at each of two group sizes. All **64/64** probe calls returned readable plans, with **0/64** first-step rejections and **0/64** cutoffs. A guard-and-resume test verified that finished probe cells and the recorded calls of an interrupted episode were reused. [Endpoint digests and probe recount](review/chen2d-16/verification.json) · [G = 4 probe summary](review/chen2d-16/probe-g4/summary.json) · [G = 8 probe summary](review/chen2d-16/probe-g8/summary.json)

### Commands for the main session

Run these from the task folder. The commands reproduce the comparison with the fake model in fresh run folders. Keep the same map, history, horizon and ceilings in each arm. Use an output folder per G so its run file fixes the partition. CMAS and OWN appear once in the combined summary.

```bash
export TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1
base=runs/chen16
common=(--model fake --protocol matched --envs 0 --conditions static --map-set scaled:1
        --horizon 5 --history-method authors --history-window 3000 --state-position before
        --max-env-steps 20 --max-planning-rounds 4 --episode-call-ceiling 300
        --max-calls 350 --max-cost-usd 1.5)
python3 -B run_chen2d.py "${common[@]}" --sizes 4x4,4x8 --frameworks CMAS,OWN,GROUP --group-size 4 --out "$base/g4"
python3 -B run_chen2d.py "${common[@]}" --sizes 4x4,4x8 --frameworks GROUP --group-size 8 --out "$base/g8"
python3 -B summarize.py --by planning "$base/g4" "$base/g8"
python3 -B cost.py "$base/g4"
python3 -B cost.py "$base/g8"
python3 -B output_demand.py "$base/g4" "$base/g8" --calls-csv "$base/writer-calls.csv"
```

To reproduce the four endpoint pairs and the corresponding reading probes on those same maps, use the numeric whole-board sizes 16 and 32.

```bash
python3 -B run_chen2d.py "${common[@]}" --sizes 4x4,4x8 --frameworks GROUP --group-size 1 --out "$base/endpoints/g1"
python3 -B run_chen2d.py "${common[@]}" --sizes 4x4 --frameworks GROUP --group-size 16 --out "$base/endpoints/g16"
python3 -B run_chen2d.py "${common[@]}" --sizes 4x8 --frameworks GROUP --group-size 32 --out "$base/endpoints/g32"

sources="$base/g4/episodes/4x4_CMAS_static_env0,$base/g4/episodes/4x8_CMAS_static_env0"
for g in 4 8; do
  python3 -B probe_reading.py --model fake --episodes "$sources" --per-episode 2 \
    --protocol matched --group-size "$g" --callers group_first,group_last \
    --arms none,last1,all_before,all_after --horizon 5 --max-calls 32 --max-cost-usd 0.1 \
    --out "$base/probe-g$g"
  python3 -B probe_reading.py --summarize "$base/probe-g$g"
done
```

The folder-local test harness and the independent recount of the published traces run with these commands.

```bash
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v14.py \
  test_chen2d test_chen2d_v{2..14} test_chen2d_v15_{maps,matched,cli,probe,probe_exec} test_chen2d_v16
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B review/chen2d-16/verify_evidence.py
```

### 확인 안 됨

- Live-model completion rates, generated and reasoning tokens, cutoff rates, latency and billing for each G.
- Whether any group size performs better across map seeds, box densities, state orders or private event announcements.
- Human or physical-robot handover performance and the effect of adding a planner above the block leaders. The implemented structure has one layer of sub-team writers.

## CHEN2D-17

The matched pilot completed 1 of 8 episodes. Across the four OWN episodes, the model returned 2,030 texts. The saved planning-round checks marked 1,979 as parse failures. One additional logical call ended without a response. In 4×8 seed 0 alone, 574 of the 586 returned texts had no recorded OWN form. The rows below replay the actual GLM texts on their original boards. [Original pilot episode table](../20261124-chen2d-snap-v15/runs/v15-pilot-r1/episodes.csv) · [Offline replay](review/chen2d-17/replay_own.py) · [Replay results and call numbers](review/chen2d-17/own-replay.json)

### Matched writer prompts

The tables reproduce the first user message at H = 1 and H = 5 on the same 2×2 scaled:1 seed-0 board, with state after history and no prior turns. Read each column from top to bottom. Bold cells mark the two writer-specific lines. Each full-width row supplies identical text to all three writers. After the first writer, the shared peer-list field contains earlier submissions from that round. GROUP uses the block’s first robot as its writer. The existing single-robot and whole-board GROUP endpoints use the OWN and CMAS writer roles respectively. [Prompt generator](review/chen2d-17/show_prompts.py) · [Writer templates](matched_protocol.py)

#### H = 1

System message for all three writers is `You are a helpful assistant.`.

<table><thead><tr><th>CMAS</th><th>OWN</th><th>GROUP (G = 2)</th></tr></thead><tbody>
<tr><td colspan="3"><code>Match all boxes to their color-coded targets.</code></td></tr>
<tr><td colspan="3"><code>Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.</code></td></tr>
<tr><td colspan="3"><code>Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).</code></td></tr>
<tr><td colspan="3"><code>&nbsp;</code></td></tr>
<tr><td colspan="3"><code>Earlier executed state and action pairs:</code></td></tr>
<tr><td colspan="3"><code>&nbsp;</code></td></tr>
<tr><td colspan="3"><code>Current board and doable actions:</code></td></tr>
<tr><td colspan="3"><code>Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [&#x27;box_red&#x27;], I can do [&#x27;move(box_red, square[1.5, 0.5])&#x27;, &#x27;move(box_red, square[0.5, 1.5])&#x27;]</code></td></tr>
<tr><td colspan="3"><code>Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe [], I can do []</code></td></tr>
<tr><td colspan="3"><code>Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [&#x27;target_red&#x27;, &#x27;box_purple&#x27;], I can do [&#x27;move(box_purple, square[0.5, 0.5])&#x27;, &#x27;move(box_purple, square[1.5, 1.5])&#x27;]</code></td></tr>
<tr><td colspan="3"><code>Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [&#x27;box_blue&#x27;, &#x27;target_blue&#x27;, &#x27;box_green&#x27;, &#x27;target_green&#x27;, &#x27;target_purple&#x27;], I can do [&#x27;move(box_blue, square[0.5, 1.5])&#x27;, &#x27;move(box_blue, square[1.5, 0.5])&#x27;, &#x27;move(box_blue, target_blue)&#x27;, &#x27;move(box_green, square[0.5, 1.5])&#x27;, &#x27;move(box_green, square[1.5, 0.5])&#x27;, &#x27;move(box_green, target_green)&#x27;]</code></td></tr>
<tr><td colspan="3"><code>&nbsp;</code></td></tr>
<tr><td><strong><code>Write a joint entry for every step, choosing the actions of all robots.</code></strong></td><td><strong><code>Write an individual entry for every step, choosing only the action of Agent[0.5, 0.5].</code></strong></td><td><strong><code>Write a joint entry for every step, choosing actions only for [&quot;Agent[0.5, 0.5]&quot;, &quot;Agent[0.5, 1.5]&quot;].</code></strong></td></tr>
<tr><td colspan="3"><code>Earlier robots&#x27; lists in this planning round: {}</code></td></tr>
<tr><td colspan="3"><code>Return a JSON list for the next 1 steps in execution order.</code></td></tr>
<tr><td><strong><code>Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.</code></strong></td><td><strong><code>Each list entry is your own action string or the JSON literal null for a wait.</code></strong></td><td><strong><code>Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.</code></strong></td></tr>
<tr><td colspan="3"><code>Assume the earlier entries have been executed. Return only the list.</code></td></tr>
<tr><td colspan="3"><code>Respond concisely.</code></td></tr>
</tbody></table>

#### H = 5

System message for all three writers is `You are a helpful assistant.`.

<table><thead><tr><th>CMAS</th><th>OWN</th><th>GROUP (G = 2)</th></tr></thead><tbody>
<tr><td colspan="3"><code>Match all boxes to their color-coded targets.</code></td></tr>
<tr><td colspan="3"><code>Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.</code></td></tr>
<tr><td colspan="3"><code>Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).</code></td></tr>
<tr><td colspan="3"><code>&nbsp;</code></td></tr>
<tr><td colspan="3"><code>Earlier executed state and action pairs:</code></td></tr>
<tr><td colspan="3"><code>&nbsp;</code></td></tr>
<tr><td colspan="3"><code>Current board and doable actions:</code></td></tr>
<tr><td colspan="3"><code>Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe [&#x27;box_red&#x27;], I can do [&#x27;move(box_red, square[1.5, 0.5])&#x27;, &#x27;move(box_red, square[0.5, 1.5])&#x27;]</code></td></tr>
<tr><td colspan="3"><code>Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe [], I can do []</code></td></tr>
<tr><td colspan="3"><code>Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe [&#x27;target_red&#x27;, &#x27;box_purple&#x27;], I can do [&#x27;move(box_purple, square[0.5, 0.5])&#x27;, &#x27;move(box_purple, square[1.5, 1.5])&#x27;]</code></td></tr>
<tr><td colspan="3"><code>Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe [&#x27;box_blue&#x27;, &#x27;target_blue&#x27;, &#x27;box_green&#x27;, &#x27;target_green&#x27;, &#x27;target_purple&#x27;], I can do [&#x27;move(box_blue, square[0.5, 1.5])&#x27;, &#x27;move(box_blue, square[1.5, 0.5])&#x27;, &#x27;move(box_blue, target_blue)&#x27;, &#x27;move(box_green, square[0.5, 1.5])&#x27;, &#x27;move(box_green, square[1.5, 0.5])&#x27;, &#x27;move(box_green, target_green)&#x27;]</code></td></tr>
<tr><td colspan="3"><code>&nbsp;</code></td></tr>
<tr><td><strong><code>Write a joint entry for every step, choosing the actions of all robots.</code></strong></td><td><strong><code>Write an individual entry for every step, choosing only the action of Agent[0.5, 0.5].</code></strong></td><td><strong><code>Write a joint entry for every step, choosing actions only for [&quot;Agent[0.5, 0.5]&quot;, &quot;Agent[0.5, 1.5]&quot;].</code></strong></td></tr>
<tr><td colspan="3"><code>Earlier robots&#x27; lists in this planning round: {}</code></td></tr>
<tr><td colspan="3"><code>Return a JSON list for the next 5 steps in execution order.</code></td></tr>
<tr><td><strong><code>Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.</code></strong></td><td><strong><code>Each list entry is your own action string or the JSON literal null for a wait.</code></strong></td><td><strong><code>Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.</code></strong></td></tr>
<tr><td colspan="3"><code>Assume the earlier entries have been executed. Return only the list.</code></td></tr>
<tr><td colspan="3"><code>Respond concisely.</code></td></tr>
</tbody></table>

### Replay of the four OWN episodes

| Grid and seed | Logical calls | Returned replies | Read before | Refused before | Newly read | Still refused | Read now | Newly read with a doable first step |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4×4, seed 0 | 280 | 279 | 9 | 270 | 267 | 3 | 276 | 265 |
| 4×4, seed 1 | 579 | 579 | 17 | 562 | 550 | 12 | 567 | 550 |
| 4×8, seed 0 | 586 | 586 | 12 | 574 | 566 | 8 | 578 | 562 |
| 4×8, seed 1 | 586 | 586 | 13 | 573 | 566 | 7 | 579 | 560 |
| **Total** | **2,031** | **2,030** | **51** | **1,979** | **1,949** | **30** | **2,000** | **1,937** |

All 51 previously readable responses remained readable. Each of the 30 remaining refusals named a robot outside the writer’s assignment. Call 280 of 4×4 seed 0 had a recorded `ResponseError` and no saved response text. The replay reconciled all 2,089 physical attempts with the episode totals and checked that each saved attempt with response text matched exactly one returned reply. It compared the original `own_reply_form` with the original planning-round check before using the current reader. Twelve newly readable responses proposed a first action that the historical board did not allow. An idle first entry counts as doable. Later actions and the replies that would follow a changed board were outside this replay. [Per-episode shapes, refusal details and input hashes](review/chen2d-17/own-replay.json)

### Physical episode ceiling and calls per round

The pilot’s `run.json` records a request of 900, a client `HARD_EPISODE_CALLS` value of 600 and an effective ceiling of 600. The bridge takes the smaller of the request and the client cap. Each provider attempt counts toward it, including retries. Three OWN episodes stopped at exactly 600 physical attempts, after 6, 3 and 2 executed steps respectively. The runner now prints the request, client cap and effective ceiling before dispatch whenever the cap lowers the request. The run manifest retains the request and effective ceiling. Each episode records its effective value in `episode_call_ceiling`. The fake backend has no 600-call provider cap. [Runner](run_chen2d.py) · [Episode and invocation limits](test_chen2d_v17_limits.py)

These are full planning rounds with no optional relay and enough episode budget to reach every writer. A format repair is a new logical call. Each writer can make one initial submission and two repairs. Fake episodes exercised both logical-call columns on both grids. The last two columns give physical upper bounds when individual logical calls also need transport or reply retries.

| Robots | Framework | Logical calls, no repairs | Logical calls, both repairs per writer | Physical upper bound, no repairs | Physical upper bound, both repairs |
|---:|---|---:|---:|---:|---:|
| 16 | CMAS | 1 | 3 | 5 | 15 |
| 16 | GROUP, G = 4 | 4 | 12 | 20 | 60 |
| 16 | GROUP, G = 8 | 2 | 6 | 10 | 30 |
| 16 | OWN | 16 | 48 | 80 | 240 |
| 32 | CMAS | 1 | 3 | 5 | 15 |
| 32 | GROUP, G = 4 | 8 | 24 | 40 | 120 |
| 32 | GROUP, G = 8 | 4 | 12 | 20 | 60 |
| 32 | OWN | 32 | 96 | 160 | 480 |

At one physical attempt per logical call, a 600-call episode can fund 18 full 32-robot OWN rounds with no repairs, or six if every writer uses both repairs. Either case leaves 24 attempts for a partial round.

### Reader decisions and repairs

A matched individual writer receives only the action-string/null instruction. A joint writer receives only the instruction to map acting robots to action strings. For the same board, horizon, history, earlier submissions and notices, the assignment and format are the only two lines that differ. The system message and shared wording are reproduced above. [Prompt comparison](review/chen2d-17/show_prompts.py)

The lenient OWN reader accepts self-keyed entries, empty-object waits, mixed lists and a single self/idle object at H = 1. It also recognizes the pilot’s self-keyed empty object, quoted empty object and “idle” wait spellings. Existing lenient scalar-list padding and trimming apply to recognized OWN entries. The reader checks the whole decoded candidate for another robot’s key before retaining any prefix. The lenient joint reader accepts an idle `{}` step and checks each named robot against the board or the assigned block. Strict writers require a bare list with exactly H entries of their requested type. The call fields `reply_shape`, `reply_shape_accepted`, `reply_refusal_reason` and `reply_refusal_detail` record the decision. A subsequent first-step check records whether the plan can be executed. [Reader](plan_parse.py) · [Episode checks](horizon.py)

The replay counted 1,480 plain lists containing self-keyed objects and 336 plain lists consisting entirely of empty objects. Another 74 responses used an embedded or fenced object/mixed list. An additional 59 used a plain mixed list, 50 a plain scalar list, and one used nested lists. Each of the 30 remaining refusals has its call number, writer, original step and offending agent in the replay output. [Shape counts and refusal records](review/chen2d-17/own-replay.json)

Repairs identify the wrong length, missing list, wrong entry type, out-of-assignment name or rejected first-step action. For an infeasible first step, the message gives each offending robot, its proposed action and its current doable actions. Its example has H entries and takes its first action from the writer’s assigned robots. An OWN writer with no available action sees null entries. A joint writer with no available action sees empty objects. For example, the strict H = 1 test on a board with a red box at `Agent[0.5, 0.5]` produces the following two messages for their respective writers. [Fake repair tests](test_chen2d_v17_writers.py)

```text
Wrong list length (expected 1, got 0). Expected shape: ["move(box_red, square[1.5, 0.5])"] Revise your list using the same board and writer assignment.
Unknown agent named "Agent[0.5, 0.5]" for this writer. Expected shape: [null] Revise your list using the same board and writer assignment.
```

### Retry budgets and terminal labels

Matched calls now have two budgets. They allow three reply-bearing attempts and three transport failures per logical call. A 429, timeout, connection failure or 5xx uses a transport slot. An HTTP 200 with an unusable body uses a reply slot. Either third failure terminates the logical call. Two transport failures and two failed replies can therefore precede one final attempt, for a maximum of five physical requests. The call traces record both counts and retain the individual attempts, finish reasons and metered usage. The runner also records both limits and the five-request maximum. [Client bridge](LLM.py) · [Run manifest settings](run_chen2d.py)

Transport retries use the client’s provider-directed delay or jittered backoff, indexed by transport failures. There are at most two transport waits, with a cumulative allowance of 60 seconds per logical call. A Retry-After beyond the remaining allowance ends the retry. The client deadline can shorten the available window further. A permanent HTTP refusal stops immediately. Reply retries use the client’s reply-delay rule. A plain response error without that rule waits one second. After an interruption, the recorded attempts, accumulated waits and logical call ID carry over to the next authorized invocation. Every physical send still goes through the existing reservation, settlement and request-ID handling. [Retry implementation](LLM.py) · [Recovery and resume tests](test_chen2d_v17_retry.py)

| Terminal condition | Reported label |
|---|---|
| Every reply-bearing attempt was confirmed cut off, including a call that also hit transport errors | `failure output limit` |
| The transport bound, wait window or permanent service refusal ended the call without a reply-bearing attempt | `failure model service` |
| Reply-bearing attempts were unusable and at least one lacks confirmed cutoff evidence | `failure unusable model reply` |
| The physical episode budget prevents another needed call or retry | `episode call ceiling` |
| An invocation call, spend, client or input-token guard stops the episode | The corresponding invocation, client or token-limit label |

A successful final allowed response can complete the task. If a terminal reply or transport budget is already exhausted on that attempt, its own diagnosis is retained. The environment-step and planning-round ceilings have their own labels. [Ceiling tests](test_chen2d_v17_limits.py)

In the pilot, 4×4 CMAS seed 1 call 1 recorded `rate_limit, truncated, truncated`. The 4×8 CMAS seed 0 call 2 recorded `truncated, truncated, rate_limit`. Each truncated attempt had a provider finish reason of `length`. Under the new budgets each prefix leaves a third reply opportunity. Scripted tests exercised both continuations for each prefix. A complete reply succeeded and another cutoff ended as `failure output limit`. The historical pilot does not contain those fourth attempts. [Scripted pilot-prefix tests](test_chen2d_v17_retry.py)

### Reproduction

Run from this task folder. The test harness reconstructs its pinned client and upstream references from the folder-local archive, replaces the HTTP transport and disables socket connections. The replay reads the designated historical pilot and writes its output locally.

```bash
python3 -B review/chen2d-17/replay_own.py > review/chen2d-17/own-replay.json
python3 -B review/chen2d-17/show_prompts.py
TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 python3 -B test_chen2d_v14.py \
  test_chen2d test_chen2d_v{2..14} test_chen2d_v15_{maps,matched,cli,probe,probe_exec} \
  test_chen2d_v16 test_chen2d_v17_{writers,retry,limits,replay} \
  > review/chen2d-17/all-tests.txt 2>&1
```

### Compatibility and verification

The native H = 1 replay still compares every episode file for all five native writers, the assignment manifest and the CSV against frozen Task 15 output with fixed clocks and the source stamp normalized. The matched-only archival comparison now checks the new writer sentences, shape records, two budgets and reader version before comparing the remaining bytes. The older GROUP strict-scope fixture now supplies five entries at H = 5 so that it continues to test the out-of-block key. A separate native OWN test compares entries, form and rescue metadata with the archived native reader. [Compatibility tests](test_chen2d_v16.py) · [Historical CMAS and DMAS byte replays](test_chen2d_v11.py) · [Native OWN reader replay](test_chen2d_v17_replay.py)

An independent scan of the archived JSON found the same 3, 12, 8 and 7 call numbers containing another robot’s key. In every case it verified that the name in the new refusal appears as a foreign key in the original reply. A fresh run of the replay reproduced the published JSON byte for byte. Regenerating the side-by-side prompts reproduced both tables in this report. The 288,588 report bytes preceding this section retain SHA-256 `ca12bd125d6f987b3796b481209b73bf2ed2085d6b19e217392b720e5d850200`.

All **240 tests passed** in 300.465 seconds at protocol revision `a441dc3fbaf2`. The suite covered all 218 earlier cases and 22 CHEN2D-17 cases. The legacy byte replays passed, including the archived native framework outputs, CMAS/DMAS H = 1 episode trees, and the DMAS state-after prompts. The new tests exercised both literal pilot reply shapes, strict and lenient repairs, block ownership, simultaneous reply/transport budgets, interruption and resume, startup ceiling reporting, and all 16 combinations of grid size, writer arrangement and repair use in the table. [Full test log](review/chen2d-17/all-tests.txt)

### 확인 안 됨

The revised prompts’ live GLM completion rate, subsequent robot decisions, actual rate-limit frequency, token use, latency and charges remain unverified. The four replayed OWN episodes contain historical responses to the old prompts. For the two mixed CMAS failures, the next real provider reply is unknown.

The archived client used for scripted HTTP tests has SHA-256 `2b9c5dda01817ad4d3889efcf4f845505bd8c1b21333081c9ce566e323a7dcad`. The pilot recorded `bac988e962c28b7d801d3d081f3c1d6d3e10efb113506f4c958e98b555fa3d64`. Runtime behavior with that exact client revision remains unverified. All retry and ceiling changes are in this task folder. [Folder-local client fixture](review/chen2d-4/offline_suite.py) · [Original pilot manifest](../20261124-chen2d-snap-v15/runs/v15-pilot-r1/run.json)

## CHEN2D-18

**All 48 registered maps were solvable.** With one box per robot, CMAS, GROUP (three robots per writer) and OWN delivered every box to a matching target in all 288 scripted episodes across H=1 and H=5. The H=5 pilot design took 124 fake calls across 18 episodes. The experiment design took 832 across 108 episodes. [Per-episode measurements](review/chen2d-18/board-results.csv) · [Fresh replay by seed split](review/chen2d-18/fresh-replay.txt)

### Recovery from the interrupted run

The stop record is dated 2026-11-24 15:55:35 UTC. The interrupted run had added the board catalog and its tests, edited ten existing modules, enrolled the 48 maps, and saved two sets of six scripted runs. Its board-test log covered ten cases. An eleventh case for the measurement CLI was already in the source. The report still ended at CHEN2D-17. To keep the comparison inside this folder, I reversed the final cumulative patch in the local transcript, checked both sides of all twelve paths against their recorded Git blob IDs, and reproduced the verified v17 protocol fingerprint `a441dc3fbaf2` across all 26 source files. [Stop record](review/ASTRA-CHEN2D-18.STOPPED.txt) · [File-by-file restart comparison](review/chen2d-18/restart-audit.txt) · [Interrupted board tests](review/chen2d-18/board-tests.txt)

The first set of scripted runs recorded revision `5f842e5774b9`. The retained `scripted/` runs recorded `ba217a48219a`, matching the source at restart. The interrupted legacy-suite log contained five source-version mismatches during edits and one reproducible fixture error. The v15 replay fixture assembled the current runner from v15’s file list, which omitted `board_sizes.py`. I changed the fixture to copy and hash-check each revision’s own source manifest. It then ran the original comparisons of episode files, assignments and CSVs. A fresh run of every new-board assignment reproduced the retained writer checks, issued plans, final boards and counts. [Interrupted regression log](review/chen2d-18/prior-tests.txt) · [Replay fixture](test_chen2d_v16.py) · [Final test log](review/chen2d-18/all-tests.txt)

### Boards, maps and speaking order

Seeds **0–3** are the development maps, with **0–1** used for the pilot. Seeds **4–15** are the experiment maps. Each size has sixteen independently seeded boards with a fixed total of 3, 6 or 9 boxes and the same number of targets. Box and target positions are sampled, so one square can contain several boxes. The table gives the minimum, maximum and mean over all sixteen maps per size. For the reference trajectory, the central scripted writer at H=5 took exactly `ceil(steps / 5)` rounds on every map. [Registered maps](review/chen2d-18/enrolment.txt) · [Reference trajectories and round counts](review/chen2d-18/reference-measurements.json)

| Board | Robots | Boxes per map | Reference steps min / max / mean | Reference H=5 rounds min / max / mean | Total H=5 calls CMAS / GROUP / OWN |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1×3 | 3 | 3 | 2 / 5 / 3.625 | 1 / 1 / 1 | 16 / 16 / 87 |
| 2×3 | 6 | 6 | 4 / 8 / 5.875 | 1 / 2 / 1.4375 | 23 / 56 / 240 |
| 3×3 | 9 | 9 | 5 / 11 / 7.3125 | 1 / 3 / 1.9375 | 31 / 126 / 495 |

At G=3, each row is one sub-team. Its robot columns are 0.5, 1.5 and 2.5. On 2×3 and 3×3, the robot in column 0.5 speaks for its row, starting at row 0.5 and continuing in increasing row order. The 1×3 team uses the map’s CMAS speaker `L`. G=9 uses that same central role on 3×3. G=1 uses the OWN speaker sequence on all three boards. Across both horizons and all seeds, the endpoint comparisons found identical speakers, message contents, replies, merged and executed plans, final states and call counts in 160 paired episodes (2,835 paired calls). Each run file records the block shape and every member of each block. [1×3 partition](review/chen2d-18/scripted/h5-1x3/run.json) · [2×3 partition](review/chen2d-18/scripted/h5-2x3/run.json) · [3×3 partition](review/chen2d-18/scripted/h5-3x3/run.json) · [Endpoint replay](review/chen2d-18/endpoint-replay.txt)

The runner accepts the three new sizes with a scaled map family, `--protocol matched` and `--conditions static`. The two ends of 1×3 each have a single horizontal neighbour. The middle robot has two. The prompt and first-step check use those same neighbours. Matched runs default to 30 environment steps and 30 planning rounds. The CLI rejects a legacy map request before enrolment and explains the static-only limit for e1/e2. Changed-order destinations can violate the intended placement rule on a dense board. On 1×3 at `scaled:3`, seed 4, the assigned destination already holds the selected blue box at reference step 4. [Board selection](board_sizes.py) · [Map assignment](map_events.py) · [Edge and refusal tests](test_chen2d_v18.py)

The new map and event hashes are indexed under `envs-scaled/r1/<size>/`. Re-enrolling seeds 0–15 reproduced the enrolment listing. The tests regenerated each new board, checked its event hash and delivered its final box. The 863 pre-existing legacy files and all 297 pre-existing scaled registry files matched their pre-enrolment byte digests, including the published manifests. [1×3 registry](envs-scaled/r1/1x3/manifest.json) · [2×3 registry](envs-scaled/r1/2x3/manifest.json) · [3×3 registry](envs-scaled/r1/3x3/manifest.json) · [Registry checks](test_chen2d_v18.py)

### Scripted steps, planning rounds and calls on every map

At **H=1**, every structure followed the reference step count and planned once per executed step. The calls column lists CMAS, GROUP and OWN in that order. At **H=5**, each cell gives the observed **steps / planning rounds / calls** for one structure. The scripted writers used zero repairs. A block or individual writer sees the current submissions of earlier speakers. At H=5 the saved logs record 14 GROUP rounds and 64 OWN rounds ending with an empty tail before completion. A new planning round then began on the current board. This accounts for cases such as 1×3 seed 0, where OWN delivered all three boxes in three steps but used two rounds. [Recount from call files and executed actions](review/chen2d-18/verify_measurements.py) · [Machine-readable table](review/chen2d-18/board-results.csv)

#### 1×3 board

| Seed | H=1 steps, all | H=1 calls C / G / O | H=5 CMAS steps / rounds / calls | H=5 GROUP steps / rounds / calls | H=5 OWN steps / rounds / calls |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 3 / 2 / 6 |
| 1 | 5 | 5 / 5 / 15 | 5 / 1 / 1 | 5 / 1 / 1 | 5 / 1 / 3 |
| 2 | 5 | 5 / 5 / 15 | 5 / 1 / 1 | 5 / 1 / 1 | 5 / 1 / 3 |
| 3 | 4 | 4 / 4 / 12 | 4 / 1 / 1 | 4 / 1 / 1 | 5 / 3 / 9 |
| 4 | 4 | 4 / 4 / 12 | 4 / 1 / 1 | 4 / 1 / 1 | 4 / 1 / 3 |
| 5 | 4 | 4 / 4 / 12 | 4 / 1 / 1 | 4 / 1 / 1 | 5 / 2 / 6 |
| 6 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 3 / 3 / 9 |
| 7 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 4 / 2 / 6 |
| 8 | 5 | 5 / 5 / 15 | 5 / 1 / 1 | 5 / 1 / 1 | 5 / 2 / 6 |
| 9 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 3 / 1 / 3 |
| 10 | 4 | 4 / 4 / 12 | 4 / 1 / 1 | 4 / 1 / 1 | 6 / 3 / 9 |
| 11 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 3 / 1 / 3 |
| 12 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 3 / 2 / 6 |
| 13 | 3 | 3 / 3 / 9 | 3 / 1 / 1 | 3 / 1 / 1 | 3 / 1 / 3 |
| 14 | 4 | 4 / 4 / 12 | 4 / 1 / 1 | 4 / 1 / 1 | 5 / 3 / 9 |
| 15 | 2 | 2 / 2 / 6 | 2 / 1 / 1 | 2 / 1 / 1 | 2 / 1 / 3 |

#### 2×3 board

| Seed | H=1 steps, all | H=1 calls C / G / O | H=5 CMAS steps / rounds / calls | H=5 GROUP steps / rounds / calls | H=5 OWN steps / rounds / calls |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 8 | 8 / 16 / 48 | 8 / 2 / 2 | 10 / 2 / 4 | 9 / 2 / 12 |
| 1 | 4 | 4 / 8 / 24 | 4 / 1 / 1 | 4 / 1 / 2 | 7 / 3 / 18 |
| 2 | 6 | 6 / 12 / 36 | 6 / 2 / 2 | 6 / 2 / 4 | 6 / 2 / 12 |
| 3 | 7 | 7 / 14 / 42 | 7 / 2 / 2 | 8 / 2 / 4 | 10 / 3 / 18 |
| 4 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 5 / 1 / 2 | 6 / 2 / 12 |
| 5 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 7 / 2 / 4 | 6 / 2 / 12 |
| 6 | 4 | 4 / 8 / 24 | 4 / 1 / 1 | 7 / 2 / 4 | 7 / 3 / 18 |
| 7 | 8 | 8 / 16 / 48 | 8 / 2 / 2 | 9 / 2 / 4 | 10 / 3 / 18 |
| 8 | 7 | 7 / 14 / 42 | 7 / 2 / 2 | 8 / 2 / 4 | 8 / 2 / 12 |
| 9 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 7 / 2 / 4 | 7 / 4 / 24 |
| 10 | 8 | 8 / 16 / 48 | 8 / 2 / 2 | 9 / 2 / 4 | 8 / 3 / 18 |
| 11 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 5 / 1 / 2 | 4 / 2 / 12 |
| 12 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 6 / 2 / 4 | 7 / 2 / 12 |
| 13 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 5 / 1 / 2 | 5 / 1 / 6 |
| 14 | 5 | 5 / 10 / 30 | 5 / 1 / 1 | 6 / 2 / 4 | 6 / 4 / 24 |
| 15 | 7 | 7 / 14 / 42 | 7 / 2 / 2 | 7 / 2 / 4 | 7 / 2 / 12 |

#### 3×3 board

| Seed | H=1 steps, all | H=1 calls C / G / O | H=5 CMAS steps / rounds / calls | H=5 GROUP steps / rounds / calls | H=5 OWN steps / rounds / calls |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 6 | 6 / 18 / 54 | 6 / 2 / 2 | 6 / 2 / 6 | 7 / 3 / 27 |
| 1 | 5 | 5 / 15 / 45 | 5 / 1 / 1 | 7 / 3 / 9 | 7 / 3 / 27 |
| 2 | 6 | 6 / 18 / 54 | 6 / 2 / 2 | 11 / 3 / 9 | 10 / 3 / 27 |
| 3 | 7 | 7 / 21 / 63 | 7 / 2 / 2 | 9 / 3 / 9 | 12 / 3 / 27 |
| 4 | 9 | 9 / 27 / 81 | 9 / 2 / 2 | 11 / 3 / 9 | 10 / 4 / 36 |
| 5 | 11 | 11 / 33 / 99 | 11 / 3 / 3 | 12 / 3 / 9 | 13 / 5 / 45 |
| 6 | 7 | 7 / 21 / 63 | 7 / 2 / 2 | 9 / 3 / 9 | 8 / 4 / 36 |
| 7 | 8 | 8 / 24 / 72 | 8 / 2 / 2 | 11 / 3 / 9 | 11 / 3 / 27 |
| 8 | 8 | 8 / 24 / 72 | 8 / 2 / 2 | 11 / 3 / 9 | 10 / 3 / 27 |
| 9 | 8 | 8 / 24 / 72 | 8 / 2 / 2 | 10 / 3 / 9 | 13 / 4 / 36 |
| 10 | 5 | 5 / 15 / 45 | 5 / 1 / 1 | 7 / 2 / 6 | 7 / 3 / 27 |
| 11 | 6 | 6 / 18 / 54 | 6 / 2 / 2 | 8 / 2 / 6 | 10 / 4 / 36 |
| 12 | 6 | 6 / 18 / 54 | 6 / 2 / 2 | 8 / 2 / 6 | 7 / 3 / 27 |
| 13 | 9 | 9 / 27 / 81 | 9 / 2 / 2 | 8 / 2 / 6 | 14 / 3 / 27 |
| 14 | 10 | 10 / 30 / 90 | 10 / 2 / 2 | 10 / 2 / 6 | 10 / 2 / 18 |
| 15 | 6 | 6 / 18 / 54 | 6 / 2 / 2 | 13 / 3 / 9 | 11 / 5 / 45 |

### Calls per planning round

Each cell gives total calls in one round with **zero / one / two repairs per writer**. Two is the matched allowance. The count for mixed outcomes is the number of writers plus the number of repairs actually requested. All 54 combinations of board, framework, horizon and repair count were checked with `correct`, `repair` and `invalid` fake replies. Each logical call used one physical attempt in these checks. Provider retries would also consume the physical episode ceiling. At 27 attempts per round, 22 full-repair rounds on 3×3 OWN use 594 of a 600-attempt budget. [Metered one-round runs](review/chen2d-18/repair-counts.csv)

| Board | CMAS | GROUP, G=3 | OWN |
| --- | ---: | ---: | ---: |
| 1×3 | 1 / 2 / 3 | 1 / 2 / 3 | 3 / 6 / 9 |
| 2×3 | 1 / 2 / 3 | 2 / 4 / 6 | 6 / 12 / 18 |
| 3×3 | 1 / 2 / 3 | 3 / 6 / 9 | 9 / 18 / 27 |

### Main-session commands

Run these Bash commands from the project directory. The pilot and experiment use separate output directories and identical H=5 writer settings. The commands select the earlier GLM model, the runner’s USD 1.50 invocation guard and a requested limit of 600 physical attempts per episode. I verified both commands with the fake model and temporary output directories. All 18 pilot and 108 experiment assignments completed under the printed call and cost limits. [Runner options](run_chen2d.py) · [Command checks and fake call counts](review/chen2d-18/fresh-replay.txt)

```bash
common=(--protocol matched --map-set scaled:1 --sizes 1x3,2x3,3x3
        --frameworks CMAS,GROUP,OWN --group-size 3 --conditions static
        --horizon 5 --history-method authors --history-window 100000 --state-position after
        --dropoff always --dropoff-rule on --parse lenient
        --max-env-steps 30 --max-planning-rounds 30 --episode-call-ceiling 600
        --max-output-tokens 8192 --temperature 0 --retry-temperature 0
        --reasoning default --jobs 2 --max-cost-usd 1.50)

# Pilot, 18 assignments
python3 -B run_chen2d.py "${common[@]}" --model z-ai/glm-5.3-flash \
  --envs 0-1 --max-calls 10800 --out runs/chen2d-18-pilot

# Experiment, 108 assignments
python3 -B run_chen2d.py "${common[@]}" --model z-ai/glm-5.3-flash \
  --envs 4-15 --max-calls 64800 --out runs/chen2d-18-experiment
```

### Offline verification

All **251 tests passed** in 401.827 seconds at protocol revision `ba217a48219a`, including the 240 earlier tests and 11 board tests. The suite covered all three structures at both horizons, row-major order, the one-neighbour edges, matched endpoints, repairs, refusals, resume, and size filters in the reading probe, summary and cost tools. The legacy episode and prompt byte replays passed. The summary and cost CLIs also reproduced all nine H=5 per-size structure totals. The independent action replay checked every saved board and reconciled the call files with the invocation totals of **2,657 at H=1** and **1,090 at H=5**. [Full test log](review/chen2d-18/all-tests.txt) · [Verified episode measurements](review/chen2d-18/board-results.csv)

```bash
export TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python3 -B enrol_maps.py --map-set scaled:1 --sizes 1x3,2x3,3x3 --envs 0-15
python3 -B scaled_map_measurements.py --rates 1 --sizes 1x3,2x3,3x3 --envs 0-15 \
  --out review/chen2d-18/reference-measurements.json
python3 -B review/chen2d-18/verify_measurements.py > review/chen2d-18/board-results.csv
python3 -B test_chen2d_v14.py test_chen2d test_chen2d_v{2..14} \
  test_chen2d_v15_{maps,matched,cli,probe,probe_exec} test_chen2d_v16 \
  test_chen2d_v17_{writers,retry,limits,replay} test_chen2d_v18
```

### 확인 안 됨

Live-model completion rates, repair frequency, physical attempts, tokens, latency and billed cost on the new boards remain unmeasured. Transfer to the project’s 3D task also remains unverified. All episode results above come from offline BoxNet runs.

## CHEN2D-19

The first-round comparison pairs **108 writer assignments on 12 boards**. Each assignment receives the original prompt and the same prompt with one sentence explaining that planning continues. At the archived GLM price ceilings, the 216 single attempts have a combined reservation of **USD 0.4525602**. The fake model answered all 216. In the separate 18-episode rehearsal, all 18 episodes achieved strict completion under the equal failure rule. [Paired probe results](review/chen2d-19/paired-probe/summary.json) · [Episode results](review/chen2d-19/pilot-fake/episodes.csv) · [Counts and reservation arithmetic](review/chen2d-19/verification.json)

### Writer instructions and failures

The matched runner defaults to `--plan-note none --failed-writer drop`. With `--plan-note continue`, CMAS, GROUP and OWN receive the following sentence immediately after the horizon request. It occupies the same position in the initial user message retained by every repair. The singular sentence uses “1 step” and “it is executed.” The run, assignments, episode and numbered call records identify the note setting. [Prompt builder](matched_protocol.py) · [Runner settings](review/chen2d-19/pilot-fake/run.json) · [Prompt and repair tests](test_chen2d_v19.py)

```text
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
```

With `--failed-writer fail`, a writer is **required if at least one robot assigned to it has a nonempty doable-action list on the board at the start of the round**. CMAS owns the whole board, a GROUP writer owns its block, and an OWN writer owns one square. An idle block leader is required when another robot in its block can act. Every scheduled writer still gets an initial turn. A valid wait passes the same shape and first-step checks as any other reply. A writer with no doable action can still propose a later handoff. [Round implementation](horizon.py) · [Assignment and failure tests](test_chen2d_v19.py)

| Required writer’s final result | Episode label | First-blocked cause if this is the first blocked round |
| --- | --- | --- |
| Every reply-bearing attempt in the exhausted call ended on length | `failure output limit` | `output limit` |
| Client reply attempts exhausted on mixed or unusable replies | `failure unusable model reply` | `unusable replies after client retries` |
| Transport attempts exhausted without a reply | `failure model service` | `model service` |
| Last format repair still unreadable | `Syntactic Error` | `unusable replies after repairs` |
| Last repair still proposes a first-step action outside the doable list | `Syntactic Error` | `not-doable actions` |

The planner checks the second and final repair. On a required failure it records the speaker and call number and executes zero steps from that round. A failed optional writer can drop out after exhausting its call or its repairs. Episode and invocation ceilings and interruptions retain their usual stopping and resume behavior. [Retry accounting](LLM.py) · [Episode metrics](planning_metrics.py)

### Visible replies and archived runs

Each physical attempt in a matched call or probe records `visible_reply_chars`. It counts Unicode characters in the visible assistant content, including whitespace. A length-stopped attempt records `cutoff_reply_class` as `empty` for absent, empty or whitespace-only content and `partial` for content with a non-whitespace character. The decoder measures the visible field before the client validates the reply. The completion and reasoning meters retain the provider’s separate reported values. The scripted transport test supplies 8,192 completion tokens and 8,282 reasoning tokens for the same attempt. [Attempt metering](LLM.py) · [Scripted transport cases](test_chen2d_v19.py)

The episode JSON, episode CSV and matched summary table count `cutoff_attempts_{empty,partial,unknown}`, including retries that later recover. The three `rounds_all_attempts_cutoff_{empty,partial,unknown}` columns subdivide the existing exhausted-call round count. Earlier writers can succeed in that round. The class comes from the **last reply-bearing attempt of the exhausted call**. A trailing timeout or HTTP error supplies no visible reply for that decision. A cut-off from an optional writer that drops out contributes to attempt counts even when the round proceeds. [Summary reader](summarize.py) · [Archived-run regression](test_chen2d_v19.py)

For older matched folders the reader uses saved per-attempt raw text. A final logical reply can supply the last attempt’s text, and a client-log entry can supply text when its attempt ID matches. A missing raw reply or missing call file leaves the corresponding count in `unknown`. Rebuilding the CSV preserves the source episode JSON and call records. [Archive recovery](summarize.py)

### Main-session first-round check

Run from the project directory. Each selected map contributes every scheduled writer, including idle assignments. Earlier writers’ lists in this probe come from the first five steps of the deterministic static reference trajectory, restricted to each earlier writer’s robots. The probe freezes those lists across arms. Both arms see the same board, speaker, assignment, history, peer lists and output limit. Each cell has one physical attempt and zero repairs. The ordinary episode pilot below uses actual earlier writer replies. [Probe implementation](probe_reading.py) · [Reference peer lists](probe_wording.py) · [Planned cells](review/chen2d-19/paired-probe/planned-cells.json)

| Board | CMAS per seed | GROUP per seed, G=3 | OWN per seed | Four seeds per note | Both notes |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1×3 | 1 | 1 | 3 | 20 | 40 |
| 2×3 | 1 | 2 | 6 | 36 | 72 |
| 3×3 | 1 | 3 | 9 | 52 | 104 |
| Total | | | | **108** | **216** |

On 1×3 GROUP and CMAS use the same central-writer prompt. Each is a separate scheduled observation. Across four seeds and three sizes, one note arm has 12 CMAS, 24 GROUP and 72 OWN attempts. `--shuffle 19` interleaves cells reproducibly. A completed cell reuses its durable record on resume. [Probe configuration](review/chen2d-19/paired-probe/config.json)

```bash
python3 -B probe_wording.py --first-round --protocol matched \
  --sizes 1x3,2x3,3x3 --frameworks CMAS,GROUP,OWN --group-size 3 \
  --map-set scaled:2 --envs 0-3 --dropoff event --horizon 5 --state-position after \
  --plan-note none,continue --max-output-tokens 8192 --reasoning default \
  --max-calls 216 --max-cost-usd 0.60 --shuffle 19 --jobs 2 \
  --model z-ai/glm-5.3-flash --out runs/chen2d-19-first-round-r2

python3 -B probe_reading.py --summarize runs/chen2d-19-first-round-r2
```

`summary.json` reports both arms and each board-size/structure cell. “Usable” requires a returned, uncut reply that passes the matched reader and first-step feasibility check. A valid wait qualifies. The summary reports total visible characters and metered tokens. If a meter is missing for any attempt, the total is null and the unreported count identifies the gap. Individual lengths, exact messages and raw replies are in the cell results. [Fake results by arm and cell](review/chen2d-19/paired-probe/summary.json) · [Per-writer results](review/chen2d-19/paired-probe/results.jsonl)

| Note | Fake attempts | Cut-offs empty / partial | Usable | Generated tokens | Reasoning tokens | Visible reply chars | GLM reservation, USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `none` | 108 | 0 / 0 | 108 | 756 | 216 | 32,315 | 0.2255133 |
| `continue` | 108 | 0 / 0 | 108 | 756 | 216 | 32,315 | 0.2270469 |

The archived GLM profile reserves USD 0.10 per million input units and USD 0.20 per million completion tokens. The adapter budgets the UTF-8 byte count of the serialized system/user messages plus 1,024 input units per attempt. The two arms have 375,069 and 390,405 wire bytes, giving input bounds of 485,661 and 500,997 units. Each arm reserves 108 × 8,192 = 884,736 completion tokens. Summing the per-attempt reservations gives USD 0.4525602. The command sets a USD 0.60 invocation guard. These figures use folder-local pricing evidence. [Archived price ceilings](review/ASTRA-CHEN2D-raw.txt#L503) · [Adapter formula](LLM.py) · [Computed bounds](review/chen2d-19/verification.json)

### Main-session 18-episode pilot

The pilot uses the task-18 seeds 0–1, three sizes and three structures. It retains the H=5 history layout, temperatures, lenient parser, 30-step and 30-round ceilings, and requested limit of 600 physical attempts per episode. Event-mode dropoff omits the neutral site and its instruction on these static maps. The runner applies the installed client’s effective episode ceiling and the USD 1.50 invocation guard. [Fake pilot settings](review/chen2d-19/pilot-fake/run.json)

```bash
python3 -B run_chen2d.py --protocol matched --map-set scaled:2 \
  --sizes 1x3,2x3,3x3 --frameworks CMAS,GROUP,OWN --group-size 3 --conditions static --envs 0-1 \
  --horizon 5 --history-method authors --history-window 100000 --state-position after \
  --plan-note continue --failed-writer fail --dropoff event --parse lenient \
  --max-env-steps 30 --max-planning-rounds 30 --episode-call-ceiling 600 \
  --max-output-tokens 8192 --temperature 0 --retry-temperature 0 --reasoning default \
  --jobs 2 --max-cost-usd 1.50 --max-calls 10800 \
  --model z-ai/glm-5.3-flash --out runs/chen2d-19-pilot-r2

python3 -B summarize.py --by planning runs/chen2d-19-pilot-r2
```

The fake rehearsal completed six episodes per structure. CMAS used 13 physical attempts, GROUP used 33 and OWN used 138. All 184 calls passed on their first attempt. The two command rehearsals used a separate folder-local map registry and the same map loader as the main commands. [Verified commands and console output](review/chen2d-19/verified-commands.txt) · [Pilot episode CSV](review/chen2d-19/pilot-fake/episodes.csv)

### Full first-round episode prompts on 2×3

The following nine pairs reproduce all initial messages on static `scaled:2`, seed 0, map SHA-256 `6cc4fb43c9df8bf3b6d40c83dddbd957a8f07fbbb4d681287cb5355badc4cdce`. Each block contains the complete serialized system and user messages that the adapter would send. Earlier lists are the preceding fake writers’ actual submissions. Removing the note and its newline makes the two messages byte-identical in all nine pairs. [Original-prompt control](review/chen2d-19/prompt-control/run.json) · [Continuation pilot](review/chen2d-19/pilot-fake/run.json)

#### CMAS writer 1 · Agent[1.5, 1.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write a joint entry for every step, choosing the actions of all robots.
Earlier robots' lists in this planning round: {}
Return a JSON list for the next 5 steps in execution order.
Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_CMAS_static_env0/calls/00001.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write a joint entry for every step, choosing the actions of all robots.
Earlier robots' lists in this planning round: {}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_CMAS_static_env0/calls/00001.json)

</details>

#### GROUP G=3 writer 1 · Agent[0.5, 0.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write a joint entry for every step, choosing actions only for ["Agent[0.5, 0.5]", "Agent[0.5, 1.5]", "Agent[0.5, 2.5]"].
Earlier robots' lists in this planning round: {}
Return a JSON list for the next 5 steps in execution order.
Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_GROUP-g3_static_env0/calls/00001.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write a joint entry for every step, choosing actions only for ["Agent[0.5, 0.5]", "Agent[0.5, 1.5]", "Agent[0.5, 2.5]"].
Earlier robots' lists in this planning round: {}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_GROUP-g3_static_env0/calls/00001.json)

</details>

#### GROUP G=3 writer 2 · Agent[1.5, 0.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write a joint entry for every step, choosing actions only for ["Agent[1.5, 0.5]", "Agent[1.5, 1.5]", "Agent[1.5, 2.5]"].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [{"Agent[0.5, 0.5]": "move(box_blue, square[1.5, 0.5])", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, square[0.5, 1.5])"}, {"Agent[0.5, 0.5]": "move(box_purple, square[0.5, 1.5])", "Agent[0.5, 1.5]": "move(box_green, target_green)", "Agent[0.5, 2.5]": "move(box_orange, target_orange)"}, {"Agent[0.5, 1.5]": "move(box_purple, square[1.5, 1.5])", "Agent[0.5, 2.5]": "move(box_purple, square[0.5, 1.5])"}, {"Agent[0.5, 1.5]": "move(box_purple, square[1.5, 1.5])"}, {}]}
Return a JSON list for the next 5 steps in execution order.
Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_GROUP-g3_static_env0/calls/00002.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write a joint entry for every step, choosing actions only for ["Agent[1.5, 0.5]", "Agent[1.5, 1.5]", "Agent[1.5, 2.5]"].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [{"Agent[0.5, 0.5]": "move(box_blue, square[1.5, 0.5])", "Agent[0.5, 1.5]": "move(box_orange, square[0.5, 2.5])", "Agent[0.5, 2.5]": "move(box_green, square[0.5, 1.5])"}, {"Agent[0.5, 0.5]": "move(box_purple, square[0.5, 1.5])", "Agent[0.5, 1.5]": "move(box_green, target_green)", "Agent[0.5, 2.5]": "move(box_orange, target_orange)"}, {"Agent[0.5, 1.5]": "move(box_purple, square[1.5, 1.5])", "Agent[0.5, 2.5]": "move(box_purple, square[0.5, 1.5])"}, {"Agent[0.5, 1.5]": "move(box_purple, square[1.5, 1.5])"}, {}]}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is a joint object mapping acting Agent[row, col] names to action strings. Use {} for an idle step.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_GROUP-g3_static_env0/calls/00002.json)

</details>

#### OWN writer 1 · Agent[0.5, 0.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[0.5, 0.5].
Earlier robots' lists in this planning round: {}
Return a JSON list for the next 5 steps in execution order.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_OWN_static_env0/calls/00001.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[0.5, 0.5].
Earlier robots' lists in this planning round: {}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_OWN_static_env0/calls/00001.json)

</details>

#### OWN writer 2 · Agent[0.5, 1.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[0.5, 1.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null]}
Return a JSON list for the next 5 steps in execution order.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_OWN_static_env0/calls/00002.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[0.5, 1.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null]}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_OWN_static_env0/calls/00002.json)

</details>

#### OWN writer 3 · Agent[0.5, 2.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[0.5, 2.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null]}
Return a JSON list for the next 5 steps in execution order.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_OWN_static_env0/calls/00003.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[0.5, 2.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null]}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_OWN_static_env0/calls/00003.json)

</details>

#### OWN writer 4 · Agent[1.5, 0.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[1.5, 0.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])", "move(box_orange, target_orange)", "move(box_purple, square[0.5, 1.5])", null, null]}
Return a JSON list for the next 5 steps in execution order.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_OWN_static_env0/calls/00004.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[1.5, 0.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])", "move(box_orange, target_orange)", "move(box_purple, square[0.5, 1.5])", null, null]}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_OWN_static_env0/calls/00004.json)

</details>

#### OWN writer 5 · Agent[1.5, 1.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[1.5, 1.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])", "move(box_orange, target_orange)", "move(box_purple, square[0.5, 1.5])", null, null], "Agent[1.5, 0.5]": ["move(box_blue, target_blue)", "move(box_blue, target_blue)", "move(box_red, square[0.5, 0.5])", "move(box_red, square[0.5, 0.5])", null]}
Return a JSON list for the next 5 steps in execution order.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_OWN_static_env0/calls/00005.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[1.5, 1.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])", "move(box_orange, target_orange)", "move(box_purple, square[0.5, 1.5])", null, null], "Agent[1.5, 0.5]": ["move(box_blue, target_blue)", "move(box_blue, target_blue)", "move(box_red, square[0.5, 0.5])", "move(box_red, square[0.5, 0.5])", null]}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_OWN_static_env0/calls/00005.json)

</details>

#### OWN writer 6 · Agent[1.5, 2.5]

<details><summary>Full prompt with plan-note none</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[1.5, 2.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])", "move(box_orange, target_orange)", "move(box_purple, square[0.5, 1.5])", null, null], "Agent[1.5, 0.5]": ["move(box_blue, target_blue)", "move(box_blue, target_blue)", "move(box_red, square[0.5, 0.5])", "move(box_red, square[0.5, 0.5])", null], "Agent[1.5, 1.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_green, square[0.5, 1.5])", "move(box_red, square[0.5, 1.5])", "move(box_purple, target_purple)", null]}
Return a JSON list for the next 5 steps in execution order.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/prompt-control/episodes/2x3_OWN_static_env0/calls/00006.json)

</details>

<details><summary>Full prompt with plan-note continue</summary>

```text
[system]
You are a helpful assistant.

[user]
Match all boxes to their color-coded targets.
Each robot occupies a 1x1 square identified by its center coordinates. It can move one box in its square to a neighboring square or to a matching target in its square. Each square can contain multiple boxes and targets.
Example actions are move(box_blue, square[0.5, 1.5]) and move(box_blue, target_blue).

Earlier executed state and action pairs:

Current board and doable actions:
Agent[0.5, 0.5]: I am in square[0.5, 0.5], I can observe ['box_blue', 'box_purple'], I can do ['move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[0.5, 1.5])', 'move(box_purple, square[1.5, 0.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[0.5, 1.5]: I am in square[0.5, 1.5], I can observe ['target_red', 'target_green', 'target_green', 'box_orange'], I can do ['move(box_orange, square[1.5, 1.5])', 'move(box_orange, square[0.5, 0.5])', 'move(box_orange, square[0.5, 2.5])']
Agent[0.5, 2.5]: I am in square[0.5, 2.5], I can observe ['target_blue', 'target_red', 'target_red', 'box_green', 'box_purple', 'target_orange'], I can do ['move(box_green, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_purple, square[1.5, 2.5])', 'move(box_purple, square[0.5, 1.5])']
Agent[1.5, 0.5]: I am in square[1.5, 0.5], I can observe ['box_blue', 'target_blue', 'target_blue', 'box_red', 'box_red'], I can do ['move(box_blue, square[0.5, 0.5])', 'move(box_blue, square[1.5, 1.5])', 'move(box_blue, target_blue)', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])', 'move(box_red, square[0.5, 0.5])', 'move(box_red, square[1.5, 1.5])']
Agent[1.5, 1.5]: I am in square[1.5, 1.5], I can observe ['box_blue', 'box_red', 'box_green', 'target_purple', 'target_purple', 'target_orange'], I can do ['move(box_blue, square[0.5, 1.5])', 'move(box_blue, square[1.5, 0.5])', 'move(box_blue, square[1.5, 2.5])', 'move(box_red, square[0.5, 1.5])', 'move(box_red, square[1.5, 0.5])', 'move(box_red, square[1.5, 2.5])', 'move(box_green, square[0.5, 1.5])', 'move(box_green, square[1.5, 0.5])', 'move(box_green, square[1.5, 2.5])']
Agent[1.5, 2.5]: I am in square[1.5, 2.5], I can observe ['box_orange'], I can do ['move(box_orange, square[0.5, 2.5])', 'move(box_orange, square[1.5, 1.5])']

Write an individual entry for every step, choosing only the action of Agent[1.5, 2.5].
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_purple, square[0.5, 1.5])", null, null, null], "Agent[0.5, 1.5]": ["move(box_orange, square[0.5, 2.5])", null, "move(box_purple, square[1.5, 1.5])", null, null], "Agent[0.5, 2.5]": ["move(box_green, square[0.5, 1.5])", "move(box_orange, target_orange)", "move(box_purple, square[0.5, 1.5])", null, null], "Agent[1.5, 0.5]": ["move(box_blue, target_blue)", "move(box_blue, target_blue)", "move(box_red, square[0.5, 0.5])", "move(box_red, square[0.5, 0.5])", null], "Agent[1.5, 1.5]": ["move(box_blue, square[1.5, 0.5])", "move(box_green, square[0.5, 1.5])", "move(box_red, square[0.5, 1.5])", "move(box_purple, target_purple)", null]}
Return a JSON list for the next 5 steps in execution order.
The job may need more than 5 steps: plan only the next 5 steps; after they are executed, another planning round continues from the new state.
Each list entry is your own action string or the JSON literal null for a wait.
Assume the earlier entries have been executed. Return only the list.
Respond concisely.
```

[Numbered call record](review/chen2d-19/pilot-fake/episodes/2x3_OWN_static_env0/calls/00006.json)

</details>

### Offline verification

All **263 tests passed in 396.748 seconds** at protocol revision `6380864dd82f`. The suite includes the 251 earlier tests and 12 task-19 regressions. The matched byte-replay test checks each new default field against its expected value before comparing the archived fields. The new prompt test compares the rendered bytes directly with the frozen task-18 builder at H=1 and H=5. The archive regression runs the summary CLI on a copied run and covers whitespace, missing text, client-log recovery and a missing numbered call. The registry checks passed on the published maps. [Full suite](review/chen2d-19/all-tests.txt) · [Task-19 tests](test_chen2d_v19.py) · [Matched archive comparison](test_chen2d_v16.py)

An initial test pass overlapped source edits and hit the suite’s code-version checks. The successful full pass used a fresh process at the fixed revision. All command rehearsals used the fake model. Provider-boundary tests used a folder-local archived decoder with scripted HTTP responses and disabled network connections. The verification checked every probe cell against its call record, all 108 pairs against their shared inputs, and every prompt printed above against the episode messages. [Development log](review/chen2d-19/development-tests.txt) · [Final verification](review/chen2d-19/verification.json) · [Matched pilot table](review/chen2d-19/pilot-planning.txt)

```bash
export TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python3 -B test_chen2d_v14.py test_chen2d test_chen2d_v{2..14} \
  test_chen2d_v15_{maps,matched,cli,probe,probe_exec} test_chen2d_v16 \
  test_chen2d_v17_{writers,retry,limits,replay} test_chen2d_v18 test_chen2d_v19
```

### 확인 안 됨

Whether the continuation sentence reduces empty cut-offs, changes reasoning use or improves strict completion on a live model remains unmeasured. The main session reported horizon-as-deadline wording in five of 428 saved calls. The cut-off attempts did not preserve the reasoning text needed to establish that explanation. Live outcomes under the equal failure rule, current provider routing prices and actual billed cost also remain unverified. [Task brief](TASK-CHEN2D-19.md)

## CHEN2D-20

With `--protocol matched --failed-writer idle`, a writer that exhausts its replies or repairs leaves its assigned robots idle for all H steps of that round. The team executes the other writers’ usable actions. On a 3×3 board, a failed OWN writer covers one robot, a failed three-robot GROUP writer covers one row and a failed CMAS writer covers all nine. Each can write again in the next round. The default policy is `drop`. [Round execution](horizon.py) · [Writer settings](matched_protocol.py)

### What later writers see

The runner keeps the initial speaking order and the two repair sweeps. In the existing earlier-lists slot, each robot whose writer has no usable submission gets an empty JSON array under its own name. A later writer sees the same representation while a repair is pending. For example, after the first row fails on a three-column board, the next row sees this line in its prompt. [Prompt builder](matched_protocol.py) · [Peer-list and repair tests](test_chen2d_v20.py)

```text
Earlier robots' lists in this planning round: {"Agent[0.5, 0.5]": [], "Agent[0.5, 1.5]": [], "Agent[0.5, 2.5]": []}
```

The existing idle-step or wait instruction gains “In the earlier lists, [] means that robot has no usable entries yet.” when these entries are present. Successful writers retain their usual list representation. The sole central writer starts with `{}` in its peer slot. If a repair follows a block by a speaker who originally spoke later, the repair message adds that speaker’s empty robot lists to the original peer view. The saved initial message remains available in the call history. [Initial and repair prompts](horizon.py)

### When an episode ends

A writer is **required** if at least one of its robots has a doable action on the board at round start. A finished planning round is **stalled** if the executor applied zero actions. It consumes one planning round and zero environment steps. Any applied action resets the consecutive-stall count. An optional writer’s failure is recorded even when its teammates act. [Round execution](horizon.py)

The default for `idle` is three consecutive stalls. On the Kth stall the episode uses the last required writer’s blocking label in that round. If a merged step is later rejected before any action executes, that rejection supplies the cause. If the usable lists contain only waits and there is no required writer failure, the end label is the existing cause text `no actions proposed`. A coincident call or round ceiling at the end of the Kth fully processed stall yields the stall label. Board completion, environment steps, earlier ceilings, invocation interruptions and service errors keep their existing handling. A service stop or interrupted sweep contributes no completed stall. [Stall and ceiling tests](test_chen2d_v20.py)

| Outcome | Recorded cause | End label when decisive |
| --- | --- | --- |
| Exhausted logical call with all reply-bearing attempts cut off | `output limit` | `failure output limit` |
| Client exhausts mixed or unusable replies | `unusable replies after client retries` | `failure unusable model reply` |
| Final repair is unreadable | `unusable replies after repairs` | `Syntactic Error` |
| Final repair’s first action is outside the doable list | `not-doable actions` | `Syntactic Error` |
| Merged list rejected before any action executes | `not-doable actions` | `Syntactic Error` |
| Only waits from the required writers | `no actions proposed` | `no actions proposed` |

The first four outcomes produce a writer-block event. The last two describe execution of submitted lists. Transport-only failures propagate `failure model service` immediately, including on an optional writer’s turn. The client retains its existing classification for mixed transport and reply-bearing attempts. [Client classification](LLM.py) · [Round classification](planning_metrics.py)

### Record fields and counting

| Location | Fields | Meaning |
| --- | --- | --- |
| Run, assignments, invocation selectors and episode | `failed_writer`, `max_stalled_rounds` | `idle` and the effective positive integer K. A resumed run checks the same K. |
| `episode.json` → `round_log[].writer_blocked[]` | `event`, `planning_round`, `framework`, `speaker`, `robots`, `required` | One `writer_blocked` event per exhausted writer in the round, with its full assignment and round-start eligibility. |
| Same event | `cause`, `end_label`, `call`, `calls` | Cause and corresponding episode label, terminal logical call number, and the ordered numbers of this writer’s initial call and repairs. |
| Same event | `attempts`, `last_call_attempts`, `last_cutoff_class` | Physical attempts across those calls, physical attempts in the terminal call, and the class of its last reply-bearing attempt. A cut can be `empty`, `partial` or `unknown` when evidence is missing. An uncut last reply has JSON `null`. |
| Same event | `prompt_tokens`, `generated_tokens` | Sum of each meter across the writer’s calls and retries. A missing meter makes its total unknown. Generated tokens use the completion meter, which includes reasoning. |
| `round_log[]` | `stalled`, `stall_cause`, `stall_call`, `executed_writer_calls` | Whether this round finished without an action, the reason for a stall, the decisive required writer’s call number when applicable, and distinct call numbers whose lists contributed applied actions. An interrupted sweep has `stalled: null`. |
| Episode JSON and CSV | `robot_rounds_blocked_by_cause`, `writer_calls_blocked_by_cause` | Per cause, sum the number of covered robots and count one exhausted writer per event. The existing `robots_dropped` also counts the covered robots. |
| Episode JSON and CSV | `stalled_rounds`, `rounds_with_blocked_writer`, `first_blocked_round`, `first_blocked_cause`, `first_blocked_stage` | Count zero-action rounds and rounds with any blocked writer independently. The first observed writer block includes optional writers and can precede successful execution. Stall and ceiling causes remain available when they occur first. |
| Episode JSON and CSV | `blocked_prompt_tokens`, `blocked_generated_tokens`, `executed_prompt_tokens`, `executed_generated_tokens`, `other_prompt_tokens`, `other_generated_tokens` | Blocked includes the initial submission and repairs for a writer that exhausts them. Executed charges each logical call that produced an applied action once, including physical retries of that call. Other covers valid waits, unused lists, superseded proposals for a writer that later succeeds, relays and interrupted calls without an execution. |
| Episode JSON and CSV | `correct_deliveries`, `box_count`, `tokens`, `tokens_per_delivered_box` | Correct deliveries, initial boxes, total prompt plus generated tokens, and tokens divided by correct deliveries. |

The matched table starts its result columns with `correct_deliveries` and `box_count`. For each structure, size and setting, `tokens_per_delivered_box` divides `total_tokens` across all recorded episodes by all correct deliveries, including partial episodes. Zero deliveries produce `NA` alongside the raw totals and JSON `null` in the episode. The matched cost table uses the same denominator and splits sizes by default. The summary retains the historical strict-completion measures and reports `NA` for writer measures that older folders did not record. [Episode measurements and matched table](planning_metrics.py) · [CSV and archive reader](summarize.py) · [Cost table](cost.py)

### Main-session commands

Run the following in Bash from the project directory. Each pilot has 18 assignments. The common settings preserve the task-19 history, parsing, temperatures, ceilings and USD 1.50 per-invocation guard. The output limits count visible completion and reasoning tokens together. [Runner](run_chen2d.py)

```bash
common=(--model z-ai/glm-5.3-flash --protocol matched --map-set scaled:2
        --sizes 1x3,2x3,3x3 --frameworks CMAS,GROUP,OWN --group-size 3 --conditions static
        --horizon 5 --history-method authors --history-window 100000 --state-position after
        --plan-note continue --failed-writer idle --max-stalled-rounds 3 --dropoff event --parse lenient
        --max-env-steps 30 --max-planning-rounds 30 --episode-call-ceiling 600
        --temperature 0 --retry-temperature 0 --reasoning default --jobs 2 --max-cost-usd 1.50)

for limit in 8192 16384; do
  python3 -B run_chen2d.py "${common[@]}" --envs 0-1 --max-calls 10800 \
    --max-output-tokens "$limit" --out "runs/chen2d-20-pilot-r2-$limit"
done
python3 -B summarize.py --by planning runs/chen2d-20-pilot-r2-{8192,16384}
```

The held-out experiment has 108 assignments per output limit. With the same `common` array, this command runs seeds 4–15 at 8,192. Set `limit=16384` to run the higher-limit experiment in its own output directory. [Experiment design and offline rehearsal](review/chen2d-20/rehearse.py)

```bash
limit=8192
out="runs/chen2d-20-experiment-r2-$limit"
python3 -B run_chen2d.py "${common[@]}" --envs 4-15 --max-calls 64800 \
  --max-output-tokens "$limit" --out "$out" &&
  python3 -B summarize.py --by planning "$out" &&
  python3 -B cost.py "$out" --sizes 1x3,2x3,3x3
```

### Offline evidence

On a constructed 3×3 board with two boxes and two matching targets in every square and H=2, the executor produced the following outcomes. The tests inject the listed failure and check the issued actions, later prompts, call numbers and token attribution. [Writer-failure tests](test_chen2d_v20.py)

| Scripted failure | Blocked robot-rounds | Logical calls / physical attempts | Stalls | Correct deliveries |
| --- | ---: | ---: | ---: | --- |
| One OWN writer proposes an infeasible first action through both repairs | 1 | 11 / 11 | 0 | 16 / 18 in the first round |
| One GROUP writer remains unreadable through both repairs | 3 | 5 / 5 | 0 | 12 / 18 in the first round |
| CMAS exhausts three cut-off replies, then supplies a usable list | 9 | 2 / 4 | 1 | 0 / 18 after round one, 18 / 18 after round two |

The ordinary correct-fake rehearsal exercised the pilot and held-out commands at both output limits. Each limit gave the counts below. The recount compared numbered attempts to the invocation ledger, initial boards to correct deliveries, and applied actions to the producing calls’ token meters. All 252 episodes finished, with 2,390 physical fake attempts across the four runs. [Episode recount](review/chen2d-20/fake-episodes.csv) · [Pilot table](review/chen2d-20/pilot-planning.txt) · [Experiment table](review/chen2d-20/experiment-planning.txt)

| Seeds at one limit | Episodes | Delivered / total | CMAS calls | GROUP calls | OWN calls | All calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pilot 0–1 | 18 | 216 / 216 | 13 | 33 | 138 | 184 |
| Experiment 4–15 | 108 | 1,296 / 1,296 | 78 | 186 | 747 | 1,011 |

The zero-delivery CMAS test spent 33 prompt and 21 generated tokens on three calls. Both reporting tools show 54 total tokens, zero deliveries and `NA` per delivered box. A separate three-episode cell delivered three boxes with 72 tokens, giving 24 tokens per box across partial, complete and zero-delivery episodes. [Delivery-denominator tests](test_chen2d_v20.py)

For the default `drop` and explicit `fail` policies, the task-19 and task-20 runners received the same correct, infeasible and unreadable fake replies on 2×2 boards. With fixed clocks and invocation IDs and normalized source-version stamps, all 414 compared files matched byte for byte, including 188 numbered calls, the episode JSON files, prompt and action files, assignments and episode CSVs. [Comparison against task 19](review/chen2d-20/default-replay.txt)

**All 278 tests passed in 595.006 seconds at revision `bc8ca8b14f1e`**, including all 263 earlier tests and 15 new regressions. The suite used folder-local fixtures, a fake model and scripted transport responses with network connections disabled. An earlier development pass crossed the final CSV formatting edit and triggered the source-version checks. The full test result uses a fresh process at the fixed revision. [Full test log](review/chen2d-20/all-tests.txt) · [Focused test log](review/chen2d-20/focused-tests.txt) · [Development run](review/chen2d-20/initial-tests.txt)

```bash
export TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python3 -B test_chen2d_v14.py test_chen2d test_chen2d_v{2..14} \
  test_chen2d_v15_{maps,matched,cli,probe,probe_exec} test_chen2d_v16 \
  test_chen2d_v17_{writers,retry,limits,replay} test_chen2d_v18 test_chen2d_v19 test_chen2d_v20
```

### 확인 안 됨

Live-model delivery rates, the frequency and token cost of blocked writers, the effect of raising the output limit, provider latency and billed cost remain unmeasured. The failure examples use scripted replies, and both command designs were rehearsed with the local fake model. [Offline run log](review/chen2d-20/fake-runs.txt)

## CHEN2D-21

With `--protocol matched --cut-answer prefix`, a writer can use the complete leading steps visible when the provider reaches its output limit. On a scripted three-step CMAS reply cut inside step three, the executor applied steps one and two, then closed the round. The call used one physical attempt and the trace counted one cut. The default setting is `discard`. [Writer and retry tests](test_chen2d_v21.py)

### Which steps survive

The retry decision uses the recorded answer text from a reply-bearing attempt with `cut_off is True`. Reasoning tokens do not supply plan text. The reader accepts the existing lenient reply shapes, including bare lists, JSON fences and leading prose. It can close a recognized outer list or wrapper. A joint step must have its own closing `}`. A cut after a complete robot/action pair but before that brace loses the entire step for every robot. An empty joint object `{}` is a written idle step. The joint reader also recognizes a closed standalone step, a list wrapper and numbered step objects. [Prefix reader](plan_parse.py)

For OWN, an action string needs its closing quote, a literal wait needs the complete `null`, and a per-entry object or singleton list needs its own closing delimiter. The reader also accepts its existing self-keyed and nested list forms. In an unfinished first inner list, a separator between inner entries distinguishes a wrapped timeline from an unfinished singleton step. The normal reader checks the writer’s scope and recognizes the retained entries before it adds any waits. A blank reply, a cut in the fence opener, an unfinished first step or an unrecognized shape follows the existing physical retry path. If the retries run out, the configured failed-writer policy applies. [Matched reader](plan_parse.py) · [Attempt handling](LLM.py)

One recognized step is enough to return the short reply to the configured judge. An infeasible first action gets the usual repair prompt and allowance. A strict judge can request a repair for a short list because it requires exactly H entries. Repairs can also return a cut prefix. [Judging, repair and execution](horizon.py)

### Rest of the round

| Writer | When it writes k of H steps |
| --- | --- |
| CMAS, including a full-board GROUP | The sole writer proposes k slots. After them the round ends. If work remains and the ceilings permit, the next round starts from the resulting board. |
| GROUP with multiple joint writers | The merge has H slots. This block contributes actions through k, and the other blocks can still act in later slots. The next writer sees the k retained joint entries. |
| OWN, including a GROUP of size one with multiple writers | The usual short-list reader fills the execution tail with null waits. The next writer sees only the k written entries from a salvaged reply. |

An empty merged slot consumes zero environment steps. Completion, a later infeasible action and the ordinary ceilings can end execution sooner. [Merge and executor](horizon.py)

### What the counts measure

The attempt retains the provider finish, the client’s recorded visible text in `raw_output`, `visible_reply_chars` and `cutoff_reply_class=partial`. Both the attempt and its logical call record `cut_answer_salvaged=true` and `salvaged_steps=k`. The call’s `response_from_attempt` identifies its one-based physical attempt and `response` supplies the short reply to the judge. The round’s `writer_cut_prefix` event records the round, framework, speaker, covered robots, call, attempt, k and H. Cut, retry and usage totals continue to count the actual physical attempts. A successful salvage qualifies as a recovered cut even when it occurs on the first attempt. [Call trace](LLM.py) · [Round events](horizon.py) · [Measurements](planning_metrics.py)

The prefix summary and planning tables lead each cell with correctly delivered boxes and total boxes. `cutoff_attempts_empty` counts blank cuts. `cutoff_attempts_partial_zero_steps` and `cutoff_attempts_partial_salvaged` split the existing nonblank partial count. The existing unknown bucket covers attempts without a visible-text classification. For every salvaged submission, `cut_prefix_robot_steps_kept` adds k × covered robots and `cut_prefix_robot_steps_not_written` adds (H − k) × covered robots. These measure what the writer supplied, including written waits and submissions later repaired. The executed-step and delivered-box columns measure what reached the board. Cells distinguish frameworks, GROUP sizes and cut-answer policies. [Summary and CSV](summarize.py) · [Cell totals](planning_metrics.py)

### Main-session pilot command

The task-20 pilot uses seeds 0–1 and 18 assignments at each output limit. This command adds `--cut-answer prefix` and writes each limit to a fresh task-21 directory. [Task-20 pilot](#chen2d-20)

```bash
common=(--model z-ai/glm-5.3-flash --protocol matched --map-set scaled:2
        --sizes 1x3,2x3,3x3 --frameworks CMAS,GROUP,OWN --group-size 3 --conditions static
        --horizon 5 --history-method authors --history-window 100000 --state-position after
        --plan-note continue --failed-writer idle --max-stalled-rounds 3 --dropoff event --parse lenient
        --cut-answer prefix --max-env-steps 30 --max-planning-rounds 30 --episode-call-ceiling 600
        --temperature 0 --retry-temperature 0 --reasoning default --jobs 2 --max-cost-usd 1.50)

for limit in 8192 16384; do
  python3 -B run_chen2d.py "${common[@]}" --envs 0-1 --max-calls 10800 \
    --max-output-tokens "$limit" --out "runs/chen2d-21-pilot-r2-$limit"
done
python3 -B summarize.py --by planning runs/chen2d-21-pilot-r2-{8192,16384}
```

### Offline verification

At H=3, a partially written third joint step already contained one whole robot/action pair. CMAS executed the first two steps, counted eight kept and four unwritten robot-steps on the four-robot board, and made one physical call. With GROUP, the second writer saw the two entries and supplied the third step. Its peer’s two-robot prefix counted as four kept and two unwritten robot-steps. With OWN, the next writer saw the two written entries and the other robots completed the third step. The single-robot prefix counted as two kept and one unwritten. [Scripted executor tests](test_chen2d_v21.py)

To script a fixed visible cut locally, pass `--model fake --protocol matched --fake-script 'cut:[{},'`. With `--cut-answer prefix` this gives one complete idle step on the first attempt. Tests can return `fake_model.CutReply(text)` among ordinary replies to vary the cut by attempt, writer or repair. The tests also exercise provider finish fields through the folder-local client with scripted transport responses. [Fake model](fake_model.py) · [Focused test log](review/chen2d-21/focused-tests.txt)

The byte-compatibility test compares explicit `discard` against fingerprints collected from task 20 at revision `bc8ca8b14f1e`. It covers correct, infeasible and unreadable replies under each of `drop`, `fail` and `idle`, across CMAS, GROUP and OWN. The comparison includes every saved prompt, numbered call, episode, action, assignment and CSV in those runs, plus both summary modes. It fixes clocks and invocation IDs and normalizes the source-version stamp. A separate replay of all four task-20 fake cohorts reproduced both archived planning tables byte for byte. Across 252 episodes and 2,390 attempts, the per-episode CSV also matched after normalizing its source-version column. [Compatibility test](test_chen2d_v21.py) · [Archive comparison and hashes](review/chen2d-21/default-replay.txt)

The task-21 pilot command was rehearsed with the ordinary correct fake. Each output limit produced 18 episodes, 216/216 deliveries, 184 physical attempts and zero cuts. The scripted cut cases above exercise the salvage decision. A cut-position sweep also checked 908 character boundaries in bare and fenced replies, including wrappers, escaped text and complete waits. A scripted transport error followed by three cut replies kept two steps on the final allowed reply and charged all four physical attempts. [Fake pilot](review/chen2d-21/pilot-fake.txt) · [Boundary and retry tests](test_chen2d_v21.py)

**All 292 offline tests passed in 374.072 seconds on revision `6172cbfbac44`**, including all 278 earlier tests and 14 task-21 tests. The first full run caught an extra field in legacy OWN reader metadata. The prefix reader now requests unpadded entries during salvage recognition, and the archived metadata comparison passes. [Full suite](review/chen2d-21/all-tests.txt) · [Focused suite](review/chen2d-21/focused-tests.txt) · [Earlier development run](review/chen2d-21/development-tests.txt)

```bash
export TMPDIR="$PWD" OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
python3 -B test_chen2d_v14.py test_chen2d test_chen2d_v{2..14} \
  test_chen2d_v15_{maps,matched,cli,probe,probe_exec} test_chen2d_v16 \
  test_chen2d_v17_{writers,retry,limits,replay} test_chen2d_v18 test_chen2d_v19 test_chen2d_v20 test_chen2d_v21
```

### 확인 안 됨

The task brief reports empty visible answers on 72 of 74 cuts in the earlier real run. Only two replies had visible text, and their complete-step counts remain unverified here. How often a live provider returns usable leading steps, how many robot-steps those replies preserve, and their effect on deliveries, latency or billed cost remain unmeasured. The pilot results above come from the local fake model. [Task brief](TASK-CHEN2D-21.md) · [Pilot rehearsal](review/chen2d-21/pilot-fake.txt)
