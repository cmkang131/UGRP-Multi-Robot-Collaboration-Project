"""Classify published Chen BoxNet1 episodes from v6 onward, without writing to any input.

Assign one cause, in order:
* completed: strict_success, including a strict completion on the last allowed step.
* output_limit: the terminal label is "failure output limit", or every attempt of the
  last non-relay planning call was truncated and supplied no salvaged plan.
* context: a syntactic failure, query/episode-call ceiling, or a non-technical
  non-strict ending with boxes left AND at least one observed pattern:
  (1) an author invalid-action or JSON-format repair in the final planning iteration;
  (2) an action singled out by that feedback proposed again on the unchanged board,
      or shown infeasible again by feedback or the authors' checker on a later board;
  (3) four consecutive executed steps shuttling a box across the same edge (period
      two, including a period-one joint plan that swaps boxes every step). Use applied
      square moves and the private box ID when recorded, otherwise the box type.
* wrong_delivery: finished, all boxes gone, a wrong delivery, no terminal technical
  failure or context pattern. Includes changed orders and drop-off misuse.
* other: all remaining outcomes, including service errors and unsupported causal claims.

Patterns are trace evidence, not a causal estimate of the effect of input length.
Only the last user turn can request a repair. Reviewer objections, dialogue and
transport retries are distinct. The first submitted joint plan is the first returned
central proposal or local EXECUTE (or checker reply) in the iteration. An unparseable
submission or one rejected by the checker is invalid. Reapply the same check to the
saved pre-step state, including when a ceiling prevented a repair. With no saved
state, only recorded rejections and parse errors establish invalidity. All started planning iterations
enter the share, including those with no submission. A recovered cutoff counts in the
call rate. Plan-making token statistics cover central, local dialogue and repair calls;
review-only and relay calls are excluded. Input length is measured once per logical
call from the first metered attempt. Completion and reasoning sum the call's attempts.
Unknown measurements stay blank in CSV and NA in tables. Early = steps 1–4, late = 9+.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict, deque
from fractions import Fraction
from pathlib import Path
from statistics import mean

from LLM import was_truncated
from analysis_runs import recorded_calls
from env1_create import plan_feedback
from episode import HISTORY_DEFAULTS, history_settings
from limits import CALL_CEILING, OUTPUT_LIMIT
from plan_parse import PlanParser, first_object
from planning_metrics import ending_counts, repair_feedback
from storage import atomic_file, local_path, read_json
from summarize import TECHNICAL, read_episode_rows, run_settings


CAUSES = ("completed", "output_limit", "context", "wrong_delivery", "other")
PATTERNS = ("last_iteration_repair", "repeated_invalid_action", "move_cycle")
HISTORY = tuple(HISTORY_DEFAULTS)
GROUP = ("model", "reasoning_setting", "max_output_tokens", *HISTORY, "size", "framework", "condition", "horizon",
         "state_position", "max_env_steps", "map_set")
AHEAD = ("model", "reasoning_setting", "size", "max_output_tokens", *HISTORY, "condition", "horizon",
         "state_position", "max_env_steps", "map_set")
COORD = r"\d+(?:\.\d+)?"
BAD_AGENT = re.compile(rf"assigned task for ({COORD})_({COORD}) is not in the doable action list", re.I)
AGENT = re.compile(rf"Agent\[\s*({COORD}),\s*({COORD})\s*\]", re.I)
METERS = ("prompt_tokens", "completion_tokens", "reasoning_tokens")
METADATA = ("run", "episode_id", "code_version", *GROUP, "env_seed", "speech", "tell", "dropoff",
            "dropoff_rule", "finished", "success_failure", "boxes_left", "wrong_deliveries")
ENDING_FIELDS = ("ended_by_output_limit", "ended_by_syntactic_error", "ended_by_iteration_limit",
                 "ended_by_env_step_limit", "iteration_limit_with_move_cycle", "iteration_limit_without_move_cycle")
EPISODE_FIELDS = (*METADATA, "cause", *PATTERNS, *ENDING_FIELDS, "steps_executed", "planning_rounds", "all_calls", "all_cutoff_attempts",
                  "all_cutoff_calls", "planning_calls", "cutoff_attempts", "cutoff_calls", "cutoff_call_share",
                  "repair_calls", "repair_iterations", "planning_iterations",
                  "iterations_with_proposal", "proposals_with_saved_state", "first_plan_invalid_iterations", "first_plan_invalid_share",
                  "first_invalid_call", "prompt_tokens_at_first_invalid", "plan_making_calls", "mean_prompt_tokens",
                  "max_prompt_tokens", "mean_completion_tokens", "mean_reasoning_tokens",
                  "early_iterations", "early_invalid", "late_iterations", "late_invalid", "plan_call_tokens")


def ratio(n, d):
    return n / d if d else None


def actions(reply):
    plan = first_object(reply)
    result = set()
    for name, move in json.loads(plan or "{}").items():
        agent = AGENT.fullmatch(name.strip())
        if agent and isinstance(move, str):
            result.add((tuple(map(float, agent.groups())), re.sub(r"\s+", "", move)))
    return result


def rejected_actions(proposal, feedback):
    named = {tuple(map(float, m)) for m in BAD_AGENT.findall(feedback)}
    # JSON-format feedback names no offending action. Valid co-actions must not count.
    return {action for action in actions(proposal) if action[0] in named}


def move_cycle(iterations):
    recent = deque(maxlen=4)
    last = 0
    for it in iterations:
        if it["step"] != last + 1 or not it["executed"]:
            recent.clear()
        last = it["step"]
        if not it["executed"]:
            continue
        moves = set()
        ids = it.get("applied_box_ids")
        for i, (origin, item, dest) in enumerate(it.get("applied_actions", ())):
            if isinstance(dest, (list, tuple)) and item.startswith("box_") and tuple(origin) != tuple(dest):
                moves.add((item, ids[i] if ids is not None else None, tuple(origin), tuple(dest)))
        recent.append(moves)
        if len(recent) == 4:
            a, b, c, d = recent
            for item, identity, start, end in a & c:
                reverse = (item, identity, end, start)
                if reverse in b and reverse in d:
                    return True
    return False


def call_tokens(call):
    attempts = call["attempts"]
    # Input is identical across retries. The trace's top-level prompt_tokens adds them.
    prompt = next((a["prompt_tokens"] for a in attempts if a.get("prompt_tokens") is not None), None)
    return dict(number=call["number"], step=call["step"], prompt_tokens=prompt,
                completion_tokens=call.get("completion_tokens"), reasoning_tokens=call.get("reasoning_tokens"))


def invalid_proposals(calls, parser, states, returned_only):
    """Follow each checker's reply chain and its immediate feedback, in call order."""
    first = {}
    invalid, repairs, rejected_before = set(), [], set()
    repeated = False
    checked = 0
    previous = None
    for call in calls:
        step, number = call["step"], call["number"]
        if previous is None or previous["step"] != step:
            rejected_here = set()
            previous = None
        feedback = repair_feedback(call)
        if feedback:
            repairs.append(step)
            if previous is not None:
                invalid.add(previous["number"])
            bad = rejected_actions(call["messages"][-2]["content"], feedback)
            repeated |= bool(bad & rejected_before)
            rejected_here.update(bad)
            rejected_before.update(bad)

        reply = call.get("response")
        if isinstance(reply, str) and (feedback or call["role"] == "central" or
                                      (call["role"] == "dialogue" and "EXECUTE" in reply)):
            first.setdefault(step, number)
            selected = parser.for_check(reply) if feedback else parser.extract(reply)
            if selected is not None and call["role"] == "central" and len(call["messages"]) > 2:
                # The HMAS-2 revision site passes the entire reply to the checker.
                selected = parser.for_check(reply)
            try:
                if step in states:
                    checked += 1
                    reason = plan_feedback(states[step], selected, reply, returned_only)
                    if reason:
                        invalid.add(number)
                        if rejected_before:
                            repeated |= bool(rejected_actions(reply, reason) & rejected_before)
                elif selected is None or not isinstance(json.loads(selected), dict):
                    invalid.add(number)
            except (ValueError, RecursionError, re.error):
                invalid.add(number)
            if rejected_here:
                repeated |= bool(actions(reply) & rejected_here)
        previous = call
    return first, invalid, repairs, repeated, checked


def list_proposals(rounds, planning, states, *, own):
    """A first OWN joint proposal is invalid if any initial contributor was rejected."""
    first, invalid, first_invalid_steps = {}, set(), set()
    checked, repeated, prior = 0, False, set()
    for batch in rounds:
        step = batch["planning_round"]
        rejections = []
        for check in batch["checks"]:
            number = check["call"]
            first.setdefault(step, number)
            checked += int(batch["first_step"] in states)
            if check["status"] != "valid":
                invalid.add(number)
                if not check["repair"] and (own or first[step] == number):
                    first_invalid_steps.add(step)
                rejections.append(check["rejected_actions"])
        rejections.append(batch.get("rejected_actions", {}))
        invalid.update(batch.get("rejected_calls", {}).values())
        for actions in rejections:
            keys = {(agent, json.dumps(move, sort_keys=True)) for agent, move in actions.items()}
            repeated |= bool(keys & prior)
            prior.update(keys)
    repairs = [c.get("planning_round", c["step"]) for c in planning if repair_feedback(c)]
    return first, invalid, first_invalid_steps, repairs, repeated, checked


def classify(row, calls, states=None):
    planning = [c for c in calls if c["role"] != "relay"]
    cuts = [[was_truncated(a) for a in c["attempts"]] for c in planning]
    terminal_cutoff = bool(cuts and cuts[-1]) and all(cuts[-1]) and not planning[-1].get("cut_answer_salvaged")
    iterations = row["iterations"]
    if row.get("env") == "boxnet2" or row.get("horizon", 1) > 1 or row.get("framework") in ("OWN", "GROUP"):
        rounds = row["round_log"]
        steps = [b["planning_round"] for b in rounds]
        env_step = {b["planning_round"]: b["first_step"] for b in rounds}
        first, invalid, first_invalid_steps, repairs, repeated, checked = list_proposals(
            rounds, planning, states or {}, own=row.get("framework") in ("OWN", "GROUP"))
    else:
        steps = [it["step"] for it in iterations]
        env_step = {s: s for s in steps}
        first, invalid, repairs, repeated, checked = invalid_proposals(
            planning, PlanParser(row["parse"]), states or {}, row.get("condition") == "e2")
        first_invalid_steps = {s for s, number in first.items() if number in invalid}
    physical = (it for it in iterations if it["executed"]) if row.get("horizon", 1) > 1 else iterations
    patterns = dict(last_iteration_repair=bool(steps and steps[-1] in repairs),
                    repeated_invalid_action=repeated, move_cycle=move_cycle(physical))
    endings = ending_counts(row)
    limited = endings["ended_by_iteration_limit"]
    endings.update(iteration_limit_with_move_cycle=int(limited and patterns["move_cycle"]),
                   iteration_limit_without_move_cycle=int(limited and not patterns["move_cycle"]))
    label = row["success_failure"]
    context_ending = (label in ("Syntactic Error", "failure over query time limit", CALL_CEILING)
                      or (row["boxes_left"] > 0 and label not in TECHNICAL))
    if row["strict_success"]:
        cause = "completed"
    elif label == OUTPUT_LIMIT or terminal_cutoff:
        cause = "output_limit"
    elif context_ending and any(patterns.values()):
        cause = "context"
    elif (row["finished"] and row["boxes_left"] == 0 and row["wrong_deliveries"] > 0
          and label in ("success", "failure over query time limit") and not any(patterns.values())):
        cause = "wrong_delivery"
    else:
        cause = "other"

    samples = [call_tokens(c) for c in planning if c["role"] != "review" or repair_feedback(c)]
    measures = {field: [c[field] for c in samples if c[field] is not None] for field in METERS}
    first_invalid = min(invalid, default=None)
    prompt_at_invalid = next((c["prompt_tokens"] for c in samples if c["number"] == first_invalid), None)
    cutoff_calls = sum(any(flags) for flags in cuts)
    all_cuts = [sum(was_truncated(a) for a in c["attempts"]) for c in calls]
    return dict(cause=cause, **patterns, **endings, steps_executed=sum(it["executed"] for it in iterations), planning_rounds=len(steps),
                all_calls=len(calls), all_cutoff_attempts=sum(all_cuts), all_cutoff_calls=sum(n > 0 for n in all_cuts),
                planning_calls=len(planning), cutoff_attempts=sum(map(sum, cuts)),
                cutoff_calls=cutoff_calls, cutoff_call_share=ratio(cutoff_calls, len(planning)),
                repair_calls=len(repairs), repair_iterations=len(set(repairs)), planning_iterations=len(steps),
                iterations_with_proposal=len(first), proposals_with_saved_state=checked,
                first_plan_invalid_iterations=len(first_invalid_steps),
                first_plan_invalid_share=ratio(len(first_invalid_steps), len(steps)),
                first_invalid_call=first_invalid, prompt_tokens_at_first_invalid=prompt_at_invalid, plan_making_calls=len(samples),
                **{"mean_" + k: mean(v) if v else None for k, v in measures.items()},
                max_prompt_tokens=max(measures["prompt_tokens"], default=None), plan_call_tokens=samples,
                early_iterations=sum(1 <= env_step[s] <= 4 for s in steps), late_iterations=sum(env_step[s] >= 9 for s in steps),
                early_invalid=sum(1 <= env_step[s] <= 4 for s in first_invalid_steps),
                late_invalid=sum(env_step[s] >= 9 for s in first_invalid_steps))


def read_runs(outs):
    records, coverage = [], []
    for out in outs:
        config = run_settings(out)
        history = history_settings(config)
        rows = read_episode_rows(out)
        for row in rows:
            row.setdefault("map_set", "legacy")
            data = {k: row.get(k) for k in METADATA}
            if row["framework"] == "GROUP":
                data["group_size"] = row["group_size"]
            data.update(run=str(out), **history)
            data["max_env_steps"] = str(row["max_env_steps"]) if row["max_env_steps"] is not None else "default"
            states = {}
            for it in row["iterations"]:
                step = it["step"]
                path = out / "episodes" / row["episode_id"] / "pg_state" / f"pg_state{step}.json"
                if path.is_file():
                    states[step] = read_json(path)
            data.update(classify(row, recorded_calls(out, row), states))
            records.append(data)
        manifest = out / "assignments.json"
        assigned = len(read_json(manifest)) if manifest.is_file() else None
        coverage.append((out, assigned, len(rows), sum(not r["finished"] for r in rows)))
    return records, coverage


def grouped(rows, keys):
    result = defaultdict(list)
    for row in rows:
        result[tuple(row.get(k) if k == "group_size" else row[k] for k in keys)].append(row)
    return result


def share(n, d):
    return f"{n / d:.2%} ({n}/{d})" if d else "NA (0/0)"


def print_row(stream, fields):
    print(" | ".join(map(str, fields)), file=stream)


def print_tables(rows, coverage, stream):
    group_fields = GROUP if any(r.get("map_set", "legacy") != "legacy" for r in rows) else GROUP[:-1]
    if any("group_size" in row for row in rows):
        group_fields += ("group_size",)
    for out, assigned, published, interrupted in coverage:
        print(f"{out}: assigned {assigned if assigned is not None else 'NA'}, published {published}, "
              f"interrupted {interrupted}", file=stream)
    print("\nfailure causes", file=stream)
    print_row(stream, (*group_fields, "episodes", *CAUSES[:3], *PATTERNS, *CAUSES[3:], "cutoff_calls_share",
                       "all_cutoff_calls_share", "first_plan_invalid_early", "first_plan_invalid_late", "mean_prompt_early", "mean_prompt_late",
                       "completed_episodes", *ENDING_FIELDS))
    for key, group in sorted(grouped(rows, group_fields).items()):
        n = len(group)
        causes = Counter(r["cause"] for r in group)
        counts = {cause: share(causes[cause], n) for cause in CAUSES}
        patterns = [share(sum(r["cause"] == "context" and r[p] for r in group), n) for p in PATTERNS]
        def total(field):
            return sum(r[field] for r in group)
        early, late = [], []
        for r in group:
            for c in r["plan_call_tokens"]:
                if c["prompt_tokens"] is not None:
                    if 1 <= c["step"] <= 4:
                        early.append(c["prompt_tokens"])
                    elif c["step"] >= 9:
                        late.append(c["prompt_tokens"])
        print_row(stream, (*key, n, counts["completed"], counts["output_limit"], counts["context"], *patterns,
                           counts["wrong_delivery"], counts["other"], share(total("cutoff_calls"), total("planning_calls")),
                           share(total("all_cutoff_calls"), total("all_calls")),
                           share(total("early_invalid"), total("early_iterations")),
                           share(total("late_invalid"), total("late_iterations")),
                           *(f"{mean(v):.2f}" if v else "NA" for v in (early, late)), total("completed"),
                           *(total(f) for f in ENDING_FIELDS)))

    if any(r["framework"] == "DMAS" for r in rows) or not any(r["framework"] == "OWN" for r in rows):
        print_comparison(rows, "DMAS", "who is ahead", stream)
    if any(r["framework"] == "OWN" for r in rows):
        print_comparison(rows, "OWN", "who is ahead (CMAS and OWN)", stream)


def print_comparison(rows, other, title, stream):
    ahead_fields = AHEAD if any(r.get("map_set", "legacy") != "legacy" for r in rows) else AHEAD[:-1]
    print("\n" + title, file=stream)
    print_row(stream, (*ahead_fields, "CMAS_completed", other + "_completed", other + "_cmas_history", "ahead"))
    cells = grouped([r for r in rows if r["framework"] in ("CMAS", other)], ahead_fields)
    for key, group in sorted(cells.items()):
        arms = grouped(group, ("framework",))
        cmas, peers = arms.get(("CMAS",), []), arms.get((other,), [])
        flag_pos = ahead_fields.index("cmas_history")
        ref = key[flag_pos]
        if cmas and not peers:
            # The switch only affects CMAS. Label the independently observed comparison arm.
            ref = "off" if ref == "on" else "on"
            sibling = (*key[:flag_pos], ref, *key[flag_pos + 1:])
            peers = [r for r in cells.get(sibling, []) if r["framework"] == other]
        a, b = (sum(r["cause"] == "completed" for r in arm) for arm in (cmas, peers))
        winner = "NA"
        if cmas and peers:
            x, y = Fraction(a, len(cmas)), Fraction(b, len(peers))
            winner = "CMAS" if x > y else other if y > x else "tie"
        print_row(stream, (*key, share(a, len(cmas)), share(b, len(peers)), ref if peers else "NA", winner))


def write_episodes(rows, stream):
    fields = EPISODE_FIELDS + (("group_size",) if any("group_size" in r for r in rows) else ())
    writer = csv.DictWriter(stream, fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row, plan_call_tokens=json.dumps(row["plan_call_tokens"], separators=(",", ":"))))


def main():
    parser = argparse.ArgumentParser(description="Classify published BoxNet1 episodes and compare CMAS with DMAS.")
    parser.add_argument("rundirs", nargs="+", type=Path)
    parser.add_argument("--episodes-csv", "--csv", metavar="PATH", default="-",
                        help="write episode CSV outside the inputs (default stdout, tables on stderr)")
    args = parser.parse_args()
    try:
        outs = [out.resolve() for out in args.rundirs]
        if len(set(outs)) != len(outs):
            raise ValueError("A run directory was supplied twice")
        path = None if args.episodes_csv == "-" else local_path(args.episodes_csv)
        if path and any(path.is_relative_to(out) for out in outs):
            raise ValueError("The episode CSV must be outside all input run directories")
        rows, coverage = read_runs(outs)
        if path:
            with atomic_file(path) as stream:
                write_episodes(rows, stream)
        else:
            write_episodes(rows, sys.stdout)
        print_tables(rows, coverage, sys.stdout if path else sys.stderr)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
