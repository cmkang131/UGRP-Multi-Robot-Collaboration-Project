# TASK-CHEN2D-10: a small edge-sized model and a table of output demand per planning call (2026-11-24)

Context: tasks 1 to 9 are done (`REPORT-CHEN2D.md`). Same hard limits: this folder only, no network, fake model for tests, no real-model batches, and do NOT edit anything under `<work>/20261123-phase3/` (the shared client `link/brain/llm.py` is imported by batches that are running right now). No existing option may change behaviour; all existing tests stay green.

Why. The user narrowed the paper to one thing: failures caused by the max output token limit, by structure and team size, and asked for a small Qwen model of the size that runs on a Colab GPU. A probe (ten saved prompts replayed by hand) showed that `qwen/qwen3.5-9b` works through the shared client without any profile entry when the request carries `reasoning={"enabled": False}` (reasoning tokens 0, default price ceilings admit its endpoints), and that its output behaves differently from the default model: the leader's reply is short JSON, the no-leader robots write long visible reasoning.

## R1. Model and reasoning options
- `--model` also accepts `qwen/qwen3.5-9b` (name the constant `SMALL_QWEN`).
- `--reasoning default | off` (default `default` = today's behaviour byte for byte: the client decides). `off` makes the episode client pass `reasoning={"enabled": False}` to `RealLLM`. Refuse `off` for the default GLM model with a clear message (that model requires reasoning) and refuse it for the 235B Qwen (its profile has no reasoning parameter). For `qwen/qwen3.5-9b`, `default` means the client's default (`{"effort": "low"}`), so both arms are available.
- Record the setting in `run.json`, in every episode record and in `episodes.csv` (`reasoning_setting`). `summarize.py`, `cost.py`, `paired.py`, `failure_causes.py` and the other tools must group by (model, reasoning setting) or refuse to mix, as fits each tool.
- Provider: the shared client already stores the provider name of each physical attempt in its own log. Copy it into each attempt of the saved call record (`provider`), and add `providers` to `episodes.csv` (distinct names, sorted, joined by `+`). Old run folders without the field must still load (empty).

## R2. `output_demand.py RUNDIR [RUNDIR ...]` (read-only; accepts run folders of versions 3 to 10)
For every plan-making call (the leader's planning call, each no-leader robot's dialogue turn, HMAS-2 planner and reviewers; relay calls excluded and counted separately), per physical attempt and per logical call:
- generated tokens = completion tokens (reasoning included), reasoning tokens, visible tokens = completion − reasoning (when known);
- whether the attempt was cut at the limit; the limit;
- plan size: number of agents in the plan that was finally extracted from that reply (0 when none), and an approximate token count of that plan text alone (use the folder's existing approximate counter);
- step, role, speaker, team size, framework, model, reasoning setting, condition.
Outputs: a CSV per call, and a table grouped by (model, reasoning setting, max_output_tokens, size, framework, role): logical calls, attempts, share of attempts cut, median / 90th percentile / maximum generated tokens of attempts that were NOT cut, the same for reasoning and for visible tokens, median plan tokens and median agents per plan. A second table per (model, reasoning setting, size, framework): generated tokens per environment step (all plan-making calls of the step added up), median and 90th percentile, so that "one call of the leader" and "one round of the whole team" can both be read.
State in the docstring that demand measured under a low limit is censored (cut attempts only give a lower bound), and print the censored share next to every statistic.

## R3. Tests and report
Tests (fake model): `--reasoning off` reaches the client constructor for the small Qwen and is refused for the other two models; default settings reproduce a saved version-9 episode byte for byte; the new CSV columns exist and old folders load; `output_demand.py` on a constructed run with known token counts, a cut attempt and a relay call, and on one old run folder copied into the tests. Append "CHEN2D-10" to `REPORT-CHEN2D.md` with the command for: sizes 2x2, 2x4, 4x4, 4x8, static, `--dropoff event`, CMAS and DMAS, envs 0 to 3, `--model qwen/qwen3.5-9b --reasoning off`, `--max-output-tokens 8192`, temperature 0.0 with retry temperature 0.7, and a call estimate. Last step: create `review/ASTRA-CHEN2D-10.done`.
