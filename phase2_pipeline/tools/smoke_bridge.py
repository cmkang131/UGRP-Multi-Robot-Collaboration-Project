#!/usr/bin/env python3
"""Fake-motion smoke of the planner host (no MuJoCo, no paid call): the real brain_server.py (its argument parser, TeamBrain, HTTP handler) with a
scripted model, driven over HTTP by a small simulation of the bridge's per-robot loop (run_team_carry.py: ask / waiting / poll / RETHINK_S).

  python3 -I -B smoke_bridge.py LINK_DIR SCENES_JSON [SCENE_ID]       # 3 robots: the 14 older conditions + the free-talk conditions P and LE
  python3 -I -B smoke_bridge.py LINK_DIR N9_SCENES.json MG_tworoom_N09_s0001   # 9 robots: free-talk P and LE (+ the protocol conditions with N-robot plan examples)

A robot asks 'pick' at 12 s; 'wait' means: ask again when /poll reports a new message (not before 2 s) or after RETHINK_S = 20 s. A picked box takes
30 s, then 'destination' is asked, then 'door' ('go' or 'wait', one robot at a time, 20 s each), then the box is set down at the zone: the run
of that robot ends. 'finish' / 'put_down' / a halted robot end the robot where it stands. The scripted model answers a protocol dialogue with the
scene's oracle plan (a peer EXECUTEs after everyone has spoken, a reviewer says "I Agree") and every plain choice with the first listed option,
so the check is about plumbing (every condition runs to the end, caps hold, records are written), not about how well a model plans.

Free talk (phase 2): the scripted model of a free prompt says once to everyone what it knows (P) or, as the leader of a binding run, the assign lines of the
scene's oracle plan (LE); a member whose list holds only wait and say waits; everything else is the first listed body action. The simulated runner follows
run_team_carry ask(): an answer `wait` with `sent` and no `sent_with_action` makes the robot stand max(2, wait_s) s (`turn_used`), any other `wait` RETHINK_S = 20 s,
and the waiting robot's /poll (once per second, not before asked + 2 s) can end the wait. Not simulated: message chances, re-decision of the destination, report-point
standing (the runner reads wait_s only at ask()). The case "free P, body label + say" answers {"action": <body label>, "say": "rX, ..."}: it must produce a directed message and
no body action in the decision that spoke.

Star route (--leader-route star, mode "star"): the scripted member sees only "say to <leader>" and speaks once, in one of five shapes by turns (a say label of the leader entry; the text
"say to <other member>: ..."; a body label + say + "to": "everyone"; a body label + say starting "<other member>, "; a body label + say with no addressee), each with its own marker
[m:rX]. The case is ok only when every member message was delivered to the leader alone, the redirected count equals the number of redirect shapes the model used, no member prompt shows
another member's marker and every member's say entries are the leader's only (the leader's are every teammate and everyone).
Mode "relay" (star route, the leader stays available): the members speak only at their door question, and only after the leader's own run is over (until then they wait); the simulated
runner keeps the leader in the conversation as run_team_carry.relay_step does (a robot whose answers carried relay=True and whose run is over: /poll once per second, on `new` the point
'relay' with the option wait). The case is ok only when each member's later message [q:rX] reached the leader alone, the leader answered it in a 'relay' decision after its run
([a:rX] to that member) and the member's next prompt shows the answer. Mode "down": the elected leader fails at 40 s (--fail-robot), so it halts and the members, told so in their next
prompt, are offered `say to everyone` only; the case is ok only when every member message after 40 s is such a fallback (leader_down, no leader among its recipients, counted).

For N=3/6 the multi P and LE cases exercise back/finish after a speech, the complete ordered assignments, and late relay.
They use the scene's multi-trip list if present and a labelled 5/10-job fixture when the input scene has one trip per robot.
"""
import heapq, json, math, re, sys, tempfile, zlib
from pathlib import Path

LINK, SCENES = Path(sys.argv[1]).resolve(), sys.argv[2]
SCENE_ID = sys.argv[3] if len(sys.argv) > 3 else "L3M01"
sys.path.insert(0, str(LINK)); sys.dont_write_bytecode = True
import brain_server  # noqa: E402
from brain.tests.bridge_http import BridgeHTTP  # noqa: E402

SCENE = next(s for s in json.loads(Path(SCENES).read_text())["scenes"] if s["id"] == SCENE_ID)
ZONE = {o["id"]: "sign%d" % o["sign"] for o in SCENE["orders"]}
ORDER_OF = {o["id"]: (o["colour"], "sign%d" % o["sign"]) for o in SCENE["orders"]}
BOX = {b["id"]: b for b in SCENE["boxes"]}
ROBOTS = [r["rid"] for r in SCENE["robots"]]
ORACLE = {rid: ({"box": BOX[v[0][0]]["colour"], "zone": ZONE[v[0][1]]} if v else "stay") for rid, v in SCENE["oracle_plan"].items()}
ZONES = tuple("sign%d" % n for n in (sorted(s["number"] for s in SCENE["arena"]["signs"]) if (SCENE.get("arena") or {}).get("signs") else (11, 12, 13)))
SIZE_BOUND = 12000                                            # planner input bound (bytes) of the main experiment; cases with --max-input-bytes use their own


LEADER_END = {}                                               # simulate(): {"t": time} when a robot that the planner marked relay=True ended its run (any way)
RELAY_LOG = []                                                # simulate(): every 'relay' decision the simulated runner asked
RELAY_OPTIONS = [{"key": "wait", "text": "stay here and keep relaying for the team"}]      # run_team_carry.RELAY_OPTIONS


def robot_of(prompt):
    return json.loads(re.search(r"^Progress: (\{.*\})$", prompt, re.M)[1])["robot"]


def look(robot, trip=1):
    rows = []
    for b in SCENE["boxes"]:
        dx, dy = b["x"] - robot["x"], b["y"] - robot["y"]
        bearing = math.degrees((math.atan2(dy, dx) - robot["yaw"] + math.pi) % (2 * math.pi) - math.pi)
        rows.append((math.hypot(dx, dy), bearing, b["colour"]))
    rows.sort()
    prefix = robot["rid"] if trip == 1 else f"{robot['rid']}-t{trip}-l2"
    facts = [dict(entry=f"{prefix}-box{i}", colour=c, room="box room", distance_m=round(d, 2), bearing_deg=round(a))
             for i, (d, a, c) in enumerate(rows)]
    opts = [{"key": "box:%d" % i, "text": "go grasp target object <%s box> in the box room, %.1f m away, %d° %s of me (my label %s)"
             % (c, d, abs(round(a)), "left" if a > 0 else "right", facts[i]["entry"])} for i, (d, a, c) in enumerate(rows)]
    return opts + [{"key": "wait", "text": "wait here for now"}, {"key": "finish", "text": "finish: there is nothing useful for me to do"}], facts


class Model:
    """Scripted model (see the module text). Keeps the largest prompt it saw."""
    def __init__(self, *a, mode=None, **k):
        self.call_count, self.max_calls, self.records, self.spend_guard = 0, 10 ** 9, [], None
        self.biggest = 0
        self.said = {}
        self.mode, self.prompts = mode, []            # mode "body_say": the free-talk answer is a body label plus a say field (the real model's habit), see free()
        self.shapes, self.spoke = {}, {}              # mode "star": the shape each member speaks in (by turns) and the shape it used
        self.answered = set()                         # mode "relay": the members the leader has answered
        self.spoke_at_next = set()

    def free(self, prompt):
        """Scripted answer of a free-talk choice prompt (see the module text)."""
        robot = json.loads(re.search(r"^Progress: (\{.*\})$", prompt, re.M)[1])["robot"]
        entries = [(l.split(". ", 1)[0], l.split(". ", 1)[1]) for l in re.search(r"Available actions:\n(.*)\nAnswer:", prompt, re.S)[1].splitlines()]
        label = lambda start: next((l for l, x in entries if x.startswith(start)), None)
        body = [l for l, x in entries if not x.startswith("say to ")]
        if self.mode in ("multi_p", "multi_le", "multi_le_open"):
            return self.multi_choice(robot, prompt, entries, body)
        star = re.search(r"You can only talk to the leader (r\d+); the leader relays", prompt) if self.mode == "star" else None
        if star:
            return self.star_member(robot, star[1], entries, body)
        if self.mode in ("relay", "down"):
            handled = self.relay_model(robot, prompt, entries, body)
            if handled is not None:
                return handled
        everyone, first = label("say to everyone"), self.said.setdefault(robot, 0)
        if everyone and first == 0:
            if "You are the leader: decide which box each robot takes" in prompt and "assign " in prompt:
                words = "; ".join("assign %s: %s -> %s" % (r, e["box"], e["zone"]) for r, e in ORACLE.items() if r != robot and e != "stay")
            else:
                words = "I know these orders: " + ", ".join("%s box to %s" % (ORDER_OF[o][0], ORDER_OF[o][1]) for o in SCENE["knows"][robot]) if SCENE["knows"][robot] else ""
            if words:
                self.said[robot] += 1
                if self.mode == "body_say":
                    mate = next(r for r in ROBOTS if r != robot)
                    return {"raw_output": json.dumps({"reasoning": "tell", "action": body[0], "say": "%s, %s" % (mate, words)})}
                return {"raw_output": json.dumps({"reasoning": "tell", "action": everyone, "say": words})}
        return {"raw_output": json.dumps({"reasoning": "act", "action": body[0]})}

    def multi_choice(self, robot, prompt, entries, body):
        progress = json.loads(re.search(r"^Progress: (\{.*\})$", prompt, re.M)[1])
        point = progress["point"]
        done = sum(f.get("milestone") == "carry_finished" and f.get("outcome") == "at_zone" for f in progress["own_facts"])
        jobs = MULTI_JOBS[robot]
        action, words = None, None
        if self.mode == "multi_le":
            if point == "relay" or (robot != ELECTED and point == "door" and done + 1 == len(jobs)):
                return self.relay_model(robot, prompt, entries, body)
        if self.mode in ("multi_le", "multi_le_open"):          # the elected leader says its assign lines to everyone once (open: no relay, members may also talk to each other)
            if robot == ELECTED and not self.said.get(robot):
                action = "say to everyone:"
                words = "\n".join(f"assign {r}: {c} -> {z}" for r, trips in MULTI_JOBS.items() if r != robot for c, z in trips)
                self.said[robot] = 1
        if action is None and point == "next":
            if robot not in self.spoke_at_next and any(t.startswith("say to ") for _, t in entries):
                self.spoke_at_next.add(robot)
                action, words = "say to ", f"I have set down my box on trip {done}."
                if self.mode == "multi_le_open" and robot != ELECTED:
                    members = [r for r in ROBOTS if r != ELECTED]
                    other = members[(members.index(robot) + 1) % len(members)]      # the next member: a member-to-member message, not one to the leader
                    if any(t.startswith(f"say to {other}:") for _, t in entries):
                        action, words = f"say to {other}:", f"[mm:{robot}] I have set down my box on trip {done}."
            else:
                action = "go back" if done < len(jobs) else "finish my run"
        if point == "blocked":
            action = "step aside"
        if point == "pick" and any(t == "look around here" for _, t in entries):
            action = "look around here"
        if action is None and point in ("pick", "destination"):
            if self.mode in ("multi_le", "multi_le_open") and robot != ELECTED:
                # Pick the first permitted body entry. A stale or prematurely advanced queue changes the observed delivery.
                return {"raw_output": json.dumps({"action": body[0]})}
            colour, zone = jobs[done]
            action = f"go grasp target object <{colour} box>" if point == "pick" else f"transport the box I am holding to the <{zone} zone>"
        label = next((l for l, t in entries if action and t.startswith(action)), body[0])
        return {"raw_output": json.dumps({"action": label, **({"say": words} if words else {})})}

    def relay_model(self, robot, prompt, entries, body):
        """Modes relay / down: a member speaks once, at its door question, after the leader's run is over ([q:robot]); the leader answers it at the relay point ([a:robot]).
        None = not handled here (the leader's ordinary decisions use the leader branch of free())."""
        label = lambda start: next((l for l, x in entries if x.startswith(start)), None)
        act = lambda key: {"raw_output": json.dumps({"reasoning": "act", "action": key})}
        if "You are the leader: decide which box each robot takes" in prompt:
            if "My own carry is over and my body is done" not in prompt:
                return None
            pending = sorted(set(re.findall(r"\[q:(r\d+)\]", prompt)) - self.answered)
            target = label("say to %s:" % pending[0]) if len(pending) == 1 else label("say to everyone")
            if not pending or target is None:
                return act(body[0])
            self.answered |= set(pending)
            return {"raw_output": json.dumps({"reasoning": "relay", "action": target, "say": " ".join("[a:%s] go through the door now." % r for r in pending)})}
        if "You can only talk to the leader" not in prompt and "is no longer available" not in prompt:
            return None
        door, wait_door = label("carry the box through the door now"), label("wait here before going to the door")
        if door is None:
            return act(body[0])
        if not LEADER_END.get("t"):
            return act(wait_door)                                     # the leader's run is not over yet: nothing to ask it
        if not self.said.get(robot):
            say = label("say to ")
            if say is None:
                return act(wait_door)
            self.said[robot] = 1
            self.spoke[robot] = "door"
            return {"raw_output": json.dumps({"reasoning": "ask", "action": say, "say": "I am at the door [q:%s], which way do I go?" % robot})}
        return act(door if self.mode == "down" or "[a:%s]" % robot in prompt else wait_door)

    STAR_SHAPES = (1, 2, 3, 0, 4)                 # members take these in turn: three redirect shapes (1, 2, 3) first, then the two that go to the leader without a redirect

    def star_member(self, robot, leader, entries, body):
        """A member of a star run: speaks once (its words carry the marker [m:robot]), then the first listed body action."""
        say = next((l for l, x in entries if x.startswith("say to ")), None)
        if say is None or self.said.setdefault(robot, 0) or not SCENE["knows"][robot]:
            return {"raw_output": json.dumps({"reasoning": "act", "action": body[0]})}
        self.said[robot] += 1
        shape = self.shapes.setdefault(robot, self.STAR_SHAPES[len(self.shapes) % len(self.STAR_SHAPES)])
        self.spoke[robot] = shape
        other = next(r for r in ROBOTS if r not in (robot, leader))
        words = "I know these orders: " + ", ".join("%s box to %s" % (ORDER_OF[o][0], ORDER_OF[o][1]) for o in SCENE["knows"][robot]) + " [m:%s]" % robot
        answer = {0: {"action": say, "say": words},
                  1: {"action": "say to %s: %s" % (other, words)},
                  2: {"action": body[0], "say": words, "to": "everyone"},
                  3: {"action": body[0], "say": "%s, %s" % (other, words)},
                  4: {"action": body[0], "say": words}}[shape]
        return {"raw_output": json.dumps(dict({"reasoning": "tell"}, **answer))}

    def call(self, prompt, response_format=None):
        self.call_count += 1
        self.biggest = max(self.biggest, len(prompt.encode()))
        if self.mode:
            self.prompts.append(prompt)
        if "Besides acting you may speak" in prompt and "Available actions:" in prompt:
            return self.free(prompt)
        if "speak in our team dialogue" in prompt:
            said = len(re.findall(r"^r\d: ", prompt.split("Team dialogue this round")[1].split("You are robot")[0], re.M))
            return {"raw_output": ("OK. EXECUTE " + json.dumps(ORACLE)) if said + 1 >= len(ROBOTS) else "I will take my nearest box. PROCEED"}
        if "propose the plan" in prompt or "revise the plan" in prompt:
            return {"raw_output": json.dumps(ORACLE)}
        if "review the leader's plan" in prompt:
            return {"raw_output": "I Agree"}
        if "generate a short message" in prompt:
            return {"raw_output": json.dumps({"message": "I see my boxes.", "facts": []})}
        if prompt.endswith("So the answer is option") or '"action":"option label"' in prompt:
            return {"raw_output": json.dumps({"action": "A", "send": True})}
        return {"raw_output": '{"reasoning":"stub"}'}


def serve(argv, log_dir, mode=None):
    model = Model(mode=mode)
    return BridgeHTTP(brain_server, argv, log_dir, model), model


def simulate(server, multi=False):
    """Event loop over the robots. Returns {rid: outcome} and the delivered (colour, zone) pairs."""
    for r in SCENE["robots"]:
        mine = [{"box": ORDER_OF[o][0], "count": 1, "zone": ORDER_OF[o][1]} for o in SCENE["knows"][r["rid"]]]
        if multi and MULTI_SOURCE != "scene oracle_plan":
            jobs = [job for trips in MULTI_JOBS.values() for job in trips]
            mine = [dict(box=c, zone=z, count=jobs.count((c, z))) for c, z in sorted(set(jobs))]
        server.post("/tell", {"rid": r["rid"], "facts": {"orders": mine, "progress": "I am in the box room and I am not holding anything."}})
    robots = {r["rid"]: r for r in SCENE["robots"]}
    views = {rid: look(robot) for rid, robot in robots.items()}
    state = {rid: {"stage": "pick", "asked": 0.0, "holding": None, "colour": None, "out": None, "trip": 1} for rid in ROBOTS}
    LEADER_END.clear(); RELAY_LOG.clear()
    relay_t = {}                                              # robots kept in the conversation after their run: the next time they poll

    def ended(rid, now):
        """A robot's run is over. The planner marked it relay=True (the star leader): remember when, and keep it in the conversation unless it halted."""
        st = state[rid]
        if st.get("relay") and "relay_end" not in st:
            st["relay_end"] = now
            LEADER_END["t"] = now
            if not str(st["out"]).startswith("halted"):
                relay_t[rid] = now

    def relay_polls(now):
        """run_team_carry.relay_step: once per second a robot whose run is over polls the planner; on `new` it is asked the point 'relay'."""
        for rid in list(relay_t):
            while rid in relay_t and relay_t[rid] <= now:
                t = relay_t[rid]
                relay_t[rid] = t + 1.0
                if server.post("/poll", {"rid": rid, "now_s": t}).get("new"):
                    answer = server.post("/decide", {"rid": rid, "now_s": t, "point": "relay", "options": RELAY_OPTIONS})
                    RELAY_LOG.append(dict(t=t, rid=rid, sent=len(answer.get("sent", [])), option=answer.get("option"), halted=bool(answer.get("halted"))))
                    if answer.get("halted"):
                        relay_t.pop(rid)
    queue, door_free = [(12.0, i, rid) for i, rid in enumerate(ROBOTS)], 0.0
    heapq.heapify(queue)
    seq, delivered, asks = len(ROBOTS), [], 0

    def schedule(rid, when):
        nonlocal seq
        seq += 1
        heapq.heappush(queue, (when, seq, rid))

    zone_options = [{"key": "zone:" + z, "text": "transport the box I am holding to the <%s zone>" % z} for z in ZONES]
    while queue and asks < 600:
        now, _, rid = heapq.heappop(queue)
        relay_polls(now)
        st = state[rid]
        if now > 900:
            st["out"] = st["out"] or "time_cap"; continue
        point = st["stage"]
        if point in ("carry", "set_down_here"):
            at_zone = point == "carry"
            if at_zone:
                delivered.append((st["colour"], st["zone"]))
            if not multi:
                st["out"] = "delivered"; ended(rid, now); continue
            st["in_zone_room"] = at_zone
            facts = dict(milestone="carry_finished", trip=st["trip"], box=st["colour"], outcome="put_down", progress="I set the box down where I stand.")
            if at_zone:
                facts.update(outcome="at_zone", zone=st["zone"], progress="I set the box down at the <%s zone>." % st["zone"])
            server.post("/tell", {"rid": rid, "facts": facts})
            point = st["stage"] = "next"
        if multi and point == "pick" and st.get("listed_trip") != st["trip"]:
            views[rid] = look(robots[rid], st["trip"])
            server.post("/tell", {"rid": rid, "facts": {"seen_boxes": views[rid][1]}})
            st["listed_trip"] = st["trip"]
        put_down = {"key": "put_down", "text": "put the box I am holding down here" + ("" if multi else " and finish")}
        back = "go back to the box room for another box" if st.get("in_zone_room") else "look around the box room again for another box"
        options = {"pick": views[rid][0], "destination": zone_options + [{"key": "wait", "text": "wait here, holding the box"}, put_down],
                   "door": [{"key": "go", "text": "carry the box through the door now (one robot at a time fits)"}, {"key": "wait", "text": "wait here before going to the door"},
                            put_down],
                   "next": [{"key": "back", "text": back}, {"key": "finish", "text": "finish my run"}],
                   "empty": [{"key": "move:look", "text": "look around here"}, {"key": "wait", "text": "wait here"}, {"key": "finish", "text": "finish my run"}],
                   "blocked": [{"key": "wait", "text": "keep waiting here"}, {"key": "move:aside", "text": "step aside to let a teammate pass"}]}[point]
        asks += 1
        if point == "door" and door_free > now:
            schedule(rid, door_free)
            continue
        answer = server.post("/decide", {"rid": rid, "now_s": now, "point": "pick" if point == "empty" else point, "options": options})
        st["asked"] = now
        if answer.get("relay"):
            st["relay"] = True                              # run_team_carry hooks.ask: the planner keeps this robot in the conversation after its run
        if answer.get("halted"):
            st["out"] = "halted:" + str(answer.get("reason")); ended(rid, now); continue
        opt = answer["option"]
        if opt == "wait" or opt not in [o["key"] for o in options]:
            turn_used = answer.get("sent") and not answer.get("sent_with_action")        # run_team_carry ask(): a say (or an older message that used the turn)
            nxt = now + (max(2.0, float(answer.get("wait_s") or 2.0)) if turn_used else 20.0)    # else RETHINK_S; /poll (once per second, not before asked + 2 s) can end the wait sooner
            t = now + 2.0
            while t < nxt and not server.post("/poll", {"rid": rid, "now_s": t}).get("new"):
                t += 1.0
            schedule(rid, min(t, nxt))
            continue
        if multi and opt == "put_down":
            st["stage"] = "set_down_here"
            schedule(rid, now + 2.)
            continue
        if opt in ("finish", "put_down", "none"):
            st["out"] = "delivered" if point == "next" and opt == "finish" else opt
            ended(rid, now); continue
        if point == "next" and opt == "back":
            st.update(stage="empty", trip=st["trip"] + 1, colour=None, zone=None)
            server.post("/tell", {"rid": rid, "facts": dict(milestone="trip_started", trip=st["trip"], progress="I am back in the box room.")})
            server.post("/tell", {"rid": rid, "facts": {"progress": "I looked around and I see no box."}})
            schedule(rid, now + 15.)
            continue
        if point == "empty" and opt == "move:look":
            st["stage"] = "pick"
            server.post("/tell", {"rid": rid, "facts": {"progress": "I looked around again here."}})
            schedule(rid, now + 2.)
        elif point == "pick":
            text = next(o["text"] for o in options if o["key"] == opt)
            st.update(stage="blocked" if multi and st["trip"] > 1 else "destination", colour=re.search(r"<(\w+) box>", text).group(1))
            schedule(rid, now + 30.0)
        elif point == "blocked" and opt == "move:aside":
            # A refused move keeps the same approach and pick in the runner.
            st["stage"] = "destination"
            server.post("/tell", {"rid": rid, "facts": {"progress": "I could not step aside: there is no room beside me."}})
            schedule(rid, now + 2.)
        elif point == "destination":
            st.update(stage="door", zone=opt.split(":")[1])
            schedule(rid, now)
        else:
            door_free = now + 20.0
            st.update(stage="carry")
            schedule(rid, now + 20.0)
    return {rid: st["out"] or "unfinished" for rid, st in state.items()}, delivered, asks


def score(delivered, wanted=None):
    left, correct = list(ORDER_OF.values() if wanted is None else wanted), 0
    total = len(left)
    for pair in delivered:
        if pair in left:
            left.remove(pair); correct += 1
    return max(0, correct - (len(delivered) - correct)) / total, correct / total


CASES = [
    ("v38-style T1 (no switch)", ["--team", "T1"]),
    ("v38-style T2 (no switch)", ["--team", "T2"]),
    ("T1 budget 4", ["--team", "T1", "--max-messages", "4"]),
    ("T2 leader r3, leader budget 16", ["--team", "T2", "--leader", "r3", "--max-messages", "8", "--leader-max-messages", "16"]),
    ("T1 peer-roco", ["--team", "T1", "--protocol", "peer-roco"]),
    ("T2 hub-hmas2 leader r1", ["--team", "T2", "--protocol", "hub-hmas2"]),
    ("T2 hub-hmas2 elected", ["--team", "T2", "--protocol", "hub-hmas2", "--leader-election"]),
    ("T2 cmas (no review)", ["--team", "T2", "--protocol", "hub-hmas2", "--hub-rounds", "0"]),
    ("T1 peer delay 6 s", ["--team", "T1", "--protocol", "peer-roco", "--msg-delay-s", "6"]),
    ("T1 peer loss 0.5", ["--team", "T1", "--protocol", "peer-roco", "--msg-loss", "0.5", "--msg-seed", "3"]),
    ("T2 hub, leader fails at 5 s", ["--team", "T2", "--protocol", "hub-hmas2", "--fail-robot", "r1", "--fail-at-s", "5"]),
    ("T1 peer, r2 fails at 5 s", ["--team", "T1", "--protocol", "peer-roco", "--fail-robot", "r2", "--fail-at-s", "5"]),
    ("T2 v38-style, leader fails at 40 s", ["--team", "T2", "--fail-robot", "r1", "--fail-at-s", "40"]),
    ("T2 all small switches", ["--team", "T2", "--parser-fix", "--merge-calls", "--options-v2", "--route-note", "--idle-option", "--leader-authority"]),
]

# Phase 2 (PREREG-PHASE2.md): the flag sets of the manifest rows (tools/make_phase2.py cell_args), P = peers talk freely (T1), LE = elected leader with binding assignments (T2)
FREE = ["--parser-fix", "--merge-calls", "--options-v2", "--talk", "free", "--no-message-budget", "--msg-delay-s", "2", "--say-fix-s", "1.45", "--say-per-char-s", "0.0036",
        "--read-fix-s", "0.7", "--read-per-char-s", "0.0018"]
LE_SEED = zlib.crc32(("elect|%s|%d" % (SCENE_ID, 1)).encode()) % 2 ** 31
LE = ["--leader-authority", "--leader-election", "--leader-bind", "--hold-s", "75", "--leader-seed", str(LE_SEED)]
_COUNTS = {r: len(set(SCENE["knows"][r])) for r in ROBOTS}
_TIED = sorted(r for r, c in _COUNTS.items() if c == max(_COUNTS.values()))
ELECTED = _TIED[LE_SEED % len(_TIED)]                          # the leader the election will pick (most orders known; the tie by the seed): the robot of the case that fails
SCENE_ARGS = ["--scene-file", str(Path(SCENES).resolve()), "--scene-id", SCENE_ID]
BIG = ["--max-input-bytes", "24000", "--map-doors"] if len(ROBOTS) > 3 else []
FREE_CASES = [
    ("free P (T1)", ["--team", "T1"] + FREE + BIG),
    ("free LE (T2, election+binding)", ["--team", "T2"] + FREE + LE + BIG),
    ("free P, scene file", ["--team", "T1"] + FREE + BIG + SCENE_ARGS),
    ("free LE, scene file", ["--team", "T2"] + FREE + LE + BIG + SCENE_ARGS),
    ("free LE, no hold (hold 0 s)", ["--team", "T2"] + FREE + ["--leader-authority", "--leader-election", "--leader-bind", "--hold-s", "0", "--leader-seed", str(LE_SEED)] + BIG),
    # the model answers {"action": <body label>, "say": "r2, ..."}: the words are a speech to r2 and the body action of that answer is not done (PREREG-PHASE2.md 8)
    ("free P, body label + say", ["--team", "T1"] + FREE + BIG, "body_say"),
    # star route: every message goes through the leader (members: the leader entry only; their words to others are redirected to the leader)
    ("free LE star (T2, election+binding)", ["--team", "T2"] + FREE + LE + ["--leader-route", "star"] + BIG, "star"),
    ("free LE star, scene file", ["--team", "T2"] + FREE + LE + ["--leader-route", "star"] + BIG + SCENE_ARGS, "star"),
    ("free star, fixed leader r2, no election", ["--team", "T2"] + FREE + ["--leader", "r2", "--leader-route", "star"] + BIG, "star"),
    # the leader stays available: its own run ends first, a member's later message still reaches it and is answered
    ("free LE star, leader done first, relay", ["--team", "T2"] + FREE + LE + ["--leader-route", "star"] + BIG, "relay"),
    # the leader halts (fails at 40 s): the members are told and speak to everyone
    ("free LE star, leader fails at 40 s", ["--team", "T2"] + FREE + LE + ["--leader-route", "star", "--fail-robot", ELECTED, "--fail-at-s", "40"] + BIG, "down"),
]
# a protocol run of N > 3 robots names its zones (--scene-file here): without them it keeps the three-zone wording and plan check of the first protocol runs
BIG_PROTOCOL = [("T1 peer-roco, N robots", ["--team", "T1", "--protocol", "peer-roco", "--max-input-bytes", "24000"] + BIG[2:] + SCENE_ARGS),
                ("T2 hub-hmas2 elected, N robots", ["--team", "T2", "--protocol", "hub-hmas2", "--leader-election", "--max-input-bytes", "24000"] + BIG[2:] + SCENE_ARGS)]

MULTI_JOBS = {r: [(BOX[b]["colour"], ZONE[o]) for b, o in trips] for r, trips in SCENE["oracle_plan"].items()}
MULTI_SOURCE = "scene oracle_plan"
if len(ROBOTS) in (3, 6):
    if not any(len(trips) > 1 for trips in MULTI_JOBS.values()):
        MULTI_SOURCE = "scripted 5/10-job fixture"
        priority = [ELECTED] + [r for r in ROBOTS if r != ELECTED]
        colours = sorted({b["colour"] for b in BOX.values()})
        MULTI_JOBS = {r: [(colours[(i + j) % len(colours)], ZONES[(i + j) % len(ZONES)])
                          for j in range(2 if i < 2 * len(ROBOTS) // 3 else 1)] for i, r in enumerate(priority)}
    FREE_CASES.extend([
        ("multi P, repeated trips", ["--team", "T1", "--multi-carry"] + FREE + BIG + SCENE_ARGS, "multi_p"),
        ("multi LE, queued trips and relay", ["--team", "T2", "--multi-carry", "--leader-route", "star"] + FREE + LE + BIG + SCENE_ARGS, "multi_le"),
        # L-open: T2 leader structure (election + binding) and multi-carry, but no star route: members talk to each other directly, no relay
        ("multi L-open, no star, direct talk", ["--team", "T2", "--multi-carry"] + FREE + LE + BIG + SCENE_ARGS, "multi_le_open"),
    ])


def check_multi(rec, outcomes, model):
    if not all(brain_server.MULTI_CARRY in p and brain_server.ONE_CARRY not in p for p in model.prompts):
        return False
    for rid, jobs in MULTI_JOBS.items():
        rows = rec["decisions"][rid]
        picks = [next(o["text"] for o in d["options"] if o["key"] == d["option"]) for d in rows if d["point"] == "pick" and d["option"].startswith("box:")]
        zones = [d["option"][5:] for d in rows if d["point"] == "destination" and d["option"].startswith("zone:")]
        choices = [d for d in rows if d["point"] == "next"]
        if ([re.search(r"<(\w+) box>", t)[1] for t in picks] != [c for c, _ in jobs] or zones != [z for _, z in jobs]
                or sum(d["option"] == "move:look" for d in rows) != len(jobs) - 1
                or sum(d["option"] == "move:aside" and d["point"] == "blocked" for d in rows) != len(jobs) - 1
                or [d["option"] for d in choices if not d["sent"]] != ["back"] * (len(jobs) - 1) + ["finish"]):
            return False
        for i, d in enumerate(choices):
            if d["sent"] and (d["option"] != "wait" or i + 1 == len(choices) or choices[i+1]["time"] < d["time"] + max(2., d["wait_s"]) - 1e-8):
                return False
        if model.mode in ("multi_le", "multi_le_open") and rid != ELECTED:
            fulfilled = rec["binding"]["members"][rid]["fulfilled"]
            if [(a["box"], a["zone"]) for a in fulfilled] != jobs:
                return False
    return bool(rec["conditions"].get("multi_carry") and model.spoke_at_next and all(o == "delivered" for o in outcomes.values()))


def bound_of(argv):
    return int(argv[argv.index("--max-input-bytes") + 1]) if "--max-input-bytes" in argv else SIZE_BOUND


def talk_summary(rec):
    talk, bind = rec.get("talk", {}), rec.get("binding")
    if not talk:
        return ""
    text = "says %d (directed %d) say_s %.1f read_s %.1f" % (talk["says"], talk["directed"], talk["say_s"], talk["read_s"])
    if "star" in rec:
        star = rec["star"]
        text += " | star leader %s redirected %d in %d/%d chars out %d/%d chars" % (star["leader"], star["redirected"], star["leader_inbound"]["messages"],
                                                                             star["leader_inbound"]["chars"], star["leader_outbound"]["messages"], star["leader_outbound"]["chars"])
    if "election" in rec:
        text += " leader %s tied %s" % (rec["election"]["leader"], ",".join(rec["election"]["tied"]))
    if bind:
        text += " assign %d/%d held %d bound %d unlock timeout %d" % (bind["assign_valid"], bind["assign_lines"], sum(m["held_decisions"] for m in bind["members"].values()),
                                                                     sum(m["bound_decisions"] for m in bind["members"].values()), bind["unlocked_by_timeout"])
    return text


if __name__ == "__main__":
    print("scene %s  robots %d  oracle %s" % (SCENE_ID, len(ROBOTS), json.dumps(ORACLE)[:160]))
    print("%-36s %-44s %5s %5s %6s %6s %7s %s" % ("case", "robot outcomes", "R", "R0", "calls", "msgs", "maxprompt", "rounds / talk"))
    cases = (CASES if len(ROBOTS) <= 3 else []) + (BIG_PROTOCOL if len(ROBOTS) > 3 else []) + FREE_CASES
    bad = 0
    for case in cases:
        name, argv, mode = case[0], case[1], (case[2] if len(case) > 2 else None)
        multi = mode in ("multi_p", "multi_le", "multi_le_open")
        with tempfile.TemporaryDirectory() as tmp:
            server, model = serve(argv + ["--robots", ",".join(ROBOTS)], Path(tmp) / "log", mode)
            try:
                if case == cases[0]:
                    print("HTTP transport:", "loopback" if server.server is not None else "in-memory")
                out, delivered, asks = simulate(server, multi)
                rec = server.post("/record", {})
            finally:
                server.close()
        r, r0 = score(delivered, [job for jobs in MULTI_JOBS.values() for job in jobs] if multi else None)
        rounds = [x["calls"] for x in rec.get("conditions", {}).get("protocol", {}).get("rounds", [])]
        worst = max(rec["calls_by_robot"].values())
        ok = all(v != "unfinished" for v in out.values()) and worst <= 150 and rec["calls"] <= 600 and model.biggest < bound_of(argv) - 1024
        if "--talk" in argv:                                   # free talk: nobody halted, no draft prompt was needed, say / read times were recorded, binding was observed
            halted = {r_ for r_, v in rec["halted_by_robot"].items() if v}
            ok = ok and (halted <= {ELECTED} if mode == "down" else not halted) and rec["talk"]["says"] > 0 and rec["talk"]["say_s"] > 0 and rec["talk"]["read_s"] > 0
            if "--leader-bind" in argv and "--hold-s" in argv and argv[argv.index("--hold-s") + 1] != "0":
                bind = rec["binding"]
                ok = ok and bind["assign_valid"] > 0 and bind["members_assigned"] > 0 and bind["assign_invalid"] == 0 and rec["election"]["tied"]
        if mode == "body_say":                                  # a delivered message to r2 and no body action in the decision that spoke
            spoken = [d for r_ in ROBOTS for d in rec["decisions"][r_] if "say_with_action" in d]
            to_r2 = [m for m in rec["messages"] if m["to"] == ["r2"]]
            seen = any("r2, I know these orders" in p for p in model.prompts if json.loads(re.search(r"^Progress: (\{.*\})$", p, re.M)[1])["robot"] == "r2")
            ok = ok and len(spoken) >= 1 and all(d["option"] == "wait" and d["sent"] for d in spoken) and to_r2 and seen \
                and rec["talk"]["events"].get("say_with_action", 0) == len(spoken) and "words_beside_an_action_not_sent" not in rec["talk"]["events"]
            print("   body label + say: %d speeches (decision option %s), %d messages to r2 only, text shown to r2: %s, events %s"
                  % (len(spoken), sorted({d["option"] for d in spoken}), len(to_r2), seen, json.dumps(rec["talk"]["events"])))
        if mode == "star":                                      # all talk goes through the leader (see the module text)
            leader, star = rec["star"]["leader"], rec["star"]
            from_members = [m for m in rec["messages"] if m["from"] != leader]
            redirect_shapes = sum(1 for s in model.spoke.values() if s in (1, 2, 3))
            seen_by = robot_of
            member_prompts = [(seen_by(p), p) for p in model.prompts if seen_by(p) != leader]
            leaks = [(rid, y) for rid, p in member_prompts for y in model.spoke if y != rid and "[m:%s]" % y in p]
            listings = {tuple(l.split(". ", 1)[1] for l in re.search(r"Available actions:\n(.*)\nAnswer:", p, re.S)[1].splitlines() if l.split(". ", 1)[1].startswith("say to ")) for _, p in member_prompts} - {()}       # a prompt right after the robot's own say has no say entry
            leader_lists = {len(x) for x in ({l for l in re.search(r"Available actions:\n(.*)\nAnswer:", p, re.S)[1].splitlines() if ". say to " in l} for p in model.prompts if seen_by(p) == leader)} - {0}
            to_leader_only = bool(from_members) and all(m["to"] == [leader] for m in from_members)
            ok = ok and to_leader_only and star["member_messages_to_non_leader"] == 0 and len(model.spoke) > 0 and redirect_shapes > 0 \
                and rec["talk"]["events"].get("member_redirected_to_leader", 0) == redirect_shapes == star["redirected"] \
                and not leaks and listings == {("say to %s: <text>" % leader,)} and leader_lists == {len(ROBOTS)} \
                and not any(p for _, p in member_prompts if "say to everyone" in p) and "say_to_nobody" not in rec["talk"]["events"]
            seen = sum(1 for y in model.spoke if any("[m:%s]" % y in p for p in model.prompts if seen_by(p) == leader))
            print("   star: leader %s; %d member messages, all to the leader only: %s; shapes used %s; redirected %d (expected %d); member prompts showing another member's words: %d; "
                  "member say entries %s; leader entries per prompt %s; the leader's prompts show %d of %d member messages; events %s"
                  % (leader, len(from_members), to_leader_only, dict(sorted(model.spoke.items())), star["redirected"], redirect_shapes, len(leaks),
                     sorted(listings), sorted(leader_lists), seen, len(model.spoke), json.dumps(rec["talk"]["events"])))
        if multi:
            matched = check_multi(rec, out, model)
            ok = ok and matched and rec["paid_calls"] == 0
            print(f"   {MULTI_SOURCE}: {len(delivered)} releases, ordered picks/destinations and next choices match: {matched}")
        if mode == "multi_le_open":                              # L-open: every member-to-member message was delivered to that member alone, nothing redirected, no star record
            leader = ELECTED
            direct = [m for m in rec["messages"] if m["from"] != leader and "[mm:" in m["text"]]
            members = [r_ for r_ in ROBOTS if r_ != leader]
            to_member = bool(direct) and all(m["to"] == [members[(members.index(m["from"]) + 1) % len(members)]] and leader not in m["to"] for m in direct)
            shown = bool(direct) and all(any("[mm:%s]" % m["from"] in p for p in model.prompts if robot_of(p) == m["to"][0]) for m in direct)
            redirected = rec["talk"]["events"].get("member_redirected_to_leader", 0)
            ok = ok and to_member and shown and "star" not in rec and redirected == 0 and rec["paid_calls"] == 0 and len(RELAY_LOG) == 0 \
                and not any(d["point"] == "relay" for r_ in ROBOTS for d in rec["decisions"][r_])
            print("   L-open: leader %s; %d member-to-member messages delivered to that member alone: %s; shown in the receiver's next prompt: %s; star record: %s; redirected %d; paid_calls %d"
                  % (leader, len(direct), to_member, shown, "star" in rec, redirected, rec["paid_calls"]))
        if mode in ("relay", "multi_le"):                        # the leader stays available (see the module text)
            leader, t_end = rec["star"]["leader"], LEADER_END.get("t")
            questions = [m for m in rec["messages"] if m["from"] != leader and "[q:" in m["text"]]
            asked_by = sorted(m["from"] for m in questions)
            reply_rows = [m for m in rec["messages"] if m["from"] == leader and "[a:" in m["text"]]
            answered = {r_ for m in reply_rows for r_ in re.findall(r"\[a:(r\d+)\]", m["text"]) if r_ in m["to"]}
            relay_rows = [d for d in rec["decisions"][leader] if d["point"] == "relay"]
            shown = all(any("[a:%s]" % r_ in p for p in model.prompts if robot_of(p) == r_) for r_ in asked_by)
            after = bool(t_end) and all(m["time"] >= t_end and m["to"] == [leader] for m in questions) and all(
                m["time"] > min(q["time"] for q in questions) for m in reply_rows) and all(d["time"] >= t_end for d in relay_rows) and out[leader] == "delivered"
            ok = ok and bool(questions) and after and set(asked_by) == answered == set(model.spoke) and len(relay_rows) >= 1 and shown \
                and rec["star"]["relay_decisions"] == len(relay_rows) == len(RELAY_LOG) and rec["star"]["member_messages_to_non_leader"] == 0
            print("   relay: leader %s finished at %s (%s); %d member messages after that, all to the leader alone: %s; %d relay decisions at %s; answered %s of %s; the members' prompts show the answer: %s"
                  % (leader, t_end, out[leader], len(questions), after, len(relay_rows), [round(d["time"], 1) for d in relay_rows], sorted(answered), asked_by, shown))
        if mode == "down":                                      # the leader halts: members are told and speak to everyone (see the module text)
            leader, star = rec["star"]["leader"], rec["star"]
            from_members = [m for m in rec["messages"] if m["from"] != leader]
            fallback = [m for m in from_members if m.get("leader_down")]
            told = [p for p in model.prompts if robot_of(p) != leader and "is no longer available" in p]
            lists = {tuple(l.split(". ", 1)[1] for l in re.search(r"Available actions:\n(.*)\nAnswer:", p, re.S)[1].splitlines() if l.split(". ", 1)[1].startswith("say to ")) for p in told} - {()}
            ok = ok and leader == ELECTED and out[leader].startswith("halted") and bool(fallback) and len(fallback) == len([m for m in from_members if m["time"] >= 40.0]) \
                and all(leader not in m["to"] and m["tgt"] == "everyone" for m in fallback) and star["leader_down_fallback"] == len(fallback) \
                == rec["talk"]["events"].get("leader_down_fallback", 0) and (star["leader_down"] or {}).get("reason") == "robot_failed" and bool(told) \
                and lists == {("say to everyone: <text>",)} and star["member_messages_to_non_leader"] == 0 and all(v == "delivered" for r_, v in out.items() if r_ != leader)
            print("   down: leader %s %s; %d member messages in the fallback (to everyone, the leader no recipient), counted %s; %d member prompts told that the leader is gone, say entries %s; leader_down %s"
                  % (leader, out[leader][:20], len(fallback), star["leader_down_fallback"], len(told), sorted(lists), json.dumps(star["leader_down"])))
        bad += not ok
        extra = talk_summary(dict(rec.get("talking", {}), **{k: rec[k] for k in ("talk", "binding", "election", "star") if k in rec})) if "--talk" in argv else rounds
        print("%-36s %-44s %5.2f %5.2f %6d %6d %7d  %s %s" % (name, ",".join("%s=%s" % (k, v[:9]) for k, v in out.items()), r, r0, rec["calls"], len(rec["messages"]),
                                                               model.biggest, extra, "" if ok else "  <-- NOT OK"))
    print("cases not ok: %d of %d" % (bad, len(cases)))
    sys.exit(1 if bad else 0)
