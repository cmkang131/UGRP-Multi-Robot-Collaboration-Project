#!/usr/bin/env python3
"""Look at the three protocol prompts (and, with --real, send each ONE time to the real model: at most 3 paid calls, client ceiling 3).

  python3 -I -B llm_prompt_check.py LINK_DIR SCENES_JSON [--real]

Scene L3M01 (r1 knows all three orders, r2 and r3 know none). The three prompts: (1) r1's first utterance in a peer-roco round, (2) the leader r1's
proposal in a hub-hmas2 round, (3) member r2's review of the oracle plan. Without --real a recording stub answers and the prompts are printed.
"""
import json, sys, tempfile
from pathlib import Path

LINK, SCENES, REAL = Path(sys.argv[1]).resolve(), sys.argv[2], "--real" in sys.argv
sys.path.insert(0, str(LINK)); sys.dont_write_bytecode = True
import brain_server  # noqa: E402
from brain import TeamBrain  # noqa: E402
from brain.llm import RealLLM  # noqa: E402
from brain.protocol import HUB_PROPOSE, HUB_REVIEW, PEER_RULE, plan_line, plan_text  # noqa: E402

scene = next(s for s in json.load(open(SCENES))["scenes"] if s["id"] == "L3M01")
ORACLE = {"r1": {"box": "blue", "zone": "sign11"}, "r2": {"box": "red", "zone": "sign12"}, "r3": {"box": "red", "zone": "sign13"}}


class Recorder:
    def __init__(self):
        self.prompts, self.call_count, self.records = [], 0, []

    def call(self, prompt, response_format=None):
        self.prompts.append(prompt)
        return {"raw_output": "(stub answer)"}


def build(team, protocol, client, log):
    brain = TeamBrain(team, ["r1", "r2", "r3"], brain_server.GOAL, client=client, log_dir=Path(log), leader="r1", protocol=protocol,
                      parser_fix=True, merge_calls=True, options_v2=True)
    for r in scene["robots"]:
        mine = [{"box": o["colour"], "count": 1, "zone": "sign%d" % o["sign"]} for o in scene["orders"] if o["id"] in scene["knows"][r["rid"]]]
        brain.tell(r["rid"], {"orders": mine, "progress": "I am in the box room and I am not holding anything."})
        boxes = [{"entry": "%s-box%d" % (r["rid"], i), "colour": b["colour"], "distance_m": 1.0 + 0.3 * i, "room": "box room"} for i, b in enumerate(scene["boxes"])]
        brain.tell(r["rid"], {"seen_boxes": boxes})
    return brain


def main():
    tmp = tempfile.mkdtemp()
    if REAL:
        client = RealLLM(3, Path(tmp) / "llm-calls.jsonl", model="z-ai/glm-5.3-flash", max_output_tokens=2048, temperature=0.7,
                         campaign_log_path=Path(tmp) / "campaign.jsonl", campaign_max_calls=3, budget_usd=0.02)
    else:
        client = Recorder()
    peer = build("T1", "peer-roco", client, Path(tmp) / "peer")
    hub = build("T2", "hub-hmas2", client, Path(tmp) / "hub")
    jobs = [("1 peer-roco: r1 speaks first", peer, "r1", "speak in our team dialogue",
             "Team dialogue this round (robots speak in number order):\n(nobody has spoken yet)\nYou are robot r1. " + PEER_RULE),
            ("2 hub-hmas2: leader r1 proposes", hub, "r1", "propose the plan for the whole team", HUB_PROPOSE),
            ("3 hub-hmas2: member r2 reviews", hub, "r2", "review the leader's plan", HUB_REVIEW % (plan_line(ORACLE, "r2"), plan_text(ORACLE)))]
    for title, brain, rid, request, body in jobs:
        prompt = brain._prompt_protocol(rid, request, body, 12.0, "pick")
        print("=" * 100, "\n", title, "  (prompt bytes: %d)\n" % len(prompt.encode()), "=" * 100, "\n", prompt, sep="")
        answer = brain._utter(rid, 12.0, "pick", prompt)
        print("\n--- answer ---\n", answer, sep="")
    print("\nmodel calls made: %d" % (client.call_count if REAL else 0))


main()
