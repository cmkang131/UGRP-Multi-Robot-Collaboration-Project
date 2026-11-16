"""CoELA persistent skills and delivered-message HMAS-2 for the L0 simulator.

Public integration: instantiate once per episode, call decide(detached_observation)
for each ready robot, submit the returned primitive unchanged, then advance the
environment. No environment handle, shared peer memory, or runner barrier is used.
client=None runs deterministic *module response* mocks, not a primitive policy.
records counts every attempted module call; real usage remains in client.records.
plan_events contains start/end/change events with robot/time/plan/box/zone/reason.

Source: CoELA TDW LLM.py:439-575, lm_agent.py:313-406,568-606, prompt_com.csv;
commit 3e12dea925d735eefce33da71806ae9da6fcaf3f. Adaptations and HMAS-2
composition are documented in docs/planning_messages.md. Adapted prompt text license:

MIT License, Copyright (c) 2023 Esther Alter
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from collections import deque
import copy
import hashlib
import json
import math
import random
import re


class PlanningContextError(ValueError):
    """Mandatory context exceeds the common cap; no shortened menu is used."""


class PlanningResponseError(ValueError):
    """A non-choice module response is invalid."""


class PlanningConsensusError(RuntimeError):
    """HMAS-2 terminated without an executable, reviewed agreement."""


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _object(text):
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


HEAD = (
    "My friends and I want to transport as many target boxes as possible to their "
    "required zones within the time limit. I can hold one box at a time. "
    "Given our shared goal, dialogue history, my progress, and previous actions, "
    "please help me {request} to achieve the goal as soon as possible. "
    "All objects are denoted as <name> (id). Actions take several steps to finish. "
    "It may be costly to go to another room or transport to a zone, use these "
    "actions sparingly. Only local observations and delivered reports are known. "
    "Agent 1 means robot 0.\n"
)
# Wording origin (checked 2026-11-15 against CoELA commit 3e12dea tdw_mat/LLM/prompt_com.csv, LLM.py and
# tdw-gym/lm_agent.py): "stale" occurs in none of them, so the clause "reported facts may be stale" was
# removed. "My friends and I" (prompt_com.csv line 2 and 13: "My friend X and I") and "dialogue history"
# (same lines) are CoELA wording. CoELA's own no-communication prompt (prompt_nocom.csv) reads "Given our
# shared goal, my progress, and previous actions" with no dialogue block, so T0 drops "dialogue history, ".
# "delivered reports" and "Agent 1 means robot 0." are L0 additions that only mean something with messages;
# T0 drops them too (no reports, no speakers).
T0_HEAD_DROPS = ("dialogue history, ", " and delivered reports", " Agent 1 means robot 0.")
SEEDS = ('Agent 1: "Hi, I\'ll let you know if I find any target boxes, finish any '
         'subgoals, and ask for your help when necessary."\n'
         'Agent 2: "Thanks! I\'ll let you know if I find any target boxes, finish any '
         'subgoals, and ask for your help when necessary."\n')
FINAL = "Answer with only one best next action. So the answer is option"
# Answer line of a choice prompt that shows a drafted message (T1/T2, a draft exists); without a draft the old line is used.
SEND_EXTRA = ('Return {"action":"option label","send":true or false}: the action to take now, and whether to send the message '
              'shown above to my friends together with it (sending does not use up my action).')


# Tail of the choice prompt when a draft is shown (the CoELA tail FINAL otherwise): the model is asked to say it in the answer itself.
FINAL_SEND = ("Answer with only one best next action, and say whether to send the message shown above "
              "(send:true or send:false). So the answer is option")
_SEND_KEY = re.compile(r"send[\"']?\s*[:=]\s*[\"']?(true|false|yes|no)\b", re.I)
_NO_SEND = re.compile(r"(?:\b(?:not|never|no|without)\b|n't)\W+(?:\w+\W+){0,2}send|\bsend(?:ing)?\W+(?:it\W+)?(?:is\W+)?(?:false|no|not|none)\b", re.I)
_SEND_WORD = re.compile(r"\bsend(?:ing)?\b", re.I)


def _send_flag(value):
    """True / False when the answer says so (JSON boolean or the words true/false/yes/no), else None (read as: do not send)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "yes", "false", "no"):
        return value.strip().lower() in ("true", "yes")
    return None


def _send_answer(result):
    """(send, source) from a choice answer. The model often answers a bare label (274 of 324 choice answers in the earlier real runs
    were bare labels, 50 JSON objects), so the "send" field of a JSON answer comes first (source "json") and the text of the answer
    is the fallback (source "text"): 'send:true|false', else the word 'send' (read as false when negated: "do not send", "no send"),
    else (None, None): no statement, read as: do not send."""
    flag = _send_flag(result.get("send"))
    if flag is not None:
        return flag, "json"
    text = result.get("action", "")
    text = text if isinstance(text, str) else _json(text)
    found = _SEND_KEY.search(text)
    if found:
        return found.group(1).lower() in ("true", "yes"), "text"
    if _NO_SEND.search(text):
        return False, "text"
    if _SEND_WORD.search(text):
        return True, "text"
    return None, None


TABLES = ("boxes", "zones", "orders", "assignments")


class PlanningPolicy:
    def __init__(self, team, robots, client=None, recent_messages=3,
                 max_input_tokens=12000, compact=True, cot=True):
        if team not in ("T0", "T1", "T2", "T3"):
            raise ValueError("unknown team")
        if type(robots) is not int or robots < 2:
            raise ValueError("robots must be an integer >= 2")
        if type(recent_messages) is not int or recent_messages < 0:
            raise ValueError("recent_messages must be nonnegative")
        if type(max_input_tokens) is not int or max_input_tokens <= 1024:
            raise ValueError("max_input_tokens must exceed framing reserve 1024")
        self.team, self.robots, self.client = team, robots, client
        self.recent_messages, self.max_input_tokens = recent_messages, max_input_tokens
        self.compact, self.cot = compact, cot
        self.records, self.plan_events = [], []
        self._states = {}

    def _new_state(self, rid):
        return dict(rid=rid, tables={k: {} for k in TABLES}, graph={}, visited={}, room_scans={},
                    explored=set(), inbox=0, history_cursor=0, dialogue=[],
                    actions=[], plan=None, plan_start=None, previous=None, last_send=None,
                    queue=deque(), pending=None, protocol=[], epoch=0, round=0,
                    phase="prepare", ready={}, reviews={}, done=set(), proposal=None,
                    reviewed=None, menu={}, candidate=None, draft_sent=False,
                    halted=False, halt_sent=False, halt_reason=None, new_objects=False, latest=None)

    def _remember(self, s, table, ident, value, seen, source):
        if table not in TABLES or not isinstance(ident, str) or not isinstance(value, dict):
            return
        if type(seen) not in (int, float) or not math.isfinite(seen) or seen < 0 or seen > s["now"]:
            return
        if table == "boxes" and source != "self":
            scan = s["room_scans"].get(value.get("room"))
            if scan and seen <= scan[0] and ident not in scan[1]:
                return
        old = s["tables"][table].get(ident)
        # A report cannot resurrect an older/equal-time direct negative observation.
        if old and (old["seen"] > seen or
                    (old["seen"] == seen and old["source"] == "self" and source != "self")):
            return
        s["tables"][table][ident] = {"value": copy.deepcopy(value), "seen": seen,
                                     "source": source}

    def _update(self, s, o):
        s["now"], s["me"] = o["time"], copy.deepcopy(o["self"])
        s["isolated"] = (o.get("c1_variant") == "isolated" or
                         o.get("c2_variant") == "isolated_corridor")
        s["c2_isolated"] = o.get("c2_variant") == "isolated_corridor"
        s["new_objects"] = any(b not in s["tables"]["boxes"] for b in o["boxes"])
        messages = o.get("messages", []) if self.team != "T0" else []
        if len(messages) < s["inbox"]:
            raise ValueError("append-only inbox required; create a new policy per episode")
        for index in range(s["inbox"], len(messages)):
            m = messages[index]
            payload = _object(m["text"])
            if payload.get("protocol") == "l0-hmas2-v3":
                s["protocol"].append((m["from"], payload))
                continue
            s["dialogue"].append({"from": m["from"], "time": m["time"],
                                  "text": payload.get("message", m["text"])})
            facts = payload.get("facts", [])
            if isinstance(facts, list):
                for fact in facts:
                    if isinstance(fact, dict):
                        self._remember(s, fact.get("table"), fact.get("id"),
                                       fact.get("value"), fact.get("seen", m["time"]),
                                       "message:%s:%s" % (m["from"], index))
        s["inbox"] = len(messages)
        for room, info in o["rooms"].items():
            s["room_scans"][room] = (o["time"], {ident for ident, box in o["boxes"].items()
                                                if box.get("room") == room})
            s["graph"][room] = list(info["neighbors"])
            for neighbor in info["neighbors"]:
                s["graph"].setdefault(neighbor, [])
            for ident, old in list(s["tables"]["boxes"].items()):
                if old["value"].get("room") == room and ident not in o["boxes"]:
                    self._remember(s, "boxes", ident, dict(old["value"], absent=True), o["time"], "self")
            for order in info.get("orders", []):
                self._remember(s, "orders", order["box"], order, o["time"], "self")
        for table in ("boxes", "zones"):
            for ident, value in o[table].items():
                self._remember(s, table, ident, value, o["time"], "self")
        orders = o.get("private_orders", []) + list(o.get("full_orders", {}).values())
        for order in orders:
            self._remember(s, "orders", order["box"], order, o["time"], "self")
        s["visited"][s["me"]["room"]] = o["time"]
        history = o.get("history", [])
        for event in history[s["history_cursor"]:]:
            s["latest"] = event
            if s["pending"] is not None and event["action"] == s["pending"]:
                if event["ok"]:
                    action = s["pending"]
                    payload = _object(action.get("text"))
                    if action["type"] == "message" and not payload.get("protocol"):
                        s["dialogue"].append({"from": s["rid"], "time": event["time"],
                                              "text": payload.get("message", action["text"])})
                    s["pending"] = None
                # Failed transport is retried as a real primitive, never delivered internally.
        s["history_cursor"] = len(history)
        s["dialogue"].sort(key=lambda message: message["time"])
        s["dialogue"] = s["dialogue"][-self.recent_messages:] if self.recent_messages else []

    def _facts(self, s):
        return [{"table": table, "id": ident, "value": row["value"], "seen": row["seen"]}
                for table in TABLES for ident, row in sorted(s["tables"][table].items())
                if row["source"] == "self"]

    def _progress(self, s):
        if self.compact:
            tables = {table: [[ident, row["value"], row["seen"], row["source"]]
                              for ident, row in sorted(s["tables"][table].items())]
                      for table in TABLES}
        else:
            tables = s["tables"]
        variant = ({"c2_variant": "isolated_corridor"} if s.get("c2_isolated") else
                   {"c1_variant": "isolated"} if s.get("isolated") else {})
        return _json({**variant,
                      "robot": s["rid"], "time": s["now"], "self": s["me"],
                      "table_columns": ["id", "value", "seen_time", "provenance"],
                      "memory": tables, "own_observed_graph": s["graph"]})

    def _prompt(self, s, module, menus=None, extra="", draft=None):
        communication = module == "message"
        request = ("generate a short message to send to my friends" if communication else
                   "choose the best available action")
        head = HEAD.format(request=request)
        if self.team == "T0":
            for text in T0_HEAD_DROPS:
                assert text in head
                head = head.replace(text, "")
        organization = "Agent 1 is the leader to coordinate the task." if self.team == "T2" else ""
        head += "Organization instructions: " + organization + "\n"
        head += "Goal: Transport each target box to its required zone.\n"
        head += "Progress: " + self._progress(s) + "\n"
        actions = "Previous actions: " + _json(s["actions"][-10:]) + "\n"
        dialogue = ""
        if self.team != "T0":
            dialogue = "Dialogue history:\n" + SEEDS + _json(self._recent(s)) + "\n"
        if communication:
            return (head + actions + dialogue + self._allowance(s) +
                    "Note: The generated message should be accurate, helpful and brief. "
                    "Do not generate repetitive messages. Return plain text or {\"message\":\"natural language\","
                    "\"facts\":[{\"table\":\"boxes|zones|orders|assignments\",\"id\":\"id\","
                    "\"value\":{},\"seen\":0}]}. Facts must come from progress; "
                    "assignments are reported intentions, not actions. Use an empty message for silence." +
                    self._moving_note(s))
        listing = "\n".join("%s. %s" % (self._label(i), text)
                            for i, text in enumerate(menus or {}))
        # A drafted message is shown on its own line before the action list (not as a list entry): the list holds only
        # things the robot can do, and the draft is sent together with the chosen action (it does not use up the turn).
        offer = ("Message I can send to my friends together with my action (not sent yet): " + draft + "\n" +
                 self._allowance(s)) if draft else ""
        return (head + dialogue + actions + offer + "Available actions:\n" + listing +
                "\nAnswer: " + extra)

    def _allowance(self, s):
        """Hook, '' here: the line a message prompt shows about the robot's own message allowance (the brain owns the count)."""
        return ""

    def _moving_note(self, s):
        """Hook, '' here: closing sentence of the message prompt when the robot is between two decisions (a message chance)."""
        return ""

    def _recent(self, s):
        """Dialogue window shown in a prompt. CoELA LLM.py:488 keeps the last 3 entries of one list."""
        return s["dialogue"][-self.recent_messages:] if self.recent_messages else []

    @staticmethod
    def _label(index):
        label = ""
        while True:
            index, rem = divmod(index, 26)
            label = chr(65 + rem) + label
            if not index:
                return label
            index -= 1

    def _call(self, s, module, prompt, mock):
        bound = len(prompt.encode("utf-8")) + 1024
        if bound > self.max_input_tokens:
            self.plan_events.append(dict(robot=s["rid"], time=s["now"], plan=None,
                                         box=None, zone=None, reason="mandatory_context_overflow",
                                         start=None, end=s["now"], change=False, event="failure",
                                         input_bound=bound))
            raise PlanningContextError("%s input bound %s exceeds %s; no context/menu dropped" %
                                       (module, bound, self.max_input_tokens))
        record = dict(robot=s["rid"], time=s["now"], module=module, status="started",
                      mock=self.client is None, input_tokens_bound=bound,
                      prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                      input_tokens=None, output_tokens=None, cost_usd=0 if self.client is None else None)
        self.records.append(record)
        try:
            if self.client is None:
                result = mock()
            elif callable(getattr(self.client, "call", None)):
                result = self.client.call(prompt, response_format=None)["raw_output"]
                record["raw_output"] = result
            else:
                # Existing offline ScriptClient fixtures expose decide only.
                result = self.client.decide(prompt)
            if isinstance(result, str):
                text = result.strip()
                if text.startswith("```"):
                    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
                try:
                    decoded = json.loads(text)
                except ValueError:
                    decoded = text
                field = {"message": "message", "choice": "action", "review": "feedback",
                         "reasoning": "reasoning", "central_reasoning": "reasoning"}.get(module)
                result = decoded if isinstance(decoded, dict) else ({field: decoded} if field else decoded)
            if not isinstance(result, dict):
                raise PlanningResponseError("%s response must be a dict" % module)
            record.update(status="ok", response=copy.deepcopy(result))
            return result
        except Exception as error:
            record.update(status="error", error=type(error).__name__)
            raise

    def _candidate(self, s):
        # No ban on a message right after a message (user decision 2026-11-15); the sender's per-robot cap is the brain's.
        if self.team == "T0":
            return None
        result = self._call(s, "message", self._prompt(s, "message"),
                            lambda: {"message": "Here are my observed box and order facts.",
                                     "facts": self._facts(s)})
        if not isinstance(result.get("message"), str):
            raise PlanningResponseError("message must be text")
        if not result["message"]:
            return None
        facts = result.get("facts", [])
        if not isinstance(facts, list):
            raise PlanningResponseError("facts must be a list")
        return _json({"message": result["message"], "facts": facts})

    def _menu(self, s, candidate=None):
        menu = {}
        if candidate:
            text = "send a message: private candidate" if self.team == "T3" else "send a message: " + candidate
            menu[text] = {"skill": "send", "text": candidate}
        held = s["me"]["carrying"]
        if held is None:
            for ident, row in sorted(s["tables"]["boxes"].items()):
                box = row["value"]
                order = s["tables"]["orders"].get(ident, {}).get("value", {})
                if (not box.get("absent") and box.get("carrier") is None and
                        not (order and box.get("zone") == order.get("zone"))):
                    text = "go grasp target object <%s> (%s)" % (box.get("color", "box"), ident)
                    menu[text] = {"skill": "grasp", "box": ident, "room": box["room"]}
        else:
            order = s["tables"]["orders"].get(held, {}).get("value", {})
            zone = s["tables"]["zones"].get(order.get("zone"), {}).get("value", {})
            if zone:
                text = "transport objects I'm holding to the required zone <%s>" % order["zone"]
                menu[text] = {"skill": "transport", "box": held, "zone": order["zone"], "room": zone["room"]}
            elif not order and s.get("isolated"):
                for ident, row in sorted(s["tables"]["zones"].items()):
                    zone = row["value"]
                    if zone["room"] == s["me"]["room"]:
                        text = "transport held object to speculative zone <%s> (order unknown)" % ident
                        menu[text] = {"skill": "transport", "box": held,
                                      "zone": ident, "room": zone["room"]}
        for room in sorted(s["graph"]):
            if room != s["me"]["room"]:
                menu["go to " + room] = {"skill": "go", "room": room}
        if s["me"]["room"] not in s["explored"]:
            menu["explore current room " + s["me"]["room"]] = {"skill": "explore", "room": s["me"]["room"]}
        return menu

    def _mock_choice(self, s, menu):
        # Mock selection is deliberately simple and shared across T0-T3. It is
        # not scientific evidence of LLM performance or of an organization advantage.
        for text, skill in menu.items():
            if skill["skill"] == "send":
                facts = _object(skill["text"]).get("facts", [])
                signature = _json([{k: v for k, v in f.items() if k != "seen"} for f in facts])
                if signature != s["last_send"]:
                    return text
        for kind in ("transport", "grasp", "go", "explore"):
            candidates = [(text, skill) for text, skill in menu.items() if skill["skill"] == kind]
            if candidates:
                if kind == "go":
                    return min(candidates, key=lambda x: (s["visited"].get(x[1]["room"], -1),
                                                         x[1]["room"]))[0]
                if kind == "grasp":
                    candidates.sort(key=lambda x: (x[1]["room"] != s["me"]["room"], x[0]))
                return candidates[0][0]
        return None

    def _select(self, s, menu):
        return self._choose(s, menu)[0]

    def _choose(self, s, menu, draft=None):
        """(chosen menu text, send, source of send). With a draft message the prompt shows it on its own line and the answer is
        {"action": label, "send": true|false}: the message goes out together with the action and the action keeps the turn.
        send is None (source None) when no draft was shown or the answer said nothing about it (read as: do not send);
        see _send_answer for how a bare-label or prose answer is read."""
        # CoELA LLM.py:517-523 rejects send-only menus. Isolated readers need
        # this explicit task adaptation; keep the legacy condition unchanged.
        if not menu or (not s.get("isolated") and
                        not any(v["skill"] != "send" for v in menu.values())):
            return None, None, None
        prompt = self._prompt(s, "choice", menu, SEND_EXTRA if draft else
                              'Return an action or option label, optionally as {"action":"text"}.', draft)
        if self.cot:
            result = self._call(s, "reasoning", prompt + ' Let\'s think step by step. Return {"reasoning":"text"}.',
                                lambda: {"reasoning": "Compare the available persistent skills using local memory."})
            prompt += "\nAssistant: " + _json(result) + "\n" + (FINAL_SEND if draft else FINAL)
        result = self._call(s, "choice", prompt, lambda: {"action": self._mock_choice(s, menu)})
        text = result.get("action", "")
        text = text if isinstance(text, str) else _json(text)
        return (self._match(s, menu, text),) + (_send_answer(result) if draft else (None, None))

    def _match(self, s, menu, text):
        # CoELA TDW LLM.py:215-295: action text, option, entity/verb fuzzy,
        # then random. Entity extraction adapts TDW room names to L0 room IDs.
        for action in menu:
            match = "send a message" if menu[action]["skill"] == "send" else action
            if match.lower() in text.lower():
                return action
        for i, action in enumerate(menu):
            label = self._label(i)
            if (text.strip() == label or
                    re.search(r"\b(?:option|Option|action) " + label + r"\b", text) or
                    re.search(r"(?<!\w)" + label + r"[.,](?!\w)|\(" + label + r"\)", text)):
                return action
        fuzzy = []
        for i, (action, skill) in enumerate(menu.items()):
            if skill["skill"] == "send":
                continue
            names = re.findall(r"<([^>]+)>|\(([^)]+)\)", action)
            entities = [a or b for a, b in names]
            if skill["skill"] in ("go", "explore"):
                entities = [skill["room"]]
            if entities and all(entity in text for entity in entities):
                self._event(s, "fuzzy_match", "coela_entity_match")
                return action
            fuzzy.append((i, action, skill, entities))
        for i, action, skill, entities in fuzzy:
            verb = {"grasp": "grasp", "explore": "explore", "transport": "transport"}.get(skill["skill"])
            if (self._label(i) + " " in text or (verb and verb in text) or
                    any(entity in text for entity in entities)):
                self._event(s, "fuzzy_match", "coela_partial_match")
                return action
        action = random.choice(list(menu))
        self.plan_events.append(dict(robot=s["rid"], time=s["now"], event="random_fallback",
                                     plan=action, box=menu[action].get("box"), zone=menu[action].get("zone"),
                                     reason="coela_failed_to_parse", start=None, end=None, change=False))
        return action

    def _event(self, s, kind, reason):
        plan = s["plan"]
        skill = plan[1] if plan else {}
        self.plan_events.append(dict(robot=s["rid"], time=s["now"], event=kind,
                                     plan=plan[0] if plan else None, box=skill.get("box"),
                                     zone=skill.get("zone"), reason=reason,
                                     start=s["plan_start"], end=s["now"] if kind == "end" else None,
                                     change=kind == "start" and s["previous"] is not None and
                                     s["previous"] != (plan[0] if plan else None)))

    def _start(self, s, text, menu):
        s["plan"] = (text, copy.deepcopy(menu[text]))
        s["plan_start"] = s["now"]
        s["actions"].append("send a message" if menu[text]["skill"] == "send" else text)
        self._event(s, "start", "consensus" if self.team == "T3" else "selected")

    def _finish(self, s, reason):
        self._event(s, "end", reason)
        s["previous"] = s["plan"][0]
        s["plan"] = None

    def _route(self, s, target, explore=False):
        origin = s["me"]["room"]
        queue, seen = deque([(origin, [])]), {origin}
        frontier = None
        while queue:
            room, path = queue.popleft()
            if room == target:
                return path
            if explore and frontier is None and path and room not in s["room_scans"]:
                frontier = path
            for neighbor in s["graph"].get(room, []):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        # L0 adaptation of CoELA agent_memory.explore: nearest reachable
        # unobserved room, only if the selected destination has no known route.
        return frontier

    def _execute(self, s, o):
        text, skill = s["plan"]
        kind, held = skill["skill"], s["me"]["carrying"]
        if kind == "send":
            facts = _object(skill["text"]).get("facts", [])
            s["last_send"] = _json([{k: v for k, v in f.items() if k != "seen"} for f in facts])
            self._enqueue(s, {"type": "message", "to": [i for i in range(self.robots) if i != s["rid"]],
                              "text": skill["text"]})
            self._finish(s, "message_queued")
            return self._outgoing(s)
        if kind == "grasp":
            box = s["tables"]["boxes"].get(skill["box"], {}).get("value", {})
            if held == skill["box"]:
                self._finish(s, "grasp_confirmed")
                return None
            if box.get("absent") or box.get("carrier") is not None or held is not None:
                self._finish(s, "target_unavailable")
                return None
            skill["room"] = box.get("room", skill["room"])
        if kind == "transport" and held != skill["box"]:
            self._finish(s, "transport_confirmed" if held is None else "held_object_changed")
            return None
        if kind == "go" and s["new_objects"]:
            self._finish(s, "new_target_observed")
            return None
        target = skill["room"]
        if s["me"].get("retreat_required"):
            return {"type": "move", "room": s["me"]["retreat_target"]}
        if s["me"]["room"] != target:
            path = self._route(s, target, explore=True)
            if not path:
                self._finish(s, "no_own_observed_route")
                return None
            if o.get("doors", {}).get(path[0], {}).get("busy"):
                return {"type": "wait"}
            return {"type": "move", "room": path[0]}
        if kind == "grasp":
            return {"type": "pick", "box": skill["box"]}
        if kind == "transport":
            return {"type": "place", "zone": skill["zone"]}
        if kind == "explore":
            s["explored"].add(target)
        self._finish(s, "room_observed" if kind == "explore" else "room_reached")
        return None

    @staticmethod
    def _enqueue(s, action):
        s["queue"].append(action)

    @staticmethod
    def _outgoing(s):
        if s["pending"] is None and s["queue"]:
            s["pending"] = s["queue"].popleft()
        return copy.deepcopy(s["pending"])

    def _wire(self, s, kind, to, **fields):
        payload = dict(protocol="l0-hmas2-v3", kind=kind, epoch=s["epoch"], **fields)
        self._enqueue(s, {"type": "message", "to": to, "text": _json(payload)})

    def _review(self, s, proposal, version):
        text = proposal.get(str(s["rid"]))
        menu = self._menu(s, s["candidate"])
        valid = text in menu
        prompt = self._prompt(s, "review", menu,
                              "Central proposal: " + _json(proposal) +
                              "\nReview your assigned action and joint conflicts using only your local "
                              "knowledge. Think step by step, first analyse for each acting agent the "
                              "collision risks and then: if you agree with it, respond 'I Agree', "
                              "without any extra words; if not, briefly explain your objections to "
                              'the central planner. Return {"feedback":"I Agree or objection"}.')
        result = self._call(s, "review", prompt, lambda: {
            "feedback": "I Agree" if valid else "Assigned action is not in my current available actions."})
        feedback = result.get("feedback")
        if not isinstance(feedback, str):
            raise PlanningResponseError("review feedback must be text")
        if not valid:
            feedback = "Syntax/availability check failed: assigned action is not available. " + feedback
        s["reviewed"] = (version, copy.deepcopy(proposal), feedback)
        return feedback

    def _propose(self, s):
        menus = {str(rid): row["menu"] for rid, row in sorted(s["ready"].items())}
        schema = ("Return only a nonempty JSON dictionary mapping robot ID strings from "
                  + _json(list(menus)) + " to exact plan strings from that robot's delivered menu. "
                  "No reasoning, thoughts, action wrapper, or other keys; no prose. "
                  "Include a robot only if it has an action.")
        extra = ("You are the central planner. Propose one available high-level action per acting "
                 "robot. Include a robot only if it has an action. Return a dictionary mapping "
                 "robot ID strings to exact offered plan strings. These are delivered menu reports, "
                  "not privileged observations. A private message candidate in a menu has NOT "
                  "delivered its facts. When required task facts are unknown, select peers' "
                  "offered message actions to obtain their local information before speculative "
                  "placement; do not assume readiness or agreement transmitted those facts. "
                  "Independent useful work may be proposed concurrently.\nDelivered available actions: " + _json(menus))
        if s["proposal"] is not None:
            extra += ("\nPrevious proposal: " + _json(s["proposal"]) + "\nLocal feedback: " +
                      _json(s["reviews"]) + "\nIf you find some errors in your previous plan, "
                      "try to modify it. Otherwise, output the same plan as before.")
        prompt = self._prompt(s, "central", extra=extra)
        if self.cot:
            reasoning = self._call(s, "central_reasoning", prompt +
                                   ' Let\'s think step by step. Return {"reasoning":"text"}.',
                                   lambda: {"reasoning": "Compare delivered menus and current objections."})
            if not isinstance(reasoning.get("reasoning"), str):
                raise PlanningResponseError("central reasoning must be text")
            prompt += "\nAssistant reasoning: " + _json(reasoning["reasoning"])
        prompt += "\nFinal proposal schema: " + schema
        def mock():
            result = {}
            for rid, row in s["ready"].items():
                # Preferences are delivered by readiness messages, never read from peer state.
                if row.get("preferred") in row["menu"]:
                    result[str(rid)] = row["preferred"]
            return result
        proposal = self._call(s, "central_revision" if s["round"] else "central_proposal", prompt, mock)
        for attempt in range(4):
            errors = [] if proposal else ["Empty proposal: assign at least one acting robot."]
            for rid, text in proposal.items():
                if rid not in menus:
                    errors.append("Invalid robot key %s; allowed keys: %s." % (_json(rid), _json(list(menus))))
                elif not isinstance(text, str):
                    errors.append("Invalid action for robot %s: expected a string, got %s." % (_json(rid), _json(text)))
                elif text not in menus[rid]:
                    errors.append("Invalid action for robot %s: %s is not in its delivered menu." % (_json(rid), _json(text)))
            if not errors:
                break
            self.records[-1]["validation_errors"] = errors
            if attempt == 3:
                self._halt(s, "central_syntax_correction_exhausted")
                return
            # Keep the frozen prompt and latest rejection, not a growing retry history.
            correction = (prompt + "\nRejected response: " + _json(proposal) +
                          "\nSyntax/availability errors: " + _json(errors) +
                          "\nCorrect the rejected response. " + schema)
            proposal = self._call(s, "central_syntax_correction", correction, mock)
        s["round"] += 1
        s["proposal"], s["reviews"], s["phase"] = proposal, {}, "review"
        recipients = [int(rid) for rid in proposal if rid != "0"]
        # The old environment requires one initial draft before physical work.
        if not s["draft_sent"]:
            recipients = list(range(1, self.robots))
        if recipients:
            self._wire(s, "proposal" if s["draft_sent"] else "draft", recipients,
                       version=s["round"], proposal=proposal)
            s["draft_sent"] = True
        if "0" in proposal:
            s["reviews"][0] = self._review(s, proposal, s["round"])

    def _halt(self, s, reason):
        if s["halted"]:
            return
        s["halted"] = True
        s["halt_reason"] = reason
        s["queue"].clear()
        s["pending"] = None
        self.plan_events.append(dict(robot=s["rid"], time=s["now"], plan=None, box=None,
                                     zone=None, reason=reason, start=None, end=s["now"],
                                     change=False, event="consensus_failure", epoch=s["epoch"]))
        if s["rid"] == 0:
            self._wire(s, "abort", list(range(1, self.robots)), reason=reason)
        else:
            self._wire(s, "halt", [0], reason=reason)

    def _t3(self, s, o):
        rid = s["rid"]
        for sender, p in s["protocol"]:
            kind = p.get("kind")
            if sender == 0 and kind == "begin" and p.get("epoch") == s["epoch"] + 1:
                s.update(epoch=p["epoch"], phase="prepare", round=0, proposal=None,
                         reviewed=None, ready={}, reviews={}, done=set())
            if p.get("epoch") != s["epoch"]:
                continue
            if sender == 0 and kind == "abort":
                s["halted"] = True
                s["halt_reason"] = p.get("reason", "central_abort")
                s["halt_sent"] = True
            elif rid == 0 and sender != 0 and kind == "halt":
                self._halt(s, "follower_%s:%s" % (sender, p.get("reason", "halt")))
            elif rid == 0 and sender != 0 and kind == "ready" and s["phase"] in ("prepare", "ready"):
                if isinstance(p.get("menu"), list) and all(isinstance(t, str) for t in p["menu"]):
                    s["ready"][sender] = p
            elif sender == 0 and kind in ("draft", "proposal") and rid != 0:
                proposal, version = p.get("proposal", {}), p.get("version", 0)
                if not isinstance(proposal, dict) or version <= s["round"]:
                    continue
                s["round"], s["proposal"] = version, proposal
                if str(rid) in proposal and not s["halted"]:
                    feedback = self._review(s, proposal, version)
                    self._wire(s, "review", [0], version=version, feedback=feedback)
            elif rid == 0 and kind == "review" and s["phase"] == "review":
                if p.get("version") == s["round"] and str(sender) in s["proposal"]:
                    s["reviews"][sender] = p.get("feedback")
            elif sender == 0 and kind == "commit" and rid != 0 and not s["halted"]:
                proposal, version = p.get("proposal"), p.get("version")
                if str(rid) in (proposal or {}):
                    if s["reviewed"] != (version, proposal, "I Agree"):
                        continue
                    menu = self._menu(s, s["candidate"])
                    if proposal[str(rid)] not in menu:
                        self._halt(s, "action_changed_after_review")
                        continue
                    self._start(s, proposal[str(rid)], menu)
                s["phase"] = "execute"
            elif rid == 0 and kind == "done" and s["phase"] == "execute":
                s["done"].add(sender)
        s["protocol"].clear()
        if s["halted"]:
            if s["halt_sent"]:
                raise PlanningConsensusError(s["halt_reason"])
            s["halt_sent"] = True
            return self._outgoing(s)
        outgoing = self._outgoing(s)
        if outgoing:
            return outgoing
        if s["phase"] == "prepare":
            s["candidate"] = self._candidate(s)
            s["menu"] = self._menu(s, s["candidate"])
            row = {"menu": list(s["menu"])}
            if self.client is None:
                row["preferred"] = self._mock_choice(s, s["menu"])
            s["phase"] = "ready"
            if rid == 0:
                s["ready"][0] = row
            else:
                self._wire(s, "ready", [0], **row)
        if rid == 0 and s["phase"] == "ready" and len(s["ready"]) == self.robots:
            self._propose(s)
        if rid == 0 and s["phase"] == "review" and len(s["reviews"]) == len(s["proposal"]):
            if all(reply == "I Agree" for reply in s["reviews"].values()):
                # Exact current-version consensus, then local syntax/availability check.
                if "0" in s["proposal"] and s["proposal"]["0"] not in self._menu(s, s["candidate"]):
                    s["reviews"][0] = "Action changed after review."
                else:
                    self._wire(s, "commit", list(range(1, self.robots)),
                               version=s["round"], proposal=s["proposal"])
                    if "0" in s["proposal"]:
                        self._start(s, s["proposal"]["0"], s["menu"])
                    s["phase"] = "execute"
            if s["phase"] == "review":
                if s["round"] >= 3:
                    self._halt(s, "nonconsensus_after_3_rounds")
                else:
                    self._propose(s)
        if s["halted"]:
            s["halt_sent"] = True
            return self._outgoing(s)
        outgoing = self._outgoing(s)
        if outgoing:
            return outgoing
        if s["phase"] == "execute":
            if s["plan"]:
                primitive = self._execute(s, o)
                if primitive:
                    return primitive
            if rid == 0:
                s["done"].add(0)
                if len(s["done"]) == self.robots:
                    s.update(epoch=s["epoch"] + 1, phase="prepare", round=0,
                             proposal=None, reviewed=None, ready={}, reviews={}, done=set())
                    self._wire(s, "begin", list(range(1, self.robots)))
            else:
                self._wire(s, "done", [0])
                s["phase"] = "barrier"
        return self._outgoing(s) or {"type": "wait"}

    def decide(self, observation):
        rid = observation["robot_id"]
        if type(rid) is not int or not 0 <= rid < self.robots:
            raise ValueError("robot ID outside configured roster")
        if rid not in self._states:
            self._states[rid] = self._new_state(rid)
        s = self._states[rid]
        self._update(s, observation)
        if self.team == "T3":
            return self._t3(s, observation)
        outgoing = self._outgoing(s)
        if outgoing:
            return outgoing
        if s["plan"]:
            primitive = self._execute(s, observation)
            if primitive:
                return primitive
        candidate = self._candidate(s)
        menu = self._menu(s, candidate)
        text = self._select(s, menu)
        if text is None:
            return {"type": "wait"}
        self._start(s, text, menu)
        return self._execute(s, observation) or {"type": "wait"}
