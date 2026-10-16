# Frozen command trajectories

Source: `3327a0ea686cf15dc56d118fe89bf736b93ba284`, extracted with `git archive` before
changing product code. The manifest records exact file byte counts and SHA-256.
These are offline command trajectories, not physical motion or model results.

- `*-scheduler.json`: existing `tests/pair_llm_window_replay.py:replay`, duration 24 s,
  stop 12 s, origin 0; policy returns `release(cargoX)` on call index 1, otherwise
  `continue`. Exactly 480 control command rows per condition.
- `*-hooks.json`: existing `tests/test_highpose_refix.py:team(BEFORE_DOOR,
  over={'r1': True})`, `short_route`/`stub_states` fixtures; attach the existing
  StopAdapter for each condition and poll before `run_one(ctls, i/10)` for
  `i=0..1400`. Serialize `[c.issued_log for c in ctls]`: 2,252 r1 commands and
  2,251 r2 commands (4,503 per condition).
- Serialization: `json.dumps(value, sort_keys=True, separators=(',', ':')).encode()`.

The hook controller and fixed status channel are real production Python. Frames,
plant and look/refix fixture inputs are test doubles. Rule has no PairTrial; its
actual HIGH hook command log is independently pinned here. No network, physics,
MuJoCo rendering, or live model calls were used.

The old event path before e1 (`a7bb0ec1`) is intentionally not the baseline. The
0.1 s no_comm stop wake mutation must differ from the frozen scheduler trace at
15.3 s, even if both sides of an availability-only comparison share that mutation.
