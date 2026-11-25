"""Rebuild episode CSVs and compare recorded episodes from compatible runs."""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from statistics import mean

from LLM import validate_reasoning
from board_sizes import size_filter, validate_board
from episode import DROPOFF_RULES, HISTORY_DEFAULTS, attach_relay_measurements, delivery_outcomes, history_settings
from horizon import validate_horizon
from limits import CALL_CEILING, CALL_LIMIT, CLIENT_LIMIT, COST_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, TOKEN_LIMIT, UNUSABLE_REPLY
from map_events import DROPOFF_MODES, E2_EVENT_FILE_VERSION, stratified_set
from map_sets import parse_map_set
from matched_protocol import group_partition, validate_writer_options
from planning_metrics import (BLOCK_COUNTS, CUTOFF_COUNTS, CUTOFF_SPLITS, CUT_PREFIX_COUNTS, DMAS_RETENTIONS, IDLE_TOTALS,
                              ROUND_COUNTS, comparison_metrics, cut_prefix_counts, cutoff_records,
                              fill_cutoff_splits, fill_planning_counts, prefix_cell_metrics, print_matched_table,
                              print_planning_table, recorded_rule_counts)
from relay import SPEECH_RULES, check_relay_options, relay_cell
from storage import atomic_file, digest, local_path, locked, read_json, version_from_hashes

COLUMNS = (
    "episode_id code_version event_file_version max_output_tokens dropoff dropoff_rule size framework condition tell parse env_seed env_sha256 event_sha256 "
    "model reasoning_setting providers fake_script usage_source finished success_failure detail success strict_success change_respected "
    "steps authors_env_action_times api_calls retried_calls truncated_attempts prompt_tokens completion_tokens reasoning_tokens "
    "known_prompt_tokens known_completion_tokens known_reasoning_tokens "
    "tokens cost_usd known_reported_cost_usd guard_cost_usd wrong_deliveries correct_deliveries "
    "dropoff_misuse dropoff_misuse_before dropoff_misuse_after "
    "boxes_left L M leader_is_member A D A2 D2 S scheduled_event_step event_step event_fired event_nothing_to_change "
    "event_not_fired box_A_left_at_event first_plan_after_event_wrong first_plan_after_event_towards_dropoff "
    "steps_to_last_dropoff trigger_step steps_to_returned_dropoff first_plan_returned_towards_D2 "
    "post_event_calls post_event_planning_seconds post_event_rounds told_turns_after_event "
    "told_order_positions first_post_event_speakers first_told_speaker_positions first_told_agent_spoke "
    "first_told_agent_mentioned_change first_plan_respected_change later_mention_iterations "
    "later_mention_iterations_respected lenient_rescues episode_call_ceiling call_ceiling "
    "speech wording stratum member_position temperature retry_temperature relay_records relay_calls relay_seconds "
    "relay_tokens relay_prompt_tokens relay_completion_tokens relay_reasoning_tokens relay_cost_usd relay_known_prompt_tokens "
    "relay_known_completion_tokens relay_known_reasoning_tokens relay_known_reported_cost_usd relay_guard_cost_usd "
    "first_plan_maker_told first_plan_maker_message_block first_plan_maker_had_news horizon planning_rounds"
).split()
RELAY_COLUMNS = ("relay_timing", "relay_display", "relay_delivery_iteration", "relay_delivery_speaker_position",
                 "first_wrong_delivery_step", "delivered_before_first_wrong", "relay_deliveries")

# This published protocol predates the mode field and only used the coloured site.
V3_CODE_VERSION = "0bd42cf7f6e1"
V4_CODE_VERSION = "f51489cfe776"
V5_CODE_VERSION = "4c7eb2bfe352"
PRE_RULE_VERSIONS = (V3_CODE_VERSION, V4_CODE_VERSION, V5_CODE_VERSION)
TECHNICAL = {CALL_CEILING, CALL_LIMIT, CLIENT_LIMIT, COST_LIMIT, MODEL_SERVICE, OUTPUT_LIMIT, TOKEN_LIMIT, UNUSABLE_REPLY}


def temperatures(record):
    legacy = record.get("code_version") in (V3_CODE_VERSION, V4_CODE_VERSION)
    result = {}
    for key in ("temperature", "retry_temperature"):
        value = record.get(key, 0.0 if legacy else None)
        if type(value) not in (float, int) or not 0 <= value <= 2:
            raise ValueError(f"Missing or invalid {key}")
        result[key] = value
    return result


def recorded_dropoff(record):
    if record.get("code_version") == V3_CODE_VERSION and "dropoff" not in record:
        return "event"
    return record.get("dropoff")


def recorded_dropoff_rule(record):
    if record.get("code_version") in PRE_RULE_VERSIONS and "dropoff_rule" not in record:
        return "off"
    return record.get("dropoff_rule")


def run_settings(out):
    path = out / "run.json"
    if not path.is_file():
        raise ValueError(f"Missing run.json in {out}")
    config = read_json(path)
    env = config.get("env", "boxnet1")
    if (env not in ("boxnet1", "boxnet2") or
            (env == "boxnet2" and config.get("collision") not in ("skip", "fail")) or
            (env == "boxnet1" and "collision" in config)):
        raise ValueError(f"Invalid environment or collision policy in {path}")
    if config.get("protocol", "legacy") not in ("legacy", "matched"):
        raise ValueError(f"Invalid protocol in {path}")
    if "map_set" in config:
        design = parse_map_set(config["map_set"])
        if design.metadata != {k: config.get(k) for k in ("map_set", "boxes_per_robot")}:
            raise ValueError(f"Inconsistent map set or rate in {path}")
    if config.get("protocol") == "matched":
        validate_writer_options("matched", config.setdefault("plan_note", "none"), config.setdefault("failed_writer", "drop"),
                                config.get("max_stalled_rounds"), config.get("cut_answer", "discard"))
        if config["failed_writer"] == "idle" and config.get("max_stalled_rounds") is None:
            raise ValueError(f"Missing max_stalled_rounds in {path}")
        for field in ("max_env_steps", "max_planning_rounds", "episode_call_ceiling", "effective_episode_call_ceiling"):
            if type(config.get(field)) is not int or config[field] < 0:
                raise ValueError(f"Missing or invalid {field} in {path}")
    if not isinstance(config.get("model"), str) or not config["model"]:
        raise ValueError(f"Missing model in {path}")
    if "stratified_e2_event_file_version" in config and config["stratified_e2_event_file_version"] != E2_EVENT_FILE_VERSION:
        raise ValueError(f"Unknown stratified e2 event version in {path}")
    hashes = config.get("source_sha256")
    if not isinstance(hashes, dict) or not hashes or config.get("code_version") != version_from_hashes(hashes):
        raise ValueError(f"Missing or invalid code version in {path}. Version-one runs require the version-one summary.")
    if "output_demand.py" in hashes and "reasoning_setting" not in config:
        raise ValueError(f"Missing reasoning_setting in {path}")
    config["reasoning_setting"] = validate_reasoning(config["model"], config.get("reasoning_setting", "default"))
    planning_fields = {"state_position", "max_env_steps"}
    versioned = "planning_metrics.py" in hashes and "horizon" in config
    if (versioned or planning_fields & config.keys()) and not planning_fields <= config.keys():
        raise ValueError(f"Missing planning settings in {path}")
    config["horizon"] = validate_horizon(config.get("horizon", 1))
    if config.get("state_position", "before") not in ("before", "after"):
        raise ValueError(f"Invalid state_position in {path}")
    cap = config.get("max_env_steps")
    if cap is not None and (type(cap) is not int or cap < 0):
        raise ValueError(f"Invalid max_env_steps in {path}")
    history_settings(config)
    if "failure_causes.py" in hashes and "history_window" not in config:
        raise ValueError(f"Missing history settings in {path}")
    for field in ("event_file_version", "max_output_tokens"):
        if type(config.get(field)) is not int or config[field] < 1:
            raise ValueError(f"Missing or invalid {field} in {path}")
    mode = recorded_dropoff(config)
    if mode not in DROPOFF_MODES or (config["code_version"] == V3_CODE_VERSION and mode != "event"):
        raise ValueError(f"Missing or invalid dropoff mode in {path}")
    config["dropoff"] = mode
    rule = recorded_dropoff_rule(config)
    if rule not in DROPOFF_RULES or (rule == "on" and (mode == "event" or config["code_version"] in PRE_RULE_VERSIONS)):
        raise ValueError(f"Missing or invalid dropoff_rule in {path}")
    config["dropoff_rule"] = rule
    config.update(temperatures(config))
    return config


def check_planning_settings(record, settings, location):
    if (record.get("env", "boxnet1"), record.get("collision")) != (settings.get("env", "boxnet1"), settings.get("collision")):
        raise ValueError(f"Mixed environment or collision policy in {location}")
    position = settings.get("state_position", "before")
    protocol = settings.get("protocol", "legacy")
    validate_board(record["size"], record.get("map_set", "legacy"), protocol, (record["condition"],))
    effective = position if protocol == "matched" or record["framework"] in ("DMAS", "OWN") else "ignored"
    if record.get("protocol", "legacy") != protocol:
        raise ValueError(f"Mixed protocol in {location}")
    if record.get("cut_answer", "discard") != settings.get("cut_answer", "discard"):
        raise ValueError(f"Mixed cut_answer in {location}")
    if record.get("map_set", "legacy") != settings.get("map_set", "legacy"):
        raise ValueError(f"Mixed map_set in {location}")
    if "map_set" in settings:
        if ("boxes_per_robot" not in record or record["boxes_per_robot"] != settings["boxes_per_robot"] or
                type(record.get("box_count")) is not int or record["box_count"] < 1 or "map_set" not in record):
            raise ValueError(f"Missing or invalid map metadata in {location}")
    if protocol == "matched" and record.get("max_planning_rounds") != settings["max_planning_rounds"]:
        raise ValueError(f"Mixed planning-round cap in {location}")
    if protocol == "matched":
        for key, default in (("plan_note", "none"), ("failed_writer", "drop")):
            if record.setdefault(key, default) != settings[key]:
                raise ValueError(f"Mixed {key} in {location}")
        if record.get("max_stalled_rounds") != settings.get("max_stalled_rounds"):
            raise ValueError(f"Mixed max_stalled_rounds in {location}")
    if record["framework"] == "GROUP":
        partition = group_partition(*map(int, record["size"].split("x")), record.get("group_size"))
        if (protocol != "matched" or settings.get("group_size") != partition.group_size or
                record.get("callers_per_round") != len(partition.blocks) or
                settings.get("group_partitions", {}).get(record["size"]) != partition.record()):
            raise ValueError(f"Inconsistent group partition in {location}")
    expected = dict(state_position=position, state_position_effective=effective, max_env_steps=settings.get("max_env_steps"))
    for key, value in expected.items():
        if record.get(key, value) != value or ("state_position" in settings and key not in record):
            raise ValueError(f"Mixed or missing {key} in {location}")
    record.update(expected)


def recover_cutoff_splits(row, folder):
    directory = folder / "calls"
    if "cut_calls" in row:
        paths = [directory / f"{cut['call']:05d}.json" for cut in row["cut_calls"]]
        calls = [read_json(p) for p in paths if p.is_file()]
    else:
        calls = []
        if row.get("truncated_attempts"):
            # Only the physical prefix already published by this episode is attributable.
            remaining = row["api_calls"]
            for path in sorted(directory.glob("[0-9]*.json")):
                if not remaining:
                    break
                call = read_json(path)
                attempts = call["attempts"]
                if len(attempts) > remaining:
                    call = dict(call, attempts=attempts[:remaining], response=None, failure=None)
                calls.append(call)
                remaining -= sum(a["api_calls"] for a in call["attempts"])
        row["cut_calls"] = cutoff_records(row, calls)
        failures = {c["number"] for c in calls if c.get("failure") == OUTPUT_LIMIT}
        for cut in row["cut_calls"]:
            cut["terminal"] = cut["terminal"] and cut["call"] in failures
    missing_raw = {a["attempt_id"]: a for c in calls for a in c["attempts"] if a.get("attempt_id") and
                   a.get("cut_off") is True and a.get("raw_output") is None and not a.get("cutoff_reply_class")}
    client_log = folder / "client-calls.jsonl"
    if missing_raw and client_log.is_file():
        with client_log.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = json.loads(line)
                key = entry.get("attempt_id")
                if key in missing_raw and isinstance(entry.get("raw_output"), str):
                    missing_raw.pop(key)["raw_output"] = entry["raw_output"]
                    if not missing_raw:
                        break
    fill_cutoff_splits(row, calls)


def read_episode_rows(out, *, require_model=True):
    """Validate atomic episode records without touching the run directory."""
    settings = run_settings(out)
    history = history_settings(settings)
    rows = []
    for path in sorted((out / "episodes").glob("*/episode.json")):
        raw = path.read_bytes()
        row = json.loads(raw)
        if row.get("model", None if require_model else settings["model"]) != settings["model"]:
            raise ValueError(f"Mixed or missing model in {path}")
        fallback = None if "output_demand.py" in settings["source_sha256"] else "default"
        if row.get("reasoning_setting", fallback) != settings["reasoning_setting"]:
            raise ValueError(f"Mixed or missing reasoning_setting in {path}")
        row["reasoning_setting"] = settings["reasoning_setting"]
        row.setdefault("providers", "")
        row["horizon"] = validate_horizon(row.get("horizon", 1), row["framework"])
        if row["horizon"] != settings["horizon"]:
            raise ValueError(f"Mixed horizon in {path}")
        check_planning_settings(row, settings, path)
        if row["horizon"] > 1 or row["framework"] == "OWN" or row.get("protocol") == "matched":
            log = row.get("round_log")
            if not isinstance(log, list) or row.get("planning_rounds") != len(log):
                raise ValueError(f"Invalid planning_rounds or round_log in {path}")
            if row["steps"] != sum(b["plans_executed"] for b in log):
                raise ValueError(f"Environment steps disagree with planning rounds in {path}")
            if "own_reply_form_counts" in row or "own_robots_dropped" in row:
                dropped = [b.get("own_robots_dropped") for b in log]
                if any(type(n) is not int or n < 0 for n in dropped) or row.get("own_robots_dropped") != sum(dropped):
                    raise ValueError(f"Planning rounds disagree with own_robots_dropped in {path}")
            for key in (*DMAS_RETENTIONS, "own_unreachable_skipped"):
                if key in row:
                    counts = [batch.get(key) for batch in log]
                    if any(type(n) is not int or n < 0 for n in counts) or row[key] != sum(counts):
                        raise ValueError(f"Planning rounds disagree with {key} in {path}")
        else:
            row.setdefault("planning_rounds", len(row.get("iterations", ())))
        if row.get("code_version") != settings["code_version"]:
            raise ValueError(f"Mixed or missing code version in {path}")
        if history_settings(row) != history:
            raise ValueError(f"Mixed history settings in {path}")
        row.update(history)
        if recorded_dropoff(row) != settings["dropoff"]:
            raise ValueError(f"Mixed or missing dropoff mode in {path}")
        row["dropoff"] = settings["dropoff"]
        if recorded_dropoff_rule(row) != settings["dropoff_rule"]:
            raise ValueError(f"Mixed or missing dropoff_rule in {path}")
        row["dropoff_rule"] = settings["dropoff_rule"]
        if row["code_version"] in PRE_RULE_VERSIONS:
            row.update(delivery_outcomes(row["event"], row["iterations"]))
        for field, value in temperatures(row).items():
            if value != settings[field]:
                raise ValueError(f"Mixed {field} in {path}")
        if settings["code_version"] not in (V3_CODE_VERSION, V4_CODE_VERSION):
            if row.get("speech") not in SPEECH_RULES or row.get("wording") not in (1, 2):
                raise ValueError(f"Missing or invalid speech assignment in {path}")
        version = settings["event_file_version"]
        if ("stratified_e2_event_file_version" in settings and row.get("condition") == "e2"
                and row.get("map_set", "legacy") == "legacy"):
            cohort = stratified_set(*map(int, row["size"].split("x")), row["env_seed"])
            if cohort in ("main", "confirm") or (cohort == "cause" and settings.get("relay_measurement_version")):
                version = settings["stratified_e2_event_file_version"]
        if row.get("event_file_version") != version:
            raise ValueError(f"Mixed or missing event_file_version in {path}")
        if row.get("max_output_tokens") != settings["max_output_tokens"]:
            raise ValueError(f"Mixed or missing max_output_tokens in {path}")
        if row["map_assignment"].get("event_file_version") != version:
            raise ValueError(f"Mixed or missing event_file_version in map assignment in {path}")
        if settings.get("relay_measurement_version") and row["speech"] == "auto":
            if "relay_timing" not in row:
                companion = out / "relay" / path.parent.name / (digest(raw) + ".json")
                if not companion.is_file():
                    raise ValueError(f"Missing relay measurements for {path}")
                attach_relay_measurements(row, read_json(companion))
            validate_relay_fields(row, path)
        # Paired outcome projections can omit all trace and usage data.
        has_planning_trace = "round_log" in row or "iterations" in row
        if has_planning_trace and "state_position" in settings:
            log = row.get("round_log")
            if not isinstance(log, list) or len(log) != row.get("planning_rounds"):
                raise ValueError(f"Invalid planning_rounds or round_log in {path}")
            for field in ROUND_COUNTS:
                if (field not in row or any(type(b.get(field)) is not int or b[field] < 0 for b in log)
                        or row[field] != sum(b[field] for b in log)):
                    raise ValueError(f"Planning rounds disagree with {field} in {path}")
        if has_planning_trace:
            fill_planning_counts(row)
        if row.get("protocol") == "matched":
            counts = Counter(b["cutoff_class"] for b in row["round_log"])
            if (set(counts) - CUTOFF_COUNTS.keys() or
                    any(row.get(field) != counts[name] for name, field in CUTOFF_COUNTS.items())):
                raise ValueError(f"Planning rounds disagree with cut-off counts in {path}")
            if not all(field in row for field in CUTOFF_SPLITS):
                recover_cutoff_splits(row, path.parent)
            if row.get("cut_answer") == "prefix":
                if any(v < 0 or row.get(k) != v for k, v in cut_prefix_counts(row).items()):
                    raise ValueError(f"Planning rounds disagree with cut-answer counts in {path}")
        if "cut_calls" not in row and row.get("truncated_attempts"):
            from analysis_runs import recorded_calls
            row["cut_calls"] = cutoff_records(row, recorded_calls(out, row))
        rows.append(row)
    return rows


def validate_relay_fields(item, location):
    if not item.get("relay_timing") or not item.get("relay_display"):
        raise ValueError(f"Missing relay_timing or relay_display in {location}")
    check_relay_options(item["speech"], item["framework"], item["relay_timing"], item["relay_display"])


def episode_csv(out):
    with locked(out / ".summary.lock"):
        rows = read_episode_rows(out)
        with atomic_file(out / "episodes.csv") as handle:
            settings = run_settings(out)
            columns = [*COLUMNS]
            if settings.get("env") == "boxnet2":
                columns.extend(("env", "collision", "collision_cancelled_moves"))
            if "map_set" in settings:
                columns.extend(("map_set", "boxes_per_robot", "box_count", "protocol"))
            if settings.get("protocol") == "matched":
                columns.extend(("max_planning_rounds", "repair_calls", "robots_dropped", "first_blocked_round",
                                "first_blocked_cause", "first_blocked_stage", *CUTOFF_COUNTS.values(),
                                "plan_note", "failed_writer", *CUTOFF_SPLITS))
                if settings["failed_writer"] == "idle":
                    columns.extend(("max_stalled_rounds", *BLOCK_COUNTS, *IDLE_TOTALS, "tokens_per_delivered_box"))
                if settings.get("cut_answer") == "prefix":
                    columns.extend(("cut_answer", *CUT_PREFIX_COUNTS))
            if "group_size" in settings:
                columns.extend(("group_size", "callers_per_round"))
            if settings.get("relay_measurement_version"):
                columns.extend(RELAY_COLUMNS)
            if "history_window" in settings:
                columns.extend(HISTORY_DEFAULTS)
            if "state_position" in settings:
                columns.extend(("state_position", "state_position_effective", "max_env_steps", *ROUND_COUNTS,
                                "stop_reason", "cut_calls"))
            if any("own_reply_form_counts" in row for row in rows):
                columns.extend(("own_reply_form_counts", "own_robots_dropped"))
            columns.extend(recorded_rule_counts(rows))
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                values = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()}
                values.setdefault("protocol", "legacy")
                if "tokens_per_delivered_box" in row and row["tokens_per_delivered_box"] is None:
                    values["tokens_per_delivered_box"] = "NA"
                if row["change_respected"] is None:
                    values["change_respected"] = "NA"
                if "delivered_before_first_wrong" in row and row["delivered_before_first_wrong"] is None:
                    values["delivered_before_first_wrong"] = "NA"
                writer.writerow(values)
        return rows


def assigned_episodes(out, rows, *, include_manifest=False):
    """Repeated invocations can finish an earlier assignment. Count each ID once."""
    names, stopped = set(), {}
    for invocation in sorted((out / "invocations").glob("*.json")):
        names.update(read_json(invocation)["requested"])
        log = invocation.with_suffix(".starts.jsonl")
        if log.is_file():
            for line in log.read_text().splitlines():
                admission = json.loads(line)
                if admission["admission"] == "not started":
                    name = admission["episode_id"]
                    stopped[name] = max(stopped.get(name, ("", "")), (admission["utc"], admission["stop_label"]))
    index = {row["episode_id"]: row for row in rows}
    path = out / "assignments.json"
    settings = run_settings(out)
    current = settings["code_version"] not in (V3_CODE_VERSION, V4_CODE_VERSION)
    if current and not path.is_file():
        raise ValueError(f"Missing assignment manifest in {out}")
    manifest = read_json(path) if path.exists() else {}
    if include_manifest:
        names.update(manifest)
    if current and (names - manifest.keys() or index.keys() - names):
        raise ValueError(f"Episode IDs disagree with the assigned run in {out}")
    results = {}
    for name in names:
        if name in manifest:
            item = manifest[name].copy()
            if item.get("reasoning_setting", settings["reasoning_setting"]) != settings["reasoning_setting"]:
                raise ValueError(f"Mixed or missing reasoning_setting in assignment: {name}")
            if settings.get("relay_measurement_version") and item.get("speech") == "auto":
                validate_relay_fields(item, name)
                if name in index and relay_cell(item) != relay_cell(index[name]):
                    raise ValueError(f"Episode disagrees with assigned relay_timing or relay_display: {name}")
            if settings["code_version"] not in PRE_RULE_VERSIONS and item.get("dropoff_rule") != settings["dropoff_rule"]:
                raise ValueError(f"Mixed or missing dropoff_rule in assignment: {name}")
            if name in index:
                for field in ("size", "framework", "condition", "tell", "speech", "env_seed", "env_sha256",
                              "event_sha256", "stratum", "wording", "member_position"):
                    if item[field] != index[name][field]:
                        raise ValueError(f"Episode disagrees with assigned {field}: {name}")
        else:
            size, framework, condition, *rest = name.split("_")
            row = index.get(name, {})
            d = row.get("D")
            item = dict(size=size, framework=framework, condition=condition, speech="authors",
                        env_seed=int(rest[-1][3:]), tell=None if condition == "static" else rest[0],
                        stratum=("first_column" if d[1] == 0.5 else "other_columns") if d else "unknown")
            if include_manifest:
                item.update({k: row[k] for k in ("env_sha256", "event_sha256") if k in row})
        if name not in index:
            item["missing_label"] = stopped.get(name, ("", "unrecorded"))[1]
        item["horizon"] = validate_horizon(item.get("horizon", 1), item["framework"])
        if item["horizon"] != settings["horizon"]:
            raise ValueError(f"Mixed horizon in assignment: {name}")
        check_planning_settings(item, settings, name)
        if name in index and "map_set" in settings and item["box_count"] != index[name]["box_count"]:
            raise ValueError(f"Episode disagrees with assigned box count: {name}")
        item["max_output_tokens"] = settings["max_output_tokens"]
        results[name] = item
    return results


def group_key(row, by=None):
    key = (row["size"], row["framework"], row.get("speech", "authors"), row["condition"], row["tell"] or "-")
    if by == "stratum":
        d = row.get("D")
        key = (*key, row.get("stratum", ("first_column" if d[1] == 0.5 else "other_columns") if d else "unknown"))
    elif by == "relay":
        key = (*key, *relay_cell(row))
    if row["framework"] == "GROUP":
        key += (row["group_size"],)
    return (*key, row.get("horizon", 1), row.get("state_position", "before"), row.get("max_output_tokens"),
            row.get("map_set", "legacy"), row.get("protocol", "legacy"))


def share(values):
    n = len(values)
    if not n:
        return "NA (0/0)"
    positives, missing = sum(v is True for v in values), values.count(None)
    suffix = f" [{missing} NA]" if missing else ""
    return f"{positives/n:.1%} ({positives}/{n}){suffix}"


def compare(rows, planned, by=None, missing=None):
    groups = defaultdict(list)
    for row in rows:
        if "effective_steps" not in row:
            fill_planning_counts(row)
        groups[group_key(row, by)].append(row)
    include_own = any(key[1] == "OWN" for key in groups.keys() | planned.keys())
    include_group = any(key[1] == "GROUP" for key in groups.keys() | planned.keys())
    rule_counts = recorded_rule_counts(rows)
    options = dict(include_own=include_own, include_group=include_group, rule_counts=rule_counts)
    extra_headers = {"stratum": ("stratum",), "relay": ("relay_timing", "relay_display")}.get(by, ())
    if include_group:
        extra_headers += ("group_size",)
    prefix = any(row.get("cut_answer") == "prefix" for row in rows)
    if prefix:
        extra_headers += ("cut_answer", *prefix_cell_metrics([]))
    headers = ("size", "framework", "speech", "condition", "tell", *extra_headers,
               "assigned", "recorded", "interrupted",
               "event fired", "nothing to change", "not fired", "success", "strict success", "change respected",
               "mean steps", "mean calls", "retried_calls", "truncated_attempts", "failure output limit",
               "mean tokens", "cost USD", "wrong deliveries", "dropoff misuse", "dropoff misuse before", "dropoff misuse after",
               "first-plan wrong", "first-plan towards", "first-plan respected", "first told mention",
               "later mention iterations", "later mentions with respected plan", "told turns",
               "mean fixed order position", "mean position among speakers", "first iteration told agent spoke",
               "mean trigger step", "mean steps to last drop-off", "mean steps to returned drop-off",
               "first returned towards D2", "mean first calls", "mean first seconds", "mean first rounds",
               "episodes with rescue", "failure labels (count)", "technical failures by label",
               "share that sent", "first plan-maker had news", "total calls", "relay calls", "relay seconds",
               "relay tokens", "relay cost USD", "relay format errors", "horizon", "mean planning rounds",
               "state_position", "max_output_tokens", *comparison_metrics([], **options),
               "map_set", "protocol")
    print(" | ".join(headers))
    for key in sorted(groups.keys() | planned.keys()):
        group = groups[key]
        event = key[3] != "static"
        assigned = planned.get(key, len(group))
        absent = assigned - len(group)
        def get(field):
            return [row[field] for row in group]
        def average(field, digits, *, conditional=False):
            values = [v for v in get(field) if v is not None]
            if not values or (not conditional and len(values) < len(group)):
                return "NA"
            coverage = f" ({len(values)}/{len(group)})" if conditional else ""
            return f"{mean(values):.{digits}f}{coverage}"
        def event_share(field):
            return share(get(field)) if event else "NA"
        def mean_position(field):
            positions = [p for row in group for p in row.get(field, {}).values()]
            known = [p for p in positions if p is not None]
            return f"{mean(known):.2f} ({len(known)}/{len(positions)})" if known else "NA"
        costs = get("cost_usd")
        cost = "NA" if None in costs else f"{sum(costs):.8f}"
        failures = Counter(r["success_failure"] for r in group if not r["success"])
        technical = Counter({k: n for k, n in failures.items() if k in TECHNICAL})
        technical.update((missing or {}).get(key, {}))
        relays = [r for row in group for r in row.get("relay_records", [])]
        relay_tokens = [r.get("relay_tokens", 0) for r in group]
        relay_costs = [r.get("relay_cost_usd", 0) for r in group]
        news = [r.get("first_plan_maker_had_news") for r in group] + [None] * absent
        strict = [bool(r["finished"] and r["strict_success"]) for r in group] + [False] * absent
        eligible = [bool(v) for v in get("change_respected") if v is not None]
        change = share(eligible)
        if len(eligible) < assigned:
            change += f" [{assigned - len(eligible)} NA]"
        misuse = [sum(get(field)) if group else "NA"
                  for field in ("dropoff_misuse", "dropoff_misuse_before", "dropoff_misuse_after")]
        round_counts = [r.get("planning_rounds", len(r.get("iterations", ()))) for r in group]
        cell = key[:-5]
        if include_group and key[1] != "GROUP":
            cell += ("-",)
        if prefix:
            cell += ("prefix", *("NA" if v is None else v for v in prefix_cell_metrics(group).values()))
        line = (*cell, assigned, len(group), sum(not r["finished"] for r in group),
                *(sum(get(f)) if event else "NA" for f in ("event_fired", "event_nothing_to_change", "event_not_fired")),
                share(get("success")), share(strict), change, average("steps", 2), average("api_calls", 2),
                sum(get("retried_calls")), sum(get("truncated_attempts")), failures[OUTPUT_LIMIT],
                average("tokens", 1), cost, sum(get("wrong_deliveries")), *misuse, event_share("first_plan_after_event_wrong"),
                event_share("first_plan_after_event_towards_dropoff"), event_share("first_plan_respected_change"),
                event_share("first_told_agent_mentioned_change"), sum(get("later_mention_iterations")) if event else "NA",
                sum(get("later_mention_iterations_respected")) if event else "NA",
                sum(sum(c.values()) for c in get("told_turns_after_event")) if event else "NA",
                mean_position("told_order_positions"), mean_position("first_told_speaker_positions"),
                share([row.get("first_told_agent_spoke") for row in group]) if event else "NA",
                average("trigger_step", 2, conditional=True), average("steps_to_last_dropoff", 2, conditional=True),
                average("steps_to_returned_dropoff", 2, conditional=True),
                event_share("first_plan_returned_towards_D2") if key[3] == "e2" else "NA",
                average("post_event_calls", 2, conditional=True), average("post_event_planning_seconds", 3, conditional=True),
                average("post_event_rounds", 2, conditional=True), share([n > 0 for n in get("lenient_rescues")]),
                ", ".join(f"{s} ({n})" for s, n in sorted(failures.items())) or "—",
                ", ".join(f"{s} ({n})" for s, n in sorted(technical.items())) or "—",
                share([bool(r["recipients"]) for r in relays]) if event else "NA",
                share(news) if event else "NA", sum(get("api_calls")),
                sum(r.get("relay_calls", 0) for r in group), f"{sum(r.get('relay_seconds', 0) for r in group):.3f}",
                sum(relay_tokens) if None not in relay_tokens else "NA",
                f"{sum(relay_costs):.8f}" if None not in relay_costs else "NA",
                sum(r["reply_class"] == "relay_format_error" for r in relays), key[-5],
                f"{mean(round_counts):.2f}" if round_counts else "NA", *key[-4:-2],
                *("NA" if v is None else v for v in comparison_metrics(group, **options).values()), *key[-2:])
        print(" | ".join(map(str, line)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--sizes", help="compare only these comma-separated grid sizes")
    parser.add_argument("--by", choices=("stratum", "relay", "planning"),
                        help="planning compares horizons, output limits and prompt positions in separate cells")
    args = parser.parse_args()
    try:
        sizes = size_filter(args.sizes)
        outs = [local_path(p) for p in args.runs]
        if len(set(outs)) != len(outs):
            raise ValueError("A run directory was supplied twice")
        configs = [run_settings(out) for out in outs]
        if any(history_settings(c) != history_settings(configs[0]) for c in configs):
            raise ValueError("Refusing to mix runs with different history settings")
        grouped_fields = {"horizon", "state_position", "map_set", "boxes_per_robot", "group_size", "group_partitions"}
        if args.by == "planning":
            grouped_fields.update(("max_output_tokens", "max_env_steps", "protocol", "max_planning_rounds",
                                   "effective_episode_call_ceiling", "episode_call_ceiling", "repairs_per_writer",
                                   "plan_note", "failed_writer", "max_stalled_rounds", "cut_answer"))
        for field in ("model", "reasoning_setting", "dropoff", "dropoff_rule", "event_file_version", "max_output_tokens", "temperature", "retry_temperature"):
            if field in grouped_fields:
                continue
            if len({c[field] for c in configs}) > 1:
                raise ValueError(f"Refusing to mix runs with different {field}")
        if len({c["code_version"] for c in configs}) > 1:
            raise ValueError("Refusing to mix code versions")
        fixed = [{k: v for k, v in c.items() if k not in grouped_fields} for c in configs]
        if any(c != fixed[0] for c in fixed):
            raise ValueError("Run settings differ across the supplied directories")
        if configs[0].get("env") == "boxnet2":
            print(f'BoxNet2 · collision {configs[0]["collision"]}')
        rows, planned, missing = [], Counter(), defaultdict(Counter)
        for out in outs:
            recorded = episode_csv(out)
            rows.extend(row for row in recorded if sizes is None or row["size"] in sizes)
            for assignment in assigned_episodes(out, recorded).values():
                if sizes is not None and assignment["size"] not in sizes:
                    continue
                key = group_key(assignment, args.by)
                planned[key] += 1
                if "missing_label" in assignment:
                    missing[key][assignment["missing_label"]] += 1
        if args.by == "planning":
            print_planning_table(rows, sys.stdout)
            print_matched_table(rows, sys.stdout)
            return
        e2_version = configs[0].get("stratified_e2_event_file_version")
        e2_note = f" (stratified e2 v{e2_version})" if e2_version else ""
        history_note = (" · " + " · ".join(f"{k} {configs[0][k]}" for k in HISTORY_DEFAULTS)
                        if "history_window" in configs[0] else "")
        print(f'{configs[0]["model"]} · reasoning {configs[0]["reasoning_setting"]} · code {configs[0]["code_version"]} · events v{configs[0]["event_file_version"]}{e2_note}'
              f' · dropoff {configs[0]["dropoff"]} · dropoff_rule {configs[0]["dropoff_rule"]} · max output tokens {configs[0]["max_output_tokens"]}'
              f' · temperature {configs[0]["temperature"]} · retry {configs[0]["retry_temperature"]}{history_note} · {len(rows)} episode rows')
        compare(rows, planned, args.by, missing)
        print_matched_table(rows, sys.stdout)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
