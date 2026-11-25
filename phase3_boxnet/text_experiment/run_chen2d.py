"""Run Chen BoxNet1 with shared seeded environments and optional changed orders."""
import argparse
import json
import math
import os
import random
import uuid
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from itertools import product

from LLM import (BRAIN, MAX_ATTEMPTS, MAX_OUTPUT_TOKENS, MAX_REPLY_ATTEMPTS, MAX_TRANSPORT_ATTEMPTS, MODEL,
                 QWEN, REASONING_SETTINGS, SMALL_QWEN, TRANSPORT_RETRY_TOTAL_S, load_real_api, validate_reasoning)
from board_sizes import ENROL_SIZES, MATCHED_SIZES, SCALED_ONLY_SIZES, selection, validate_board
from enrol_maps import seed_selection, speech_event
from episode import DROPOFF_RULES, HISTORY_DEFAULTS, HISTORY_METHODS, Spec, admit_episode, history_settings, run_episode
from fake_model import SCRIPTS
from horizon import validate_horizon
from limits import Invocation
from map_events import DROPOFF_MODES, E2_EVENT_FILE_VERSION, EVENT_FILE_VERSION, event_path, event_version
from map_sets import parse_map_set, saved_map_env
from matched_protocol import (CUT_ANSWERS, FAILED_WRITERS, PLAN_NOTES, REPAIRS_PER_WRITER, block_shapes,
                              group_partition, validate_writer_options)
from relay import RELAY_DISPLAYS, RELAY_TIMINGS, SPEECH_RULES, check_relay_options
from storage import ROOT, digest, local_path, locked, read_json, snapshot, source_hashes, version_from_hashes, write_json
from summarize import episode_csv

FRAMEWORKS = ("CMAS", "HMAS-2", "DMAS", "HMAS-1")
SUPPORTED_FRAMEWORKS = (*FRAMEWORKS, "OWN", "GROUP")


def select_specs(args):
    protocol = getattr(args, "protocol", "legacy")
    plan_note, failed_writer = getattr(args, "plan_note", "none"), getattr(args, "failed_writer", "drop")
    max_stalled_rounds = getattr(args, "max_stalled_rounds", None)
    cut_answer = getattr(args, "cut_answer", "discard")
    validate_writer_options(protocol, plan_note, failed_writer, max_stalled_rounds, cut_answer)
    sizes = selection(args.sizes, MATCHED_SIZES if protocol == "matched" else ENROL_SIZES)
    map_set = parse_map_set(getattr(args, "map_set", "legacy"))
    conditions = ["e1" if c == "change" else c for c in selection(args.conditions, ("static", "e1", "e2", "change"))]
    for size in sizes:
        validate_board(size, map_set.map_set, protocol, conditions)
    frameworks = selection(args.frameworks or ("CMAS,OWN" if protocol == "matched" else ",".join(FRAMEWORKS)), SUPPORTED_FRAMEWORKS)
    if protocol == "matched" and any(f not in ("CMAS", "OWN", "GROUP") for f in frameworks):
        raise ValueError("--protocol matched requires CMAS, OWN or GROUP")
    group_size = getattr(args, "group_size", None)
    if "GROUP" in frameworks:
        if protocol != "matched":
            raise ValueError("GROUP requires --protocol matched")
        for size in sizes:
            group_partition(*map(int, size.split("x")), group_size)
    elif group_size is not None:
        raise ValueError("--group-size requires GROUP in --frameworks")
    horizon = getattr(args, "horizon", 1)
    requested_position = getattr(args, "state_position", None)
    if protocol == "legacy" and frameworks == ["CMAS"] and requested_position == "before":
        raise ValueError("CMAS keeps its authors' state order. Omit --state-position or use after for a no-op.")
    for framework in frameworks:
        validate_horizon(horizon, framework)
    if len(set(conditions)) != len(conditions):
        raise ValueError("Duplicate condition (change is an alias for e1)")
    tells = selection(args.tell, ("all", "leader", "member"))
    rules = selection(args.speech, SPEECH_RULES)
    timing_arg, display_arg = getattr(args, "relay_timing", None), getattr(args, "relay_display", None)
    timings = selection(timing_arg, RELAY_TIMINGS) if timing_arg is not None else [None]
    displays = selection(display_arg, RELAY_DISPLAYS) if display_arg is not None else [None]
    for rule, fw, timing, display in product(rules, frameworks, timings, displays):
        check_relay_options(rule, fw, timing, display)
    seeds = seed_selection(args.envs)
    history = history_settings(vars(args))
    specs = []
    for size in sizes:
        rows, cols = map(int, size.split("x"))
        envs = {}
        for seed in seeds:
            path, sha, fields = saved_map_env(rows, cols, seed, map_set)
            for condition in conditions:
                version = event_version(rows, cols, seed, condition) if map_set.map_set == "legacy" else EVENT_FILE_VERSION
                envs[seed, condition] = (path, sha, digest(event_path(path, version).read_bytes()), fields)
        for framework, condition, seed, speech, timing, display in product(frameworks, conditions, seeds, rules, timings, displays):
            for tell in (["all"] if condition == "static" else tells):
                path, sha, event_sha, fields = envs[seed, condition]
                specs.append(Spec(rows, cols, framework, condition, seed, path, sha, event_sha, tell,
                                  args.parse, args.event_step, args.dropoff, speech, args.dropoff_rule, timing, display,
                                  reasoning_setting=getattr(args, "reasoning", "default"), horizon=horizon,
                                  state_position=requested_position or "before", max_env_steps=getattr(args, "max_env_steps", None),
                                  protocol=protocol, max_planning_rounds=getattr(args, "max_planning_rounds", None),
                                  plan_note=plan_note, failed_writer=failed_writer, max_stalled_rounds=max_stalled_rounds,
                                  cut_answer=cut_answer, group_size=group_size if framework == "GROUP" else None,
                                  **fields, **history))
    return specs


def freeze_assignments(out, specs):
    path = out / "assignments.json"
    assigned = read_json(path) if path.exists() else {}
    maps, frozen = {}, []
    for spec in specs:
        key = spec.env_path, spec.event_version
        if key not in maps:
            dest = out / "maps" / spec.size / spec.env_path.name
            snapshot(spec.env_path, dest, spec.env_hash)
            source = event_path(spec.env_path, spec.event_version)
            snapshot(source, event_path(dest, spec.event_version), spec.event_hash)
            if spec.event_version == E2_EVENT_FILE_VERSION:
                snapshot(event_path(spec.env_path), event_path(dest), read_json(source)["source_event_sha256"])
            companion = spec.env_path.with_suffix(".speech.event.json")
            if companion.exists():
                snapshot(companion, dest.with_suffix(".speech.event.json"), digest(companion.read_bytes()))
            effective = speech_event(dest, spec.rows, spec.cols, spec.seed)
            event = read_json(effective)
            maps[key] = dest, dict(stratum=event["stratum"], wording=event["wording"],
                member_position=event["member_position"], generation_seed=event["seed"],
                env_sha256=spec.env_hash, event_sha256=spec.event_hash,
                speech_event_sha256=digest(effective.read_bytes()))
        dest, fields = maps[key]
        item = dict(episode_id=spec.name, size=spec.size, framework=spec.framework, condition=spec.condition,
                    tell=None if spec.condition == "static" else spec.tell, speech=spec.speech,
                    dropoff_rule=spec.dropoff_rule, env_seed=spec.seed, horizon=spec.horizon, **spec.planning_settings,
                    **spec.relay_fields, **fields)
        if spec.reasoning_setting is not None:
            item["reasoning_setting"] = spec.reasoning_setting
        if spec.map_set is not None:
            item.update(map_set=spec.map_set, boxes_per_robot=spec.boxes_per_robot, box_count=spec.box_count)
        if spec.name in assigned and assigned[spec.name] != item:
            raise ValueError(f"Assignment changed for {spec.name}")
        assigned[spec.name] = item
        frozen.append(replace(spec, env_path=dest))
    write_json(path, assigned)
    return frozen


def run(args, out):
    specs = select_specs(args)
    sources = source_hashes()
    config = dict(code_version=version_from_hashes(sources), source_sha256=sources,
                  model=args.model, reasoning_setting=specs[0].reasoning_setting,
                  map_set=specs[0].map_set, boxes_per_robot=specs[0].boxes_per_robot, protocol=specs[0].protocol,
                  parse=args.parse, horizon=specs[0].horizon, dropoff=args.dropoff, dropoff_rule=specs[0].dropoff_rule,
                  state_position=specs[0].state_position, max_env_steps=specs[0].max_env_steps,
                  event_step_override=args.event_step,
                  fake_script=args.fake_script if args.model == "fake" else None,
                  episode_call_ceiling=args.episode_call_ceiling, history=HISTORY_METHODS[specs[0].history_method],
                  **history_settings(vars(specs[0])),
                  event_file_version=EVENT_FILE_VERSION, stratified_e2_event_file_version=E2_EVENT_FILE_VERSION,
                  relay_measurement_version=1,
                  max_output_tokens=args.max_output_tokens,
                  max_attempts_per_call=MAX_ATTEMPTS, temperature=args.temperature, retry_temperature=args.retry_temperature)
    if args.model != "fake":
        api = load_real_api()
        config.update(real_client_sha256=digest((BRAIN / "llm.py").read_bytes()),
                      hard_episode_calls=api.HARD_EPISODE_CALLS, hard_campaign_usd=api.HARD_CAMPAIGN_USD,
                      retry_total_s=api.RETRY_TOTAL_S, retry_window=os.environ.get("UGRP_V8_RETRY_WINDOW") == "1")
    effective_ceiling = min(args.episode_call_ceiling, config.get("hard_episode_calls", args.episode_call_ceiling))
    if effective_ceiling < args.episode_call_ceiling:
        print(f"Requested --episode-call-ceiling {args.episode_call_ceiling} exceeds the client's hard cap of "
              f"{effective_ceiling}. The effective episode ceiling is {effective_ceiling} physical calls.", flush=True)
        config["effective_episode_call_ceiling"] = effective_ceiling
    if specs[0].protocol == "matched":
        config.update(plan_note=specs[0].plan_note, failed_writer=specs[0].failed_writer,
                      max_planning_rounds=specs[0].max_planning_rounds, repairs_per_writer=REPAIRS_PER_WRITER,
                      effective_episode_call_ceiling=effective_ceiling, max_reply_attempts_per_call=MAX_REPLY_ATTEMPTS,
                      max_transport_errors_per_call=MAX_TRANSPORT_ATTEMPTS, transport_retry_total_s=TRANSPORT_RETRY_TOTAL_S,
                      max_attempts_per_call=MAX_REPLY_ATTEMPTS + MAX_TRANSPORT_ATTEMPTS - 1)
    if specs[0].max_stalled_rounds is not None:
        config["max_stalled_rounds"] = specs[0].max_stalled_rounds
    if specs[0].cut_answer == "prefix":
        config["cut_answer"] = specs[0].cut_answer
    config_path = out / "run.json"
    previous = read_json(config_path) if config_path.exists() else None
    group_size = getattr(args, "group_size", None)
    if group_size is not None:
        # Validate the published catalog before admitting additional scaled boards.
        recorded = (previous or {}).get("group_partitions", {})
        partitions = {}
        for size in MATCHED_SIZES:
            if size in SCALED_ONLY_SIZES and size not in recorded:
                continue
            rows, cols = map(int, size.split("x"))
            if group_size in block_shapes(rows, cols):
                partitions[size] = group_partition(rows, cols, group_size).record()
        config.update(group_size=group_size, group_partitions=partitions)
    if previous is not None and previous != config:
        raise ValueError("Run settings or protocol source changed. Use a new output directory.")
    if group_size is not None:
        for spec in specs:
            if spec.framework == "GROUP" and spec.size not in partitions:
                partitions[spec.size] = spec.partition.record()
    if previous is None and ((out / "episodes").exists() or (out / "campaign-calls.jsonl").exists()):
        raise ValueError("Existing results require their original run.json")
    if previous != config:
        write_json(config_path, config)
    for name, sha in sources.items():
        snapshot(ROOT / name, out / "source" / name, sha)
    specs = freeze_assignments(out, specs)
    if args.shuffle is not None:
        random.Random(args.shuffle).shuffle(specs)
    invocations = out / "invocations"
    invocations.mkdir(exist_ok=True)
    path = invocations / (uuid.uuid4().hex + ".json")
    selectors = {k: getattr(args, k) for k in ("sizes", "frameworks", "conditions", "tell", "speech",
                                               "envs", "dropoff", "dropoff_rule")}
    selectors.update({k: getattr(args, k) for k in ("relay_timing", "relay_display") if getattr(args, k, None) is not None})
    selectors["horizon"] = specs[0].horizon
    selectors.update(state_position=specs[0].state_position, max_env_steps=specs[0].max_env_steps)
    selectors.update(protocol=specs[0].protocol, map_set=specs[0].map_set, boxes_per_robot=specs[0].boxes_per_robot)
    if specs[0].protocol == "matched":
        selectors.update(max_planning_rounds=specs[0].max_planning_rounds, plan_note=specs[0].plan_note,
                         failed_writer=specs[0].failed_writer)
    if specs[0].max_stalled_rounds is not None:
        selectors["max_stalled_rounds"] = specs[0].max_stalled_rounds
    if specs[0].cut_answer == "prefix":
        selectors["cut_answer"] = specs[0].cut_answer
    if group_size is not None:
        selectors["group_size"] = group_size
    Invocation(out, path).create(args.max_calls, args.max_cost_usd, args.model, (s.name for s in specs),
                                 shuffle=args.shuffle, jobs=args.jobs, selectors=selectors)
    other = (out, path, args.model, args.fake_script, effective_ceiling, args.max_output_tokens,
             args.temperature, args.retry_temperature)
    pending = {}
    def collect():
        done, _ = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            print(f"{pending.pop(future)}  {future.result()}", flush=True)
        episode_csv(out)

    # Admission is serial and durable. Up to jobs admitted episodes may plan concurrently.
    with ProcessPoolExecutor(max_workers=args.jobs) as pool, path.with_suffix(".starts.jsonl").open("x") as starts:
        for index, spec in enumerate(specs, 1):
            if len(pending) >= args.jobs:
                collect()
            status, previous = admit_episode(spec, out, path, args.max_output_tokens, args.temperature, args.retry_temperature)
            label = read_json(path)["stop_label"] if status == "not started" else None
            starts.write(json.dumps(dict(index=index, episode_id=spec.name, admission=status, stop_label=label,
                                         utc=datetime.now(timezone.utc).isoformat())) + "\n")
            starts.flush()
            os.fsync(starts.fileno())
            if status == "started":
                pending[pool.submit(run_episode, spec, *other, previous)] = spec.name
            else:
                print(f"{spec.name}  {status}", flush=True)
        while pending:
            collect()
    rows = episode_csv(out)
    state = read_json(path)
    print(f'{len(rows)} recorded episodes. This invocation made {state["calls"]} calls. '
          f'Known {"scripted" if args.model == "fake" else "API-reported"} cost USD {state["reported_cost_usd"]}.')
    if state["stop_label"]:
        print(f'{state["stop_label"]} ({state["stop_detail"]})')


def main():
    tilings = []
    for size in MATCHED_SIZES:
        valid = sorted(block_shapes(*map(int, size.split("x"))))
        tilings.append(f"  {size}: " + ", ".join(map(str, valid)))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="Valid GROUP sizes by grid (rows x columns):\n" + "\n".join(tilings))
    parser.add_argument("--sizes", default="2x2", help="comma-separated grids; matched supports " + ", ".join(MATCHED_SIZES))
    parser.add_argument("--frameworks",
                        help="comma-separated frameworks: " + ", ".join(SUPPORTED_FRAMEWORKS))
    parser.add_argument("--group-size", type=int, metavar="G",
                        help="robots per GROUP writer (required for GROUP). 4 uses 2x2 blocks and 8 uses 2x4. "
                             "3 uses 1x3 rows on the three-column boards.")
    parser.add_argument("--conditions", "--condition", "--event", default="static,e1,e2",
                        help="static, e1 (order change), e2 (returned delivery), or a comma-separated list")
    parser.add_argument("--tell", default="all", help="all, leader, member or a comma-separated list (static ignores it)")
    parser.add_argument("--speech", default="authors", help="authors, auto, choice, free or a comma-separated list")
    parser.add_argument("--relay-timing", help="auto only: immediate (default), turn, or a comma-separated list")
    parser.add_argument("--relay-display", help="auto only: persistent (default), once, or a comma-separated list")
    parser.add_argument("--shuffle", type=int, metavar="SEED", help="randomise episode admission using this seed")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--retry-temperature", type=float, help="temperature immediately after a truncated attempt")
    parser.add_argument("--dropoff", choices=DROPOFF_MODES, default="always",
                        help="persistent neutral site (always, default) or version-3 coloured site (event)")
    parser.add_argument("--dropoff-rule", choices=DROPOFF_RULES, default="on",
                        help="explain the neutral site in every task prompt (default on, forced off with --dropoff event)")
    parser.add_argument("--event-step", type=int, help="override the e1 trigger with this executed step")
    parser.add_argument("--parse", choices=("lenient", "strict"), default="lenient")
    parser.add_argument("--horizon", type=int, default=1, metavar="H",
                        help="steps per planning round (CMAS, DMAS, OWN and GROUP support H > 1)")
    parser.add_argument("--protocol", choices=("legacy", "matched"), default="legacy",
                        help="matched CMAS, OWN and GROUP share wording, layout and repair allowance")
    parser.add_argument("--plan-note", choices=PLAN_NOTES, default="none",
                        help="tell matched writers that another round follows this horizon")
    parser.add_argument("--cut-answer", choices=CUT_ANSWERS, default="discard",
                        help="keep complete leading steps from an output-limited matched writer with prefix")
    parser.add_argument("--failed-writer", choices=FAILED_WRITERS, default="drop",
                        help="matched writer failure policy: drop (original), fail a required writer, or idle its robots")
    parser.add_argument("--max-stalled-rounds", type=int, metavar="K",
                        help="with --failed-writer idle, stop after K consecutive rounds without an action (default 3)")
    parser.add_argument("--map-set", default="legacy", help="legacy or scaled:R boxes per robot")
    parser.add_argument("--max-planning-rounds", type=int, metavar="N",
                        help="matched planning-round ceiling for all grid sizes (default 30)")
    parser.add_argument("--max-env-steps", type=int, metavar="N",
                        help="stop after N executed environment steps (matched default 30)")
    parser.add_argument("--state-position", choices=("before", "after"),
                        help="position the current state relative to history (legacy CMAS keeps its order)")
    parser.add_argument("--history-window", type=int, default=HISTORY_DEFAULTS["history_window"], metavar="N",
                        help="authors' approximate input-token window (default 3000, 0 disables past steps)")
    parser.add_argument("--history-method", choices=HISTORY_METHODS, default="authors",
                        help="past steps include state/actions, dialogue as well, or no past steps")
    parser.add_argument("--cmas-history", choices=("off", "on"), default="off",
                        help="opt the CMAS planner into state/action history within the selected window")
    parser.add_argument("--envs", default="0,1,2", help="seeds and inclusive ranges, e.g. 0-9 or 0,2,4-6")
    parser.add_argument("--out", required=True)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--episode-call-ceiling", type=int, default=300)
    parser.add_argument("--max-output-tokens", type=int, default=MAX_OUTPUT_TOKENS,
                        help="completion-token limit per HTTP attempt, including reasoning (default: 8192)")
    parser.add_argument("--max-cost-usd", type=Decimal, default=Decimal("1.5"))
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--model", choices=(MODEL, QWEN, SMALL_QWEN, "fake"), default=MODEL)
    parser.add_argument("--reasoning", choices=REASONING_SETTINGS, default="default",
                        help="use the client default, or disable reasoning on the small Qwen")
    parser.add_argument("--fake-script", default="correct",
                        help="choose " + ", ".join(SCRIPTS) + ", or cut:TEXT for a scripted matched output limit")
    try:
        args = parser.parse_args()
        if args.frameworks is None:
            args.frameworks = "CMAS,OWN" if args.protocol == "matched" else ",".join(FRAMEWORKS)
        validate_reasoning(args.model, args.reasoning)
        if args.retry_temperature is None:
            args.retry_temperature = args.temperature
        if not all(math.isfinite(t) and 0 <= t <= 2 for t in (args.temperature, args.retry_temperature)):
            raise ValueError("Temperatures must be finite and in [0, 2]")
        if args.max_output_tokens < 1:
            raise ValueError("--max-output-tokens must be positive")
        if args.event_step is not None and args.event_step < 1:
            raise ValueError("--event-step must be a positive executed step number")
        if args.jobs < 1 or args.episode_call_ceiling < 0 or (args.max_calls is not None and args.max_calls < 0):
            raise ValueError("Jobs must be positive and call ceilings nonnegative")
        if not args.max_cost_usd.is_finite() or args.max_cost_usd < 0:
            raise ValueError("Cost cap must be finite and nonnegative")
        if args.fake_script != "correct" and args.model != "fake":
            raise ValueError("--fake-script requires --model fake")
        if args.fake_script not in SCRIPTS and not (args.fake_script.startswith("cut:") and args.protocol == "matched"):
            raise ValueError("Unknown --fake-script. cut:TEXT requires --protocol matched")
        out = local_path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with locked(out / ".runner.lock"):
            run(args, out)
    except (ValueError, InvalidOperation) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
