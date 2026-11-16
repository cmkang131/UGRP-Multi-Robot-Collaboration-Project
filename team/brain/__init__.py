"""Decision-only adapter. No simulator or peer-observation access."""

import copy
import json
import math
import os
from pathlib import Path
import threading

from .llm import CallLimitError, RealLLM, check_spend_guard
from .planning import TABLES, PlanningPolicy, _json, _object

PLANNER_VERSION = "brain-v3-msg4-20261116"  # 2026-11-16 03:1x KST: final pre-freeze planner (put_down, one carry, action+send, reply chance, budget 8)
# Dialogue window (audit 6d). CoELA LLM.py:488 shows the last 3 entries of one list that mixes both sides, so
# a robot's own messages push received ones out. Here a robot sees its last RECEIVED_WINDOW received messages
# plus its own last OWN_WINDOW message(s): a documented deviation from CoELA, the same for T1 and T2.
RECEIVED_WINDOW = 5
OWN_WINDOW = 1
# Message rules (user decision 2026-11-15): a robot may send a message together with any action (it does not use up the turn),
# and between decisions it is offered a message chance (see TeamBrain.chance). The cap below counts every message a robot sent
# (decision-time, between-decision and pre-exchange ones); at the cap the draft step, the send question and the chances are all
# skipped, so no call is made for them.
MAX_MESSAGES = 8
# Sentences shown only to a talking structure (T1/T2); T0 prompts are untouched (user decision 2026-11-15, second message change).
# The robot is told its own cap (the number comes from MAX_MESSAGES / TeamBrain.max_messages), what a message is for, and that
# repeats cost the team; every message prompt also shows its own remaining count ("Messages left: N", see _Planner._allowance).
# One more sentence for the reply chance between decisions (point "moving", offered when a new message has reached the robot): silence unless
# there is something to answer or something new to say.
MESSAGE_RULE = ("You can send at most %d messages in your whole run. Send a message only when it tells your teammates something "
                "they need and do not already know; repeated or unnecessary messages lower the team's score.")
CHANCE_NOTE = ("A message from my friends has just arrived and I have no decision to make right now. Write a reply only if I have "
               "something to answer or something new to tell my friends that they need and do not already know; otherwise return an "
               "empty message (\"\") for silence.")


def message_body(text):
    """The sentence a robot wrote; the raw JSON envelope (message + facts) is never shown as dialogue."""
    body = _object(text).get("message")
    return body if isinstance(body, str) else text


class _Planner(PlanningPolicy):
    def __init__(self, brain):
        super().__init__(brain.team, len(brain.robots), client=brain.client)
        self.brain = brain

    def _progress(self, s):
        progress = {"robot": s["rid"], "time": s["now"], "point": s["point"],
                    "own_facts": s["facts"], "roster": self.brain.robots}
        if s.get("reported"):
            # Facts carried by delivered messages, kept apart from own observations (own_facts).
            progress["reported_facts"] = [
                {"table": table, "id": ident, "value": row["value"],
                 "provenance": "reported by %s at %.1f s" % (sender, row["time"])}
                for (table, ident, sender), row in sorted(s["reported"].items())]
        return _json(progress)

    def _recent(self, s):
        # s["dialogue"] holds every own and delivered message, oldest first (built in TeamBrain.decide).
        received = [m for m in s["dialogue"] if m["from"] != s["rid"]][-RECEIVED_WINDOW:]
        own = [m for m in s["dialogue"] if m["from"] == s["rid"]][-OWN_WINDOW:]
        return sorted(received + own, key=lambda m: m["time"])

    def _prompt(self, s, module, menus=None, extra="", draft=None):
        prompt = super()._prompt(s, module, menus, extra, draft)
        mapping = "Agent 1 means robot " + self.brain.robots[0] + "."
        if self.team == "T2" and self.brain.leader != self.brain.robots[0]:
            # A leader other than Agent 1 must be identifiable: list every agent number once.
            mapping = ", ".join("Agent %d means robot %s" % (i + 1, r)
                                for i, r in enumerate(self.brain.robots)) + "."
        prompt = prompt.replace("Agent 1 means robot 0.", mapping)
        goal = self.brain.goal_text
        if self.team in ("T1", "T2"):
            goal += " " + MESSAGE_RULE % self.brain.max_messages
        prompt = prompt.replace("Goal: Transport each target box to its required zone.", "Goal: " + goal)
        if self.team == "T2":
            index = self.brain.robots.index(self.brain.leader) + 1
            prompt = prompt.replace("Agent 1 is the leader to coordinate the task.",
                                    f"Agent {index} is the leader to coordinate the task.")
        return prompt

    def _allowance(self, s):
        """T1/T2: the robot's own remaining messages (not new outside information; it is counted from its own sent messages)."""
        if self.team not in ("T1", "T2"):
            return ""
        return "Messages left: %d\n" % max(0, self.brain.max_messages - self.brain._sent_by(s["rid"]))

    def _moving_note(self, s):
        return " " + CHANCE_NOTE if self.team in ("T1", "T2") and s.get("point") == "moving" else ""

    def _call(self, s, module, prompt, mock):
        rid = s["rid"]
        if self.brain._calls_for(rid) >= self.brain.max_calls:
            raise CallLimitError("Robot call cap reached")
        paid = isinstance(self.client, RealLLM)
        if paid:
            # The client's own ceiling is the run total: max_calls per robot times the roster.
            self.client.max_calls = min(self.client.max_calls, self.brain.max_calls * len(self.brain.robots))
        before = self.client.call_count if paid else 0
        try:
            return super()._call(s, module, prompt, mock)
        finally:
            if paid:
                self.brain._paid[rid] += self.client.call_count - before


class TeamBrain:
    """One instance per run; decide times must be globally nondecreasing.

    Every menu needs a wait key or text beginning with 'wait'. goal_text is
    PUBLIC text, never the evaluator's order table. max_calls is the cap PER ROBOT
    (default 150); a robot that reaches it, or whose call fails, halts alone and the
    other robots keep deciding. The client's own ceiling stays the run total.
    T2 routing: the leader's messages go to every other robot, a non-leader's
    messages go only to the leader (for two robots this is the same as T1).
    """

    def __init__(self, team, robots, goal_text, *, client=None, log_dir=None, leader=None,
                 option_order="forward", pre_exchange=False):
        if team not in ("T0", "T1", "T2", "T3"):
            raise ValueError("Unknown team")
        if option_order not in ("forward", "reverse"):
            raise ValueError("option_order must be 'forward' or 'reverse'")
        if pre_exchange and team not in ("T1", "T2"):
            raise ValueError("pre_exchange needs a structure that can send messages (T1 or T2)")
        if (len(robots) < 2 or len(set(robots)) != len(robots)
                or not all(isinstance(r, str) and r for r in robots)):
            raise ValueError("Expected unique robot names")
        self.team, self.robots, self.goal_text = team, list(robots), str(goal_text)
        self.leader = leader if leader is not None else self.robots[0]
        if self.leader not in self.robots:
            raise ValueError("Leader must be in roster")
        self.max_calls = 150
        self.max_messages = MAX_MESSAGES
        # Experiment conditions (default = the study's normal behaviour; see team/README.md). option_order 'reverse' shows
        # the whole action list of every decision in reverse order (letters follow the shown order). pre_exchange makes
        # every robot write one message (message module, unchanged prompt) at its first pick decision and hold the first
        # real decision until the messages already sent to it have arrived.
        self.option_order, self.pre_exchange = option_order, bool(pre_exchange)
        self._exchange, self._skip_candidate = {}, set()
        # Evidence root: UGRP_BRAIN_EVIDENCE_DIR, default outputs/team-brain (relative to the working directory, git-ignored).
        root = Path(os.environ.get("UGRP_BRAIN_EVIDENCE_DIR", "outputs/team-brain"))
        self.log_dir = Path(log_dir) if log_dir is not None else root / "brain-default"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        root.mkdir(parents=True, exist_ok=True)
        self.client = client if client is not None else RealLLM(
            60, self.log_dir / "llm-calls.jsonl",
            campaign_log_path=root / "task15-calls.jsonl", campaign_max_calls=60,
            model="z-ai/glm-5.3-flash", max_output_tokens=2048)
        self._planner = _Planner(self)
        self._states = {}
        for rid in self.robots:
            s = self._planner._new_state(rid)
            s.update(facts=[], reported={}, point=None, now=0, isolated=True)
            self._states[rid] = s
        self._messages = []
        self._decisions = {rid: [] for rid in self.robots}
        self._halts = {rid: None for rid in self.robots}
        self._paid = {rid: 0 for rid in self.robots}
        self._chances = {rid: [] for rid in self.robots}
        self._now = -1.0
        self._lock = threading.RLock()

    def tell(self, rid, facts):
        with self._lock:
            value = json.loads(json.dumps(facts, allow_nan=False))
            self._states[rid]["facts"].append(value)

    def _calls(self):
        if isinstance(self.client, RealLLM):
            return max(self.client.call_count, len(self._planner.records))
        return len(self._planner.records)

    def _calls_for(self, rid):
        """Module calls attempted for one robot (paid HTTP attempts when the client is the real one)."""
        module = sum(1 for r in self._planner.records if r["robot"] == rid)
        return max(self._paid[rid], module)

    def _sent_by(self, rid):
        return sum(1 for m in self._messages if m["from"] == rid)

    def _sent_at(self, rid, now_s):
        """True when robot rid already sent a message at this simulated time (the same tick): one message per robot per instant."""
        return any(m["from"] == rid and abs(m["time"] - now_s) < 1e-6 for m in self._messages)

    def _may_draft(self, rid, now_s=None):
        """A talking structure, the robot below its message cap, and (given now_s) no message of its own at this same simulated
        time (T0 never drafts). The destination question and the door question of one robot can fall on the same tick: the
        second one then has no draft and no send question (real run CF2-C01-T1-r1: r1 sent two messages at 38.5 s)."""
        return (self.team in ("T1", "T2") and self._sent_by(rid) < self.max_messages
                and not (now_s is not None and self._sent_at(rid, now_s)))

    def _recipients(self, rid):
        others = [r for r in self.robots if r != rid]
        if self.team == "T2" and rid != self.leader:
            return [self.leader]
        return others

    def _receive(self, s, rid, now_s):
        """Rebuild what robot rid has been told by delivered messages (deliver_at <= now_s) plus its own."""
        dialogue, reported = [], {}
        for m in self._messages:
            if m["from"] != rid and not (rid in m["to"] and m["deliver_at"] <= now_s):
                continue
            dialogue.append({"from": m["from"], "time": m["time"], "text": message_body(m["text"])})
            if m["from"] == rid:
                continue
            facts = _object(m["text"]).get("facts")
            for fact in facts if isinstance(facts, list) else []:
                if not isinstance(fact, dict):
                    continue
                table, ident, value = fact.get("table"), fact.get("id"), fact.get("value")
                if table not in TABLES or not isinstance(ident, str) or not isinstance(value, dict):
                    continue
                # Provenance comes from the message envelope; the model's own "seen" field is not trusted.
                reported[(table, ident, m["from"])] = {"value": value, "time": m["time"]}
        s["dialogue"], s["reported"] = dialogue, reported

    def _post(self, rid, now_s, candidate, via=None):
        """Record one message (delivered 2 s later). via="chance" marks a reply written at a message chance between decisions (not
        shown to any model); a message written at a decision point (with an action, or the pre-exchange one) has no `via` key."""
        message = {"time": float(now_s), "deliver_at": float(now_s) + 2.0,
                   "from": rid, "to": self._recipients(rid),
                   "text": candidate}
        if via:
            message["via"] = via
        self._messages.append(message)
        return message

    def _exchange_hold(self, s, rid, now_s):
        """pre_exchange, pick point only. First pick decision of a robot: the message module writes one message (the
        prompt is the one a pick decision would use; the content is the model's, empty means silence) and it is sent
        without a choice step; the decision is held in either case (a silent robot still waits for the others' messages,
        which may not be sent yet when it is asked first). Later pick decisions are held while a pre-exchange message
        addressed to this robot has not arrived yet. Returns (hold, sent message or None). A robot that never reaches its
        first pick decision (nothing it can grasp) sends nothing and nobody waits for it."""
        message, first = None, rid not in self._exchange
        if first:
            self._exchange[rid] = None
            candidate = self._planner._candidate(s) if self._may_draft(rid, now_s) else None
            if candidate:
                message = self._exchange[rid] = self._post(rid, now_s, candidate)
                message["exchange"] = True                    # marks the forced message in the record (not shown to any model)
                s["actions"].append("send a message")
            else:
                self._skip_candidate.add(rid)
        pending = any(m is not None and rid in m["to"] and m["deliver_at"] > now_s for m in self._exchange.values())
        return first or pending, message

    def decide(self, rid, now_s, point, options):
        with self._lock:
            s = self._states[rid]
            if point not in ("pick", "destination", "door", "report"):
                raise ValueError("Unknown decision point")
            if not math.isfinite(now_s) or now_s < self._now:
                raise ValueError("Decisions must use nondecreasing simulation time")
            options = copy.deepcopy(options)
            if (not options or any(not isinstance(o.get("key"), str) or
                                   not isinstance(o.get("text"), str) for o in options)
                    or len({o["key"] for o in options}) != len(options)
                    or len({o["text"] for o in options}) != len(options)):
                raise ValueError("Expected nonempty unique option keys and texts")
            wait = next((o for o in options if o["key"] == "wait"), None)
            if wait is None:
                wait = next((o for o in options if o["text"].lower().startswith("wait")), None)
            if point == "report":
                wait = next((o for o in options if o["key"] == "continue"), None)
            if wait is None:
                raise ValueError("Executor must offer a wait option for messaging/budget stops")
            self._now = float(now_s)
            s.update(now=float(now_s), point=point)
            before = self._calls_for(rid)
            result = dict(option=wait["key"], wait_s=0.0 if point == "report" else 2.0,
                          sent=[], calls=0)
            if self.team != "T0":
                self._receive(s, rid, now_s)
            try:
                if self._halts[rid]:
                    raise CallLimitError(self._halts[rid])
                if self._calls_for(rid) >= self.max_calls:
                    raise CallLimitError("Robot call cap reached")
                if isinstance(self.client, RealLLM):
                    self.client.spend_guard = check_spend_guard()
                if self.team == "T3":
                    raise CallLimitError("T3 central-proposal/local-review skeleton only; execution disabled")
                hold, forced = (self._exchange_hold(s, rid, now_s) if self.pre_exchange and point == "pick"
                                else (False, None))
                if hold:
                    # pre_exchange: the forced message is out (or messages sent to this robot are still in flight): wait
                    if forced is not None:
                        result["sent"] = [copy.deepcopy(forced)]
                else:
                    if rid in self._skip_candidate:          # pre_exchange: this robot already declined to write one
                        self._skip_candidate.discard(rid)
                        candidate = None
                    else:
                        candidate = (self._planner._candidate(s) if self._may_draft(rid, now_s) and not (point == "report" and self.team == "T0")
                                     else None)
                    menu = {o["text"]: {"skill": "executor", "key": o["key"]} for o in options}
                    if self.option_order == "reverse":
                        menu = dict(reversed(list(menu.items())))
                    if point == "report" and self.team == "T0":
                        text, send, source = wait["text"], None, None
                    else:
                        text, send, source = self._planner._choose(s, menu, draft=candidate)
                    chosen = menu[text]
                    s["actions"].append(text)
                    result.update(option=chosen["key"],
                                  wait_s=2.0 if point != "report" and chosen["key"] == wait["key"] else 0.0)
                    if candidate:
                        # a draft was shown: send is True / False, or None when the answer said nothing about it (read as: not sent);
                        # send_source tells how it was read: "json" (the answer's send field), "text" (read from the answer text) or None
                        result["draft"], result["send"], result["send_source"] = True, send, source
                    if candidate and send:
                        s["actions"].append("send a message")
                        result["sent"] = [copy.deepcopy(self._post(rid, now_s, candidate))]
                        result["sent_with_action"] = True      # the message did not use up the turn (the bridge does not ask again in 2 s)
            except CallLimitError as error:
                self._halts[rid] = str(error)
                result.update(halted=True, reason=self._halts[rid])
            except Exception as error:
                self._halts[rid] = type(error).__name__
                result.update(halted=True, reason=self._halts[rid])
            result["calls"] = self._calls_for(rid) - before
            self._decisions[rid].append(dict(time=float(now_s), point=point,
                                             options=options, **copy.deepcopy(result)))
            (self.log_dir / "brain-record.json").write_text(
                json.dumps(self.record(), indent=2, allow_nan=False) + "\n")
            return result

    def chance(self, rid, now_s):
        """A reply chance between decisions (T1/T2 only): a message has reached the robot and it has no decision point open (the bridge
        offers this when /poll says a message is new and its own hooks ask nothing). One draft step, the normal message prompt plus
        CHANCE_NOTE: a non-empty message is sent at once, an empty one is silence. A chance is a planner contact like a decision:
        brain_server.py moves the robot's `seen` mark for the new-message poll after it, so one message is answered once (before
        2026-11-15 'chance on new message' the chance left it alone and the bridge offered a chance every 15 s). A message written here is
        recorded with via="chance" and does not open a chance for its receivers (brain_server.py /poll with chance=true counts only
        messages written at decision points), so one message gets at most one reply per teammate; the receivers still see it at their
        next decision, and the re-decision poll (/poll without the flag) still reacts to it. An optional step never halts
        the robot: a failed or capped chance only turns the robot's chances off. Returns dict(sent, calls, asked, final):
        asked = the model was called, final = this robot will not get another chance (T0/T3, halted, message cap, call cap, failure).
        Nothing is touched for a structure that cannot talk."""
        with self._lock:
            result = dict(sent=[], calls=0, asked=False, final=False)
            if self.team not in ("T1", "T2") or self._halts[rid] or self._sent_by(rid) >= self.max_messages:
                result["final"] = True
                return result
            if not math.isfinite(now_s) or now_s < self._now:
                raise ValueError("Decisions must use nondecreasing simulation time")
            if self._sent_at(rid, now_s):
                return result       # already spoke at this instant: no call; not final (the robot is offered chances again later)
            s = self._states[rid]
            self._now = float(now_s)
            s.update(now=float(now_s), point="moving")
            before = self._calls_for(rid)
            self._receive(s, rid, now_s)
            try:
                if self._calls_for(rid) >= self.max_calls:
                    raise CallLimitError("Robot call cap reached")
                if isinstance(self.client, RealLLM):
                    self.client.spend_guard = check_spend_guard()
                result["asked"] = True
                candidate = self._planner._candidate(s)
                if candidate:
                    s["actions"].append("send a message")
                    result["sent"] = [copy.deepcopy(self._post(rid, now_s, candidate, via="chance"))]
            except CallLimitError as error:
                result.update(final=True, reason=str(error))
            except Exception as error:
                result.update(final=True, reason=type(error).__name__)
            result["calls"] = self._calls_for(rid) - before
            if self._sent_by(rid) >= self.max_messages:
                result["final"] = True
            if result["asked"] or result.get("reason"):
                self._chances[rid].append(dict(time=float(now_s), **copy.deepcopy(result)))
                (self.log_dir / "brain-record.json").write_text(
                    json.dumps(self.record(), indent=2, allow_nan=False) + "\n")
            return result

    def record(self):
        with self._lock:
            usage = getattr(self.client, "records", [])
            unknown = sum(r.get("cost_usd") is None for r in usage)
            known = sum(r.get("cost_usd") or 0 for r in usage)
            halted = [reason for reason in self._halts.values() if reason]
            conditions = {}
            if self.option_order != "forward":
                conditions["option_order"] = self.option_order
            if self.pre_exchange:
                conditions["pre_exchange"] = True
            talking = {}
            if self.team in ("T1", "T2"):
                talking = dict(max_messages_per_robot=self.max_messages,
                               messages_by_robot={rid: self._sent_by(rid) for rid in self.robots})
            if any(self._chances.values()):
                talking["chances"] = self._chances
            return copy.deepcopy(dict(team=self.team, leader=self.leader, planner=PLANNER_VERSION,
                decisions=self._decisions, messages=self._messages,
                calls=self._calls(), module_calls=len(self._planner.records),
                calls_by_robot={rid: self._calls_for(rid) for rid in self.robots},
                max_calls_per_robot=self.max_calls, halted_by_robot=dict(self._halts),
                paid_calls=self.client.call_count if isinstance(self.client, RealLLM) else 0,
                cost_usd=None if unknown else known, known_cost_usd=known,
                unknown_cost_calls=unknown, halted=halted[0] if halted else None,
                module_records=self._planner.records, plan_events=self._planner.plan_events,
                **talking, **({"conditions": conditions} if conditions else {})))
