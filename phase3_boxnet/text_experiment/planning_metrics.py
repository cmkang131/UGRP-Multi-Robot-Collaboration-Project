"""Planning-round counters shared by episode publication and the comparison tools."""
from collections import Counter, defaultdict
import json
from statistics import median

from LLM import is_transport_attempt, visible_reply_fields
from limits import (CALL_CEILING, CALL_LIMIT, CLIENT_LIMIT, COST_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, TOKEN_LIMIT,
                    UNUSABLE_REPLY)
from matched_protocol import REPAIR_INSTRUCTION
from plan_parse import OWN_FORMS


ITERATION_LIMIT = "failure over query time limit"
ENV_STEP_LIMIT = "failure over environment step limit"
MATCHED_ENV_CAP = "environment step ceiling"
MATCHED_ROUND_CAP = "planning round ceiling"
MATCHED_CALL_CAP = "episode call ceiling"
MATCHED_CEILINGS = (MATCHED_ENV_CAP, MATCHED_ROUND_CAP, MATCHED_CALL_CAP)
WRITER_CAUSES = {OUTPUT_LIMIT: "output limit", UNUSABLE_REPLY: "unusable replies after client retries",
                 "parse failure": "unusable replies after repairs", "invalid": "not-doable actions"}
BLOCK_COUNTS = ("robot_rounds_blocked_by_cause", "writer_calls_blocked_by_cause")
TOKEN_METERS = (("prompt_tokens", "prompt_tokens"), ("completion_tokens", "generated_tokens"))
IDLE_TOTALS = ("stalled_rounds", "rounds_with_blocked_writer",
               *(bucket + "_" + name for bucket in ("blocked", "executed", "other") for _, name in TOKEN_METERS))
CUTOFF_COUNTS = {
    "no cut-off": "rounds_no_cutoff",
    "first attempt cut off and recovered": "rounds_cutoff_recovered",
    "all attempts cut off": "rounds_all_attempts_cutoff",
    "unknown": "rounds_cutoff_unknown",
}
CUTOFF_CLASSES = ("empty", "partial", "unknown")
CUTOFF_SPLITS = tuple(prefix + kind for prefix in ("cutoff_attempts_", "rounds_all_attempts_cutoff_")
                      for kind in CUTOFF_CLASSES)
CUT_PREFIX_COUNTS = ("cutoff_attempts_partial_zero_steps", "cutoff_attempts_partial_salvaged",
                     "cut_prefix_robot_steps_kept", "cut_prefix_robot_steps_not_written")
ROUND_COUNTS = ("plans_proposed", "effective_steps", "empty_steps_skipped", "discarded_steps", "untried_steps_after_invalid")
DMAS_RETENTIONS = ("dmas_unparsable_overwrites_prevented", "dmas_empty_overwrites_prevented")
CUT_ROLES = ("leader", "final_dmas_speaker", "individual_robot", "repair_call", "dialogue_turn", "other")
COMPARISON_GROUP = ("model", "reasoning_setting", "framework", "horizon", "max_output_tokens", "size",
                    "condition", "speech", "tell", "history_method", "history_window", "cmas_history",
                    "state_position", "max_env_steps")


def round_cutoff(calls, optional_failures=()):
    """Classify exhausted required calls even when a different writer can still act."""
    recovered, unknown = False, not calls
    for call in calls:
        # Matched transport-only failures have no provider reply to classify as
        # cut-off.  They may sit between cut-off replies without changing the
        # output-limit classification of those reply-bearing attempts.
        flags = [a.get("cut_off") for a in call["attempts"]
                 if a["api_calls"] and (call.get("reply_attempt_count") is None or not is_transport_attempt(a))]
        if call.get("reply_attempt_count") == 0:
            # A matched transport-only logical call supplies no completion to
            # classify; it is a service terminal, not an unknown cut-off.
            continue
        if flags and all(f is True for f in flags) and call.get("failure") == OUTPUT_LIMIT:
            if call.get("number") in optional_failures:
                unknown = True
                continue
            return "all attempts cut off"
        if not flags or None in flags:
            unknown = True
        elif any(flags):
            if call["status"] == "ok" and (call.get("cut_answer_salvaged") or (flags[0] and flags[-1] is False)):
                recovered = True
            else:
                unknown = True
    if unknown:
        return "unknown"
    return "first attempt cut off and recovered" if recovered else "no cut-off"


def blocked_cause(batch, label):
    if label in (*MATCHED_CEILINGS, CALL_CEILING, CALL_LIMIT, COST_LIMIT, CLIENT_LIMIT, TOKEN_LIMIT):
        return "ceiling"
    if label in WRITER_CAUSES:
        return WRITER_CAUSES[label]
    if label == MODEL_SERVICE:
        return "model service"
    reason = batch.get("stop_reason")
    if "failed_speaker" in batch and label == "Syntactic Error":
        return WRITER_CAUSES["invalid" if reason == "invalid" else "parse failure"]
    checks = [c for c in batch.get("checks", ()) if c.get("own_dropped") or c.get("group_dropped")]
    if reason == "invalid" or any(c["status"] == "invalid" for c in checks):
        return WRITER_CAUSES["invalid"]
    if reason == "parse failure" or checks:
        return WRITER_CAUSES["parse failure"]
    if reason == "all empty":
        return "no actions proposed"
    return "unknown"


def metered_total(records, field):
    values = [r.get(field) for r in records]
    return None if None in values else sum(values)


def writer_block_event(framework, robots, required, status, calls):
    """Charge the blocked writer's initial call and repairs, including their physical retries."""
    last = calls[-1]
    reply = next((a for a in reversed(last["attempts"]) if not is_transport_attempt(a)), {})
    cutoff_class = reply.get("cutoff_reply_class")
    if cutoff_class is None and reply.get("cut_off") is True:
        cutoff_class = visible_reply_fields(reply.get("raw_output"), True)["cutoff_reply_class"]
    return dict(event="writer_blocked", planning_round=last["planning_round"], framework=framework,
                speaker=last["speaker"], robots=list(robots), required=required, cause=WRITER_CAUSES[status],
                end_label=last["failure"] or "Syntactic Error", call=last["number"],
                calls=[c["number"] for c in calls], attempts=sum(c["api_calls"] for c in calls),
                last_call_attempts=last["api_calls"], last_cutoff_class=cutoff_class,
                **{name: metered_total(calls, field) for field, name in TOKEN_METERS})


def fill_cutoff_splits(row, calls):
    """Use the published cut-call counts even when an archive lacks all or part of a trace."""
    counts = dict.fromkeys(CUTOFF_SPLITS, 0)
    by_number = {call["number"]: call for call in calls}
    optional = {e["call"] for b in row["round_log"] for e in b.get("writer_blocked", ()) if not e["required"]}
    last_by_round = {}
    for cut in row.get("cut_calls", ()):
        call = by_number.get(cut["call"], {})
        attempts = call.get("attempts", ())
        count, last = 0, "unknown"
        for index, attempt in enumerate(attempts):
            if not attempt.get("api_calls") or attempt.get("cut_off") is not True or is_transport_attempt(attempt):
                continue
            raw = attempt.get("raw_output")
            if raw is None and index == len(attempts) - 1:
                raw = call.get("response")
            last = attempt.get("cutoff_reply_class") or visible_reply_fields(raw, True)["cutoff_reply_class"]
            counts["cutoff_attempts_" + last] += 1
            count += 1
            if count == cut["attempts"]:
                break  # an interrupted episode may have since acquired more attempts
        if count < cut["attempts"]:
            counts["cutoff_attempts_unknown"] += cut["attempts"] - count
            last = "unknown"
        if cut["call"] not in optional and (cut.get("terminal") or call.get("failure") == OUTPUT_LIMIT):
            last_by_round[cut["planning_round"]] = last
    classified = sum(counts.values())
    counts["cutoff_attempts_unknown"] += max(0, row.get("truncated_attempts", classified) - classified)
    for batch in row["round_log"]:
        if batch["cutoff_class"] == "all attempts cut off":
            last = last_by_round.get(batch["planning_round"], "unknown")
            batch["all_cutoff_last_class"] = last
            counts["rounds_all_attempts_cutoff_" + last] += 1
    row.update(counts)


def matched_measurements(row, calls):
    by_round = defaultdict(list)
    for call in calls:
        by_round[call.get("planning_round")].append(call)
    log = row["round_log"]
    counts = dict.fromkeys(CUTOFF_COUNTS.values(), 0)
    first, cause, stage = None, None, None
    label = row["success_failure"]
    for batch in log:
        n = batch["planning_round"]
        round_calls = by_round[n]
        if row.get("framework") == "GROUP":
            batch["callers_per_round"] = row["callers_per_round"]
            batch["callers_reached"] = len({c["speaker"] for c in round_calls if c["role"] != "relay"
                                            and (c["api_calls"] or c.get("cache_hit"))})
        optional = {check["call"] for check in batch["checks"] if check.get("optional_writer_dropped")}
        blocks = batch.get("writer_blocked", ())
        optional.update(e["call"] for e in blocks if not e["required"])
        batch["cutoff_class"] = round_cutoff(round_calls, optional)
        counts[CUTOFF_COUNTS[batch["cutoff_class"]]] += 1
        terminal = label if batch is log[-1] else None
        if first is None and blocks:
            first, cause, stage = n, blocks[0]["cause"], "before a joint action"
        elif first is None and batch.get("stalled"):
            first, cause, stage = n, batch["stall_cause"], "before a joint action"
        elif first is None and not batch["effective_steps"]:
            # A round may produce no usable action and still be followed by a replan.
            # If the round's own result was known before reaching the round cap, retain it.
            observed = None if terminal == MATCHED_ROUND_CAP and batch["checks"] else terminal
            first, cause, stage = n, blocked_cause(batch, observed), "before a joint action"
        elif first is None and terminal in MATCHED_CEILINGS:
            first, cause, stage = n, "ceiling", "after executed actions"
    if not log and label in MATCHED_CEILINGS:
        first, cause, stage = 0, "ceiling", "before the first planning round"
    row.update(**counts, first_blocked_round=first, first_blocked_cause=cause, first_blocked_stage=stage,
               repair_calls=sum(b["repair_calls"] for b in log),
               robots_dropped=sum(len(b["dropped_robots"]) for b in log))
    fill_cutoff_splits(row, calls)
    if row.get("cut_answer") == "prefix":
        row.update(cut_prefix_counts(row))
    if row.get("failed_writer") == "idle":
        idle_measurements(row, calls)


def idle_measurements(row, calls):
    """Credit a producing call once if any action from its list reached the executor."""
    robots, writers = Counter(), Counter()
    blocked, executed = set(), set()
    executing = defaultdict(set)
    for step in row["iterations"]:
        if step.get("applied_actions"):
            executing[step["planning_round"]].update(step.get("action_calls", {}).values())
    for batch in row["round_log"]:
        for event in batch["writer_blocked"]:
            robots[event["cause"]] += len(event["robots"])
            writers[event["cause"]] += 1
            blocked.update(event["calls"])
        sources = executing[batch["planning_round"]]
        if batch["effective_steps"] and not sources:
            sources.add(batch["final_call"])  # sole joint writer, including a full-board GROUP
        batch["executed_writer_calls"] = sorted(sources)
        executed.update(sources)
    row.update(robot_rounds_blocked_by_cause=dict(robots), writer_calls_blocked_by_cause=dict(writers),
               stalled_rounds=sum(b["stalled"] is True for b in row["round_log"]),
               rounds_with_blocked_writer=sum(bool(b["writer_blocked"]) for b in row["round_log"]),
               tokens_per_delivered_box=per_delivered_box(row["tokens"], row["correct_deliveries"]))
    buckets = defaultdict(list)
    for call in calls:
        number = call["number"]
        if number in blocked:
            bucket = "blocked"
        elif number in executed:
            bucket = "executed"
        else:
            bucket = "other"
        buckets[bucket].append(call)
    for bucket in ("blocked", "executed", "other"):
        for field, name in TOKEN_METERS:
            row[bucket + "_" + name] = metered_total(buckets[bucket], field)


def per_delivered_box(tokens, delivered):
    return tokens / delivered if tokens is not None and delivered else None


def cut_prefix_counts(row):
    events = [e for batch in row["round_log"] for e in batch["writer_cut_prefix"]]
    return dict(cutoff_attempts_partial_zero_steps=row["cutoff_attempts_partial"] - len(events),
                cutoff_attempts_partial_salvaged=len(events),
                cut_prefix_robot_steps_kept=sum(e["salvaged_steps"] * len(e["robots"]) for e in events),
                cut_prefix_robot_steps_not_written=sum((e["horizon"] - e["salvaged_steps"]) * len(e["robots"])
                                                       for e in events))


def prefix_cell_metrics(rows):
    fields = ("correct_deliveries", "box_count", "cutoff_attempts_empty", *CUT_PREFIX_COUNTS, "cutoff_attempts_unknown")
    return {field: metered_total(rows, field) for field in fields}


def matched_cell_metrics(rows, *, include_prefix=False):
    causes = Counter(row.get("first_blocked_cause") or "none" for row in rows)
    strict = sum(r["finished"] and r["strict_success"] for r in rows)
    if include_prefix or any(r.get("cut_answer") == "prefix" for r in rows):
        metrics = prefix_cell_metrics(rows)
    else:
        metrics = {k: metered_total(rows, k) for k in ("correct_deliveries", "box_count")}
    metrics.update({k: sum(r[k] for r in rows) for k in CUTOFF_COUNTS.values()})
    metrics.update({k: sum(r[k] for r in rows) if all(k in r for r in rows) else None for k in CUTOFF_SPLITS})
    metrics.update(strict_completions=strict, first_blocked_causes=dict(sorted(causes.items())))
    for ending in MATCHED_CEILINGS:
        metrics["ended_on_" + ending.replace(" ", "_")] = sum(r["success_failure"] == ending for r in rows)
    for field, name in (("api_calls", "calls"), ("prompt_tokens", "prompt_tokens"),
                        ("completion_tokens", "generated_tokens")):
        values = [row[field] for row in rows]
        total = None if None in values else sum(values)
        metrics["total_" + name] = total
        metrics[name + "_per_strict_completion"] = ("no completion" if not strict else
                                                    None if total is None else total / strict)
    prompt, generated = metrics["total_prompt_tokens"], metrics["total_generated_tokens"]
    metrics["total_tokens"] = prompt + generated if None not in (prompt, generated) else None
    metrics["tokens_per_delivered_box"] = per_delivered_box(metrics["total_tokens"], metrics["correct_deliveries"])
    for field in BLOCK_COUNTS:
        if all(field in row for row in rows):
            totals = Counter()
            for row in rows:
                totals.update(row[field])
            metrics[field] = dict(totals)
        else:
            metrics[field] = None
    metrics.update({k: metered_total(rows, k) for k in IDLE_TOTALS})
    return metrics


def repair_feedback(call):
    messages = call.get("messages", ())
    if len(messages) < 3 or messages[-1]["role"] != "user" or messages[-2]["role"] != "assistant":
        return ""
    feedback = messages[-1]["content"]
    if feedback.startswith(("The reply could not be read in the requested JSON format.",
                            "First-step actions outside the current doable lists: ")):
        return feedback
    if feedback.startswith("Joint plan format error. "):
        return feedback
    # V17 matched diagnostics name the precise fault, while this suffix is the
    # stable repair marker after the rejected assistant turn.
    if feedback.rstrip().endswith(REPAIR_INSTRUCTION):
        return feedback
    if call.get("role") == "own" and feedback.startswith(("Your reply could not be read as a JSON list of ",
                                                          "Your first entry ")):
        return feedback
    if feedback.startswith("Your assigned task for ") and "not in the doable action list" in feedback:
        return feedback
    if feedback.startswith("Your assigned plan is ") and "not in the correct json format" in feedback.lower():
        return feedback
    return ""


def cutoff_records(row, calls):
    """Count physical cut attempts, including those recovered by the same logical call."""
    final = {b["planning_round"]: b.get("final_submission_call", b.get("final_call"))
             for b in row.get("round_log", ())}
    if row["framework"] == "DMAS" and row.get("horizon", 1) == 1:
        for call in calls:
            if call["role"] == "dialogue" and not repair_feedback(call) and "EXECUTE" in (call.get("response") or ""):
                final[call["step"]] = call["number"]
    cuts = []
    terminal_call = None
    if calls and row["success_failure"] == OUTPUT_LIMIT:
        terminal_call = calls[-1]["number"]
        if row.get("failed_writer") == "idle" and row["round_log"] and row["round_log"][-1]["stalled"]:
            terminal_call = row["round_log"][-1]["stall_call"]
    for call in calls:
        count = sum(a["api_calls"] for a in call["attempts"]
                    if (a.get("cut_off") is True if row.get("protocol") == "matched" else a["kind"] == "truncated"))
        if not count:
            continue
        number, role = call["number"], call["role"]
        batch = call.get("planning_round", call["step"])
        terminal = number == terminal_call
        if repair_feedback(call):
            who = "repair_call"
        elif role == "central":
            who = "leader"
        elif role == "own":
            who = "individual_robot"
        elif role == "group":
            who = "group_leader"
        elif role == "dialogue":
            who = ("final_dmas_speaker" if row["framework"] == "DMAS" and (number == final.get(batch) or terminal)
                   else "dialogue_turn")
        else:
            who = "other"
        cuts.append(dict(call=number, planning_round=batch, speaker=call.get("speaker"),
                         role=who, attempts=count, terminal=terminal))
    return cuts


def fill_planning_counts(row):
    """Recover comparable counters for archived traces, including empty steps once charged."""
    by_round = defaultdict(list)
    for it in row.get("iterations", ()):
        by_round[it.get("planning_round", it["step"])].append(it)
    if "round_log" not in row:
        row["round_log"] = [dict(planning_round=n, plans_proposed=sum(it["executed"] for it in steps))
                            for n, steps in by_round.items()]
    for batch in row["round_log"]:
        if "effective_steps" not in batch:
            batch["effective_steps"] = sum(bool(it.get("applied_actions")) for it in by_round[batch["planning_round"]]
                                           if it["executed"])
        batch.setdefault("empty_steps_skipped", 0)
        invalid = batch.get("invalid_position")
        batch.setdefault("discarded_steps", max(0, batch["plans_proposed"] - invalid + 1) if invalid else 0)
        batch["untried_steps_after_invalid"] = max(0, batch["discarded_steps"] - 1)
    row.update({k: sum(b[k] for b in row["round_log"]) for k in ROUND_COUNTS})


def ending_counts(row):
    done = bool(row["finished"] and row["strict_success"])
    label = row["success_failure"] if row["finished"] and not done else None
    return dict(completed=int(done), ended_by_output_limit=int(label == OUTPUT_LIMIT),
                ended_by_syntactic_error=int(label == "Syntactic Error"),
                ended_by_iteration_limit=int(label == ITERATION_LIMIT),
                ended_by_env_step_limit=int(label == ENV_STEP_LIMIT))


def recorded_rule_counts(rows):
    return tuple(f for f in (*DMAS_RETENTIONS, "own_prefixes_kept", "own_unreachable_skipped")
                 if any(f in row for row in rows))


def comparison_metrics(rows, *, include_own=False, include_group=False, rule_counts=None):
    endings, cuts, terminal_cuts = Counter(), Counter(), Counter()
    effective = []
    for row in rows:
        endings.update(ending_counts(row))
        for cut in row.get("cut_calls", ()):
            cuts[cut["role"]] += cut["attempts"]
            if cut["terminal"]:
                terminal_cuts[cut["role"]] += 1
        effective.extend(b["effective_steps"] for b in row.get("round_log", ()))
    calls = sum(r["api_calls"] for r in rows)
    counts = {k: sum(r.get(k, 0) for r in rows) for k in ROUND_COUNTS}
    if rule_counts is None:
        rule_counts = recorded_rule_counts(rows)
    rules = {k: sum(r[k] for r in rows) if rows and all(k in r for r in rows) else None for k in rule_counts}
    own = {}
    if include_own or any(r.get("framework") == "OWN" for r in rows):
        # A group of archived or non-OWN episodes has no recorded OWN counters.
        measured = bool(rows) and all("own_reply_form_counts" in r for r in rows)
        for form in OWN_FORMS:
            own["own_reply_form_" + form] = sum(r["own_reply_form_counts"].get(form, 0) for r in rows) if measured else None
        own["own_robots_dropped"] = sum(r["own_robots_dropped"] for r in rows) if measured else None
    roles = (*CUT_ROLES, "group_leader") if include_group or any(r.get("framework") == "GROUP" for r in rows) else CUT_ROLES
    return dict(episodes=len(rows), completed=endings["completed"], ended_by_output_limit=endings["ended_by_output_limit"],
                ended_by_syntactic_error=endings["ended_by_syntactic_error"],
                ended_by_iteration_limit=endings["ended_by_iteration_limit"],
                ended_by_env_step_limit=endings["ended_by_env_step_limit"], **counts,
                planning_rounds=len(effective), model_calls=calls,
                median_effective_steps_per_planning_round=median(effective) if effective else None,
                effective_steps_per_model_call=sum(effective) / calls if calls else None,
                **{"cut_" + role: cuts[role] for role in roles},
                **{"output_limit_" + role: terminal_cuts[role] for role in roles}, **own, **rules)


def print_planning_table(rows, stream):
    groups = defaultdict(list)
    include_own = any(row["framework"] == "OWN" for row in rows)
    include_group = any(row["framework"] == "GROUP" for row in rows)
    rule_counts = recorded_rule_counts(rows)
    fields = COMPARISON_GROUP
    if include_group:
        fields += ("group_size",)
    if any(row.get("map_set", "legacy") != "legacy" or row.get("protocol") == "matched" for row in rows):
        fields += ("map_set", "protocol", "max_planning_rounds", "episode_call_ceiling")
    if any(row.get("protocol") == "matched" for row in rows):
        fields += ("plan_note", "failed_writer")
    if any(row.get("failed_writer") == "idle" for row in rows):
        fields += ("max_stalled_rounds",)
    prefix = any(row.get("cut_answer") == "prefix" for row in rows)
    if prefix:
        fields += ("cut_answer",)
    defaults = {"map_set": "legacy", "protocol": "legacy", "cut_answer": "discard"}
    for row in rows:
        key = tuple(row.get(k, defaults.get(k)) for k in fields)
        groups[key].append(row)
    print("Planning outcomes and physical calls", file=stream)
    options = dict(include_own=include_own, include_group=include_group, rule_counts=rule_counts)
    first_metrics = prefix_cell_metrics([]) if prefix else ()
    print(" | ".join((*fields, *first_metrics, *comparison_metrics([], **options))), file=stream)
    for key in sorted(groups, key=lambda k: tuple(map(str, k))):
        stats = prefix_cell_metrics(groups[key]) if prefix else {}
        stats.update(comparison_metrics(groups[key], **options))
        print(" | ".join([*("-" if v is None else str(v) for v in key),
                          *("NA" if v is None else str(v) for v in stats.values())]), file=stream)


def print_matched_table(rows, stream):
    groups = defaultdict(list)
    fields = (*COMPARISON_GROUP, "map_set", "max_planning_rounds", "episode_call_ceiling", "plan_note", "failed_writer")
    idle = any(row.get("failed_writer") == "idle" for row in rows)
    if idle:
        fields += ("max_stalled_rounds",)
    if any(row["framework"] == "GROUP" for row in rows):
        fields += ("group_size",)
    prefix = any(row.get("cut_answer") == "prefix" for row in rows)
    if prefix:
        fields += ("cut_answer",)
    for row in rows:
        if row.get("protocol") == "matched":
            groups[tuple(row.get(k, "discard" if k == "cut_answer" else None) for k in fields)].append(row)
    if not groups:
        return
    title = ("Matched protocol, delivered boxes and writer failures" if idle
             else "Matched protocol, all physical attempts per strict completion")
    print(title, file=stream)
    print(" | ".join((*fields, *matched_cell_metrics([], include_prefix=prefix))), file=stream)
    for key in sorted(groups, key=lambda k: tuple(map(str, k))):
        values = matched_cell_metrics(groups[key], include_prefix=prefix)
        cells = (*key, *(json.dumps(v, sort_keys=True) if isinstance(v, dict) else v for v in values.values()))
        print(" | ".join("NA" if v is None else str(v) for v in cells), file=stream)
