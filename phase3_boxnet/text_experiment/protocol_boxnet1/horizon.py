"""Joint and individual list planning on the authors' BoxNet1 environment."""
import json
import re
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

from env1_create import (MAX_REPAIRS, action_from_response, plan_feedback, square_actions,
                         state_update_func, state_update_func_local_agent, surround_index_func)
from limits import MODEL_SERVICE, OUTPUT_LIMIT, UNUSABLE_REPLY, StopEpisode
import matched_protocol as matched
from map_events import agent_at, cell_key, coordinates, distance
from plan_parse import OWN_MOVE, PLAN_AGENT, cut_reply_prefix, speaker_coordinates
from planning_metrics import (DMAS_RETENTIONS, ENV_STEP_LIMIT, ITERATION_LIMIT, MATCHED_CALL_CAP,
                              MATCHED_ENV_CAP, MATCHED_ROUND_CAP, WRITER_CAUSES, writer_block_event)
from prompt_env1 import (OWN_DIALOGUE, input_prompt_1_func_total, input_prompt_local_agent_DMAS_dialogue_func,
                         message_construct_func)

OWN_MAX_REPAIRS = 2


def validate_horizon(horizon, framework=None):
    if type(horizon) is not int or horizon < 1:
        raise ValueError("--horizon must be a positive integer")
    if horizon > 1 and framework not in (None, "CMAS", "DMAS", "OWN", "GROUP"):
        raise ValueError(f"--horizon > 1 requires CMAS, DMAS, OWN or GROUP, got {framework}")
    return horizon


def available_actions(runtime):
    rows, cols = runtime.spec.rows, runtime.spec.cols
    actions = {}
    for i in range(rows):
        for j in range(cols):
            square = (i + .5, j + .5)
            actions[agent_at(square)] = square_actions(runtime.state[cell_key(square)],
                surround_index_func(rows, cols, i, j), runtime.condition == "e2")
    return actions


def check_joint(state, plan, available, returned_only):
    """Keep the single-proposal check and close its silent malformed/off-board cases."""
    encoded = json.dumps(plan)
    try:
        feedback = plan_feedback(state, encoded, encoded, returned_only)
    except re.error:
        feedback = ""
    bad, assigned = {}, set()
    for name, move in plan.items():
        coords = PLAN_AGENT.fullmatch(name)
        square = tuple(map(float, coords.groups())) if coords else None
        agent = agent_at(square) if square else name
        action = OWN_MOVE.fullmatch(move) if isinstance(move, str) else None
        if action:
            box, site, row, col = action.groups()
            if row is not None:
                site = f"square{[float(row), float(col)]}"
            if agent not in assigned and f"move({box}, {site})" in available.get(agent, ()):
                assigned.add(agent)
                continue
        bad[name] = move
        sentence = f"Your assigned task for {cell_key(square) if square else name} is not in the doable action list; "
        if sentence not in feedback:
            feedback += sentence
    return feedback, bad


@dataclass
class Turn:
    speaker: str
    users: list
    replies: list = field(default_factory=list)
    entries: list | None = None
    call: int | None = None
    feedback: str = ""
    initial_peers: str | None = None
    members: tuple = ()
    salvaged_steps: int | None = None


class PlanningRound:
    def __init__(self, runtime, folder, number, first_step, history, method):
        self.rt, self.folder, self.history, self.method = runtime, folder, history, method
        self.spec = runtime.spec
        self.matched = self.spec.protocol == "matched"
        self.idle = self.spec.failed_writer == "idle"
        self.own = self.spec.writer_framework == "OWN"
        self.subteams = self.spec.writer_framework == "GROUP"
        self.multi_writer = self.own or self.subteams
        if self.subteams:
            self.owner = {speaker_coordinates(name): block[0] for block in self.spec.partition.blocks for name in block}
        self.dmas = self.spec.framework == "DMAS"
        self.dialogue = ""
        self.returned_only = runtime.condition == "e2"
        self.available = available_actions(runtime)
        self.agent_positions = {coordinates(key) for key in runtime.state}
        self.turns = {}
        self.log = dict(planning_round=number, first_step=first_step, plans_proposed=0, plans_executed=0,
                        effective_steps=0, empty_steps_skipped=0, discarded_steps=0,
                        proposed_plans=[], stop_reason=None, invalid_position=None, checks=[])
        if self.own:
            self.log.update(own_robots_dropped=0, own_unreachable_skipped=0)
            boxes = [coordinates(k) for k, items in runtime.state.items() if any(item.startswith("box_") for item in items)]
            self.unreachable = {agent_at(p) for p in self.agent_positions
                                if all(distance(p, box) > self.spec.horizon for box in boxes)}
        if self.dmas:
            self.log.update(dict.fromkeys(DMAS_RETENTIONS, 0))
        if self.matched:
            self.log.update(repair_calls=0, repair_calls_by_writer={}, repair_attempts=0, dropped_robots=[])
        if self.idle:
            self.log.update(writer_blocked=[], stalled=None, stall_cause=None, stall_call=None)
        if self.spec.cut_answer == "prefix":
            self.log["writer_cut_prefix"] = []
        runtime.round_log.append(self.log)

    def earlier_entries(self):
        earlier = {}
        for turn in self.turns.values():
            if self.idle and turn.entries is None:
                earlier.update((robot, []) for robot in turn.members)
            elif turn.salvaged_steps is not None and turn.entries is not None:
                earlier[turn.speaker] = turn.entries[:turn.salvaged_steps]
            else:
                earlier[turn.speaker] = turn.entries
        return earlier

    def peer_lists(self):
        return json.dumps(self.earlier_entries())

    def local_turn(self, i, j, dialogue):
        rt, spec = self.rt, self.spec
        speaker = agent_at((i + .5, j + .5))
        local, others = state_update_func_local_agent(spec.rows, spec.cols, i, j, rt.state, self.returned_only)
        notice = rt.address(speaker, "own" if self.own else "dialogue")
        prompt = input_prompt_local_agent_DMAS_dialogue_func(local, others, dialogue, *self.history, self.method,
            notice, history_window=spec.history_window, horizon=spec.horizon,
            own_horizon=spec.horizon if self.own else None, state_position=spec.state_position)
        return Turn(speaker, [rt.with_messages(prompt)], initial_peers=dialogue if self.own else None)

    def matched_turn(self, robot=None, block=None):
        rt, spec = self.rt, self.spec
        if block is not None:
            speaker, role, members = block[0], "group", block
        elif robot is None:
            speaker, role, members = rt.leader, "central", tuple(rt.robots)
        else:
            speaker = agent_at((robot[0] + .5, robot[1] + .5))
            role, members = "own", (speaker,)
        notice = rt.address(speaker, role)
        earlier = self.earlier_entries()
        prompt = matched.build_prompt(spec.rows, spec.cols, rt.state, self.history[0], self.history[1],
            horizon=spec.horizon, history_method=self.method, history_window=spec.history_window,
            state_position=spec.state_position, robot=robot, block=block, earlier=earlier, returned_only=self.returned_only,
            announcement=notice, dropoff_rule=spec.dropoff_rule, plan_note=spec.plan_note, failed_writer=spec.failed_writer)
        prompt = rt.relay.insert(prompt, speaker, role)
        return Turn(speaker, [prompt], initial_peers=json.dumps(earlier) if self.idle else None, members=members)

    def initial_turns(self):
        rt, spec = self.rt, self.spec
        if self.matched:
            if self.subteams:
                for block in spec.partition.blocks:
                    yield self.matched_turn(block=block)
            elif self.own:
                for index in range(len(rt.robots)):
                    yield self.matched_turn(divmod(index, spec.cols))
            else:
                yield self.matched_turn()
            return
        if not self.own:
            state = state_update_func(spec.rows, spec.cols, rt.state, self.returned_only)
            prompt = input_prompt_1_func_total(state, *self.history, self.method, "CMAS", rt.address_central(),
                cmas_history=spec.cmas_history == "on", horizon=spec.horizon, history_window=spec.history_window)
            yield Turn(rt.leader, [rt.with_messages(prompt)])
            return
        for index, speaker in enumerate(rt.robots):
            if spec.horizon == 1 and not self.available[speaker]:
                continue
            i, j = divmod(index, spec.cols)
            yield self.local_turn(i, j, self.peer_lists())

    def ask(self, turn, *, repair=False):
        rt = self.rt
        if repair:
            role = {"OWN": "own", "GROUP": "group", "DMAS": "dialogue", "CMAS": "central"}[self.spec.writer_framework]
            rt.address(turn.speaker, role)
            if self.matched:
                instruction = matched.REPAIR_INSTRUCTION
                if self.idle and self.log["writer_blocked"]:
                    # A repair can follow a block by a later speaker in the original sweep.
                    # Keep the original peer submissions and add any newly blocked robots.
                    peers = json.loads(turn.initial_peers)
                    missing = [robot for event in self.log["writer_blocked"] for robot in event["robots"]
                               if robot not in peers]
                    if missing:
                        peers.update((robot, []) for robot in missing)
                        instruction = (matched.EMPTY_PEER_NOTE + "\n" + OWN_DIALOGUE + json.dumps(peers)
                                       + "\n" + instruction)
            elif self.own:
                horizon = self.spec.horizon
                example = self.available[turn.speaker][:1]
                example += [None] * (horizon - len(example))
                instruction = (f"Output only a list like {json.dumps(example)} with {self.own_list_length()}, "
                               "each one action string for yourself or null.")
                instruction += "\n" + OWN_DIALOGUE + turn.initial_peers
            else:
                instruction = "Please replan the whole list for all the agents again with the same output format."
            turn.users.append(turn.feedback.rstrip() + " " + instruction)
        else:
            (self.folder / "prompt" / f"user_prompt_{self.log['first_step']}").write_text(turn.users[0])
        messages = message_construct_func(turn.users, turn.replies, "_w_all_dialogue_history")
        previous = rt.session.cursor
        try:
            scope = self.spec.partition.call_scope(turn.members, self.available) if self.spec.framework == "GROUP" else None
            reader = None
            if self.spec.cut_answer == "prefix":
                reader = partial(cut_reply_prefix, horizon=self.spec.horizon, own=self.own, speaker=turn.speaker,
                                 agent_positions={speaker_coordinates(name) for name in turn.members})
            reply, _ = rt.session.call(messages, scope=scope, prefix_reader=reader)
        finally:
            if self.matched and repair and rt.session.cursor > previous:
                self.log["repair_calls"] += 1
                self.log["repair_attempts"] += rt.session.records[previous]["api_calls"]
                writers = self.log["repair_calls_by_writer"]
                writers[turn.speaker] = writers.get(turn.speaker, 0) + 1
        call = rt.session.records[previous]
        turn.salvaged_steps = call.get("salvaged_steps")
        if turn.salvaged_steps is not None:
            event = dict(event="writer_cut_prefix", planning_round=self.log["planning_round"],
                         framework=self.spec.framework, speaker=turn.speaker, robots=list(turn.members),
                         salvaged_steps=turn.salvaged_steps, horizon=self.spec.horizon,
                         call=call["number"], attempt=call["response_from_attempt"])
            if self.spec.framework == "GROUP":
                event["group_size"] = self.spec.group_size
            self.log["writer_cut_prefix"].append(event)
        turn.replies.append(reply)
        return reply

    def own_list_length(self):
        h = self.spec.horizon
        return f"{h} {'entry' if h == 1 else 'entries'}"

    def expected_shape(self, turn):
        """A concrete, currently doable example for a matched repair."""
        if self.own:
            action = next(iter(self.available[turn.speaker]), None)
            return json.dumps([action] + [None] * (self.spec.horizon - 1))
        candidates = turn.members or tuple(self.rt.robots)
        for name in candidates:
            actions = self.available.get(name, ())
            if actions:
                return json.dumps([{name: actions[0]}] + [{}] * (self.spec.horizon - 1))
        return json.dumps([{}] * self.spec.horizon)

    def matched_parse_feedback(self, turn):
        shape = self.rt.parser.last_shape
        expected = self.expected_shape(turn)
        if shape and shape.reason == "foreign_agent":
            return f"Unknown agent named {json.dumps(shape.detail)} for this writer. Expected shape: {expected}"
        if shape and shape.reason == "wrong_length":
            return f"Wrong list length ({shape.detail}). Expected shape: {expected}"
        if shape and shape.reason == "not_list":
            return f"The reply is not a JSON list. Expected shape: {expected}"
        if shape and shape.reason == "entry_type":
            return f"Wrong entry type ({shape.detail}). Expected shape: {expected}"
        if shape and shape.reason == "multi_key":
            return f"An OWN entry has multiple keys ({shape.detail}). Use one action string or null. Expected shape: {expected}"
        detail = shape.detail if shape and shape.detail else "The reply contains no readable plan in the requested format."
        return f"{detail} Expected shape: {expected}"

    def matched_invalid_feedback(self, turn, bad):
        expected = self.expected_shape(turn)
        rejected = []
        for name, action in bad.items():
            coords = speaker_coordinates(name)
            canonical = agent_at(tuple(map(float, coords))) if coords is not None else name
            rejected.append(dict(agent=canonical, action=action, doable_actions=self.available.get(canonical, [])))
        return ("First-step actions are not doable now. Doable actions now: " + json.dumps(rejected) +
                f". Expected shape: {expected}")

    def check_first(self, turn, *, repair=False):
        rt, reply = self.rt, turn.replies[-1]
        turn.call = rt.session.cursor
        errors = []
        positions = {speaker_coordinates(name) for name in turn.members} if self.subteams else self.agent_positions
        parsed = rt.parser.sequence(reply, self.spec.horizon, own=self.own, dialogue=self.dmas, speaker=turn.speaker,
                                    agent_positions=positions, format_errors=errors, matched_shape=self.matched)
        turn.entries = parsed
        if turn.entries is None or (not turn.entries and not complete(rt)):
            turn.entries = None
            if self.own:
                turn.feedback = f"Your reply could not be read as a JSON list of {self.own_list_length()}."
            elif errors:
                turn.feedback = "Joint plan format error. " + errors[0]
            else:
                turn.feedback = plan_feedback(rt.state, None, reply, self.returned_only)
            status, bad = "parse failure", {}
        else:
            first = turn.entries[0] if turn.entries else {}
            plan = first
            if self.own:
                plan = {turn.speaker: first} if first is not None else {}
            turn.feedback, bad = check_joint(rt.state, plan, self.available, self.returned_only)
            status = "invalid" if turn.feedback else "valid"
            if self.multi_writer and turn.feedback:
                if self.own and not self.matched:
                    turn.feedback = (f"Your first entry {json.dumps(first)} is not in your doable action list "
                                     f"{json.dumps(self.available[turn.speaker])}. Choose from that list or use null.")
                turn.entries = None
        if self.matched:
            if status == "parse failure":
                turn.feedback = self.matched_parse_feedback(turn)
            elif status == "invalid":
                turn.feedback = self.matched_invalid_feedback(turn, bad)
        check = dict(call=turn.call, speaker=turn.speaker, repair=repair, status=status, rejected_actions=bad)
        if errors and turn.entries is None and not self.own:
            check["feedback"] = turn.feedback
        self.log["checks"].append(check)
        if not self.multi_writer and (not self.dmas or repair):
            self.log.update(final_call=turn.call, final_speaker=turn.speaker)
        return parsed

    def consider_dmas_submission(self, turn):
        parsed = self.check_first(turn)
        previous = next(iter(self.turns.values()), None)
        if previous is not None and previous.entries is not None:
            if parsed is not None and not any(parsed) and any(previous.entries):
                self.log["dmas_empty_overwrites_prevented"] += 1
                return
            if turn.entries is None:
                self.log["dmas_unparsable_overwrites_prevented"] += 1
                return
        # Until a parsable plan exists, the last refusal identifies the writer to repair.
        self.turns = {turn.speaker: turn}
        self.log.update(final_speaker=turn.speaker, final_call=turn.call, final_submission_call=turn.call)
        self.record_proposal()

    def discuss(self):
        # EXECUTE still breaks only the authors' inner (column) loop.
        for sweep in range(1, 5):
            self.rt.set_round(sweep)
            for i in range(self.spec.rows):
                for j in range(self.spec.cols):
                    turn = self.local_turn(i, j, self.dialogue)
                    reply = self.ask(turn)
                    self.dialogue += f"[{turn.speaker}: {reply}]\n\n"
                    submitted = "EXECUTE" in reply
                    if submitted:
                        self.consider_dmas_submission(turn)
                    self.rt.finish_dialogue_turn()
                    if submitted:
                        break
            if self.turns:
                return
        self.log["stop_reason"] = "no agreement"

    def merged_plans(self):
        if not self.multi_writer:
            entries = next(iter(self.turns.values())).entries
            if self.idle and entries is None:
                return [{} for _ in range(self.spec.horizon)]
            return entries or []
        if self.subteams:
            steps = [{} for _ in range(self.spec.horizon)]
            for turn in self.turns.values():
                for joint, block_step in zip(steps, turn.entries or ()):
                    joint.update(block_step)
            return steps
        return [{s: t.entries[i] for s, t in self.turns.items() if t.entries is not None and t.entries[i] is not None}
                for i in range(self.spec.horizon)]

    def action_call(self, agent):
        if self.subteams:
            return self.turns[self.owner[speaker_coordinates(agent)]].call
        return self.turns[agent].call if self.own else self.log["final_call"]

    def record_proposal(self):
        plans = self.merged_plans()
        self.log.update(proposed_plans=plans, plans_proposed=len(plans))
        return plans

    def required_writer(self, turn):
        return any(self.available[name] for name in turn.members)

    def drop_writer(self, turn):
        check = self.log["checks"][-1]
        if self.own:
            self.log["own_robots_dropped"] += 1
            check["own_dropped"] = True
        elif self.subteams:
            check["group_dropped"] = True
        if self.matched:
            self.log["dropped_robots"].extend(turn.members)
        turn.feedback = ""
        turn.entries = None

    def block_writer(self, turn):
        checks = [c for c in self.log["checks"] if c["speaker"] == turn.speaker]
        calls = [self.rt.session.records[c["call"] - 1] for c in checks]
        event = writer_block_event(self.spec.framework, turn.members, self.required_writer(turn), checks[-1]["status"], calls)
        self.log["writer_blocked"].append(event)
        self.drop_writer(turn)

    def read_writer(self, turn, *, repair=False):
        try:
            self.ask(turn, repair=repair)
        except StopEpisode as stop:
            if self.idle and not stop.interrupted and stop.label in (OUTPUT_LIMIT, UNUSABLE_REPLY):
                turn.call = self.rt.session.cursor
                self.log["checks"].append(dict(call=turn.call, speaker=turn.speaker, repair=repair,
                                               status=stop.label, rejected_actions={}))
                self.block_writer(turn)
                return
            if (self.spec.failed_writer != "fail" or stop.interrupted or
                    stop.label not in (OUTPUT_LIMIT, UNUSABLE_REPLY, MODEL_SERVICE)):
                raise
            turn.call = self.rt.session.cursor
            if self.required_writer(turn):
                self.log.update(failed_speaker=turn.speaker, failed_call=turn.call)
                raise
            self.log["checks"].append(dict(call=turn.call, speaker=turn.speaker, repair=repair,
                                           status=stop.label, rejected_actions={}, optional_writer_dropped=True))
            self.drop_writer(turn)
            return
        self.check_first(turn, repair=repair)

    def repair_writers(self):
        limit = matched.REPAIRS_PER_WRITER if self.matched else OWN_MAX_REPAIRS
        for attempt in range(1, limit + 1):
            for turn in self.turns.values():
                if not turn.feedback:
                    continue
                self.read_writer(turn, repair=True)
                if self.multi_writer:
                    self.rt.finish_dialogue_turn()
                if attempt == limit and turn.feedback:
                    if self.idle:
                        self.block_writer(turn)
                    elif (self.required_writer(turn) if self.spec.failed_writer == "fail" else not self.multi_writer):
                        status = self.log["checks"][-1]["status"]
                        plans = self.record_proposal()
                        self.log.update(stop_reason=status, invalid_position=1 if status == "invalid" else None,
                                        discarded_steps=len(plans))
                        if self.spec.failed_writer == "fail":
                            self.log.update(failed_speaker=turn.speaker, failed_call=turn.call)
                        raise StopEpisode("Syntactic Error")
                    else:
                        self.drop_writer(turn)
                self.record_proposal()

    def propose(self):
        if self.dmas:
            self.discuss()
            if not self.turns:
                return []
        else:
            for turn in self.initial_turns():
                self.turns[turn.speaker] = turn
                self.read_writer(turn)
                if self.multi_writer:
                    if (not self.matched and turn.feedback and not self.available[turn.speaker]
                            and turn.speaker in self.unreachable):
                        turn.feedback = ""
                        self.log["own_unreachable_skipped"] += 1
                        self.log["checks"][-1]["repair_skipped"] = "no box within horizon"
                    self.rt.finish_dialogue_turn()
        self.record_proposal()
        if self.multi_writer or self.matched:
            self.repair_writers()
            return self.log["proposed_plans"]

        turn, = self.turns.values()
        limit = MAX_REPAIRS
        for attempt in range(1, limit + 1):
            if not turn.feedback:
                break
            self.ask(turn, repair=True)
            if attempt < limit:
                self.check_first(turn, repair=True)
            self.record_proposal()
        if turn.feedback:
            unparsable = turn.entries is None
            self.log.update(stop_reason="parse failure" if unparsable else "invalid",
                            invalid_position=None if unparsable else 1, discarded_steps=self.log["plans_proposed"])
            raise StopEpisode("Syntactic Error")
        return self.log["proposed_plans"]

    def execute(self, plans):
        rt = self.rt
        responses, states, dialogues = self.history
        rt.finish_planning()
        transcript = self.peer_lists() if self.multi_writer else self.dialogue
        for position, plan in enumerate(plans, 1):
            if complete(rt):
                break
            if not plan and (self.matched or self.spec.horizon > 1):
                self.log["empty_steps_skipped"] += 1
                continue
            available = self.available if position == 1 else available_actions(rt)
            feedback, bad = check_joint(rt.state, plan, available, self.returned_only)
            if feedback:
                self.log.update(stop_reason="invalid", invalid_position=position, feedback=feedback,
                                discarded_steps=len(plans) - position + 1,
                                rejected_actions=bad, rejected_calls={agent: self.action_call(agent) for agent in bad})
                return
            applied = []
            feedback, state = action_from_response(rt.state, plan, applied, returned_only=self.returned_only)
            if feedback or len(applied) != len(plan):
                raise ValueError("BoxNet1 executor disagrees with its checked doable actions")
            first_executed = self.log["plans_executed"] == 0
            step = len(states)
            if not first_executed:
                rt.begin_iteration(step, continuation=True)
            row = rt.iterations[-1]
            if self.multi_writer:
                row["action_calls"] = {agent: self.action_call(agent) for agent in plan}
            plan_call = None if self.multi_writer else self.log["final_call"]
            state = rt.executed(state, plan, applied, feedback, plan_call)
            responses.append(json.dumps(plan))
            states.append(state)
            dialogues.append(transcript if first_executed else "")
            (self.folder / "response" / f"response{step}.json").write_text(responses[-1])
            (self.folder / "pg_state" / f"pg_state{step + 1}.json").write_text(json.dumps(state))
            if self.multi_writer or self.dmas:
                (self.folder / "dialogue_history" / f"dialogue_history{step - 1}.txt").write_text(dialogues[-1])
            self.log["plans_executed"] += 1
            self.log["effective_steps"] += int(bool(applied))
            rt.relay_after_step(step)
            if step == self.spec.max_env_steps and not complete(rt):
                self.log["stop_reason"] = "environment step limit"
                return
        if complete(rt):
            self.log["stop_reason"] = "complete"
        elif plans and not plans[-1] and (self.matched or self.spec.horizon > 1):
            self.log["stop_reason"] = "empty tail" if self.log["effective_steps"] else "all empty"
        elif self.log["stop_reason"] is None:
            self.log["stop_reason"] = "all executed"

    def stall_label(self):
        """A terminal service error or an interrupted planning sweep never reaches this check."""
        self.log["stalled"] = self.log["effective_steps"] == 0
        if not self.log["stalled"]:
            return None
        # A rejected merged step follows writing and can itself prevent the first action.
        if self.log["stop_reason"] == "invalid":
            self.log["stall_cause"] = WRITER_CAUSES["invalid"]
            return "Syntactic Error"
        for event in reversed(self.log["writer_blocked"]):
            if event["required"]:
                self.log.update(stall_cause=event["cause"], stall_call=event["call"])
                return event["end_label"]
        self.log["stall_cause"] = "no actions proposed"
        return self.log["stall_cause"]


def complete(runtime):
    if runtime.condition == "static" and runtime.spec.dropoff == "event":
        return not any(runtime.state.values())
    return runtime.boxes_left == 0


def run_rounds(directory, runtime, limit, method):
    folder = Path(directory)
    for name in ("prompt", "response", "pg_state", "dialogue_history"):
        (folder / name).mkdir(exist_ok=True)
    history = ([], [runtime.state], [])
    (folder / "pg_state" / "pg_state1.json").write_text(json.dumps(runtime.state))
    is_matched = runtime.spec.protocol == "matched"
    if runtime.spec.max_env_steps == 0:
        return "success" if complete(runtime) else (MATCHED_ENV_CAP if is_matched else ENV_STEP_LIMIT)
    if is_matched and (not limit or complete(runtime)):
        return "success" if complete(runtime) else MATCHED_ROUND_CAP
    if is_matched and runtime.session.ceiling == 0:
        return MATCHED_CALL_CAP
    if runtime.spec.history_window == 0:
        method = "_wo_any_dialogue_history"
    runtime.relay_after_step(0)
    consecutive_stalls = 0
    for number in range(1, limit + 1):
        step = len(history[1])
        runtime.session.planning_round = number
        runtime.begin_iteration(step)
        runtime.set_round(1)
        batch = PlanningRound(runtime, folder, number, step, history, method)
        try:
            batch.execute(batch.propose())
        except StopEpisode as stop:
            if batch.log["stop_reason"] is None:
                batch.log["stop_reason"] = "output limit" if stop.label == OUTPUT_LIMIT else stop.label
            if batch.log["plans_proposed"] and any(t.feedback and t.entries is not None for t in batch.turns.values()):
                batch.log.update(invalid_position=1, discarded_steps=batch.log["plans_proposed"])
            raise
        if batch.idle:
            stall_label = batch.stall_label()
            consecutive_stalls = consecutive_stalls + 1 if stall_label else 0
            if consecutive_stalls == runtime.spec.max_stalled_rounds:
                return stall_label
        if complete(runtime):
            break
        if batch.log["stop_reason"] == "environment step limit":
            return MATCHED_ENV_CAP if is_matched else ENV_STEP_LIMIT
        if is_matched and runtime.session.api_calls >= runtime.session.ceiling:
            return MATCHED_CALL_CAP
    if is_matched:
        return "success" if complete(runtime) else MATCHED_ROUND_CAP
    return "success" if number < limit else ITERATION_LIMIT
