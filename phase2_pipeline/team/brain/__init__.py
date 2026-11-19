"""Decision-only adapter. No simulator or peer-observation access."""

import copy
import json
import math
from pathlib import Path
import random
import re
import threading

from .llm import CallLimitError, RealLLM, check_spend_guard
from .planning import TABLES, PlanningPolicy, _json, _object
from .protocol import HUB_ROUNDS, PEER_MAX_CALLS, ZONES, ProtocolMixin, default_zones, protocol_texts
from .talk import (FREE_RULE, FREE_SUFFIX_BYTES, HOLD_S, READ_FIX_S, READ_PER_CHAR_S, SAY_FIX_S, SAY_PER_CHAR_S, SAY_STREAK_MAX, FreeChoiceMixin,  # noqa: F401
                   TalkMixin)

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


# Leader-study switches (default off: none of these sentences is shown and no option text changes).
# --leader-authority (T2 only): the leader assigns, the members follow. The information rule is unchanged: the leader writes assignments
# from its own facts and the messages it has received, nothing else is added to any prompt. An assignment is a message fact of the existing
# table "assignments" (id = the robot's name, value = {box: colour, zone: zone}), which the receiver already sees as a reported fact.
LEADER_AUTHORITY_LEADER = ("You are the leader: decide which box each robot takes and to which zone, using only what you know and what your friends "
                           "have told you, and tell each robot in your message (write each assignment as a fact: table assignments, id = the "
                           "robot's name, value {\"box\":colour,\"zone\":zone}). If you do not know enough to assign a robot, say so and let it act "
                           "on its own.")
LEADER_AUTHORITY_MEMBER = ("The leader decides which robot takes which box to which zone. When the leader tells you which box to take or which zone to "
                           "carry it to, do that instead of your own guess, unless what you see shows that it cannot be done. Where the leader has "
                           "told you nothing, act on what you know.")
# --idle-option: the pick menu's "finish" entry (its key stays 'finish') says what it is for. The goal sentence variant is in brain_server.py.
IDLE_OPTION_TEXT = ("finish: do nothing and stay here (choose this when no box I can grasp is likely to be wanted: a wrongly placed box "
                    "cancels a correctly placed one, and a robot that stays still never causes an error)")


# --options-v2: the wait entry says what waiting means (the robot stays and is asked again), and finish is told apart from it (it ends the run).
WAIT_SUFFIX = " (stand by: I keep my place and my run goes on; I am asked again when a teammate's message arrives or after about 20 s)"
FINISH_V2 = "finish: end my run now without carrying anything (I will not be asked again)"
# --route-note (T2): the prompt says who hears what (v38 did not; 182 of 729 member messages named another member and reached nobody).
ROUTE_NOTE_LEADER = "Your messages go to every teammate; your teammates' messages come only to you."
ROUTE_NOTE_MEMBER = "Your messages are delivered to the leader only, not to the other teammates; the leader's messages go to everyone."
# Rule sentence (S3 scenes; brain_server --scene-file / --scene-id; default off = the key and the goal sentence below never appear). order_rules: {robot: text}; the
# text is added to that robot's own told facts as the key "order_rule" next to "orders" (a robot not in the dict does not see it; the S3 scenes list every robot, so
# every robot is told the rule). The rule is NOT an order: _elect counts only the entries of facts["orders"], so a rule holder does not "know more orders".
# Several rules (phase-2 N=9 scenes have 3): the value is a list of texts, one per rule in the scene's order, and the key is "order_rules" (a JSON list, one sentence
# per element, next to "orders"); one rule (a bare string or a list of one) is always the single key "order_rule" with the string, as before.
# (From a work record; its --status-feed and --plan-after parts are not used: free talk replaces them.)
RULES_GOAL = (" Some orders come with a rule about the order in which boxes must be set down: a box set down against a rule does not count as delivered.")


def message_body(text):
    """The sentence a robot wrote; the raw JSON envelope (message + facts) is never shown as dialogue."""
    body = _object(text).get("message")
    return body if isinstance(body, str) else text


class _Planner(FreeChoiceMixin, PlanningPolicy):
    def __init__(self, brain):
        # --max-input-bytes (default off = 12000, the main experiment's bound): the planner's mandatory-context bound (a byte count, see PlanningPolicy._call)
        super().__init__(brain.team, len(brain.robots), client=brain.client,
                         **({"max_input_tokens": brain.max_input_bytes} if brain.max_input_bytes is not None else {}))
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
        # free talk: every message that has become readable since the robot was last asked is shown (N - 1 teammates can speak while it waits), at least the usual window
        received = [m for m in s["dialogue"] if m["from"] != s["rid"]][-(max(RECEIVED_WINDOW, s.get("fresh", 0)) if self.brain.talk else RECEIVED_WINDOW):]
        own = [m for m in s["dialogue"] if m["from"] == s["rid"]][-OWN_WINDOW:]
        return sorted(received + own, key=lambda m: m["time"])[s.get("hist_skip", 0):]      # hist_skip: the oldest messages the input bound hid (free talk, _prompt below)

    def _history_note(self, s):
        return "(%d older messages not shown)\n" % s["hist_skip"] if s.get("hist_skip") else ""

    def _prompt(self, s, module, menus=None, extra="", draft=None):
        """Free talk only: the message history is bounded by the byte budget of the input (max_input_bytes; PlanningPolicy._call counts the bytes of the string it
        sends plus 1024). The newest messages are kept and the oldest dropped one by one until the prompt, with the text _choose_free still appends, fits; a line
        "(N older messages not shown)" then says how many (recorded: events history_trimmed_prompts / history_messages_dropped). Only the display is cut. When
        the prompt does not fit even without a message, nothing more is dropped and _call raises PlanningContextError as before (mandatory context)."""
        if not self.brain.talk:
            return self._build_prompt(s, module, menus, extra, draft)
        s["hist_skip"] = 0
        prompt = self._build_prompt(s, module, menus, extra, draft)
        limit = self.max_input_tokens - 1024 - FREE_SUFFIX_BYTES - self.brain._free_suffix_extra(s["rid"])
        shown = len(self._recent(s))
        while len(prompt.encode("utf-8")) > limit and s["hist_skip"] < shown:
            s["hist_skip"] += 1
            prompt = self._build_prompt(s, module, menus, extra, draft)
        if s["hist_skip"]:
            self.brain._event("history_trimmed_prompts")
            self.brain._event("history_messages_dropped", s["hist_skip"])
        s["hist_skip"] = 0
        return prompt

    def _build_prompt(self, s, module, menus=None, extra="", draft=None):
        prompt = super()._prompt(s, module, menus, extra, draft)
        mapping = "Agent 1 means robot " + self.brain.robots[0] + "."
        if self.team == "T2" and self.brain.leader != self.brain.robots[0]:
            # A leader other than Agent 1 must be identifiable: list every agent number once.
            mapping = ", ".join("Agent %d means robot %s" % (i + 1, r)
                                for i, r in enumerate(self.brain.robots)) + "."
        prompt = prompt.replace("Agent 1 means robot 0.", mapping)
        goal = self.brain.goal_text
        if self.team in ("T1", "T2") and not self.brain.protocol:
            goal += " " + (self.brain._free_rule(s["rid"]) if self.brain.talk else MESSAGE_RULE % self.brain._cap(s["rid"]))
        prompt = prompt.replace("Goal: Transport each target box to its required zone.", "Goal: " + goal)
        if self.team == "T2" and self.brain.talk:
            prompt = prompt.replace("Agent 1 is the leader to coordinate the task.", self.brain._free_org_sentence(s["rid"]))
        elif self.team == "T2":
            index = self.brain.robots.index(self.brain.leader) + 1
            sentence = f"Agent {index} is the leader to coordinate the task."
            if self.brain.leader_authority:
                sentence += " " + (LEADER_AUTHORITY_LEADER if s["rid"] == self.brain.leader else LEADER_AUTHORITY_MEMBER)
            if self.brain.route_note:
                sentence += " " + (ROUTE_NOTE_LEADER if s["rid"] == self.brain.leader else ROUTE_NOTE_MEMBER)
            prompt = prompt.replace("Agent 1 is the leader to coordinate the task.", sentence)
        return prompt

    def _allowance(self, s):
        """T1/T2: the robot's own remaining messages (not new outside information; it is counted from its own sent messages)."""
        if self.team not in ("T1", "T2") or self.brain.protocol or self.brain.talk:
            return ""
        return "Messages left: %d\n" % max(0, self.brain._cap(s["rid"]) - self.brain._sent_by(s["rid"]))

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


class TeamBrain(ProtocolMixin, TalkMixin):
    """One instance per run; decide times must be globally nondecreasing.

    Every menu needs a wait key or text beginning with 'wait'. goal_text is
    PUBLIC text, never the evaluator's order table. max_calls is the cap PER ROBOT
    (default 150); a robot that reaches it, or whose call fails, halts alone and the
    other robots keep deciding. The client's own ceiling stays the run total.
    T2 routing: the leader's messages go to every other robot, a non-leader's
    messages go only to the leader (for two robots this is the same as T1).
    """

    def __init__(self, team, robots, goal_text, *, client=None, log_dir=None, leader=None,
                 option_order="forward", pre_exchange=False, max_messages=None, leader_max_messages=None,
                 robot_max_messages=None, leader_policy=None, leader_authority=False, idle_option=False,
                 protocol=None, hub_rounds=HUB_ROUNDS, peer_max_calls=PEER_MAX_CALLS, leader_election=False,
                 msg_delay_s=2.0, msg_loss=0.0, msg_seed=0, fail_robot=None, fail_at_s=None,
                 parser_fix=False, merge_calls=False, options_v2=False, route_note=False,
                 talk=None, say=(SAY_FIX_S, SAY_PER_CHAR_S), read=(READ_FIX_S, READ_PER_CHAR_S), say_streak_max=SAY_STREAK_MAX, leader_bind=False,
                 hold_s=HOLD_S, leader_seed=None, zones=None, max_input_bytes=None, order_rules=None, leader_route=None, multi_carry=False):
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
        self.multi_carry = multi_carry
        self.leader = leader if leader is not None else self.robots[0]
        if self.leader not in self.robots:
            raise ValueError("Leader must be in roster")
        self.max_calls = 150
        self.max_messages = MAX_MESSAGES
        # Leader-study switches (all default off = the main experiment's behaviour, byte for byte). max_messages: the cap of every robot
        # (default MAX_MESSAGES = 8). leader_max_messages: a different cap for the T2 leader only. robot_max_messages: {rid: cap} for single
        # robots. The cap of a robot is _cap(rid) = its own entry in message_caps, else max_messages; message_caps stays empty unless a
        # per-robot cap is given, and only then does the record carry `max_messages_by_robot`. leader_policy is a label for the record
        # (how the leader was chosen; the planner cannot know the orders of the other robots, so the manifest maker picks the leader).
        self.message_caps = {}
        if max_messages is not None:
            self.max_messages = self._whole_cap(max_messages, "max_messages")
        if (max_messages is not None or leader_max_messages is not None or robot_max_messages) and team not in ("T1", "T2"):
            raise ValueError("message budgets need a structure that can send messages (T1 or T2)")
        if leader_max_messages is not None:
            if team != "T2":
                raise ValueError("leader_max_messages needs team T2 (only T2 has a leader role)")
            self.message_caps[self.leader] = self._whole_cap(leader_max_messages, "leader_max_messages")
        for rid, cap in (robot_max_messages or {}).items():
            if rid not in self.robots:
                raise ValueError("robot_max_messages names a robot that is not in the roster: %s" % rid)
            if rid in self.message_caps:
                raise ValueError("two caps for robot %s (leader_max_messages and robot_max_messages)" % rid)
            self.message_caps[rid] = self._whole_cap(cap, "robot_max_messages")
        if leader_policy is not None and not isinstance(leader_policy, str):
            raise ValueError("leader_policy is a label (string)")
        self.leader_policy = leader_policy
        if leader_authority and team != "T2":
            raise ValueError("leader_authority needs team T2 (only T2 has a leader role)")
        self.leader_authority, self.idle_option = bool(leader_authority), bool(idle_option)
        # Study switches of the second experiment (all default off = v38 behaviour). protocol: 'peer-roco' (T1) or 'hub-hmas2' (T2), see
        # protocol.py. leader_election: the T2 leader is the robot that knows the most orders (ties: lowest number). msg_delay_s / msg_loss /
        # msg_seed: delivery delay of every message (default 2.0 s) and the probability that one recipient does not get it (seeded, per
        # message and recipient). fail_robot / fail_at_s: from that simulated time the robot is halted ('robot_failed'), speaks no more and
        # hears nothing. parser_fix / merge_calls / options_v2 / route_note: see planning.py and the constants above.
        if protocol not in (None, "peer-roco", "hub-hmas2"):
            raise ValueError("protocol must be 'peer-roco' or 'hub-hmas2'")
        if protocol and (team, protocol) not in (("T1", "peer-roco"), ("T2", "hub-hmas2")):
            raise ValueError("protocol %s goes with team %s" % (protocol, "T1" if protocol == "peer-roco" else "T2"))
        if protocol and (max_messages is not None or leader_max_messages is not None or robot_max_messages):
            raise ValueError("a protocol run has no message budget")
        if (leader_election or route_note) and team != "T2":
            raise ValueError("leader_election and route_note need team T2")
        if not 0.0 <= msg_loss < 1.0 or msg_delay_s < 0 or (msg_loss or msg_delay_s != 2.0) and team not in ("T1", "T2"):
            raise ValueError("msg_loss must be in [0, 1), msg_delay_s >= 0, and both need team T1 or T2")
        if (fail_robot is None) != (fail_at_s is None) or (fail_robot is not None and fail_robot not in self.robots):
            raise ValueError("fail_robot and fail_at_s go together and name a robot of the roster")
        # Phase-2 study switches (all default off = the same prompts, options, results and records as before, byte for byte; talk.py holds the free-talk text).
        # talk "free": the message route of PREREG-PHASE2.md (a say is one entry of every action list, no budget); say / read = (fixed s, s per character);
        # leader_bind: the leader's assignments bind the members; hold_s: how long a member without an assignment may only wait or speak; leader_seed: tie of
        # the election (sorted(tied)[seed % len(tied)]); zones: the zone names of the scene (default: sign11..sign13, sign11..sign(10+N) for a larger team);
        # max_input_bytes: the planner's mandatory-context bound (default 12000); order_rules: {robot: rule text, or a list of rule texts} (S3 / phase-2 scenes).
        if max_input_bytes is not None and (isinstance(max_input_bytes, bool) or int(max_input_bytes) != max_input_bytes or max_input_bytes <= 1024):
            raise ValueError("max_input_bytes must be a whole number > 1024")
        self.max_input_bytes = None if max_input_bytes is None else int(max_input_bytes)
        # zones: explicit (--zones / --scene-file) > free talk: sign11..sign(10+N) > every other run: sign11..sign13 as always (the old protocol wording and plan check)
        self._zones_given = bool(zones)
        zones = tuple(zones) if zones else (default_zones(len(self.robots)) if talk == "free" else ZONES)
        if len(set(zones)) != len(zones) or not all(isinstance(z, str) and re.fullmatch(r"sign\d+", z) for z in zones):
            raise ValueError("zones must be distinct names like sign11")
        self._talk_init(talk, tuple(say), tuple(read), say_streak_max, hold_s, leader_bind, leader_seed, zones, team, protocol, pre_exchange, option_order,
                        route_note, bool(max_messages is not None or leader_max_messages is not None or robot_max_messages), leader_authority, leader_route)
        self._ptexts = protocol_texts(self.robots, self.zones if self._zones_given else None)      # plan-format wording of a protocol run (the old constants unless zones are given)
        if self.leader_bind:
            leader_authority = self.leader_authority = True         # the binding sentences extend the authority ones
        if self.leader_seed is not None and not leader_election:
            raise ValueError("leader_seed goes with leader_election (it only breaks ties of the election)")
        self.order_rules = {}
        for r, x in dict(order_rules or {}).items():
            texts = [x] if isinstance(x, str) else list(x) if isinstance(x, (list, tuple)) else None        # a text, or one text per rule
            if r not in self.robots or not texts or not all(isinstance(t, str) and t for t in texts):
                raise ValueError("order_rules maps robots of the roster to a non-empty text or a non-empty list of non-empty texts (one per rule)")
            self.order_rules[r] = texts[0] if len(texts) == 1 else texts             # one rule is always the bare string (the single-rule prompt is unchanged)
        self.protocol, self.hub_rounds, self.peer_max_calls = protocol, int(hub_rounds), int(peer_max_calls)
        if self.hub_rounds < 0 or self.peer_max_calls < 3:
            raise ValueError("hub_rounds >= 0 and peer_max_calls >= 3")
        self.leader_election, self.route_note = bool(leader_election), bool(route_note)
        self.msg_delay_s, self.msg_loss, self.msg_seed = float(msg_delay_s), float(msg_loss), msg_seed
        self.fail_robot, self.fail_at_s = fail_robot, fail_at_s
        self.parser_fix, self.merge_calls, self.options_v2 = bool(parser_fix), bool(merge_calls), bool(options_v2)
        self._plan, self._rounds, self._epoch = None, [], 0
        self._arrived, self._pick_taken, self._replanned_for = {}, set(), set()
        # Experiment conditions (default = the study's normal behaviour; see CONDITIONS.md). option_order 'reverse' shows
        # the whole action list of every decision in reverse order (letters follow the shown order). pre_exchange makes
        # every robot write one message (message module, unchanged prompt) at its first pick decision and hold the first
        # real decision until the messages already sent to it have arrived.
        self.option_order, self.pre_exchange = option_order, bool(pre_exchange)
        self._exchange, self._skip_candidate = {}, set()
        root = Path(__file__).resolve().parent.parent / "evidence"
        self.log_dir = Path(log_dir) if log_dir is not None else root / "brain-default"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        root.mkdir(parents=True, exist_ok=True)
        self.client = client if client is not None else RealLLM(
            60, self.log_dir / "llm-calls.jsonl",
            campaign_log_path=root / "task15-calls.jsonl", campaign_max_calls=60,
            model="z-ai/glm-5.3-flash", max_output_tokens=2048)
        self._planner = _Planner(self)
        self._planner.parser_fix, self._planner.merge_calls = self.parser_fix, self.merge_calls
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
            rule = self.order_rules.get(rid)
            rule_key = "order_rule" if isinstance(rule, str) else "order_rules"       # one rule: a string; several: a list, one sentence per rule
            if rule and isinstance(value, dict) and "orders" in value and "order_rule" not in value and "order_rules" not in value:
                # the rule(s) go into the same told-facts entry as the robot's orders (right after them); only the holders get the key
                entries = []
                for key, val in value.items():
                    entries.append((key, val))
                    if key == "orders":
                        entries.append((rule_key, rule if isinstance(rule, str) else list(rule)))
                value = dict(entries)
            if self.leader_bind and isinstance(value, dict) and value.get("milestone") == "grasp_failed":
                self._grasp_failed.add(rid)             # a failed grasp lifts the binding of this member (PREREG-PHASE2.md 2)
            if self.multi_carry and self.leader_bind and isinstance(value, dict):
                self._binding_progress(rid, value)
            self._states[rid]["facts"].append(value)

    def _calls(self):
        if isinstance(self.client, RealLLM):
            return max(self.client.call_count, len(self._planner.records))
        return len(self._planner.records)

    def _calls_for(self, rid):
        """Module calls attempted for one robot (paid HTTP attempts when the client is the real one)."""
        module = sum(1 for r in self._planner.records if r["robot"] == rid)
        return max(self._paid[rid], module)

    @staticmethod
    def _whole_cap(value, name):
        if isinstance(value, bool) or int(value) != value or value < 1:
            raise ValueError("%s must be a whole number >= 1" % name)
        return int(value)

    def _cap(self, rid):
        """Message cap of one robot: its own entry (study switch), else the shared max_messages."""
        return self.message_caps.get(rid, self.max_messages)

    def _sent_by(self, rid):
        return sum(1 for m in self._messages if m["from"] == rid)

    def _sent_at(self, rid, now_s):
        """True when robot rid already sent a message at this simulated time (the same tick): one message per robot per instant."""
        return any(m["from"] == rid and abs(m["time"] - now_s) < 1e-6 for m in self._messages)

    def _may_draft(self, rid, now_s=None):
        """A talking structure, the robot below its message cap, and (given now_s) no message of its own at this same simulated
        time (T0 never drafts). The destination question and the door question of one robot can fall on the same tick: the
        second one then has no draft and no send question (real run CF2-C01-T1-r1: r1 sent two messages at 38.5 s)."""
        return (self.team in ("T1", "T2") and self._sent_by(rid) < self._cap(rid)
                and not (now_s is not None and self._sent_at(rid, now_s)))

    def _recipients(self, rid):
        others = [r for r in self.robots if r != rid]
        if self.team == "T2" and rid != self.leader:
            return [self.leader]
        return others

    def _receive(self, s, rid, now_s):
        """Rebuild what robot rid has been told by delivered messages (deliver_at <= now_s) plus its own."""
        dialogue, reported = [], {}
        assigned = {}
        # free talk: a message is shown from the time its receiver can READ it (talk.py: serial reading queue), not from its arrival
        readable = self._readable(rid) if self.talk else None
        fresh, asked = 0, s.get("asked_at", -math.inf)
        for index, m in enumerate(self._messages):
            if m["from"] != rid and not (rid in m["to"] and (m["deliver_at"] <= now_s if readable is None else readable.get(index, math.inf) <= now_s)):
                continue
            entry = {"from": m["from"], "time": m["time"], "text": message_body(m["text"])}
            if self.talk:
                entry["to"] = m["tgt"] if m["tgt"] == "everyone" else ("me" if m["from"] != rid else m["tgt"])
                fresh += m["from"] != rid and readable[index] > asked
            dialogue.append(entry)
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
                key = (table, ident, m["from"])
                if self.multi_carry and readable is not None and table == "assignments":
                    assigned.setdefault(key, []).append((readable[index], index, m["time"], value))
                else:
                    reported[key] = {"value": value, "time": m["time"]}
        for key, rows in assigned.items():
            rows.sort(key=lambda row: row[:2])      # stable within one speech
            reported[key] = {"value": {"assigned_carries": [row[3] for row in rows]}, "time": rows[-1][2]}
        s["dialogue"], s["reported"] = dialogue, reported
        if self.talk:
            s["fresh"] = fresh

    def _post(self, rid, now_s, candidate, via=None, to=None, lag=0.0):
        """Record one message (delivered 2 s later). via="chance" marks a reply written at a message chance between decisions (not
        shown to any model); a message written at a decision point (with an action, or the pre-exchange one) has no `via` key."""
        recipients, lost = (self._recipients(rid) if to is None else list(to)), []
        arrive = float(now_s) + (lag + self.msg_delay_s if lag else self.msg_delay_s)
        if self.msg_loss > 0 or self.fail_robot is not None:
            kept = []
            for r in recipients:
                gone = self._failed(r, arrive) or (
                    self.msg_loss > 0 and random.Random("%s|%d|%s|%s" % (self.msg_seed, len(self._messages), rid, r)).random() < self.msg_loss)
                (lost if gone else kept).append(r)
            recipients = kept
        message = {"time": float(now_s), "deliver_at": arrive,
                   "from": rid, "to": recipients,
                   "text": candidate}
        if lost:
            message["lost"] = lost
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
            if not (point in ("pick", "destination", "door", "report", "blocked") or (point == "next" and self.multi_carry)
                    or (point == "relay" and self.leader_route == "star" and rid == self.leader)):
                raise ValueError("Unknown decision point")
            if not math.isfinite(now_s) or now_s < self._now:
                raise ValueError("Decisions must use nondecreasing simulation time")
            options = copy.deepcopy(options)
            if self.idle_option and point == "pick":
                for o in options:
                    if o.get("key") == "finish":
                        o["text"] = IDLE_OPTION_TEXT
            if self.options_v2:
                for o in options:
                    if o.get("key") == "wait" and isinstance(o.get("text"), str):
                        o["text"] += WAIT_SUFFIX
                    elif o.get("key") == "finish" and not self.idle_option and point != "next":
                        o["text"] = "finish my carrying work here without picking another box" if self.multi_carry else FINISH_V2
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
            elif point == "next" and wait is None:
                # No body wait on a back/finish menu. On a halt the body finishes. A speech returns a transient wait.
                wait = next((o for o in options if o["key"] == "finish"), None)
            if wait is None:
                raise ValueError("Executor must offer a wait option for messaging/budget stops")
            self._now = float(now_s)
            s.update(now=float(now_s), point=point)
            if self.talk == "free":
                return self._decide_free(rid, now_s, point, options, wait)
            if self.protocol:
                result = self._decide_protocol(rid, now_s, point, options, wait)
                self._decisions[rid].append(dict(time=float(now_s), point=point, options=options, **copy.deepcopy(result)))
                self._write_record()
                return result
            before = self._calls_for(rid)
            result = dict(option=wait["key"], wait_s=0.0 if point == "report" else 2.0,
                          sent=[], calls=0)
            if self.team != "T0":
                self._receive(s, rid, now_s)
            try:
                if self._halts[rid]:
                    raise CallLimitError(self._halts[rid])
                if self._failed(rid, now_s):
                    raise CallLimitError("robot_failed")
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
            self._write_record()
            return result

    def _write_record(self):
        (self.log_dir / "brain-record.json").write_text(json.dumps(self.record(), indent=2, allow_nan=False) + "\n")

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
            if self.talk == "free":
                return self._chance_free(rid, now_s)
            result = dict(sent=[], calls=0, asked=False, final=False)
            if self.protocol or self._failed(rid, now_s):    # a protocol run talks only inside its rounds; a failed robot hears nothing
                result["final"] = True
                return result
            if self.team not in ("T1", "T2") or self._halts[rid] or self._sent_by(rid) >= self._cap(rid):
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
            if self._sent_by(rid) >= self._cap(rid):
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
            if self.leader_policy is not None:
                conditions["leader_policy"] = self.leader_policy
            if self.leader_authority:
                conditions["leader_authority"] = True
            if self.idle_option:
                conditions["idle_option"] = True
            if self.protocol:
                conditions["protocol"] = dict(mode=self.protocol, hub_rounds=self.hub_rounds, peer_max_calls=self.peer_max_calls,
                                              leader_election=self.leader_election, rounds=self._rounds)
            for name, value, default in (("msg_delay_s", self.msg_delay_s, 2.0), ("msg_loss", self.msg_loss, 0.0), ("msg_seed", self.msg_seed, 0)):
                if value != default and (self.msg_loss > 0 or self.msg_delay_s != 2.0):
                    conditions[name] = value
            if self.fail_robot is not None:
                conditions["fail"] = dict(robot=self.fail_robot, at_s=self.fail_at_s)
            for name in ("parser_fix", "merge_calls", "options_v2", "route_note", "multi_carry"):
                if getattr(self, name):
                    conditions[name] = True
            if self.talk:
                conditions.update(self._talk_conditions())
            if self._zones_given and self.zones != ZONES:
                conditions["zones"] = list(self.zones)
            if self.max_input_bytes is not None:
                conditions["max_input_bytes"] = self.max_input_bytes
            if self.order_rules:
                conditions["order_rules"] = {"holders": sorted(self.order_rules)}
                if any(isinstance(x, list) for x in self.order_rules.values()):          # several rules: how many each holder was told (a single rule adds nothing)
                    conditions["order_rules"]["rules_by_holder"] = {r: 1 if isinstance(x, str) else len(x) for r, x in sorted(self.order_rules.items())}
            talking = {}
            if self.team in ("T1", "T2"):
                talking = dict(max_messages_per_robot=self.max_messages,
                               messages_by_robot={rid: self._sent_by(rid) for rid in self.robots})
                if self.message_caps:      # only when a robot has its own cap: the shared value above is then NOT every robot's cap
                    talking["max_messages_by_robot"] = {rid: self._cap(rid) for rid in self.robots}
                if self.talk:              # free talk has no message budget: the cap of the main experiment is not part of this record
                    del talking["max_messages_per_robot"]
                    talking.update(self._talk_record())
            if any(self._chances.values()):
                talking["chances"] = self._chances
            if self.leader_election:       # the leader of the latest round (the record's `leader` is the same; every round's leader is in conditions.protocol.rounds)
                talking["elected_leader"] = self.leader
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
