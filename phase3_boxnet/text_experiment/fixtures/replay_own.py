"""Replay the saved OWN responses and their original first-step boards. Writes JSON to stdout."""
import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from horizon import available_actions, check_joint
from plan_parse import PlanParser
from storage import read_json

PILOT = ROOT.parent / "20261124-chen2d-snap-v15/runs/v15-pilot-r1"


def replay_episode(directory):
    row = read_json(directory / "episode.json")
    horizon, mode = row["horizon"], row["parse"]
    if row["framework"] != "OWN" or row["protocol"] != "matched" or row["condition"] != "static":
        raise ValueError(f"Expected a matched static OWN episode at {directory}")
    checks = {c["call"]: c for batch in row["round_log"] for c in batch["checks"]}
    rows, cols = map(int, row["size"].split("x"))
    boards = {}

    def first_step_ok(step, speaker, entries):
        if step not in boards:
            state = read_json(directory / "pg_state" / f"pg_state{step}.json")
            runtime = SimpleNamespace(state=state, spec=SimpleNamespace(rows=rows, cols=cols), condition="static")
            boards[step] = state, available_actions(runtime)
        state, available = boards[step]
        plan = {speaker: entries[0]} if entries[0] is not None else {}
        feedback, _ = check_joint(state, plan, available, returned_only=False)
        return not feedback

    trace_hash = hashlib.sha256()
    counts = dict(logical_calls=0, physical_attempts=0, returned_replies=0, no_reply=0,
                  previously_read=0, previously_refused=0, newly_read=0, still_refused=0,
                  previously_read_now_refused=0, read_now=0, first_step_doable=0, newly_read_first_step_doable=0)
    shapes, refusal_reasons = Counter(), Counter()
    refusals, no_reply = [], []
    seen_checks = set()
    for path in sorted((directory / "calls").glob("[0-9]*.json")):
        raw = path.read_bytes()
        trace_hash.update(path.name.encode() + b"\0" + hashlib.sha256(raw).digest())
        call = json.loads(raw)
        if call["role"] != "own":
            raise ValueError(f"Unexpected role in {path}")
        number, speaker, response = call["number"], call["speaker"], call["response"]
        counts["logical_calls"] += 1
        counts["physical_attempts"] += call["api_calls"]

        # In this pilot the only physical attempts with saved text are exactly the returned
        # responses. Verify that premise rather than double-counting them or skipping a partial reply.
        physical_text = [a["raw_output"] for a in call["attempts"] if a.get("raw_output") is not None]
        if physical_text != ([] if response is None else [response]):
            raise ValueError(f"Additional or inconsistent physical reply text in {path}")
        if response is None:
            if number in checks or call.get("own_reply_form") or call["status"] == "ok":
                raise ValueError(f"Inconsistent missing response in {path}")
            counts["no_reply"] += 1
            no_reply.append(dict(call=number, attempt_kinds=call["attempt_kinds"], failure=call["failure"]))
            continue

        check = checks[number]
        seen_checks.add(number)
        previously_read = call["own_reply_form"] is not None
        if previously_read != (check["status"] in ("valid", "invalid")) or check["speaker"] != speaker:
            raise ValueError(f"Historical reader form and planning-round check disagree in {path}")
        counts["returned_replies"] += 1
        counts["previously_read" if previously_read else "previously_refused"] += 1
        errors, observed = [], []
        parser = PlanParser(mode, record_shape=observed.append)
        entries = parser.sequence(response, horizon, own=True, speaker=speaker, matched_shape=True,
                                  format_errors=errors)
        shape, = observed
        if entries is None:
            counts["previously_read_now_refused" if previously_read else "still_refused"] += 1
            refusal_reasons[shape.reason] += 1
            refusals.append(dict(call=number, speaker=speaker, step=call["step"], reason=shape.reason,
                                 detail=shape.detail or next(iter(errors), None), previously_read=previously_read))
            continue
        counts["read_now"] += 1
        counts["newly_read"] += int(not previously_read)
        shapes[shape.form] += 1
        doable = first_step_ok(call["step"], speaker, entries)
        counts["first_step_doable"] += int(doable)
        counts["newly_read_first_step_doable"] += int(doable and not previously_read)

    if seen_checks != checks.keys() or counts["physical_attempts"] != row["api_calls"]:
        raise ValueError(f"Saved checks or attempt totals disagree with {directory}/episode.json")
    return dict(episode=directory.name, horizon=horizon, mode=mode, **counts,
                refusal_reasons=dict(sorted(refusal_reasons.items())), shapes_read=dict(sorted(shapes.items())),
                calls_without_replies=no_reply, refused_replies=refusals, trace_sha256=trace_hash.hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", nargs="?", type=Path, default=PILOT)
    path = parser.parse_args().pilot
    config = read_json(path / "run.json")
    names = [f"{grid}_OWN_static_env{seed}" for grid in ("4x4", "4x8") for seed in (0, 1)]
    if sorted(p.name for p in (path / "episodes").glob("*_OWN_*")) != names:
        raise ValueError("Expected the four OWN episodes of the designated pilot")
    episodes = [replay_episode(path / "episodes" / name) for name in names]
    print(json.dumps(dict(pilot=path.name, pilot_code_version=config["code_version"], episodes=episodes),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
