"""Offline/reproducible same-board reading-load probe (TASK-CHEN2D-15).

This deliberately reads saved episode artefacts.  It never advances the source
environment: a cell is one fresh, single-attempt model call about one saved
state.  ``main`` is the command-line entry point; the small public helpers are
also used by the probe tests and make the source-to-probe mapping inspectable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from itertools import combinations, product
from pathlib import Path
from threading import Lock

from board_sizes import SCALED_ONLY_SIZES, selection, size_filter, validate_board
from enrol_maps import seed_selection
from env1_create import square_actions, state_update_func, state_update_func_local_agent, surround_index_func
from horizon import check_joint
from LLM import MODEL, QWEN, SMALL_QWEN, load_real_api, validate_reasoning
from map_events import DROPOFF_MODES, agent_at, boxes, cell_key, event_path
from map_sets import parse_map_set, saved_map_env
from matched_protocol import (DROPOFF_RULE, GROUP_CALL_FIELDS, PLAN_NOTES, build_prompt as build_matched,
                              group_partition, validate_writer_options)
from probe_wording import (FirstWriter, LEADER_EXAMPLE, SOURCE_MAPPING, fairness_report, first_round_writers, joint_moves,
                          strip_nonstructural_style)
from prompt_env1 import state_action_history
from limits import Invocation, StopEpisode
from plan_parse import OWN_MOVE, PlanParser, speaker_coordinates
from prompt_env1 import input_prompt_1_func_total, input_prompt_local_agent_DMAS_dialogue_func
from storage import atomic_file, local_path, locked, read_json, source_path, write_json
from fake_model import SCRIPTS

CALLERS = ("leader", "own_first", "own_last")
GROUP_CALLERS = ("group_first", "group_last")
SUPPORTED_CALLERS = CALLERS + GROUP_CALLERS
ARMS = ("none", "last1", "all_before", "all_after")
STRUCTURES = ("CMAS", "GROUP", "OWN")
SOURCE_ARTIFACTS = ("probe_reading.py", "probe_wording.py", "matched_protocol.py", "prompt_env1.py",
                    "env1_create.py", "LLM.py", "limits.py", "plan_parse.py", "horizon.py",
                    "map_events.py", "fake_model.py", "planning_metrics.py", "storage.py", "board_sizes.py")


def write_fairness_report(path: Path, horizon=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_file(path) as handle:
        handle.write(fairness_report(horizon))


def _agent(row: int, col: int) -> str:
    return f"Agent[{row + .5}, {col + .5}]"


def _key(robot: str) -> tuple[float, float]:
    numbers = re.findall(r"\d+(?:\.\d+)?", robot)
    return float(numbers[0]), float(numbers[1])


def _state_files(directory: Path) -> dict[int, Path]:
    found = {}
    for path in (directory / "pg_state").glob("pg_state*.json"):
        match = re.fullmatch(r"pg_state(\d+)\.json", path.name)
        if match:
            found[int(match.group(1))] = path
    return found


def _response_files(directory: Path) -> dict[int, Path]:
    found = {}
    for path in (directory / "response").glob("response*.json"):
        match = re.fullmatch(r"response(\d+)\.json", path.name)
        if match:
            found[int(match.group(1))] = path
    return found


@dataclass(frozen=True)
class SavedState:
    directory: Path
    run: str
    episode: str
    step: int
    rows: int
    cols: int
    states: tuple[dict, ...]  # states 1 .. current, inclusive
    responses: tuple[str, ...]  # source actions 1 .. current-1
    source_current: dict  # executor-applied actions at current step
    record: dict
    previous_applied: dict | None = None

    @property
    def returned_only(self):
        return self.record.get("condition") == "e2"

    @property
    def state(self):
        return self.states[-1]

    @property
    def state_id(self):
        return f"{self.run}/{self.episode}:step{self.step}"


def evenly_spread_steps(first: int, last: int, count: int) -> list[int]:
    """Deterministic inclusive selection, with no dependence on a probe arm."""
    if count < 1 or last < first:
        return []
    candidates = list(range(first, last + 1))
    if count >= len(candidates):
        return candidates
    if count == 1:
        return [candidates[len(candidates) // 2]]
    return [candidates[round(i * (len(candidates) - 1) / (count - 1))] for i in range(count)]


def find_episode_dirs(spec: str) -> list[Path]:
    """Accept an episode directory, an ``episodes`` directory, or a run root."""
    result = []
    for raw in filter(None, spec.split(",")):
        root = Path(raw).resolve()
        if (root / "episode.json").is_file():
            result.append(root)
        elif root.is_dir():
            result.extend(sorted(path.parent for path in root.rglob("episode.json")))
        else:
            raise ValueError(f"Episode input does not exist: {root}")
    return sorted(dict.fromkeys(result))


def applied_joint(iteration):
    """Recover physical moves, in the executor's canonical source square."""
    return joint_moves(iteration["applied_actions"])


def select_saved_states(episode_dirs: list[Path], per_episode: int, sizes=None) -> list[SavedState]:
    selected = []
    for directory in episode_dirs:
        record = read_json(directory / "episode.json")
        if not record.get("finished") or (sizes is not None and record.get("size") not in sizes):
            continue
        try:
            rows, cols = map(int, record["size"].split("x"))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"No usable size in {directory / 'episode.json'}") from exc
        validate_board(record["size"], record.get("map_set"), record.get("protocol", "legacy"),
                       (record.get("condition"),))
        boards, replies = _state_files(directory), _response_files(directory)
        steps = record["steps"]
        if set(boards) != set(range(1, steps + 2)) or not set(range(1, steps + 1)) <= replies.keys():
            raise ValueError(f"Incomplete board/response sequence in {directory}")
        states = tuple(read_json(boards[i]) for i in range(1, steps + 2))
        responses = tuple(json.dumps(read_json(replies[i])) for i in range(1, steps + 1))
        executed = {it["step"]: applied_joint(it) for it in record["iterations"] if it["executed"]}
        if set(executed) != set(range(1, steps + 1)):
            raise ValueError(f"Incomplete physical execution log in {directory}")
        eligible = [n for n in range(2, steps + 2) if any(
            _doable(states[n-1], rows, cols, record.get("condition") == "e2").values())]
        run = directory.parent.parent.name if directory.parent.name == "episodes" else directory.parent.name
        for index in evenly_spread_steps(0, len(eligible) - 1, per_episode):
            n = eligible[index]
            selected.append(SavedState(directory, run, record.get("episode_id", directory.name), n, rows, cols,
                                       states[:n], responses[:n-1], executed.get(n, {}), record, executed[n-1]))
    return selected


def initial_states(sizes, map_set, seeds, dropoff):
    design = parse_map_set(map_set)
    for size in sizes:
        validate_board(size, design.map_set, "matched", ("static",))
        rows, cols = map(int, size.split("x"))
        for seed in seeds:
            path, sha, fields = saved_map_env(rows, cols, seed, design)
            state, event = read_json(path), read_json(event_path(path))
            if dropoff == "always":
                state[cell_key(event["D"])].append("dropoff")
            record = dict(**fields, size=size, env_seed=seed, env_sha256=sha, L=event["L"],
                          condition="static", dropoff_rule="on" if dropoff == "always" else "off")
            yield SavedState(path, design.map_set, f"{size}_env{seed}", 1, rows, cols, (state,), (), {}, record)


def _doable(state: dict, rows: int, cols: int, returned_only=False) -> dict[str, list[str]]:
    result = {}
    for row in range(rows):
        for col in range(cols):
            key = f"{row + .5}_{col + .5}"
            result[_agent(row, col)] = square_actions(state[key], surround_index_func(rows, cols, row, col), returned_only)
    return result


def choose_own_robot(saved: SavedState) -> tuple[str, dict[str, list[str]]]:
    allowed = _doable(saved.state, saved.rows, saved.cols, saved.returned_only)
    choices = [robot for robot in sorted(allowed, key=_key) if allowed[robot]]
    if not choices:
        raise ValueError(f"No doable action in {saved.state_id}")
    return choices[-1], allowed


def _history(saved, arm):
    if arm == "none":
        return [saved.state], [], saved.step - 1
    if arm == "last1":
        return saved.states[-2:], saved.responses[-1:], saved.step - 2
    return saved.states, saved.responses, 0


HISTORY_SLOT = "The previous state and action pairs at each step are:\n    "


def _move_leader_state_before(prompt, notice=""):
    """Transpose two complete byte spans. All separators travel with their blocks."""
    hist = prompt.index(HISTORY_SLOT)
    state = prompt.index(notice + "Hence, the current state is", hist)
    out = prompt.rindex(LEADER_EXAMPLE)
    return prompt[:hist] + prompt[state:out] + prompt[hist:state] + prompt[out:]


def peer_lists(saved, robot, horizon):
    earlier = (name for name in sorted((_agent(i, j) for i in range(saved.rows)
               for j in range(saved.cols)), key=_key) if _key(name) < _key(robot))
    return {name: [saved.source_current.get(name)] + [None] * (horizon - 1) for name in earlier}


def _notice(saved, speaker, central):
    event = saved.record.get("event")
    if not event or event.get("step", saved.step) >= saved.step:
        return ""
    tell = saved.record.get("tell") or "all"
    hears = (tell == "all" or (tell == "leader" and speaker == saved.record.get("L")) or
             (tell == "member" and not central and speaker == saved.record.get("M")))
    return event.get("announcement", "") + "\n" if hears and event.get("announcement") else ""


def build_prompt(saved, caller, arm, horizon=1, *, protocol="authors", strip_style=False, group_size=None,
                 plan_note="none"):
    """Fill the same role template in all four arms. Only the two reading blocks can vary."""
    if caller not in SUPPORTED_CALLERS or arm not in ARMS or horizon < 1:
        raise ValueError("Invalid probe caller, arm or horizon")
    validate_writer_options(protocol, plan_note)
    own_robot, allowed = choose_own_robot(saved)
    block, scope, peers = None, {}, {}
    if caller in GROUP_CALLERS:
        if protocol != "matched":
            raise ValueError("group callers require --protocol matched")
        partition = group_partition(saved.rows, saved.cols, group_size)
        # Both arms address the same last non-idle block, including when its leader is idle.
        members = next(b for b in reversed(partition.blocks) if any(allowed[name] for name in b))
        scope = partition.call_scope(members, allowed)
        scope["writer_role"] = {"CMAS": "central", "OWN": "own", "GROUP": "group"}[partition.writer_framework]
        if scope["writer_role"] == "central":
            caller = "leader"
        elif scope["writer_role"] == "own":
            caller = "own_last" if caller == "group_last" else "own_first"
        else:
            block = members
            if caller == "group_last":
                for earlier in partition.blocks[:partition.blocks.index(block)]:
                    joint = {name: saved.source_current[name] for name in earlier if name in saved.source_current}
                    peers[earlier[0]] = [joint] + [{} for _ in range(horizon - 1)]
    leader = caller == "leader"
    robot = saved.record.get("L") if leader else (block[0] if block else own_robot)
    robot_index = None if leader else tuple(int(v - .5) for v in _key(robot))
    if caller == "own_last":
        peers = peer_lists(saved, robot, horizon)
    states, responses, offset = _history(saved, arm)
    position = "before" if arm == "all_before" else "after"
    notice = _notice(saved, robot, leader)
    rule = saved.record.get("dropoff_rule") == "on"
    counts = {name: len(set(actions)) for name, actions in allowed.items()}
    assigned = counts if leader else (block or (robot,))
    common = dict(robot=robot, caller_doable_actions=sum(counts[name] for name in assigned),
                  robot_local_doable_actions=counts.get(robot), robots_with_doable_actions=sum(bool(v) for v in counts.values()),
                  peer_lists=peers, history_state_count=len(responses), history_action_count=len(responses),
                  state_position=position, map_set=saved.record.get("map_set", "legacy"),
                  boxes_per_robot=saved.record.get("boxes_per_robot"), box_count=boxes(saved.states[0]).total(),
                  source_model=saved.record.get("model"), **scope)
    # Unbounded by design: the experiment controls the number of actual executed pairs.
    window = 1 << 62
    method = "_w_only_state_action_history"
    if protocol == "matched":
        prompt = build_matched(saved.rows, saved.cols, saved.state, responses, states, horizon=horizon,
                               history_method=method, history_window=window, state_position=position,
                               robot=None if block else robot_index, block=block, earlier=peers, step_offset=offset, strip_style=strip_style,
                               announcement=notice, dropoff_rule=rule, returned_only=saved.returned_only, plan_note=plan_note)
        return prompt, common
    if protocol not in ("authors", "legacy"):
        raise ValueError("Unknown probe protocol")
    # Render the native history-enabled template even with zero pairs. This keeps all
    # surrounding whitespace fixed when just the amount of history changes.
    if leader:
        board = state_update_func(saved.rows, saved.cols, saved.state, saved.returned_only)
        prompt = input_prompt_1_func_total(board, [], [saved.state], [], method, "CMAS", notice,
                                            history_window=window, cmas_history=True, horizon=horizon)
        if position == "before":
            prompt = _move_leader_state_before(prompt, notice)
        goal = "Your task is to instruct each agent to match all boxes to their color-coded targets."
    else:
        local, others = state_update_func_local_agent(saved.rows, saved.cols, *robot_index, saved.state, saved.returned_only)
        prompt = input_prompt_local_agent_DMAS_dialogue_func(local, others, json.dumps(peers), [], [saved.state], [],
            method, notice, history_window=window, horizon=horizon, own_horizon=horizon, state_position=position)
        goal = "achieve the goal: match each box with its color-coded target."
    if rule:
        prompt = prompt.replace(goal, goal + " " + DROPOFF_RULE, 1)
    if strip_style:
        prompt = strip_nonstructural_style(prompt, caller, horizon)
    past = state_action_history(responses, states, window, step_offset=offset)
    slot = prompt.index(HISTORY_SLOT) + len(HISTORY_SLOT)
    return prompt[:slot] + past + prompt[slot:], common


def _actions(reply, role, horizon, robot, members=None, *, matched_shape=False):
    if not isinstance(reply, str):
        return False, {}
    parser = PlanParser("lenient")
    if role != "own":
        # A block has the episode writer's restricted key set; the original leader probe scores off-board keys.
        positions = {speaker_coordinates(name) for name in members} if role == "group" or (members and matched_shape) else None
        sequence = parser.sequence(reply, horizon, agent_positions=positions, matched_shape=matched_shape)
        return (True, sequence[0]) if sequence else (False, {})
    sequence = parser.sequence(reply, horizon, own=True, speaker=robot, matched_shape=matched_shape)
    if not sequence:
        return False, {}
    return True, {} if sequence[0] is None else {robot: sequence[0]}


def judge_reply(saved, caller, reply, horizon, metadata, *, protocol="authors"):
    robot = metadata["robot"]
    allowed = _doable(saved.state, saved.rows, saved.cols, saved.returned_only)
    role = metadata.get("writer_role", "central" if caller == "leader" else "own")
    members = metadata.get("assigned_robots") if role == "group" or "writer_index" in metadata else None
    produced, actions = _actions(reply, role, horizon, robot, members,
                                 matched_shape=protocol == "matched")
    _, invalid = check_joint(saved.state, actions, allowed, saved.returned_only)
    previous_actions = saved.previous_applied
    if previous_actions is None:
        previous_actions = json.loads(saved.responses[-1]) if saved.responses else {}
    previous_state = saved.states[-2] if len(saved.states) > 1 else {}
    stale_repeat = box_left = conflicts = name_overlap = 0
    peer_actions = {}
    for peer, entries in metadata.get("peer_lists", {}).items():
        if entries:
            if role == "group":
                peer_actions.update(entries[0])
            else:
                peer_actions[peer] = entries[0]
    for name, action in actions.items():
        square = speaker_coordinates(name)
        move = OWN_MOVE.fullmatch(action) if isinstance(action, str) else None
        if square is None or move is None:
            continue
        square = tuple(map(float, square))
        box = move[1]
        origin = cell_key(square)
        if name in invalid:
            stale_repeat += action == previous_actions.get(agent_at(square))
            box_left += box in previous_state.get(origin, ()) and box not in saved.state.get(origin, ())
        if role != "central":
            peers = [peer for peer, action in peer_actions.items() if isinstance(action, str)
                     and (peer_move := OWN_MOVE.fullmatch(action)) and peer_move[1] == box]
            name_overlap += bool(peers)
            copies = sum(items.count(box) for items in saved.state.values())
            for peer in peers:
                source = cell_key(_key(peer))
                if saved.state[source].count(box) != 1:
                    continue
                # A directly observed handoff can identify the particular box even if
                # other squares contain copies of the same colour.
                handoff = f"move({box}, square{list(_key(peer))})"
                if copies == 1 or (previous_actions.get(name) == handoff and
                                   previous_state.get(origin, []).count(box) == 1 and
                                   box not in previous_state.get(source, ()) and box not in saved.state[origin]):
                    conflicts += 1
                    break
    return dict(plan_produced=produced, proposed_actions=len(actions), not_doable_actions=len(invalid),
                stale_exact_repeat=stale_repeat, stale_box_left_square=box_left,
                conflict_earlier_box=conflicts, peer_box_name_overlap=name_overlap)


def _cell_id(saved: SavedState, caller: str, arm: str, group_size=None) -> str:
    if isinstance(caller, FirstWriter):
        writer = f"{caller.framework}/{caller.index}/{caller.scope.get('group_size', '')}"
    else:
        writer = f"{caller}/g{group_size}" if caller in GROUP_CALLERS else caller
    raw = f"{saved.directory.resolve()}\0{saved.step}\0{writer}\0{arm}".encode()
    return hashlib.sha256(raw).hexdigest()[:20]


def _append_jsonl(path: Path, row: dict) -> None:
    """Commit one finished cell before another cell may be admitted."""
    with locked(path.with_suffix(path.suffix + ".lock")):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def _finished_rows(path: Path) -> dict[str, dict]:
    # Per-cell result files are the durable completion authority.  JSONL is a
    # convenient report stream and may be torn only at its final append.
    result_files = sorted((path.parent / "cells").glob("*/result.json"))
    if result_files:
        rows = [read_json(item) for item in result_files]
        return {row["cell_id"]: row for row in rows if row.get("finished")}
    if not path.exists():
        return {}
    finished = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("finished"):
            if row["cell_id"] in finished and finished[row["cell_id"]] != row:
                raise ValueError(f"Conflicting completed probe cell: {row['cell_id']}")
            finished[row["cell_id"]] = row
    return finished


def _rebuild_results_jsonl(out: Path) -> dict[str, dict]:
    """Recover an interrupted/torn journal from atomic per-cell checkpoints."""
    rows = _finished_rows(out / "results.jsonl")
    if rows:
        with atomic_file(out / "results.jsonl") as handle:
            for cell in sorted(rows):
                handle.write(json.dumps(rows[cell], ensure_ascii=False, sort_keys=True) + "\n")
    return rows


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_file(path) as handle:
        handle.write(text)


def _write_cell_result(out: Path, row: dict) -> None:
    write_json(out / "cells" / row["cell_id"] / "result.json", row)


def _input_digest(selected: list[SavedState]) -> str:
    """Freeze exactly the saved material from which this probe is rebuilt."""
    material = [dict(directory=str(item.directory.resolve()), step=item.step,
                     states=item.states, responses=item.responses, source_current=item.source_current,
                     previous_applied=item.previous_applied, episode_record=item.record)
                for item in selected]
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _source_hashes(first_round=False) -> dict[str, str]:
    files = SOURCE_ARTIFACTS + (("map_sets.py", "enrol_maps.py") if first_round else ())
    return {name: hashlib.sha256(source_path(name).read_bytes()).hexdigest() for name in files}


def _state_key(row: dict) -> tuple[str, int]:
    return str(Path(row["episode_dir"]).resolve()), int(row["step"])


def _call_cell(saved: SavedState, caller: str, arm: str, args, out: Path, budget: Invocation):
    """Return a durable result, or ``None`` when a guard refused preflight.

    A transport-reached failure always has a call record and is therefore a
    result.  A zero-attempt refusal is deliberately left absent so a later
    invocation with fresh user-approved guards can ask the cell.
    """
    size = getattr(args, "group_size", None)
    cell = _cell_id(saved, caller, arm, size)
    first_round = isinstance(caller, FirstWriter)
    if first_round:
        note = arm
        prompt, metadata = caller.prompt(saved, args.horizon, note, args.state_position, args.strip_style)
        caller = caller.framework
    else:
        note = getattr(args, "plan_note", "none")
        prompt, metadata = build_prompt(saved, caller, arm, args.horizon, protocol=args.protocol,
                                       strip_style=args.strip_style, group_size=size, plan_note=note)
    role = metadata.get("writer_role", "central" if caller == "leader" else "own")
    messages = [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": prompt}]
    cell_dir = out / "cells" / cell
    cell_dir.mkdir(parents=True, exist_ok=True)
    response = call = session = None
    try:
        from LLM import CallSession
        with CallSession(cell_dir, budget, args.model, args.fake_script, ceiling=1,
                         max_output_tokens=args.max_output_tokens, temperature=0.0,
                         reasoning_setting=args.reasoning, max_attempts=1, trace_finish=True, plan_note=note) as session:
            session.step, session.round, session.speaker = saved.step, int(first_round), metadata["robot"]
            if first_round:
                session.planning_round = 1
            session.role = role
            scope = {k: metadata[k] for k in GROUP_CALL_FIELDS if k in metadata} if "assigned_robots" in metadata else None
            response, _ = session.call(messages, scope=scope)
            call = session.records[-1]
    except StopEpisode as stop:
        if session is not None and session.records and session.records[-1].get("attempts"):
            call = session.records[-1]
            response = call.get("response")
        else:
            # No physical attempt occurred.  It is not a state asked, even if
            # CallSession persisted a refused TOKEN_LIMIT/client preflight.
            return None
        failure = dict(stop_label=stop.label, stop_detail=stop.detail)
    else:
        failure = dict(stop_label=None, stop_detail="")
    attempts = (call or {}).get("attempts", [])
    attempt = attempts[-1] if attempts else {}
    # A length/error attempt can have useful provider text even when there is
    # no accepted logical-call response.  Preserve that raw partial reply.
    if response is None:
        response = attempt.get("raw_output")
    cut_off = attempt.get("cut_off")
    row = dict(cell_id=cell, finished=True, run=saved.run, episode=saved.episode, episode_dir=str(saved.directory),
               step=saved.step, size=f"{saved.rows}x{saved.cols}", boxes_left=sum(item.startswith("box_") for items in saved.state.values() for item in items),
               caller=caller, arm=arm, horizon=args.horizon, protocol=args.protocol, plan_note=note, strip_style=args.strip_style,
               model=args.model, reasoning_setting=args.reasoning,
               physical_caller_role=role, physical_caller_name=metadata["robot"],
               messages=messages,
               prompt=prompt, reply=response, prompt_file=f"prompts/{cell}.txt", reply_file=f"replies/{cell}.txt",
               prompt_tokens=attempt.get("prompt_tokens"), generated_tokens=attempt.get("completion_tokens"),
               reasoning_tokens=attempt.get("reasoning_tokens"), cut_off=cut_off,
               visible_reply_chars=attempt.get("visible_reply_chars"), cutoff_reply_class=attempt.get("cutoff_reply_class"),
               finish_reason=attempt.get("finish_reason"), native_finish_reason=attempt.get("native_finish_reason"),
               physical_model=attempt.get("actual_model"), physical_provider=attempt.get("provider"),
               attempts=attempts, invocation=attempt.get("invocation"), **metadata, **failure)
    row.update(judge_reply(saved, caller, response, args.horizon, metadata, protocol=args.protocol))
    row["usable_reply"] = (call["status"] == "ok" and cut_off is not True and row["plan_produced"]
                           and row["not_doable_actions"] == 0)
    _write_text(out / row["prompt_file"], prompt)
    _write_text(out / row["reply_file"], response or "")
    return row


def run(args) -> list[dict]:
    if args.per_episode < 1 or args.horizon < 1 or args.jobs < 1 or args.max_output_tokens < 1:
        raise ValueError("per-episode, horizon, jobs and max-output-tokens must be positive")
    if args.max_calls is not None and args.max_calls < 0:
        raise ValueError("max-calls must be non-negative")
    if not Decimal(str(args.max_cost_usd)).is_finite() or Decimal(str(args.max_cost_usd)) < 0:
        raise ValueError("max-cost-usd must be finite and non-negative")
    first_round = getattr(args, "first_round", False)
    plan_note = getattr(args, "plan_note", "none")
    callers = selection(args.frameworks, STRUCTURES) if first_round else args.callers
    arms = selection(plan_note, PLAN_NOTES) if first_round else args.arms
    if first_round and args.protocol != "matched":
        raise ValueError("--first-round requires --protocol matched")
    if not first_round:
        validate_writer_options(args.protocol, plan_note)
    if len(set(callers)) != len(callers) or len(set(arms)) != len(arms):
        raise ValueError("Duplicate callers or arms are not allowed")
    if not first_round and (not set(callers) <= set(SUPPORTED_CALLERS) or not set(arms) <= set(ARMS)):
        raise ValueError("Unknown probe caller or arm")
    group_size = getattr(args, "group_size", None)
    has_groups = "GROUP" in callers if first_round else bool(set(callers).intersection(GROUP_CALLERS))
    if has_groups and (args.protocol != "matched" or group_size is None):
        raise ValueError("group callers require --protocol matched and --group-size G")
    if group_size is not None and not has_groups:
        raise ValueError("--group-size requires a GROUP writer")
    if args.model not in ("fake", MODEL, QWEN, SMALL_QWEN):
        raise ValueError("Unknown probe model")
    if args.fake_script not in SCRIPTS:
        raise ValueError("Unknown fake script")
    if args.model != "fake" and args.fake_script != "correct":
        raise ValueError("--fake-script requires --model fake")
    validate_reasoning(args.model, args.reasoning)
    out = local_path(args.out)
    sizes = size_filter(getattr(args, "sizes", None))
    out.mkdir(parents=True, exist_ok=True)
    # An exclusive runner lock keeps two invocations from admitting the same
    # unfinished cell.  Thread workers remain allowed inside this process.
    with locked(out / ".probe-run.lock"):
        if first_round:
            if args.episodes or not sizes:
                raise ValueError("--first-round takes --sizes and map seeds instead of --episodes")
            if has_groups:
                for size in sizes:
                    group_partition(*map(int, size.split("x")), group_size)
            selected = list(initial_states(sizes, args.map_set, seed_selection(args.envs), args.dropoff))
            requested = [(saved, writer, arm) for saved in selected
                         for writer in first_round_writers(saved, callers, group_size, args.horizon,
                                                           _doable(saved.state, saved.rows, saved.cols))
                         for arm in arms]
        else:
            selected = select_saved_states(find_episode_dirs(args.episodes), args.per_episode, sizes)
            for rows, cols in {(s.rows, s.cols) for s in selected}:
                if f"{rows}x{cols}" in SCALED_ONLY_SIZES and args.protocol != "matched":
                    raise ValueError(f"{rows}x{cols} requires --protocol matched.")
                if has_groups:
                    group_partition(rows, cols, group_size)
            requested = [(saved, caller, arm) for saved in selected for caller in callers for arm in arms]
        if not selected:
            raise ValueError("No valid saved states were selected")
        if not requested:
            raise ValueError("No probe cells were requested")
        config = dict(callers=list(callers), arms=list(arms), plan_note=plan_note,
                      horizon=args.horizon, protocol=args.protocol, strip_style=args.strip_style, model=args.model,
                      fake_script=args.fake_script, reasoning=args.reasoning, max_output_tokens=args.max_output_tokens,
                      max_attempts_per_call=1, temperature=0.0, input_digest=_input_digest(selected),
                      source_sha256=_source_hashes(first_round))
        if first_round:
            config.update(mode="first_round", map_set=selected[0].record["map_set"], envs=args.envs, dropoff=args.dropoff,
                          state_position=args.state_position, peer_source="static reference trajectory")
        else:
            config.update(episodes=args.episodes, per_episode=args.per_episode)
        if has_groups:
            config["group_size"] = group_size
        if sizes is not None:
            config["sizes"] = sizes
        if args.model != "fake":
            api = load_real_api()
            source = Path(api.__file__)
            config.update(real_client_sha256=hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None,
                          hard_episode_calls=api.HARD_EPISODE_CALLS, hard_campaign_usd=api.HARD_CAMPAIGN_USD)
        config_path = out / "config.json"
        if config_path.exists() and read_json(config_path) != config:
            raise ValueError("Saved result-generating probe configuration differs")
        write_json(config_path, config)
        if not first_round:
            write_fairness_report(out / "fairness-report.md", args.horizon)
        planned = []
        for saved, caller, arm in requested:
            item = dict(cell_id=_cell_id(saved, caller, arm, group_size), episode_dir=str(saved.directory.resolve()),
                        step=saved.step, map_set=saved.record.get("map_set", "legacy"), arm=arm)
            if first_round:
                item.update(caller=caller.framework, writer_index=caller.index, speaker=caller.speaker,
                            env_seed=saved.record["env_seed"], env_sha256=saved.record["env_sha256"], **caller.scope)
            else:
                item["caller"] = caller
                if caller in GROUP_CALLERS:
                    item["group_size"] = group_size
            if sizes is not None or saved.record["size"] in SCALED_ONLY_SIZES:
                item["size"] = saved.record["size"]
            planned.append(item)
        plan_path = out / "planned-cells.json"
        if plan_path.exists() and read_json(plan_path) != planned:
            raise ValueError("Saved planned probe cells differ")
        write_json(plan_path, planned)
        if args.shuffle is not None:
            random.Random(args.shuffle).shuffle(requested)
        # Guards are invocation-scoped, intentionally fresh on resume.  The
        # durable per-cell CallSession trace prevents a paid call from replaying.
        invocations = out / "invocations"
        invocations.mkdir(exist_ok=True)
        budget = Invocation(out, invocations / f"{uuid.uuid4().hex}.json")
        budget.create(args.max_calls, Decimal(str(args.max_cost_usd)), args.model,
                      ["reading-probe"], shuffle=args.shuffle, jobs=args.jobs)
        done = _rebuild_results_jsonl(out)
        pending = [item for item in requested if _cell_id(*item, group_size) not in done]
        completed = set(done)
        commit_lock = Lock()

        def commit(item):
            row = _call_cell(*item, args, out, budget)
            if row is not None:
                # This write is the point after which a resume must never make
                # another physical call for the cell.
                _write_cell_result(out, row)
                # Atomic checkpoint is redundant with the journal but makes the
                # completion boundary inspectable after an interrupted run.
                with commit_lock:
                    _append_jsonl(out / "results.jsonl", row)
                    completed.add(row["cell_id"])
                    write_json(out / "checkpoint.json", dict(completed=sorted(completed)))
            return row

        if args.jobs > 1:
            with ThreadPoolExecutor(max_workers=args.jobs) as pool:
                rows = list(pool.map(commit, pending))
        else:
            rows = [commit(item) for item in pending]
    return [row for row in rows if row is not None]


def _share(numerator: int, denominator: int) -> dict:
    return {"count": numerator, "denominator": denominator, "share": None if not denominator else numerator / denominator}


def summarize(out: Path, sizes=None) -> dict:
    out = local_path(out)
    with locked(out / ".probe-run.lock"):
        return _summarize_results(out, sizes)


def first_round_summary(rows, planned, config):
    def measure(group, planned_count):
        attempts = [a for row in group for a in row["attempts"] if a["api_calls"]]
        stats = dict(planned=planned_count, unasked=planned_count - len(group), attempts=len(attempts),
                     usable_replies=sum(row["usable_reply"] for row in group),
                     unknown_finish=sum(a.get("cut_off") is None for a in attempts))
        for kind in ("empty", "partial", "unknown"):
            stats["cutoff_attempts_" + kind] = sum(a.get("cut_off") is True and
                (a.get("cutoff_reply_class") or "unknown") == kind for a in attempts)
        for key, field in (("generated_tokens", "completion_tokens"), ("reasoning_tokens", "reasoning_tokens"),
                           ("visible_reply_chars", "visible_reply_chars")):
            values = [a.get(field) for a in attempts]
            stats[key] = None if None in values else sum(values)
            stats[key + "_unreported"] = values.count(None)
        return stats

    arms, cells = {}, {}
    for arm in config["arms"]:
        group = [r for r in rows if r["arm"] == arm]
        assigned = [p for p in planned if p["arm"] == arm]
        arms[arm] = measure(group, len(assigned))
        for size, framework in sorted({(p["size"], p["caller"]) for p in assigned}):
            cell = [r for r in group if (r["size"], r["caller"]) == (size, framework)]
            expected = sum((p["size"], p["caller"]) == (size, framework) for p in assigned)
            cells[f"{size}/{framework}/{arm}"] = measure(cell, expected)
    return dict(rows=len(rows), arms=arms, cells=cells)


def _summarize_results(out, sizes=None):
    rows = list(_rebuild_results_jsonl(out).values())
    config = read_json(out / "config.json")
    planned = read_json(out / "planned-cells.json") if (out / "planned-cells.json").exists() else []
    if sizes is not None:
        # Older planned cells have no size. Resolve unasked cells from their
        # source episode too, so they stay in the selected denominator.
        source_sizes = {row["episode_dir"]: row["size"] for row in rows}
        for item in planned:
            directory = item["episode_dir"]
            if "size" not in item and directory not in source_sizes:
                source_sizes[directory] = read_json(Path(directory) / "episode.json")["size"]
        planned = [p for p in planned if p.get("size", source_sizes.get(p["episode_dir"])) in sizes]
        rows = [r for r in rows if r["size"] in sizes]
    if config.get("mode") == "first_round":
        result = first_round_summary(rows, planned, config)
        if sizes is None:
            write_json(out / "summary.json", result)
        return result
    groups, paired = {}, {}
    map_sets = sorted({p.get("map_set", "legacy") for p in planned} | {r.get("map_set", "legacy") for r in rows})
    for map_set, caller in product(map_sets, config["callers"]):
        arms = {arm: {_state_key(r): r for r in rows if r.get("map_set", "legacy") == map_set
                      and r["caller"] == caller and r["arm"] == arm} for arm in config["arms"]}
        assigned = {_state_key(p) for p in planned if p.get("map_set", "legacy") == map_set and p["caller"] == caller}
        for arm in config["arms"]:
            group = arms[arm].values()
            n = len(group)
            produced = sum(r["plan_produced"] for r in group)
            wrong = sum(r["not_doable_actions"] > 0 for r in group)
            groups[f"{map_set}/{caller}/{arm}"] = dict(map_set=map_set, states_planned=len(assigned),
                states_asked=n, states_unasked=len(assigned) - n, plans_produced=_share(produced, n),
                plans_with_not_doable=_share(wrong, produced), nonplans=_share(n - produced, n),
                median_prompt_tokens=_median(group, "prompt_tokens"), median_generated_tokens=_median(group, "generated_tokens"),
                cut_offs=_share(sum(r["cut_off"] is True for r in group), n),
                unknown_cut_offs=_share(sum(r["cut_off"] is None for r in group), n))
        for left, right in combinations(config["arms"], 2):
            a, b = arms[left], arms[right]
            expected = assigned
            readable = sorted(key for key in (a.keys() & b.keys()) if a[key]["plan_produced"] and b[key]["plan_produced"])
            counts = dict(wrong_only_a=0, wrong_only_b=0, both_wrong=0, neither_wrong=0)
            for key in readable:
                x, y = a[key]["not_doable_actions"] > 0, b[key]["not_doable_actions"] > 0
                counts[("both_wrong" if x and y else "wrong_only_a" if x else "wrong_only_b" if y else "neither_wrong")] += 1
            unavailable = dict(missing_a=sum(key not in a for key in expected), missing_b=sum(key not in b for key in expected),
                               nonplan_a=sum(key in a and not a[key]["plan_produced"] for key in expected),
                               nonplan_b=sum(key in b and not b[key]["plan_produced"] for key in expected))
            paired[f"{map_set}/{caller}/{left}__{right}"] = dict(map_set=map_set, readable_both=len(readable), expected_states=len(expected),
                outcomes={name: _share(value, len(readable)) for name, value in counts.items()},
                missing_or_nonplan={name: _share(value, len(expected)) for name, value in unavailable.items()})
    result = dict(rows=len(rows), cells=groups, paired=paired)
    if "group_size" in config:
        result["group_size"] = config["group_size"]
    if sizes is None:
        write_json(out / "summary.json", result)
    return result


def _median(rows, key):
    values = [row[key] for row in rows if row.get(key) is not None]
    return statistics.median(values) if values else None


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--summarize", metavar="OUTDIR")
    p.add_argument("--episodes", help="comma-separated saved episode/run directories")
    p.add_argument("--first-round", action="store_true", help="ask each matched writer once on each selected initial map")
    p.add_argument("--frameworks", default="CMAS,OWN", help="first-round structures: CMAS,GROUP,OWN")
    p.add_argument("--map-set", default="legacy", help="first-round map registry: legacy or scaled:R")
    p.add_argument("--envs", default="0", help="first-round seeds and inclusive ranges")
    p.add_argument("--dropoff", choices=DROPOFF_MODES, default="event", help="first-round dropoff setting")
    p.add_argument("--state-position", choices=("before", "after"), default="after", help="first-round history layout")
    p.add_argument("--plan-note", default="none", help="none or continue; --first-round also accepts none,continue")
    p.add_argument("--sizes", help="limit source episodes or a probe summary to these comma-separated grid sizes")
    p.add_argument("--out", default="reading-probe")
    p.add_argument("--per-episode", type=int, default=6)
    p.add_argument("--callers", default=",".join(CALLERS), help=", ".join(SUPPORTED_CALLERS))
    p.add_argument("--group-size", type=int, metavar="G", help="robots per block for the two matched group callers")
    p.add_argument("--arms", default=",".join(ARMS))
    p.add_argument("--horizon", type=int, default=1)
    p.add_argument("--protocol", choices=("authors", "legacy", "matched"), default="authors")
    p.add_argument("--strip-style", action="store_true")
    p.add_argument("--model", default="fake")
    p.add_argument("--fake-script", default="correct")
    p.add_argument("--reasoning", default="default")
    p.add_argument("--max-output-tokens", type=int, default=8192)
    p.add_argument("--max-calls", type=int, default=None)
    p.add_argument("--max-cost-usd", type=Decimal, default=Decimal("1"))
    p.add_argument("--shuffle", type=int)
    p.add_argument("--jobs", type=int, default=1)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.summarize:
        print(json.dumps(summarize(args.summarize, size_filter(args.sizes)), indent=2))
        return
    if not args.episodes and not args.first_round:
        parser().error("--episodes, --first-round or --summarize is required")
    args.callers = tuple(s.strip() for s in args.callers.split(","))
    args.arms = tuple(s.strip() for s in args.arms.split(","))
    if not set(args.callers) <= set(SUPPORTED_CALLERS) or not set(args.arms) <= set(ARMS) or args.per_episode < 1 or args.horizon < 1 or args.jobs < 1:
        parser().error("invalid callers, arms, or positive numeric option")
    rows = run(args)
    out = local_path(args.out)
    planned = read_json(out / "planned-cells.json")
    complete = len(_finished_rows(out / "results.jsonl"))
    print(f"asked {len(rows)} cell(s) this invocation; complete {complete}/{len(planned)}; "
          f"pending or guard-refused {len(planned) - complete}.")
    if args.first_round:
        print(json.dumps(summarize(out)["arms"], indent=2))


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        parser().error(str(exc))
