"""Measure output demand from published BoxNet1 traces, without changing the runs.

Demand measured under a low output limit is censored. A cut attempt gives only a lower
bound on the tokens needed for an uninterrupted reply. Attempt quantiles use known meters
from uncut attempts. Generated tokens include reasoning. Visible tokens require both
meters. A missing meter is unknown even when the requested reasoning setting was off.

The CSV has one row per planning call, with its physical attempts in order as JSON.
Only a reply returned to an extraction site can supply a plan. Reviews and dialogue
without EXECUTE still contribute their full token demand. An absent plan has zero
agents and tokens. An extracted empty object has zero agents and its own text length.
Plan-only medians use extracted objects. Per-call medians also include absent plans.

Each started environment step sums the metered generation of all its planning attempts,
including retries, cuts and reviews. A step with an unknown completion meter has an
unknown total. Steps are distinct across runs and episodes. The step table pools the
observed limits and conditions. Relay work is counted separately. Quantiles interpolate
linearly between adjacent ordered observations. Each estimate shows its sample size
and the censored fraction of its parent population (attempts, calls or steps).
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from LLM import was_truncated
from analysis_runs import recorded_calls
from env1_create import MAX_REPAIRS
from failure_causes import AGENT, grouped, print_row, share
from limits import CALL_CEILING
from plan_parse import PlanParser, speaker_coordinates
from planning_metrics import cutoff_records, print_planning_table, repair_feedback
from prompt_env1 import history_tokens
from storage import atomic_file, local_path
from summarize import read_episode_rows


STEP_GROUP = ("model", "reasoning_setting", "size", "framework", "horizon", "state_position")
CALL_GROUP = ("model", "reasoning_setting", "max_output_tokens", "size", "framework", "role", "horizon", "state_position")
METERS = ("generated_tokens", "reasoning_tokens", "visible_tokens")
CALL_FIELDS = ("run", "episode_id", "code_version", "env_seed", *STEP_GROUP, "team_size", "condition",
               "step", "planning_round", "round", "role", "speaker", "call_number", "max_output_tokens", "attempt_count",
               "cut_attempts", "cut", "cut_role", "terminal_cut", *METERS, "plan_extracted", "plan_agents", "plan_tokens", "attempts")
OWN_CALL_FIELDS = ("own_reply_form", "own_reply_padded", "own_reply_cut")


def selected_plan(call, parser, repair_depth):
    reply = call.get("response")
    if not isinstance(reply, str) or repair_depth >= MAX_REPAIRS:
        return None
    if repair_depth:
        selected = parser.for_check(reply)
    elif call["role"] == "central":
        revision = len(call.get("messages", ())) > 2
        selected = parser.extract(reply, revision=revision)
        if revision and selected is not None:
            # The HMAS-2 revision sends the entire reply back through the checker.
            selected = parser.for_check(reply)
    elif call["role"] == "dialogue" and "EXECUTE" in reply:
        selected = parser.extract(reply)
    else:
        return None
    if selected is None:
        return None
    try:
        obj = json.loads(selected)
    except (ValueError, RecursionError):
        return None
    if isinstance(obj, dict):
        agents = {tuple(map(float, m.groups())) for key in obj if (m := AGENT.fullmatch(key.strip()))}
        return len(agents), history_tokens(selected.strip())
    return None


def selected_sequence(call, parser, horizon, *, prior_shapes=False, agent_positions=None, matched_shape=False):
    own = call["role"] == "own"
    if matched_shape and call["role"] == "group":
        agent_positions = {speaker_coordinates(name) for name in call["assigned_robots"]}
    entries = parser.sequence(call["response"], horizon, own=own, speaker=call.get("speaker"),
                              dialogue=call["role"] == "dialogue", legacy_own=own and "own_reply_form" not in call,
                              prior_shapes=prior_shapes, agent_positions=agent_positions, matched_shape=matched_shape)
    if entries is None:
        return None
    if own:
        agents = int(any(entry is not None for entry in entries))
    else:
        agents = len({tuple(map(float, m.groups())) for plan in entries for key in plan
                      if (m := AGENT.fullmatch(key.strip()))})
    return agents, history_tokens(json.dumps(entries))


def attempt_demand(index, attempt, limit):
    generated, reasoning = attempt.get("completion_tokens"), attempt.get("reasoning_tokens")
    visible = None
    if generated is not None and reasoning is not None and reasoning <= generated:
        visible = generated - reasoning
    return dict(attempt=index, kind=attempt["kind"], provider=attempt.get("provider"),
                generated_tokens=generated, reasoning_tokens=reasoning, visible_tokens=visible,
                cut=was_truncated(attempt), max_output_tokens=limit,
                plan_extracted=False, plan_agents=0, plan_tokens=0)


def measured_sum(records, field):
    values = [r[field] for r in records]
    return None if None in values else sum(values)


def measure_episode(out, row, relays):
    trace = recorded_calls(out, row)
    calls = []
    iterations = {(it.get("planning_round", it["step"]), it["step"]): it for it in row["iterations"]}
    by_step = {key: [] for key in iterations}
    if "cut_calls" not in row:
        row["cut_calls"] = cutoff_records(row, trace)
    cuts = {c["call"]: c for c in row["cut_calls"]}
    matched_shape = row.get("protocol") == "matched" and row.get("list_parser_version", 0) >= 17
    list_mode = matched_shape or row["horizon"] > 1 or row["framework"] in ("OWN", "GROUP")
    extracted = {c["call"] for b in row.get("round_log", ()) for c in b.get("checks", ())
                 if c["status"] != "parse failure"}
    parser = PlanParser(row["parse"])
    row.setdefault("map_set", "legacy")
    metadata = {field: row[field] for field in (*STEP_GROUP, "condition", "max_output_tokens",
                                                "code_version", "episode_id", "env_seed")}
    height, width = map(int, row["size"].split("x"))
    positions = {(i + .5, j + .5) for i in range(height) for j in range(width)}
    metadata.update(run=str(out), team_size=height * width)
    if row["framework"] == "GROUP":
        metadata["group_size"] = row["group_size"]
    repair_depth = 0
    for call in trace:
        physical = [a for a in call["attempts"] if a["api_calls"]]
        if call["role"] == "relay":
            relays.update(calls=1, attempts=len(physical), cuts=sum(a["kind"] == "truncated" for a in physical))
            continue
        repair_depth = repair_depth + 1 if repair_feedback(call) else 0
        attempts = [attempt_demand(i, a, row["max_output_tokens"]) for i, a in enumerate(physical, 1)]
        cut_count = sum(a["cut"] for a in attempts)
        # At the physical ceiling the runner saves the last reply but stops before returning it.
        stopped = (call is trace[-1] and row["success_failure"] == CALL_CEILING
                   and row["api_calls"] == row.get("episode_call_ceiling"))
        plan = None
        returned = attempts and (attempts[-1]["kind"] == "ok" or call.get("cut_answer_salvaged"))
        if returned and call["status"] == "ok" and not stopped:
            if not list_mode:
                plan = selected_plan(call, parser, repair_depth)
            elif call["number"] in extracted:
                plan = selected_sequence(call, parser, row["horizon"], prior_shapes=row.get("list_parser_version", 0) < 14,
                                         agent_positions=positions, matched_shape=matched_shape)
        plan_fields = dict(plan_extracted=plan is not None, plan_agents=plan[0] if plan else 0,
                           plan_tokens=plan[1] if plan else 0)
        if plan is not None:
            attempts[-1].update(plan_fields)
        cutoff = cuts.get(call["number"], {})
        result = dict(metadata, step=call["step"], planning_round=call.get("planning_round", call["step"]),
                      round=call.get("round"), role=call["role"],
                      speaker=call.get("speaker"), call_number=call["number"], attempt_count=len(attempts),
                      cut_attempts=cut_count, cut=bool(cut_count), cut_role=cutoff.get("role"),
                      terminal_cut=cutoff.get("terminal", False), attempts=attempts, **plan_fields,
                      **{field: measured_sum(attempts, field) for field in METERS})
        if "own_reply_form" in call:
            # A concurrently resumed trace may be ahead of the published episode's checks.
            if call["number"] in extracted:
                result.update({field: call[field] for field in OWN_CALL_FIELDS})
            else:
                result.update(own_reply_form=None, own_reply_padded=False, own_reply_cut=False)
            if "own_reply_invalid_position" in call:
                result["own_reply_invalid_position"] = (call["own_reply_invalid_position"]
                                                        if call["number"] in extracted else None)
        if "group_size" in metadata:
            for key in ("robots_assigned", "assigned_robots_with_doable_actions"):
                result[key] = call[key]
        calls.append(result)
        by_step.setdefault((result["planning_round"], call["step"]), []).append(result)

    steps = [dict(metadata, step=step, planning_round=batch,
                  executed=iterations.get((batch, step), {}).get("executed", False), generated_tokens=measured_sum(turns, "generated_tokens"),
                  cut=any(c["cut"] for c in turns), cut_attempts=sum(c["cut_attempts"] for c in turns),
                  attempt_count=sum(c["attempt_count"] for c in turns)) for (batch, step), turns in by_step.items()]
    return calls, steps


def read_runs(outs, *, episodes=None):
    calls, steps, coverage = [], [], []
    designs = {}
    for out in outs:
        rows = read_episode_rows(out)
        if episodes is not None:
            episodes.extend(rows)
        relays = Counter()
        for row in rows:
            designs[str(out), row["episode_id"]] = row.get("map_set", "legacy")
            episode_calls, episode_steps = measure_episode(out, row, relays)
            calls.extend(episode_calls)
            steps.extend(episode_steps)
        coverage.append((out, len(rows), sum(not row["finished"] for row in rows),
                         relays["calls"], relays["attempts"], share(relays["cuts"], relays["attempts"])))
    if any("group_size" in r for r in steps):
        for records in (calls, steps):
            for r in records:
                r["map_set"] = designs[r["run"], r["episode_id"]]
    return calls, steps, coverage


def estimates(rows, field, quantiles, censor):
    values = [r[field] for r in rows if r[field] is not None]
    stats = [f"{x:.12g}" for x in np.quantile(values, quantiles)] if values else ["NA"] * len(quantiles)
    return [f"{stat} [n={len(values)}, cut={censor}]" for stat in stats]


def unit_totals(segments, unit):
    # Several planning rounds can start on the same physical step after an empty list.
    return [dict(generated_tokens=measured_sum(batch, "generated_tokens"), cut=any(s["cut"] for s in batch),
                 executed=sum(s["executed"] for s in batch), attempt_count=sum(s["attempt_count"] for s in batch),
                 cut_attempts=sum(s["cut_attempts"] for s in batch))
            for batch in grouped(segments, ("run", "episode_id", unit)).values()]


def print_tables(calls, steps, coverage, stream):
    include_map_set = any(row.get("map_set", "legacy") != "legacy" for row in (*calls, *steps))
    step_group = STEP_GROUP + (("map_set",) if include_map_set else ())
    call_group = CALL_GROUP + (("map_set",) if include_map_set else ())
    if any("group_size" in row for row in (*calls, *steps)):
        call_group += ("group_size",)
        step_group += ("group_size",)
    print("Excluded relay work", file=stream)
    print_row(stream, ("run", "published_episodes", "interrupted_episodes", "relay_calls", "relay_attempts",
                       "relay_attempt_cut_share"))
    for row in coverage:
        print_row(stream, row)
    print("\nCut attempts give lower bounds. Each estimate shows the metered sample count and censoring share.",
          file=stream)
    print("Planning calls", file=stream)
    print_row(stream, (*call_group, "logical_calls", "attempts", "attempt_cut_share", "call_cut_share",
                       *(f"{stat}_{field}" for field in METERS for stat in ("median", "p90", "max")),
                       "extracted_plans", "median_plan_tokens", "median_agents_per_plan",
                       "median_plan_tokens_per_call", "median_agents_per_call"))
    for key, group in sorted(grouped(calls, call_group).items()):
        attempts = [a for c in group for a in c["attempts"]]
        uncut = [a for a in attempts if not a["cut"]]
        attempt_share = share(len(attempts) - len(uncut), len(attempts))
        call_share = share(sum(c["cut"] for c in group), len(group))
        plans = [c for c in group if c["plan_extracted"]]
        stats = [v for field in METERS for v in estimates(uncut, field, (.5, .9, 1.), attempt_share)]
        plan_stats = [v for population in (plans, group) for field in ("plan_tokens", "plan_agents")
                      for v in estimates(population, field, (.5,), call_share)]
        print_row(stream, (*key, len(group), len(attempts), attempt_share, call_share,
                           *stats, len(plans), *plan_stats))

    print("\nGeneration per environment step", file=stream)
    print_row(stream, (*step_group, "observed_limits", "steps", "attempts", "attempt_cut_share", "step_cut_share", "executed_steps",
                       "median_generated_tokens", "p90_generated_tokens"))
    for key, group in sorted(grouped(steps, step_group).items()):
        limits = ",".join(str(limit) for limit in sorted({s["max_output_tokens"] for s in group}))
        group = unit_totals(group, "step")
        n = sum(s["attempt_count"] for s in group)
        step_share = share(sum(s["cut"] for s in group), len(group))
        print_row(stream, (*key, limits, len(group), n, share(sum(s["cut_attempts"] for s in group), n),
                           step_share, sum(s["executed"] for s in group), *estimates(group, "generated_tokens", (.5, .9), step_share)))

    print("\nGeneration per planning round", file=stream)
    print_row(stream, (*step_group, "observed_limits", "planning_rounds", "executed_steps", "attempts",
                       "round_cut_share", "median_generated_tokens", "p90_generated_tokens"))
    for key, group in sorted(grouped(steps, step_group).items()):
        rounds = unit_totals(group, "planning_round")
        limits = ",".join(str(n) for n in sorted({s["max_output_tokens"] for s in group}))
        cut = share(sum(r["cut"] for r in rounds), len(rounds))
        print_row(stream, (*key, limits, len(rounds), sum(s["executed"] for s in group),
                           sum(s["attempt_count"] for s in group), cut, *estimates(rounds, "generated_tokens", (.5, .9), cut)))


def write_calls(calls, stream):
    fields = CALL_FIELDS + OWN_CALL_FIELDS if any("own_reply_form" in call for call in calls) else CALL_FIELDS
    if any("map_set" in call for call in calls):
        fields += ("map_set",)
    if any("group_size" in call for call in calls):
        fields += ("group_size", "robots_assigned", "assigned_robots_with_doable_actions")
    if any("own_reply_invalid_position" in call for call in calls):
        fields += ("own_reply_invalid_position",)
    writer = csv.DictWriter(stream, fields, lineterminator="\n")
    writer.writeheader()
    for call in calls:
        writer.writerow(dict(call, attempts=json.dumps(call["attempts"], separators=(",", ":"))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rundirs", nargs="+", type=Path)
    parser.add_argument("--calls-csv", "--csv", default="-", metavar="PATH",
                        help="write the call CSV outside the inputs (default stdout, tables on stderr)")
    args = parser.parse_args()
    try:
        outs = [p.resolve() for p in args.rundirs]
        if len(set(outs)) != len(outs):
            raise ValueError("A run directory was supplied twice")
        dest = None if args.calls_csv == "-" else local_path(args.calls_csv)
        if dest and any(dest.is_relative_to(out) for out in outs):
            raise ValueError("The call CSV must be outside all input run directories")
        episodes = []
        calls, steps, coverage = read_runs(outs, episodes=episodes)
        if dest:
            with atomic_file(dest) as stream:
                write_calls(calls, stream)
        else:
            write_calls(calls, sys.stdout)
        stream = sys.stdout if dest else sys.stderr
        print_tables(calls, steps, coverage, stream)
        print(file=stream)
        print_planning_table(episodes, stream)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
