#!/usr/bin/env python3
"""Look at the free-talk prompts (and, with --real, send each of FIVE decisions ONE time to the real model: at most 5 paid calls, client ceiling 5).

  python3 -I -B llm_free_check.py LINK_DIR SCENES_JSON [--real]

Scene L3M01 (r1 knows all three orders, r2 and r3 know none), the flag sets of the manifest rows (P = T1, LE = T2 with election + binding + the star route: all talk goes through the leader), --merge-calls, --parser-fix.
The five decisions: (1) P: r1's first pick decision, (2) P: r2's next decision after r1's message is readable, (3) LE: the leader r1's first pick decision, (4) LE: member r2's first
pick decision (it holds no assignment yet: wait or say only), (5) LE: r2's decision after the leader's message is readable (bound when the leader wrote valid assign lines; when it
did not, a canned assignment is used so that the member side is still seen). Without --real a recording stub answers and only the prompts are printed. The point is to see
whether the model chooses a say, whether its target and words are read, and whether the assign lines are parsed; nothing here is a result about how well it plans.
"""
import json, math, sys, tempfile
from pathlib import Path

LINK, SCENES, REAL = Path(sys.argv[1]).resolve(), sys.argv[2], "--real" in sys.argv
sys.path.insert(0, str(LINK)); sys.dont_write_bytecode = True
import brain_server  # noqa: E402
from brain import TeamBrain  # noqa: E402
from brain.llm import RealLLM  # noqa: E402

SCENE = next(s for s in json.load(open(SCENES))["scenes"] if s["id"] == "L3M01")
ROBOTS = [r["rid"] for r in SCENE["robots"]]


class Recorder:
    def __init__(self):
        self.prompts, self.call_count, self.records = [], 0, []

    def call(self, prompt, response_format=None):
        self.prompts.append(prompt)
        return {"raw_output": '{"reasoning":"(stub)","action":"A"}'}


def options_for(robot):
    rows = []
    for b in SCENE["boxes"]:
        dx, dy = b["x"] - robot["x"], b["y"] - robot["y"]
        bearing = math.degrees((math.atan2(dy, dx) - robot["yaw"] + math.pi) % (2 * math.pi) - math.pi)
        rows.append((math.hypot(dx, dy), bearing, b["colour"]))
    rows.sort()
    box = lambda r, i, d, a, c: {"key": "box:%d" % i, "text": "go grasp target object <%s box> in the box room, %.1f m away, %s (my label %s-box%d)"
                                 % (c, d, "straight ahead of me" if abs(a) < 5 else "%d° %s of me" % (abs(round(a)), "left" if a > 0 else "right"), r, i)}
    return [box(robot["rid"], i, d, a, c) for i, (d, a, c) in enumerate(rows)] + [{"key": "wait", "text": "wait here for now"},
                                                                                    {"key": "finish", "text": "finish: there is nothing useful for me to do"}]


def build(team, client, log, **kw):
    brain = TeamBrain(team, ROBOTS, brain_server.GOAL, client=client, log_dir=Path(log), leader="r1", talk="free", parser_fix=True, merge_calls=True, options_v2=True,
                      say=(1.45, 0.0036), read=(0.7, 0.0018), **kw)
    for r in SCENE["robots"]:
        mine = [{"box": o["colour"], "count": 1, "zone": "sign%d" % o["sign"]} for o in SCENE["orders"] if o["id"] in SCENE["knows"][r["rid"]]]
        brain.tell(r["rid"], {"orders": mine})
        boxes = [{"entry": "%s-box%d" % (r["rid"], i), "colour": b["colour"], "distance_m": 1.0 + 0.3 * i, "room": "box room"} for i, b in enumerate(SCENE["boxes"])]
        brain.tell(r["rid"], {"seen_boxes": boxes, "progress": "I am in the box room and I am not holding anything."})
    return brain


def show(title, brain, client, rid, now, point="pick"):
    before = len(client.prompts) if not REAL else client.call_count
    out = brain.decide(rid, now, point, options_for(next(r for r in SCENE["robots"] if r["rid"] == rid)))
    print("=" * 100, "\n", title, "\n", "=" * 100, sep="")
    prompt = (client.prompts[-1] if not REAL else json.loads(open(client.log_path).read().strip().splitlines()[-1]).get("raw_prompt", "(prompt in the log)"))
    print(prompt)
    rec = brain.record()
    raw = [m.get("raw_output") for m in rec["module_records"] if m["robot"] == rid and m["time"] == now]
    print("\n--- answer (raw) ---\n", "\n".join(str(x) for x in raw), sep="")
    print("--- decision --- option=%s wait_s=%s sent=%s halted=%s calls=%s" % (out["option"], out.get("wait_s"), [m["text"] for m in out["sent"]], out.get("halted"), out["calls"]))
    return out


def main():
    tmp = tempfile.mkdtemp()
    if REAL:
        client = RealLLM(5, Path(tmp) / "llm-calls.jsonl", model="z-ai/glm-5.3-flash", max_output_tokens=2048, temperature=0.7,
                         campaign_log_path=Path(tmp) / "campaign.jsonl", campaign_max_calls=5, budget_usd=0.05)
    else:
        client = Recorder()
    p = build("T1", client, Path(tmp) / "p")
    le = build("T2", client, Path(tmp) / "le", leader_authority=True, leader_election=True, leader_seed=zlib_seed(), leader_bind=True, hold_s=75.0, leader_route="star")
    o1 = show("1 P: r1 (knows all 3 orders), first pick decision", p, client, "r1", 12.0)
    ready = max(p._readable("r2").values(), default=18.0) + 1.0 if o1["sent"] else 20.0
    if not o1["sent"]:                                    # r1 did not speak: put a canned message in so that the receiver side is still seen
        canned = "I know all three orders: blue box to sign11, red box to sign12, red box to sign13. Please tell me which box you will take."
        p._speak("r1", 12.0, {"target": "everyone", "to": ["r2", "r3"]}, canned)
        ready = max(p._readable("r2").values()) + 1.0
        print("(r1 did not speak: canned message used for call 2)")
    show("2 P: r2 (knows no order), decision after r1's message is readable", p, client, "r2", ready)
    o3 = show("3 LE: leader r1 first pick decision (elected: %s)" % le.leader, le, client, "r1", 12.0)
    show("4 LE: member r2 first pick decision (no assignment yet)", le, client, "r2", 12.0)
    if not any(a["valid"] for a in le._assign_log):
        lines = len(le._assign_log)
        canned = "assign r2: red -> sign12; assign r3: red -> sign13"
        le._speak("r1", 12.0, {"target": "everyone", "to": ["r2", "r3"]}, canned)
        print("(the leader wrote no valid assign line: canned assignment used for call 5; assign lines read from call 3: %d)" % lines)
    t = max(le._readable("r2").values()) + 1.0
    show("5 LE: member r2 decision after the leader's message is readable", le, client, "r2", t)
    print("\nbinding record:", json.dumps(le.record().get("binding"), indent=1)[:1500])
    print("\nmodel calls made: %d" % (client.call_count if REAL else 0))


def zlib_seed():
    import zlib
    return zlib.crc32(b"elect|L3M01|1") % 2 ** 31


main()
