"""Protocol mode (study switch --protocol, default off): the team talks the way the prior work does.

  peer-roco : equal structure (T1), RoCo dialog mode / Chen DMAS. Robots speak in number order, one utterance per call; an utterance ends
              with PROCEED (hand over) or EXECUTE + the joint plan. First attempt: EXECUTE is accepted only after every robot has spoken
              at least once (RoCo dialog_prompter.py:234-237). At most `peer_max_calls` calls (RoCo code: 10), checked at the start of a
              cycle like the code; the call with index peer_max_calls-1 gets the "last call: you must end with EXECUTE" sentence.
  hub-hmas2 : leader structure (T2), Chen HMAS-2 (and CMAS when hub_rounds = 0). The leader proposes the plan of every robot, the other
              robots review it in number order (each sees the plan and its own state only, answers exactly "I Agree" or an objection),
              the objections go to the leader in one batch, the leader revises; at most `hub_rounds` (code: 3) review rounds, then the
              latest plan is executed (no failure).
Both write one JSON plan {"r1": {"box": colour, "zone": zone} | "stay", ...} that each robot reads at its own decision points.
The dialogue costs no simulated time (like a decision); utterances are recorded as messages (via="protocol") with a delivery time and a
recipient list, so message delay, message loss and a failed robot act on them like on any message. Rounds open at the first pick decision
(joint: every robot is held until all have asked, with a time-out) and at a pick decision after a lost grasp.

This module holds the prompt wording, the plan parser and the round engine (a mixin of TeamBrain). Nothing here runs unless
TeamBrain(protocol=...) is given.
"""
import copy
import json
import re

from .llm import CallLimitError
from .planning import HEAD

ZONES = ("sign11", "sign12", "sign13")
COLOURS = ("red", "blue")


def default_zones(n):
    """Zones of a team of n robots when no scene gives them (study switch --zones / --scene-file): the three wall signs sign11..sign13 as always
    (also for 2 robots), and sign11..sign(10+n) for a larger team (a generated map has one sign per robot)."""
    return ZONES if n <= 3 else tuple("sign%d" % (10 + i) for i in range(1, n + 1))
HOLD_S = 4.0            # a joint round opens when every robot has asked, or this many simulated seconds after the first one asked
PEER_MAX_CALLS = 10     # RoCo code: max_calls_per_round (run_dialog.py:144)
HUB_ROUNDS = 3          # Chen HMAS-2 code: count_round_HMAS2 < 3 (env2/3/4-box-arrange.py)
SYNTAX_RETRIES = 2      # Chen re-prompts a plan it cannot read (code: up to 6); ours is smaller, see PREREG
UTTERANCE_CHARS = 600   # an utterance is cut here before it enters later prompts (12 utterances x 600 + the base prompt stay under the 12000-byte bound; the record keeps the full text)

def plan_format(robots=("r1", "r2", "r3"), zones=ZONES):
    """The plan format sentence with an example of one entry per robot (one more than that: the last robot "stays"). The default roster and zones give
    the text of the three-robot experiments (a test pins it)."""
    entries = ['"%s": "stay"' % rid if i == len(robots) - 1 else '"%s": {"box": "%s", "zone": "%s"}' % (rid, COLOURS[i % len(COLOURS)], zones[i % len(zones)])
               for i, rid in enumerate(robots)]
    return ('one JSON object with one entry for every robot of the team, e.g. {' + ", ".join(entries) + '}; an entry is {"box": colour, "zone": zone} (the robot carries one '
            'box of that colour to that zone) or "stay" (the robot does nothing and its run ends)')


def actions_text(zones=ZONES):
    return "An action is: carry one box of a colour (%s) to a zone (%s), or stay (do nothing)." % (" or ".join(COLOURS), ", ".join(zones))


PLAN_FORMAT = plan_format()
ACTIONS = actions_text()
# Prompt wording below: the dialog-mode instruction of the prior work (Chen et al. DMAS, reference prompt file lines 186-188,
# the same dialog protocol as RoCo; RoCo's own repository text was not available to compare, PROTOCOLS-FROM-PAPERS.md 1.1): "End your response by either:
# 1) output PROCEED, if the plans require further discussion; 2) If everyone has made proposals and got approved, output the final plan as soon as
# possible, must strictly follow [Action Output Instruction]!" and an [Action Output Instruction] that says: first output 'EXECUTE', then the plan. Our
# first wording ("PROCEED to hand over to the next robot or, only after every robot has spoken at least once, summarise ... EXECUTE") never led to an
# EXECUTE in the 2026-11-17 smoke runs (three robots agreed on the same plan from the 3rd-4th utterance on and still ended every answer with PROCEED, so
# only the forced last call produced the plan). Added to the original, for our partial observations: the sentence about what a robot knows or sees.
# The rule that EXECUTE counts only after every robot has spoken (RoCo code) stays in the round engine, not in the prompt, as in the original.


def peer_rule(actions, fmt):
    return ("Say concisely what you know or see that your friends need (your own boxes, your own orders). Think step-by-step about the task and the team "
            "dialogue. Carefully check and correct them if they made a mistake. Respond very concisely but informatively, and do not repeat what others have "
            "said. Discuss with others to come up with the best plan. Propose exactly one action for yourself at the **current** round. " + actions +
            " End your response by either: 1) output PROCEED, if the plans require further discussion; 2) If everyone has made proposals and got approved, "
            "output the final plan as soon as possible, must strictly follow [Action Output Instruction]!\n"
            "[Action Output Instruction]\nMust first output 'EXECUTE', then on the new line give the plan as " + fmt + ".")


def hub_propose(actions, fmt):
    return ("You are the leader. Decide the action of every robot of the team and give the plan as " + fmt + ". " + actions +
            " You know only what you have seen and what your friends have told you. Reply with the JSON object only.")


def hub_revise(fmt):
    return "Your plan was: %s\nYour friends replied:\n%s\nRevise the plan where they are right. Reply with the JSON object only (" + fmt + ")."


SYNTAX_FEEDBACK = "\nYour previous answer could not be used: %s. Answer again; the plan must be %s."
PEER_RULE = peer_rule(ACTIONS, PLAN_FORMAT)
PEER_LAST = (" This is the last call: you must end your response by incorporating all previous discussions and output the best plan via EXECUTE.")
HUB_PROPOSE = hub_propose(ACTIONS, PLAN_FORMAT)
HUB_REVIEW = ("The leader proposes the plan below. Your own assigned action is: %s. If you agree with the plan, reply exactly: I Agree. "
              "Otherwise explain concisely why not, and tell the leader what you know or see that the plan does not take into account "
              "(your own boxes, your own orders).\nLeader's plan: %s")
HUB_REVISE = hub_revise(PLAN_FORMAT)


def protocol_texts(robots, zones=None):
    """Plan-format wording of a team: (plan format, peer rule, hub proposal, hub revision). Without `zones` (no --zones, no --scene-file) these are the module constants,
    for every team size (the wording of the main experiment and of the first protocol runs); with the zones of a scene the example has one entry per robot
    and the zone list is the scene's."""
    if zones is None:
        return PLAN_FORMAT, PEER_RULE, HUB_PROPOSE, HUB_REVISE
    fmt, actions = plan_format(robots, zones), actions_text(zones)
    return fmt, peer_rule(actions, fmt), hub_propose(actions, fmt), hub_revise(fmt)


def short(text):
    text = text if isinstance(text, str) else json.dumps(text)
    return text if len(text) <= UTTERANCE_CHARS else text[:UTTERANCE_CHARS] + " ..."


def is_agree(text):
    """Chen HMAS-2 reviewer. Code: BoxNet1 compares the whole answer with "I Agree", the other three environments test whether the answer
    contains "I Agree" (env2-box-arrange.py, env3, env4). Ours is the substring rule, ignoring case: the first real-model check answered
    "I Agree." followed by an explanation, which the exact rule would have read as an objection."""
    return re.search(r"\bi agree\b", str(text), re.I) is not None


def parse_plan(text, robots, zones=ZONES):
    """(plan, error). plan = {rid: {"box": colour, "zone": zone} | None (stay)} for exactly the robots in `robots`; error is a short sentence
    for the re-prompt when the text holds no usable plan. The first JSON object (after the last EXECUTE when there is one) is read."""
    text = str(text)
    if "EXECUTE" in text:
        text = text.rsplit("EXECUTE", 1)[1]
    decoder, start = json.JSONDecoder(), text.find("{")
    found = None
    while start != -1 and found is None:
        try:
            value, _ = decoder.raw_decode(text[start:])
            if isinstance(value, dict):
                found = value
        except ValueError:
            pass
        start = text.find("{", start + 1)
    if found is None:
        return None, "no JSON object found"
    plan = {}
    for rid in robots:
        entry = found.get(rid)
        if entry is None:
            return None, "the plan has no entry for robot %s" % rid
        if isinstance(entry, str) and entry.strip().lower() in ("stay", "none", "idle", "finish"):
            plan[rid] = None
        elif (isinstance(entry, dict) and str(entry.get("box", "")).lower() in COLOURS and str(entry.get("zone", "")) in zones):
            plan[rid] = {"box": str(entry["box"]).lower(), "zone": str(entry["zone"])}
        else:
            return None, "the entry of robot %s is neither \"stay\" nor {\"box\": red|blue, \"zone\": %s}" % (rid, "|".join(zones))
    return plan, None


def plan_line(plan, rid):
    entry = plan.get(rid) if plan else None
    return "stay" if entry is None else "carry a %s box to %s" % (entry["box"], entry["zone"])


def plan_text(plan):
    return json.dumps({rid: ("stay" if e is None else {"box": e["box"], "zone": e["zone"]}) for rid, e in plan.items()})


def nearest_option(options, colour):
    """Key of the listed 'go grasp target object <colour box> in the box room, D m away, ...' option of that colour with the smallest D
    (the first listed on a tie); None when the robot has no such option."""
    best = None
    for o in options:
        m = re.search(r"<%s box>.*?([\d.]+) m away" % re.escape(colour), o.get("text", ""))
        if m and str(o.get("key", "")).startswith("box:") and (best is None or float(m.group(1)) < best[0]):
            best = (float(m.group(1)), o["key"])
    return best[1] if best else None


class ProtocolMixin:
    """Round engine of TeamBrain (all methods are used only when self.protocol is set)."""

    # ------------------------------------------------------------------ small helpers
    def _failed(self, rid, now_s):
        return self.fail_robot == rid and self.fail_at_s is not None and now_s >= self.fail_at_s

    def _alive(self, now_s):
        return [r for r in self.robots if not self._failed(r, now_s)]

    def _elect(self, candidates):
        """Leader election (study switch): the robot that knows the most orders (own told facts) is the leader. Ties go to the lowest robot number, or with
        --leader-seed to sorted(tied)[seed % len(tied)] (the rule of PREREG-PHASE2 and tools/make_phase2.py elect()). Rule of the announcement
        'I know N orders' that every robot is assumed to have made and heard at the start."""
        counts = {}
        for r in candidates:
            seen = set()
            for facts in self._states[r]["facts"]:
                orders = facts.get("orders") if isinstance(facts, dict) else None
                for o in orders if isinstance(orders, list) else []:
                    if isinstance(o, dict):
                        seen.add((o.get("box"), o.get("zone"), o.get("count")))
            counts[r] = len(seen)
        if self.leader_seed is not None:
            top = max(counts.values())
            tied = sorted(r for r in candidates if counts[r] == top)
            return tied[self.leader_seed % len(tied)], counts
        leader = min(candidates, key=lambda r: (-counts[r], self.robots.index(r)))
        return leader, counts

    def _utter(self, rid, now_s, point, prompt):
        """One model call for robot rid (its own state, the call counts for it). Returns the answer as text."""
        s = self._states[rid]
        s.update(now=float(now_s), point=point)
        if self._calls_for(rid) >= self.max_calls:
            raise CallLimitError("Robot call cap reached")
        before = len(self._planner.records)
        paid = self.client.call_count if hasattr(self.client, "call_count") else 0
        result = self._planner._call(s, "protocol", prompt, lambda: {"text": "I Agree"})
        if hasattr(self.client, "call_count"):
            self._paid[rid] += self.client.call_count - paid
        record = self._planner.records[before] if len(self._planner.records) > before else {}
        raw = record.get("raw_output")
        return raw if isinstance(raw, str) else (result.get("text") if isinstance(result.get("text"), str) else json.dumps(result))

    def _say(self, rnd, speaker, text, recipients, now_s, order):
        """Record one utterance as a message (via="protocol"). Loss and delay apply per recipient like for any message."""
        message = self._post(speaker, now_s, json.dumps({"message": short(text)}), via="protocol", to=recipients)
        message["round"] = rnd["epoch"]
        rnd["utterances"].append({"speaker": speaker, "text": text, "to": list(message["to"]), "lost": list(message.get("lost", [])),
                                  "call": order})
        return message

    def _prompt_protocol(self, rid, request, body, now_s, point):
        s = self._states[rid]
        s.update(now=float(now_s), point=point)
        self._receive(s, rid, now_s)
        planner = self._planner
        mapping = ", ".join("Agent %d means robot %s" % (i + 1, r) for i, r in enumerate(self.robots)) + "."
        organization = ""
        if self.team == "T2":
            organization = "Agent %d is the leader to coordinate the task." % (self.robots.index(self.leader) + 1)
        head = HEAD.format(request=request).replace("Agent 1 means robot 0.", mapping)
        head += "Organization instructions: " + organization + "\n"
        head += "Goal: " + self.goal_text + "\n"
        head += "Progress: " + planner._progress(s) + "\n"
        head += "Dialogue history:\n" + json.dumps(planner._recent(s), ensure_ascii=False) + "\n"
        return head + body

    def _visible(self, rnd, rid):
        """Utterances of this round that reached robot rid (its own, and those sent to it), oldest first."""
        return [u for u in rnd["utterances"] if u["speaker"] == rid or rid in u["to"]]

    def _plan_or_retry(self, rid, now_s, point, prompt, rnd, participants):
        """Ask rid for a plan; re-prompt up to SYNTAX_RETRIES times with the parser's complaint. Returns (plan or None, text)."""
        text, feedback = "", ""
        for attempt in range(SYNTAX_RETRIES + 1):
            text = self._utter(rid, now_s, point, prompt + feedback)
            rnd["calls"] += 1
            plan, error = parse_plan(text, participants, self.zones)
            if plan is not None:
                return plan, text
            rnd["syntax_errors"] += 1
            feedback = SYNTAX_FEEDBACK % (error, self._ptexts[0])
        return None, text

    # ------------------------------------------------------------------ rounds
    def _open_round(self, rid, now_s, reason):
        """Run one dialogue round (the caller's decide() carries it out; no simulated time passes). Sets self._plan."""
        alive = self._alive(now_s)
        participants = [r for r in alive if r in self._arrived or r == rid] if reason == "first_pick" else alive
        participants = [r for r in self.robots if r in participants]
        self._epoch += 1
        rnd = dict(epoch=self._epoch, opened_at=float(now_s), opened_by=rid, reason=reason, mode=self.protocol, participants=participants,
                   leader=None, utterances=[], plan=None, status=None, calls=0, syntax_errors=0, review_rounds=0, election=None)
        self._rounds.append(rnd)
        plan = None
        if self.protocol == "peer-roco":
            plan, final_speaker = self._peer_round(rnd, participants, now_s)
        else:
            leader = self.leader
            if self.leader_election or leader not in participants:
                leader, counts = self._elect(participants)
                rnd["election"] = dict(counts=counts, leader=leader, rule="most orders known, ties: lowest robot number" if self.leader_seed is None
                                       else "most orders known, ties: sorted(tied)[seed %% len(tied)], seed %d" % self.leader_seed)
                self.leader = leader     # the prompts ("Agent N is the leader"), the routing of later messages and the record's top-level leader follow the elected leader
            rnd["leader"] = leader
            plan, final_speaker = self._hub_round(rnd, participants, leader, now_s)
        rnd["plan"] = plan_text(plan) if plan else None
        rnd["status"] = "plan" if plan else "empty"
        delivery = {}
        if plan:
            for r in participants:
                if r == final_speaker:
                    delivery[r] = float(now_s)
                else:
                    carried = [m for m in self._messages if m.get("round") == rnd["epoch"] and m["from"] == final_speaker and r in m["to"]]
                    delivery[r] = min((m["deliver_at"] for m in carried), default=None)
        self._plan = dict(epoch=rnd["epoch"], entries=plan or {}, delivery=delivery, used={}, participants=participants)
        rnd["delivery"] = {r: delivery.get(r) for r in participants}
        self._write_record()
        return self._plan

    def _peer_round(self, rnd, participants, now_s):
        """RoCo dialog mode / DMAS: speak in robot-number order until EXECUTE (see the module text)."""
        calls, plan, last = 0, None, None
        spoken = set()
        others = lambda r: [x for x in participants if x != r]
        while calls < self.peer_max_calls and plan is None:
            for r in participants:
                visible = self._visible(rnd, r)
                lines = "\n".join("%s: %s" % (u["speaker"], short(u["text"])) for u in visible) or "(nobody has spoken yet)"
                body = ("Team dialogue this round (robots speak in number order):\n%s\nYou are robot %s. %s" % (lines, r, self._ptexts[1]))
                if calls == self.peer_max_calls - 1:
                    body += PEER_LAST
                prompt = self._prompt_protocol(r, "speak in our team dialogue", body, now_s, "pick")
                text = self._utter(r, now_s, "pick", prompt)
                calls += 1
                rnd["calls"] += 1
                spoken.add(r)
                self._say(rnd, r, text, others(r), now_s, calls)
                if "EXECUTE" in text and spoken >= set(participants):
                    parsed, error = parse_plan(text, participants, self.zones)
                    retry = 0
                    while parsed is None and retry < SYNTAX_RETRIES:
                        rnd["syntax_errors"] += 1
                        text = self._utter(r, now_s, "pick", prompt + SYNTAX_FEEDBACK % (error, self._ptexts[0]))
                        calls += 1
                        rnd["calls"] += 1
                        parsed, error = parse_plan(text, participants, self.zones) if "EXECUTE" in text or "{" in text else (None, "no EXECUTE found")
                        retry += 1
                    if parsed is not None:
                        plan, last = parsed, r
                        if retry:
                            self._say(rnd, r, text, others(r), now_s, calls)
                    else:
                        rnd["syntax_errors"] += 1
                if plan is not None:
                    break
        return plan, last

    def _hub_round(self, rnd, participants, leader, now_s):
        """Chen HMAS-2 (hub_rounds = 0: CMAS, the leader's proposal runs as it is)."""
        members = [r for r in participants if r != leader]
        everyone = lambda r: [x for x in participants if x != r]
        prompt = self._prompt_protocol(leader, "propose the plan for the whole team", self._ptexts[2], now_s, "pick")
        plan, text = self._plan_or_retry(leader, now_s, "pick", prompt, rnd, participants)
        if plan is None:
            return None, leader
        self._say(rnd, leader, text, everyone(leader), now_s, rnd["calls"])
        for _ in range(self.hub_rounds):
            objections = []
            for r in members:
                body = HUB_REVIEW % (plan_line(plan, r), plan_text(plan))
                reply = self._utter(r, now_s, "pick", self._prompt_protocol(r, "review the leader's plan", body, now_s, "pick"))
                rnd["calls"] += 1
                self._say(rnd, r, reply, [leader], now_s, rnd["calls"])
                if not is_agree(reply):
                    objections.append((r, reply))
            rnd["review_rounds"] += 1
            if not objections:
                break
            feedback = "\n".join("%s: %s" % (r, short(t)) for r, t in objections)
            body = self._ptexts[3] % (plan_text(plan), feedback)
            revised, text = self._plan_or_retry(leader, now_s, "pick",
                                                self._prompt_protocol(leader, "revise the plan for the whole team", body, now_s, "pick"),
                                                rnd, participants)
            if revised is None:
                break                                   # keep the latest usable plan
            plan = revised
            self._say(rnd, leader, text, everyone(leader), now_s, rnd["calls"])
        return plan, leader

    # ------------------------------------------------------------------ decisions
    def _entry_ready(self, rid, now_s):
        """(state, entry): 'none' (no plan covers rid), 'wait' (plan reaches rid later), 'ready'."""
        plan = self._plan
        if not plan or rid not in plan["participants"] or not plan["entries"]:
            return "none", None
        when = plan["delivery"].get(rid)
        if when is None:
            return "none", None
        return ("wait", None) if when > now_s + 1e-9 else ("ready", plan["entries"].get(rid))

    def _protocol_pick(self, s, rid, now_s, options, wait, result):
        again = rid in self._pick_taken            # a pick decision after a lost grasp: the dialogue is opened again
        self._arrived.setdefault(rid, float(now_s))
        if again and rid not in self._replanned_for:
            self._replanned_for.add(rid)
            self._open_round(rid, now_s, "regrasp")
        elif not again and self._plan is None:
            first = min(self._arrived.values())
            everyone = all(r in self._arrived for r in self._alive(now_s))
            if not everyone and now_s < first + HOLD_S:
                return wait["key"]                  # held: the round opens when the others have asked (or after HOLD_S)
            self._open_round(rid, now_s, "first_pick")
        state, entry = self._entry_ready(rid, now_s)
        if state == "wait":
            return wait["key"]
        if state == "ready":
            if entry is None:
                finish = next((o["key"] for o in options if o["key"] in ("finish", "none")), None)
                return finish or wait["key"]
            key = nearest_option(options, entry["box"])
            if key:
                return key
        return None                                 # no usable entry: the caller decides on its own

    def _protocol_destination(self, rid, now_s, options):
        state, entry = self._entry_ready(rid, now_s)
        if state == "ready" and entry:
            key = "zone:" + entry["zone"]
            if any(o["key"] == key for o in options):
                return key
        return None

    def _individual(self, s, rid, options):
        menu = {o["text"]: {"skill": "executor", "key": o["key"]} for o in options}
        text, _, _ = self._planner._choose(s, menu, draft=None)
        return menu[text]["key"]

    def _decide_protocol(self, rid, now_s, point, options, wait):
        """decide() of a protocol run (T1 / T2). Returns the result dict; the bookkeeping mirrors decide()."""
        s = self._states[rid]
        s.update(now=float(now_s), point=point)
        before = self._calls_for(rid)
        result = dict(option=wait["key"], wait_s=0.0 if point == "report" else 2.0, sent=[], calls=0)
        self._receive(s, rid, now_s)
        try:
            if self._halts[rid]:
                raise CallLimitError(self._halts[rid])
            if self._failed(rid, now_s):
                raise CallLimitError("robot_failed")
            if self._calls_for(rid) >= self.max_calls:
                raise CallLimitError("Robot call cap reached")
            from .llm import RealLLM, check_spend_guard
            if isinstance(self.client, RealLLM):
                self.client.spend_guard = check_spend_guard()
            key = None
            if point == "pick":
                key = self._protocol_pick(s, rid, now_s, options, wait, result)
            elif point == "destination":
                key = self._protocol_destination(rid, now_s, options)
            elif point == "report":
                key = wait["key"]
            if key is None:
                key = self._individual(s, rid, options)
            if point == "pick" and key.startswith("box:"):
                self._pick_taken.add(rid)
            result.update(option=key, wait_s=2.0 if point != "report" and key == wait["key"] else 0.0)
        except CallLimitError as error:
            self._halts[rid] = str(error)
            result.update(halted=True, reason=self._halts[rid])
        except Exception as error:
            self._halts[rid] = type(error).__name__
            result.update(halted=True, reason=self._halts[rid])
        result["calls"] = self._calls_for(rid) - before
        return result
