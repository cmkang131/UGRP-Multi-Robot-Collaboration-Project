"""Measure the deterministic reference solver on registered scaled maps offline."""
import argparse
import json

from board_sizes import ENROL_SIZES, LEGACY_SIZES as SIZE_NAMES, selection
from enrol_maps import seed_selection
from env1_create import action_from_response
from fake_model import reply
from map_events import boxes, reference_trajectory, step_limit
from map_sets import colour_counts, parse_map_set, saved_scaled_env
from matched_protocol import build_prompt
from plan_parse import PlanParser
from prompt_env1 import message_construct_func
from storage import local_path, write_json


def measured_rounds(rows, cols, initial, trajectory, horizon):
    """Run the message-only scripted writer and compare every committed board."""
    state, steps, rounds = initial, 0, 0
    parser = PlanParser("strict")
    while boxes(state):
        prompt = build_prompt(rows, cols, state, [], [state], horizon=horizon,
                              history_method="none", history_window=0, state_position="after")
        messages = message_construct_func([prompt], [], "_w_all_dialogue_history")
        plans = parser.sequence(reply(messages, "correct"), horizon)
        if not plans:
            raise ValueError("Scripted writer supplied no joint plan")
        rounds += 1
        for plan in plans:
            applied = []
            feedback, state = action_from_response(state, plan, applied)
            if not applied or feedback or steps >= len(trajectory) or state != trajectory[steps]:
                raise ValueError(f"Scripted H={horizon} diverged at environment step {steps + 1}")
            steps += 1
    if steps != len(trajectory):
        raise ValueError("Scripted completion disagrees with the reference solver")
    return steps, rounds


def measurements(rates, sizes, seeds):
    """Return one H=1 and one H=5 scripted measurement for every selected map."""
    result = []
    for rate_text in rates:
        selected = parse_map_set("scaled:" + rate_text)
        for size in sizes:
            rows, cols = map(int, size.split("x"))
            for seed in seeds:
                path, sha, metadata = saved_scaled_env(rows, cols, seed, selected)
                state = json.loads(path.read_text())
                trajectory = [after for after, _ in reference_trajectory(state, action_from_response)]
                box_count = boxes(state).total()
                for horizon in (1, 5):
                    steps, rounds = measured_rounds(rows, cols, state, trajectory, horizon)
                    cap = step_limit(rows, cols)
                    result.append(dict(**metadata, size=size, rows=rows, cols=cols, robots=rows * cols,
                                       seed=seed, env_path=str(path), env_sha256=sha,
                                       colour_counts=colour_counts(box_count), scripted_steps=steps,
                                       horizon=horizon, scripted_planning_rounds=rounds,
                                       legacy_step_limit=cap, within_legacy_step_limit=steps <= cap,
                                       within_max_env_steps_30=steps <= 30))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rates", default="0.5,1,2", help="comma-separated positive R values")
    parser.add_argument("--sizes", default=",".join(SIZE_NAMES))
    parser.add_argument("--envs", default="0-11")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    rates = [value.strip() for value in args.rates.split(",") if value.strip()]
    if not rates:
        parser.error("--rates must contain at least one value")
    try:
        # Validate before enrolling anything.
        out = local_path(args.out)
        for rate in rates:
            parse_map_set("scaled:" + rate)
        rows = measurements(rates, selection(args.sizes, ENROL_SIZES), seed_selection(args.envs))
    except ValueError as exc:
        parser.error(str(exc))
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, rows)
    print(f"{len(rows)} horizon measurements; {len(rows) // 2} maps; max scripted steps "
          f"{max(row['scripted_steps'] for row in rows)}")


if __name__ == "__main__":
    main()
