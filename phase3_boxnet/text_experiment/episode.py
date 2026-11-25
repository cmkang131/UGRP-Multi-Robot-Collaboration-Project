"""Intervention, observation and scoring around the authors' planning loop."""
import copy
import importlib
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from board_sizes import validate_board
from LLM import MAX_OUTPUT_TOKENS, CallSession
from audit_news import news_source
from horizon import complete, run_rounds, validate_horizon
from limits import CALL_CEILING, OUTPUT_LIMIT, Invocation, StopEpisode
from map_events import (DROPOFF_MODES, EVENT_FILE_VERSION, agent_at, boxes, cell_key, coordinates,
                        distance, event_path, event_version, speech_fields, step_limit)
import matched_protocol as matched
from plan_parse import CORNER_MOVES, SQUARE_MOVES, PlanParser
from planning_metrics import (DMAS_RETENTIONS, ENV_STEP_LIMIT, ITERATION_LIMIT, MATCHED_CALL_CAP,
                              cutoff_records, fill_planning_counts, matched_measurements)
from prompt_env1 import input_prompt_token_limit
from relay import SPEECH_RULES, Relay, check_relay_options
from storage import code_version, digest, json_text, read_json, write_json

run_exp = importlib.import_module("env1-box-arrange").run_exp

DROPOFF_RULES = ("on", "off")
HISTORY_METHODS = {"authors": "_w_only_state_action_history", "dialogue": "_w_all_dialogue_history",
                   "none": "_wo_any_dialogue_history"}
HISTORY_DEFAULTS = dict(history_window=input_prompt_token_limit, history_method="authors", cmas_history="off")
DROPOFF_RULE_TEXT = matched.DROPOFF_RULE
CENTRAL_GOAL = "Your task is to instruct each agent to match all boxes to their color-coded targets."
LOCAL_GOAL = "achieve the goal: match each box with its color-coded target."


def history_settings(record):
    """v6–v8 and default episode bytes predate the three explicit treatment fields."""
    present = HISTORY_DEFAULTS.keys() & record.keys()
    if present and present != HISTORY_DEFAULTS.keys():
        raise ValueError("Incomplete history settings")
    fields = {k: record.get(k, v) for k, v in HISTORY_DEFAULTS.items()}
    if type(fields["history_window"]) is not int or fields["history_window"] < 0:
        raise ValueError("history_window must be a nonnegative integer")
    if fields["history_method"] not in HISTORY_METHODS or fields["cmas_history"] not in ("off", "on"):
        raise ValueError("Invalid history_method or cmas_history")
    if "history" in record and record["history"] != HISTORY_METHODS[fields["history_method"]]:
        raise ValueError("Inconsistent history method in run settings")
    return fields


def change_orders(state, assignment, kind, step, origin=None, *, dropoff="event"):
    after = copy.deepcopy(state)
    site = "dropoff" if dropoff == "always" else "drop-off"
    if kind == "e1":
        colour, dest = assignment["A"], assignment["D"]
        affected = boxes(state)[colour]
        item = f"box_{colour}"
        notice = (f"the order for boxes of colour {colour} has changed. They are no longer wanted in "
                  f"target_{colour}. They are now wanted in the {site} at square{dest}. A box_{colour} "
                  f"that is put into target_{colour} from now on counts as a wrong delivery.")
    else:
        colour, dest = assignment["A2"], assignment["D2"]
        affected = 1
        item = f"box_{colour}"
        if dropoff == "always":
            notice = (f"the box of colour {colour} that was just delivered at square{list(origin)} was not accepted. "
                      f"It is back in square{list(origin)} and is now wanted in the dropoff at square{dest}.")
        else:
            item += "_returned"
            notice = (f"the box of colour {colour} that was just delivered was not accepted. It is back "
                      f"in square{list(origin)} as {item} and is now wanted in the drop-off at square{dest}.")
        after[cell_key(origin)].append(item)
    if dropoff == "event":
        after[cell_key(dest)].append("dropoff_" + colour)
    return dict(kind=kind, step=step, A=colour, D=dest, X=list(origin) if origin is not None else None,
                affected_box=item, box_A_left=affected,
                announcement=f"Change of orders (announced after step {step}): " + notice,
                state_before=state, state_after=after)


class BoxIdentities:
    """Private e2 bookkeeping. The planner sees only the ordinary item strings."""
    def __init__(self, state):
        self.cells = {coordinates(key): defaultdict(list) for key in state}
        next_id = 0
        for square in sorted(self.cells):
            for item in state[cell_key(square)]:
                if item.startswith("box_"):
                    self.cells[square][item].append(next_id)
                    next_id += 1
        self.returned_id = None

    def restore(self, origin, item, box_id):
        self.returned_id = box_id
        self.cells[origin][item].append(box_id)

    def returned_present(self, item):
        return any(self.returned_id in cell.get(item, ()) for cell in self.cells.values())

    def apply(self, origin, item, target):
        ids = self.cells[origin][item]
        # Prefer the oldest ordinary copy, even if it arrived after the returned one.
        index = 1 if len(ids) > 1 and ids[0] == self.returned_id else 0
        box_id = ids.pop(index)
        if isinstance(target, tuple):
            self.cells[target][item].append(box_id)
        return box_id


def changed_box(event, item, box_id):
    return (event is not None and item == event["affected_box"]
            and ("returned_box_id" not in event or box_id == event["returned_box_id"]))


def dropoff_destination(target):
    return isinstance(target, str) and (target == "dropoff" or target.startswith("dropoff_"))


def delivery_outcomes(event, iterations):
    """Score actual deliveries. All actions in the triggering joint step precede the notice."""
    before = after = entitled = 0
    for step in iterations:
        ids = step.get("applied_box_ids")
        for index, (_, item, target) in enumerate(step.get("applied_actions", ())):
            if not dropoff_destination(target):
                continue
            if event is None or step["step"] <= event["step"]:
                before += 1
            elif changed_box(event, item, ids[index] if ids is not None else None):
                entitled += 1
            else:
                after += 1
    # Delivery removes a box permanently. Only boxes covered by the active order count.
    affected = event["box_A_left"] if event is not None else 0
    return dict(change_respected=int(entitled == affected) if affected else None,
                dropoff_misuse=before + after, dropoff_misuse_before=before, dropoff_misuse_after=after)


@dataclass(frozen=True)
class Spec:
    rows: int
    cols: int
    framework: str
    condition: str
    seed: int
    env_path: Path
    env_hash: str
    event_hash: str
    tell: str = "all"
    parse_mode: str = "lenient"
    event_step_override: int | None = None
    dropoff: str = "always"
    speech: str = "authors"
    dropoff_rule: str = "on"
    relay_timing: str | None = None
    relay_display: str | None = None
    history_window: int = input_prompt_token_limit
    history_method: str = "authors"
    cmas_history: str = "off"
    # None preserves the episode schema for standalone replays of pre-v10 runs.
    reasoning_setting: str | None = None
    horizon: int = 1
    max_env_steps: int | None = None
    state_position: str = "before"
    protocol: str = "legacy"
    max_planning_rounds: int | None = None
    # Unversioned standalone replays use their original episode schema.
    map_set: str | None = None
    boxes_per_robot: float | None = None
    box_count: int | None = None
    group_size: int | None = None
    plan_note: str = "none"
    failed_writer: str = "drop"
    max_stalled_rounds: int | None = None
    cut_answer: str = "discard"
    env: str = "boxnet1"
    collision: str | None = None

    def __post_init__(self):
        if self.env == "boxnet2":
            if self.collision is None:
                object.__setattr__(self, "collision", "skip")
            if self.collision not in ("skip", "fail"):
                raise ValueError("--collision must be skip or fail")
            if self.protocol != "matched" or self.condition != "static" or self.dropoff != "event":
                raise ValueError("BoxNet2 uses --protocol matched --conditions static --dropoff event")
        elif self.env != "boxnet1" or self.collision is not None:
            raise ValueError("--collision requires --env boxnet2")
        validate_board(self.size, self.map_set, self.protocol, (self.condition,))
        validate_horizon(self.horizon, self.framework)
        matched.validate_writer_options(self.protocol, self.plan_note, self.failed_writer, self.max_stalled_rounds,
                                        self.cut_answer)
        if self.failed_writer == "idle" and self.max_stalled_rounds is None:
            object.__setattr__(self, "max_stalled_rounds", matched.DEFAULT_STALLED_ROUNDS)
        if self.protocol not in ("legacy", "matched"):
            raise ValueError("Unknown planning protocol")
        if self.framework == "GROUP":
            if self.protocol != "matched":
                raise ValueError("GROUP requires --protocol matched")
            matched.group_partition(self.rows, self.cols, self.group_size)
        elif self.group_size is not None:
            raise ValueError("--group-size requires GROUP")
        if self.protocol == "matched":
            if self.framework not in ("CMAS", "OWN", "GROUP"):
                raise ValueError("--protocol matched requires CMAS, OWN or GROUP")
            if self.max_env_steps is None:
                object.__setattr__(self, "max_env_steps", matched.DEFAULT_ENV_STEPS)
            if self.max_planning_rounds is None:
                object.__setattr__(self, "max_planning_rounds", matched.DEFAULT_PLANNING_ROUNDS)
        elif self.max_planning_rounds is not None:
            raise ValueError("--max-planning-rounds requires --protocol matched")
        if self.max_planning_rounds is not None and (type(self.max_planning_rounds) is not int or self.max_planning_rounds < 0):
            raise ValueError("--max-planning-rounds must be a nonnegative integer")
        if self.max_env_steps is not None and (type(self.max_env_steps) is not int or self.max_env_steps < 0):
            raise ValueError("--max-env-steps must be a nonnegative integer")
        if self.state_position not in ("before", "after"):
            raise ValueError("--state-position must be before or after")
        history_settings(vars(self))
        if self.dropoff not in DROPOFF_MODES:
            raise ValueError(f"Unknown dropoff mode: {self.dropoff}")
        if self.speech not in SPEECH_RULES:
            raise ValueError(f"Unknown speech rule: {self.speech}")
        check_relay_options(self.speech, self.writer_framework, self.relay_timing, self.relay_display)
        if self.dropoff_rule not in DROPOFF_RULES:
            raise ValueError(f"Unknown dropoff rule: {self.dropoff_rule}")
        if self.dropoff == "event":
            object.__setattr__(self, "dropoff_rule", "off")

    @property
    def size(self):
        return f"{self.rows}x{self.cols}"

    @property
    def partition(self):
        return matched.group_partition(self.rows, self.cols, self.group_size) if self.framework == "GROUP" else None

    @property
    def writer_framework(self):
        return self.partition.writer_framework if self.framework == "GROUP" else self.framework

    @property
    def list_planning(self):
        return self.horizon > 1 or self.framework == "OWN" or self.protocol == "matched"

    @property
    def planning_settings(self):
        settings = dict(max_env_steps=self.max_env_steps, state_position=self.state_position,
                        state_position_effective=(self.state_position if self.protocol == "matched" or
                                                  self.framework in ("DMAS", "OWN") else "ignored"))
        if self.env == "boxnet2":
            settings.update(env=self.env, collision=self.collision)
        if self.protocol == "matched":
            settings.update(protocol=self.protocol, max_planning_rounds=self.max_planning_rounds,
                            plan_note=self.plan_note, failed_writer=self.failed_writer)
        if self.max_stalled_rounds is not None:
            settings["max_stalled_rounds"] = self.max_stalled_rounds
        if self.cut_answer == "prefix":
            settings["cut_answer"] = self.cut_answer
        if self.framework == "GROUP":
            settings.update(group_size=self.group_size, callers_per_round=len(self.partition.blocks))
        return settings

    @property
    def event_version(self):
        if self.map_set not in (None, "legacy"):
            return EVENT_FILE_VERSION
        return event_version(self.rows, self.cols, self.seed, self.condition)

    @property
    def relay_fields(self):
        if self.speech != "auto":
            return {}
        return dict(relay_timing=self.relay_timing or "immediate", relay_display=self.relay_display or "persistent")

    @property
    def name(self):
        condition = self.condition if self.condition == "static" else f"{self.condition}_{self.tell}"
        suffix = "" if self.speech == "authors" else "_" + self.speech
        if self.relay_timing == "turn" or self.relay_display == "once":
            suffix += f"_{self.relay_timing or 'immediate'}_{self.relay_display or 'persistent'}"
        framework = f"GROUP-g{self.group_size}" if self.framework == "GROUP" else self.framework
        return f"{self.size}_{framework}_{condition}_env{self.seed}{suffix}"


class Episode:
    def __init__(self, spec, session, state, previous, assignment, speech_map):
        self.spec, self.session, self.state = spec, session, state
        self.condition, self.assignment = spec.condition, assignment
        self.speech_map = speech_map
        self.relay = Relay(spec, speech_map["wording"])
        self.scheduled = assignment["event_step"] if spec.event_step_override is None else spec.event_step_override
        self.leader = assignment["L2"] if self.condition == "e2" else assignment["L"]
        self.member = None if self.condition == "e2" else assignment["M"]
        self.parser = PlanParser(spec.parse_mode, session.mark_rescue, record_own=session.record_own_reply,
                                 record_shape=session.record_reply_shape,
                                 syntax=CORNER_MOVES if spec.env == "boxnet2" else SQUARE_MOVES)
        self.previous = {(it.get("planning_round"), it["step"]): it for it in previous.get("iterations", [])}
        self.iterations = []
        self.round_log = []
        self.event = None
        self.correct = self.wrong = self.dropoffs = 0
        self.first_wrong_delivery_step = None
        self.steps_to_last_dropoff = None
        self.robots = [agent_at((i + .5, j + .5)) for i in range(spec.rows) for j in range(spec.cols)]
        self.box_ids = None
        if spec.dropoff == "always":
            self.state = copy.deepcopy(state)
            dest = assignment["D2"] if self.condition == "e2" else assignment["D"]
            self.state[cell_key(dest)].append("dropoff")
            if self.condition == "e2":
                self.box_ids = BoxIdentities(state)
        if self.condition == "e1" and self.scheduled == 0:
            self.fire_event(0)

    @property
    def recipients(self):
        if self.spec.tell == "all":
            return self.robots
        if self.spec.tell == "leader":
            return [self.leader]
        return [self.member] if self.member is not None else []

    def fire_event(self, step, origin=None, box_id=None):
        if self.condition == "e2":
            self.member = agent_at(origin)
        self.event = change_orders(self.state, self.assignment, self.condition, step, origin, dropoff=self.spec.dropoff)
        if self.box_ids is not None:
            self.box_ids.restore(origin, self.event["affected_box"], box_id)
            self.event["returned_box_id"] = box_id
        self.event.update(L=self.leader, M=self.member, leader_is_member=self.leader == self.member)
        self.state = self.event["state_after"]
        self.relay.prepare(self.recipients, self.robots, self.leader, step)

    def relay_after_step(self, step):
        if self.event and self.event["step"] == step:
            self.relay.forward(self)

    def finish_dialogue_turn(self):
        self.dialogue_position += 1
        if self.event and self.relay.timing == "turn":
            self.relay.forward(self, after_speaker=self.session.speaker, position=self.dialogue_position)

    def with_messages(self, prompt):
        # Insert after the authors have selected their history and before saving the prompt.
        prompt = self.relay.insert(prompt, self.session.speaker, self.session.role)
        if self.spec.dropoff_rule == "on":
            goal = CENTRAL_GOAL if self.session.role == "central" else LOCAL_GOAL
            before, anchor, after = prompt.partition(goal)
            if not anchor:
                raise ValueError("Task goal missing from addressed prompt")
            prompt = before + anchor + " " + DROPOFF_RULE_TEXT + after
        return prompt

    def address(self, robot, role):
        self.session.speaker, self.session.role = robot, role
        self.session.told = (self.event is not None and robot in self.recipients
                             and (self.spec.tell != "member" or role != "central"))
        return self.event["announcement"] + "\n" if self.session.told else ""

    def address_central(self):
        return self.address(self.leader, "central")

    def address_local(self, row, col):
        role = "review" if self.spec.framework == "HMAS-2" else "dialogue"
        return self.address(agent_at((row + 0.5, col + 0.5)), role)

    @property
    def boxes_left(self):
        return boxes(self.state).total()

    def begin_iteration(self, step, *, continuation=False):
        self.session.step, self.session.round = step, 0
        self.dialogue_position = 0
        self.iterations.append(dict(step=step, executed=False, rounds=0, calls=0, planning_seconds=None))
        if self.event:
            self.iterations[-1].update(plan_maker_call=None, plan_maker=None, plan_maker_role=None,
                                       plan_maker_told=None, plan_maker_robot_told=None,
                                       plan_maker_message_block=None, plan_maker_had_news=None)
        if self.spec.list_planning:
            self.iterations[-1]["planning_round"] = self.session.planning_round
        if continuation:
            self.iterations[-1]["planning_seconds"] = 0.0
            return
        self.start = time.monotonic()
        self.calls_before = self.session.api_calls

    def set_round(self, number):
        self.session.round = self.iterations[-1]["rounds"] = number

    def finish_planning(self):
        if not self.iterations:
            return
        current = self.iterations[-1]
        if current["planning_seconds"] is not None:
            return
        prior = self.previous.get((current.get("planning_round"), current["step"]), {})
        seconds = prior.get("planning_seconds") or 0.0
        if not prior.get("executed"):
            seconds += time.monotonic() - self.start
        current.update(planning_seconds=seconds, calls=self.session.api_calls - self.calls_before)

    def executed(self, state, issued, applied, feedback, plan_call):
        it = self.iterations[-1]
        step = it["step"]
        it.update(executed=True, issued_plan=issued, applied_actions=applied, execution_feedback=feedback)
        affected_box = self.event["affected_box"] if self.event else None
        wrong_before = self.wrong
        towards = None
        if self.event:
            present = (self.box_ids.returned_present(affected_box) if self.box_ids is not None
                       else boxes(self.state)[affected_box[4:]] > 0)
            if present:
                towards = False
        trigger = None
        if self.box_ids is not None:
            it["applied_box_ids"] = []
        for origin, item, target in applied:
            box_id = None
            if self.box_ids is not None:
                if item.startswith("box_"):
                    box_id = self.box_ids.apply(origin, item, target)
                it["applied_box_ids"].append(box_id)
            if not item.startswith("box_"):
                continue
            affected = changed_box(self.event, item, box_id)
            if isinstance(target, tuple):
                if affected and distance(target, self.event["D"]) < distance(origin, self.event["D"]):
                    towards = True
                continue
            # The physical executor accepted a matching target or a drop-off in this square.
            at_dropoff = dropoff_destination(target)
            if at_dropoff != affected:
                self.wrong += 1
                colour = self.assignment["A2" if self.condition == "e2" else "A"]
                if self.first_wrong_delivery_step is None and item.removesuffix("_returned") == "box_" + colour:
                    self.first_wrong_delivery_step = step
                continue
            self.correct += 1
            if at_dropoff:
                towards = True
                self.dropoffs += 1
                if self.dropoffs == self.event["box_A_left"]:
                    self.steps_to_last_dropoff = step - self.event["step"]
            elif self.condition == "e2" and self.event is None and trigger is None and item == "box_" + self.assignment["A2"]:
                trigger = origin, box_id

        if self.event:
            if plan_call is not None:
                call = self.session.records[plan_call - 1]
                block = self.relay.in_prompt(call["messages"][1]["content"], call["speaker"], call["role"])
                it.update(plan_maker_call=plan_call, plan_maker=call["speaker"], plan_maker_role=call["role"],
                          plan_maker_told=call["told"], plan_maker_robot_told=call["speaker"] in self.recipients,
                          plan_maker_message_block=block,
                          plan_maker_had_news=call["told"] or block)
            wrong = self.wrong > wrong_before
            if self.spec.dropoff == "event":
                # Version 3 measured a wrong-target instruction in the issued plan.
                colour = self.event["A"]
                wrong = any(re.match(rf"move\({affected_box},\s(target_{colour})\)", v) for v in issued.values())
            it.update(plan_wrong=wrong, plan_towards_dropoff=towards,
                      executed_plan_respected_change=(towards and not wrong) if towards is not None else None)

        self.state = state
        if self.condition == "e1" and step == self.scheduled:
            self.fire_event(step)
        elif trigger is not None:
            self.correct -= 1  # Cancel exactly the first delivery in the authors' execution order.
            self.fire_event(step, *trigger)
        return self.state

    def relay_measurements(self):
        first = next(iter(self.relay.deliveries.values()), None)
        wrong = self.first_wrong_delivery_step
        before = None
        if first is not None or wrong is not None:
            before = first is not None and (wrong is None or first["iteration"] <= wrong)
        producers = []
        for it in self.iterations:
            if not self.event or it["step"] <= self.event["step"]:
                continue
            number = it.get("plan_maker_call")
            source = news_source(self.session.records[number - 1], self.event) if number is not None and it["executed"] else None
            producer = dict(step=it["step"], producer_news_source=source,
                            producer_had_news=source != "none" if source is not None else None)
            if "planning_round" in it:
                producer["planning_round"] = it["planning_round"]
            producers.append(producer)
        return dict(**self.spec.relay_fields,
                    relay_delivery_iteration=first["iteration"] if first else "never",
                    relay_delivery_speaker_position=first["speaker_position"] if first else "never",
                    relay_deliveries={r["sender"]: self.relay.deliveries.get(r["sender"], "never") for r in self.relay.records},
                    first_wrong_delivery_step=wrong, delivered_before_first_wrong=before, post_event_producers=producers)

    def communication(self, calls):
        turns = dict.fromkeys(self.recipients, 0) if self.condition != "static" else {}
        post = []
        if self.event:
            post = [it for it in self.iterations if it["step"] > self.event["step"]]
            by_step = {(it.get("planning_round"), it["step"]): [] for it in post}
            for call in calls:
                key = call.get("planning_round"), call["step"]
                if call["told"] and key in by_step:
                    by_step[key].append(call)
                    turns[call["speaker"]] += 1
            site = "dropoff" if self.spec.dropoff == "always" else "dropoff_" + self.event["A"]
            markers = (site, "drop-off", "change of orders")
            for it in post:
                records = by_step[it.get("planning_round"), it["step"]]
                speakers = sorted({c["speaker"] for c in records
                                   if any(m in (c["response"] or "").lower() for m in markers)})
                it.update(told_turns=dict(Counter(c["speaker"] for c in records)),
                          mentioning_agents=speakers, told_agent_mentioned_change=bool(speakers))
                it.setdefault("executed_plan_respected_change", None)
        return turns, post

    def speaking_order(self, calls, post):
        recipients = self.recipients if self.condition != "static" else []
        framework = self.spec.writer_framework
        fixed = {}
        if framework in ("DMAS", "HMAS-1"):
            fixed = {robot: i for i, robot in enumerate(self.robots, 1) if robot in recipients}
        elif framework == "GROUP":
            order = {block[0]: i for i, block in enumerate(self.spec.partition.blocks, 1)}
            fixed = {robot: order.get(robot) for robot in recipients}
        elif framework == "CMAS":
            fixed = {robot: 1 if robot == self.leader and self.spec.tell != "member" else None
                     for robot in recipients}
        elif framework == "HMAS-2":
            for it in self.iterations:
                proposal = it.get("central_plan_agents")
                it["told_in_central_plan"] = {robot: robot in proposal if proposal is not None else None
                                              for robot in recipients}

        positions = dict.fromkeys(recipients)
        speakers = None
        if post:
            speakers = []
            slots = {}
            for call in calls:
                if (call["step"] != post["step"] or call.get("planning_round") != post.get("planning_round")
                        or call["status"] != "ok" or not call["response"]):
                    continue
                robot = call["speaker"]
                speakers.append(robot)
                # Count a central turn and a local turn as different speaking slots.
                index = slots.setdefault((call["role"], robot), len(slots) + 1)
                if call["told"] and positions[robot] is None:
                    positions[robot] = index
        return dict(told_order_positions=fixed, first_post_event_speakers=speakers,
                    first_told_speaker_positions=positions,
                    first_told_agent_spoke=any(p is not None for p in positions.values()) if post else None)

    def planning_metadata(self, label):
        if self.spec.list_planning:
            log = self.round_log
        else:
            log = []
            for it in self.iterations:
                plans = [it["issued_plan"]] if it["executed"] else []
                reason, position = "all executed", None
                if not plans:
                    reason = {"Syntactic Error": "invalid", "Hallucination of wrong plan": "parse failure",
                              OUTPUT_LIMIT: "output limit"}.get(label, label)
                    position = 1 if reason == "invalid" else None
                elif it is self.iterations[-1] and complete(self):
                    reason = "complete"
                log.append(dict(planning_round=it["step"], first_step=it["step"], proposed_plans=plans,
                                plans_proposed=len(plans), plans_executed=int(it["executed"]),
                                stop_reason=reason, invalid_position=position))
        return dict(horizon=self.spec.horizon, planning_rounds=len(log), round_log=log)

    def result(self, model, script, label, detail, interrupted):
        self.finish_planning()
        event = self.event or {}
        calls = [r for r in self.session.records[:self.session.cursor] if r["api_calls"]]
        author_calls = [r for r in calls if r["role"] != "relay"]
        relay_calls = [r for r in calls if r["role"] == "relay"]
        turns, after = self.communication(author_calls)
        post = after[0] if after else {}
        speaking = self.speaking_order(author_calls, post)
        later = [it for it in after[1:] if it["told_agent_mentioned_change"]]
        def total(field, records=calls):
            values = [r[field] for r in records]
            if any(v is None for v in values):
                return None
            if field.endswith("cost_usd"):
                return float(sum(Decimal(str(v)) for v in values))
            return sum(values)
        prompt, completion = total("prompt_tokens"), total("completion_tokens")
        relay_totals = {"relay_" + field: total(field, relay_calls) for field in
                        ("prompt_tokens", "completion_tokens", "reasoning_tokens", "cost_usd",
                         "known_prompt_tokens", "known_completion_tokens", "known_reasoning_tokens",
                         "known_reported_cost_usd", "guard_cost_usd")}
        relay_prompt, relay_completion = relay_totals["relay_prompt_tokens"], relay_totals["relay_completion_tokens"]
        relay_totals["relay_tokens"] = relay_prompt + relay_completion if None not in (relay_prompt, relay_completion) else None
        assignment = self.assignment
        return dict(episode_id=self.spec.name, code_version=code_version(self.spec.env), size=self.spec.size,
                    framework=self.spec.framework, condition=self.condition, dropoff=self.spec.dropoff,
                    dropoff_rule=self.spec.dropoff_rule,
                    tell=self.spec.tell if self.condition != "static" else None, parse=self.spec.parse_mode,
                    env_seed=self.spec.seed, env_sha256=self.spec.env_hash, event_sha256=self.spec.event_hash,
                    event_file_version=assignment["event_file_version"], max_output_tokens=self.session.max_output_tokens,
                    map_assignment=assignment, L=self.leader, M=self.member, S=assignment["S"],
                    leader_is_member=(self.leader == self.member if self.member is not None else None),
                    model=model, fake_script=script if model == "fake" else None,
                    usage_source="scripted" if model == "fake" else "api", finished=not interrupted,
                    success_failure=label, detail=detail, success=label == "success",
                    steps=sum(it["executed"] for it in self.iterations),
                    authors_env_action_times=len(self.round_log if self.spec.list_planning else self.iterations),
                    api_calls=self.session.api_calls,
                    retried_calls=sum(r["attempt_count"] > 1 for r in calls),
                    truncated_attempts=(sum(a.get("cut_off") is True for r in calls for a in r["attempts"])
                                        if self.spec.protocol == "matched" else
                                        sum(r["attempt_kinds"].count("truncated") for r in calls)),
                    prompt_tokens=prompt, completion_tokens=completion, reasoning_tokens=total("reasoning_tokens"),
                    known_prompt_tokens=total("known_prompt_tokens"), known_completion_tokens=total("known_completion_tokens"),
                    known_reasoning_tokens=total("known_reasoning_tokens"),
                    tokens=prompt + completion if prompt is not None and completion is not None else None,
                    cost_usd=total("cost_usd"),
                    known_reported_cost_usd=total("known_reported_cost_usd"),
                    guard_cost_usd=total("guard_cost_usd"), correct_deliveries=self.correct,
                    wrong_deliveries=self.wrong, boxes_left=self.boxes_left,
                    strict_success=not interrupted and self.boxes_left == 0 and self.wrong == 0,
                    **delivery_outcomes(self.event, self.iterations),
                    event_step=event.get("step"), scheduled_event_step=self.scheduled if self.condition == "e1" else None,
                    event_fired=bool(event), event_nothing_to_change=bool(event) and event["box_A_left"] == 0,
                    event_not_fired=self.condition != "static" and not event,
                    A=assignment["A"], D=assignment["D"], A2=assignment["A2"], D2=assignment["D2"],
                    box_A_left_at_event=event.get("box_A_left"),
                    first_plan_after_event_wrong=post.get("plan_wrong"),
                    first_plan_after_event_towards_dropoff=post.get("plan_towards_dropoff"),
                    steps_to_last_dropoff=self.steps_to_last_dropoff,
                    trigger_step=event.get("step") if self.condition == "e2" else None,
                    steps_to_returned_dropoff=self.steps_to_last_dropoff if self.condition == "e2" else None,
                    first_plan_returned_towards_D2=post.get("plan_towards_dropoff") if self.condition == "e2" else None,
                    post_event_calls=post.get("calls"), post_event_planning_seconds=post.get("planning_seconds"),
                    post_event_rounds=post.get("rounds"), told_turns_after_event=turns, **speaking,
                    first_told_agent_mentioned_change=post.get("told_agent_mentioned_change"),
                    first_plan_respected_change=post.get("executed_plan_respected_change"),
                    later_mention_iterations=len(later),
                    later_mention_iterations_respected=sum(it["executed_plan_respected_change"] is True for it in later),
                    lenient_rescues=sum(r["lenient_rescue"] for r in calls),
                    episode_call_ceiling=self.session.ceiling, call_ceiling=label in (CALL_CEILING, MATCHED_CALL_CAP),
                    event=self.event, final_state=self.state, iterations=self.iterations,
                    speech=self.spec.speech, **self.speech_map, relay_records=self.relay.records,
                    relay_calls=sum(c["api_calls"] for c in relay_calls),
                    relay_seconds=sum(c["elapsed_seconds"] for c in relay_calls), **relay_totals,
                    first_plan_maker_told=post.get("plan_maker_told"),
                    first_plan_maker_message_block=post.get("plan_maker_message_block"),
                    first_plan_maker_had_news=post.get("plan_maker_had_news"),
                    temperature=self.session.temperature, retry_temperature=self.session.retry_temperature)


def attach_relay_measurements(row, measurements):
    row.update({k: v for k, v in measurements.items() if k != "post_event_producers"})
    iterations = {(it.get("planning_round"), it["step"]): it for it in row["iterations"]}
    for producer in measurements["post_event_producers"]:
        key = producer.get("planning_round"), producer["step"]
        if key in iterations:
            iterations[key].update(producer)
        else:
            # Task 11 companions used only the environment step, which was then unique.
            next(it for it in row["iterations"] if it["step"] == producer["step"]).update(producer)


def admit_episode(spec, out, budget_path, max_output_tokens, temperature, retry_temperature):
    directory = out / "episodes" / spec.name
    result_path = directory / "episode.json"
    previous = read_json(result_path) if result_path.exists() else {}
    if previous and (previous["env_sha256"], previous.get("event_sha256"), previous.get("code_version")) != (
            spec.env_hash, spec.event_hash, code_version(spec.env)):
        raise ValueError(f"Saved episode inputs or code changed: {spec.name}")
    if previous and previous.get("max_output_tokens") != max_output_tokens:
        raise ValueError(f"Saved episode output-token limit changed: {spec.name}")
    if previous and previous.get("horizon", 1) != spec.horizon:
        raise ValueError(f"Saved episode horizon changed: {spec.name}")
    if previous and (previous.get("env", "boxnet1"), previous.get("collision")) != (spec.env, spec.collision):
        raise ValueError(f"Saved episode environment or collision policy changed: {spec.name}")
    if previous and previous.get("group_size") != spec.group_size:
        raise ValueError(f"Saved episode group size changed: {spec.name}")
    if previous and previous.get("cut_answer", "discard") != spec.cut_answer:
        raise ValueError(f"Saved episode cut-answer setting changed: {spec.name}")
    if previous and (previous.get("plan_note", "none"), previous.get("failed_writer", "drop"),
                     previous.get("max_stalled_rounds")) != (spec.plan_note, spec.failed_writer, spec.max_stalled_rounds):
        raise ValueError(f"Saved episode writer settings changed: {spec.name}")
    if previous and (previous.get("protocol", "legacy"), previous.get("max_planning_rounds"),
                     previous.get("map_set", "legacy")) != (spec.protocol, spec.max_planning_rounds, spec.map_set or "legacy"):
        raise ValueError(f"Saved episode protocol, round cap or map set changed: {spec.name}")
    if previous and (previous.get("state_position", "before"), previous.get("max_env_steps")) != (
            spec.state_position, spec.max_env_steps):
        raise ValueError(f"Saved state position or environment step cap changed: {spec.name}")
    if previous and previous.get("reasoning_setting", "default") != (spec.reasoning_setting or "default"):
        raise ValueError(f"Saved episode reasoning setting changed: {spec.name}")
    if previous and history_settings(previous) != history_settings(vars(spec)):
        raise ValueError(f"Saved episode history settings changed: {spec.name}")
    if previous and previous.get("dropoff") != spec.dropoff:
        raise ValueError(f"Saved episode dropoff mode changed: {spec.name}")
    if previous and previous.get("dropoff_rule") != spec.dropoff_rule:
        raise ValueError(f"Saved episode dropoff_rule changed: {spec.name}")
    if previous and (previous["speech"], previous["temperature"], previous["retry_temperature"]) != (
            spec.speech, temperature, retry_temperature):
        raise ValueError(f"Saved episode speech or temperature changed: {spec.name}")
    if previous and spec.speech == "auto" and (
            previous.get("relay_timing", "immediate"), previous.get("relay_display", "persistent")) != (
            spec.relay_timing or "immediate", spec.relay_display or "persistent"):
        raise ValueError(f"Saved episode relay settings changed: {spec.name}")
    if previous.get("finished"):
        return "skipped", previous
    budget = Invocation(out, budget_path)
    try:
        with budget.transaction() as state:
            budget.check(state)
    except StopEpisode:
        return "not started", previous
    return "started", previous


def run_episode(spec, out, budget_path, model, script, ceiling, max_output_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.0, retry_temperature=None, previous=None):
    retry_temperature = temperature if retry_temperature is None else retry_temperature
    config = read_json(out / "run.json") if (out / "run.json").is_file() else {}
    if config and (config.get("env", "boxnet1"), config.get("collision")) != (spec.env, spec.collision):
        raise ValueError("Episode environment or collision policy disagrees with run settings")
    if spec.reasoning_setting is None:
        spec = replace(spec, reasoning_setting=config.get("reasoning_setting"))
    if "horizon" in config and spec.horizon != config["horizon"]:
        raise ValueError("Episode horizon disagrees with run settings")
    if config and config.get("cut_answer", "discard") != spec.cut_answer:
        raise ValueError("Episode cut_answer disagrees with run settings")
    if spec.framework == "GROUP" and config and (
            config.get("group_size") != spec.group_size or
            config.get("group_partitions", {}).get(spec.size) != spec.partition.record()):
        raise ValueError("Episode group partition disagrees with run settings")
    for field in ("state_position", "max_env_steps", "protocol", "map_set", "max_planning_rounds",
                  "plan_note", "failed_writer", "max_stalled_rounds"):
        if field in config and getattr(spec, field) != config[field]:
            raise ValueError(f"Episode {field} disagrees with run settings")
    if previous is None:
        status, previous = admit_episode(spec, out, budget_path, max_output_tokens, temperature, retry_temperature)
        if status != "started":
            return status
    directory = out / "episodes" / spec.name
    result_path = directory / "episode.json"
    budget = Invocation(out, budget_path)
    data = spec.env_path.read_bytes()
    metadata = event_path(spec.env_path, spec.event_version).read_bytes()
    assignment = json.loads(metadata)
    if (digest(data), digest(metadata), assignment["env_sha256"]) != (spec.env_hash, spec.event_hash, spec.env_hash):
        raise ValueError(f"Environment or event digest mismatch: {spec.name}")
    if assignment.get("event_file_version") != spec.event_version:
        raise ValueError(f"Unexpected event file version: {spec.env_path}")
    state = json.loads(data)
    box_count = boxes(state).total()
    if spec.box_count is not None and spec.box_count != box_count:
        raise ValueError(f"Initial box count disagrees with enrolled map: {spec.name}")
    if assignment.get("env", "boxnet1") != spec.env:
        raise ValueError("Registered map belongs to a different environment")
    if spec.env == "boxnet2":
        speech_map = {k: assignment[k] for k in ("stratum", "wording", "member_position")}
    else:
        speech_map = speech_fields(assignment, spec.rows, spec.cols, spec.seed)
    extra = spec.env_path.with_suffix(".speech.event.json")
    if extra.exists():
        frozen = read_json(extra)
        if frozen.get("source_event_sha256") != spec.event_hash or any(frozen[k] != v for k, v in speech_map.items()):
            raise ValueError(f"Wrong speech event for {spec.name}")
        speech_map = {k: frozen[k] for k in speech_map}
    directory.mkdir(parents=True, exist_ok=True)
    with CallSession(directory, budget, model, script, ceiling, max_output_tokens, temperature, retry_temperature,
                     reasoning_setting=spec.reasoning_setting, trace_finish=spec.protocol == "matched",
                     partition_retries=spec.protocol == "matched", plan_note=spec.plan_note) as session:
        episode = Episode(spec, session, state, previous, assignment, speech_map)
        detail, interrupted = "", False
        try:
            limit, method = step_limit(spec.rows, spec.cols), HISTORY_METHODS[spec.history_method]
            if spec.list_planning:
                rounds = limit if spec.max_planning_rounds is None else spec.max_planning_rounds
                label = run_rounds(directory, episode, rounds, method)
            else:
                label = run_exp(str(directory), episode.state, spec.rows, spec.cols, limit, episode,
                                spec.framework, model, method,
                                history_window=spec.history_window if spec.history_window != input_prompt_token_limit else None,
                                cmas_history=spec.cmas_history == "on")
        except StopEpisode as stop:
            label, detail, interrupted = stop.label, stop.detail, stop.interrupted
            if spec.protocol == "matched" and label == CALL_CEILING:
                label = MATCHED_CALL_CAP
                if episode.round_log:
                    episode.round_log[-1]["stop_reason"] = label
        except re.error:
            label, detail = "Hallucination of wrong plan", "Upstream syntactic checker raised on invalid JSON/shape"
        result = episode.result(model, script, label, detail, interrupted)
        if spec.env == "boxnet2":
            result["collision_cancelled_moves"] = sum(len(it.get("collisions", ())) for it in episode.iterations
                                                      if spec.collision == "skip")
        if spec.protocol == "matched":
            result["protocol"] = spec.protocol
        if spec.map_set is not None or spec.protocol == "matched":
            result.update(map_set=spec.map_set or "legacy", boxes_per_robot=spec.boxes_per_robot, box_count=box_count)
        extended = (spec.list_planning or "state_position" in config or spec.state_position != "before"
                    or spec.max_env_steps is not None)
        if extended or "horizon" in config:
            result.update(episode.planning_metadata(label))
        if spec.list_planning:
            result["list_parser_version"] = 17 if spec.protocol == "matched" else 14
        if spec.framework == "OWN":
            forms = Counter(c["own_reply_form"] for c in session.records[:session.cursor] if c.get("own_reply_form"))
            result.update(own_reply_form_counts=dict(forms),
                          own_prefixes_kept=sum(c.get("own_reply_invalid_position") is not None
                                                for c in session.records[:session.cursor]),
                          own_unreachable_skipped=sum(b["own_unreachable_skipped"] for b in episode.round_log),
                          own_robots_dropped=sum(b["own_robots_dropped"] for b in episode.round_log))
        if spec.framework == "DMAS" and spec.horizon > 1:
            result.update({key: sum(b[key] for b in episode.round_log) for key in DMAS_RETENTIONS})
        if extended:
            fill_planning_counts(result)
            reason = "complete" if result["strict_success"] else label
            if label == ENV_STEP_LIMIT:
                reason = "environment step limit"
            elif label == ITERATION_LIMIT and not result["strict_success"]:
                reason = "iteration limit"
            result.update(**spec.planning_settings, stop_reason=reason)
            result["cut_calls"] = cutoff_records(result, session.records[:session.cursor])
            if label == ENV_STEP_LIMIT and result["round_log"]:
                result["round_log"][-1]["stop_reason"] = reason
        if spec.protocol == "matched":
            matched_measurements(result, session.records[:session.cursor])
        if spec.reasoning_setting is not None:
            providers = {a["provider"] for call in session.records[:session.cursor] for a in call["attempts"]
                         if a.get("provider")}
            result.update(reasoning_setting=spec.reasoning_setting, providers="+".join(sorted(providers)))
        settings = history_settings(vars(spec))
        if settings != HISTORY_DEFAULTS:
            result.update(settings)
        if spec.speech == "auto":
            measurements = episode.relay_measurements()
            if spec.relay_timing is not None or spec.relay_display is not None:
                attach_relay_measurements(result, measurements)
            else:
                # Keep the default episode and its author/call files replayable byte for byte.
                # Address by episode bytes so a concurrent reader can finish reading a prior partial result.
                sha = digest(json_text(result).encode())
                companion = out / "relay" / spec.name / (sha + ".json")
                companion.parent.mkdir(parents=True, exist_ok=True)
                write_json(companion, measurements)
        write_json(result_path, result)
        for filename, value in (("success_failure.txt", label),
                                ("env_action_times.txt", str(result["authors_env_action_times"])),
                                ("token_num_count.txt", "".join(
                                    f'{r["prompt_tokens"] + r["completion_tokens"]}\n'
                                    if r["prompt_tokens"] is not None and r["completion_tokens"] is not None
                                    else 'NA\n' for r in session.records[:session.cursor] if r["api_calls"]))):
            (directory / filename).write_text(value, encoding="utf-8")
        return label
