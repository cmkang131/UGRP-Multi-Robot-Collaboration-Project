#!/usr/bin/env python3
"""Default-identity proof: the study's planner copy with every new switch OFF must give byte-identical prompts, decide/chance results and
brain-record.json to the frozen planner (main experiment v38 version).

  python3 -I -B identity_check.py FROZEN_TREE STUDY_TREE [--keep OUTDIR]

Each tree (a folder with brain_server.py and brain/) runs the same scripted scenario in its own subprocess (the two trees both import a package
called `brain`, so they must not share a process). The scenario drives 3 robots through pick / destination / door / report decisions, message
chances and a message-cap hit with a deterministic stub model, for T0, T1, T2 (leader r1 and r2), the --pre-exchange and --option-order reverse
conditions and a lowered cap (b.max_messages = 3, as the old tests do). Every prompt the model would have received, every decide()/chance() result
and the final record are dumped as JSON; the two dumps must be equal byte for byte. brain_server.parse_args defaults (old arguments only) and the
GOAL text are compared too. The same scenario with a switch ON is run on the study tree to show the check can fail (it must differ).
"""
import argparse, hashlib, json, subprocess, sys, tempfile
from pathlib import Path

SCENARIO = r'''
import hashlib, json, random, re, sys, tempfile
from pathlib import Path
tree, switches = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, tree); sys.dont_write_bytecode = True
import brain_server
from brain import TeamBrain

FACTS = [{"table": "orders", "id": "o1", "value": {"box": "blue", "zone": "sign12"}, "seen": 0},
         {"table": "boxes", "id": "b1", "value": {"colour": "red"}}]

class Stub:
    """Deterministic: the answer depends on a hash of the prompt only. Sends a message whenever a draft is shown and the hash says so."""
    def __init__(self):
        self.prompts, self.records = [], []
    def call(self, prompt, response_format=None):
        self.prompts.append(prompt)
        h = int(hashlib.sha256(prompt.encode()).hexdigest(), 16)
        robot = json.loads(re.search(r"^Progress: (\{.*\})$", prompt, re.M)[1])["robot"]
        if "generate a short message" in prompt:
            if h % 7 == 0:
                return {"raw_output": json.dumps({"message": ""})}
            return {"raw_output": json.dumps({"message": "%s says %d" % (robot, h % 1000), "facts": FACTS})}
        if prompt.endswith("So the answer is option"):
            listing = re.search(r"Available actions:\n(.*)\nAnswer:", prompt, re.S)[1].splitlines()
            labels = [l.split(". ", 1)[0] for l in listing]
            answer = {"action": labels[h % len(labels)]}
            if "(not sent yet)" in prompt:
                answer["send"] = (h // 3) % 3 != 0
            if h % 9 == 0:                      # a malformed answer (JSON followed by text): the default parser falls back to a random action
                return {"raw_output": '{"action":"C","send":false}  Reasoning: it is closest.'}
            if h % 13 == 0:                     # "B. text" style
                return {"raw_output": json.dumps({"action": labels[h % len(labels)] + ". some option text"})}
            return {"raw_output": json.dumps(answer)}
        return {"raw_output": '{"reasoning":"stub"}'}

PICK = [{"key": "box:0", "text": "go grasp target object <blue box> in the box room, 0.8 m away, straight ahead of me (my label r1-box0)"},
        {"key": "box:1", "text": "go grasp target object <red box> in the box room, 1.4 m away, 20\u00b0 left of me (my label r1-box1)"},
        {"key": "wait", "text": "wait here for now"},
        {"key": "finish", "text": "finish: there is nothing useful for me to do"}]
DEST = [{"key": "zone:sign11", "text": "transport the box I am holding to the <sign11 zone>"},
        {"key": "zone:sign12", "text": "transport the box I am holding to the <sign12 zone>"},
        {"key": "zone:sign13", "text": "transport the box I am holding to the <sign13 zone>"},
        {"key": "wait", "text": "wait here, holding the box"},
        {"key": "put_down", "text": "put the box I am holding down here and finish"}]
DOOR = [{"key": "go", "text": "carry the box through the door now (one robot at a time fits)"},
        {"key": "wait", "text": "wait here before going to the door"}, {"key": "put_down", "text": "put the box I am holding down here and finish"}]
REPORT = [{"key": "continue", "text": "continue my task"}]
ROBOTS = ["r1", "r2", "r3"]

def run(label, team, leader=None, cap=None, **kw):
    stub = Stub()
    random.seed(20261117)                       # the random fallback of the parser (CoELA) must pick the same action in both trees
    log = tempfile.mkdtemp()
    b = TeamBrain(team, ROBOTS, brain_server.GOAL, client=stub, log_dir=Path(log), leader=leader, **kw)
    if cap is not None:
        b.max_messages = cap
    for rid in ROBOTS:
        b.tell(rid, {"orders": [{"box": "blue", "count": 1, "zone": "sign12"}]})
        b.tell(rid, {"seen_boxes": [{"entry": rid + "-box0", "colour": "blue", "distance_m": 0.8}]})
    out, t = [], 12.0
    for step in range(9):
        for rid in ROBOTS:
            point, opts = [("pick", PICK), ("pick", PICK), ("destination", DEST), ("door", DOOR), ("destination", DEST),
                           ("pick", PICK), ("report", REPORT), ("destination", DEST), ("door", DOOR)][step]
            out.append(["decide", rid, t, point, b.decide(rid, t, point, opts)])
        if team != "T0" and step % 2 == 1:
            for rid in ROBOTS:
                out.append(["chance", rid, t + 1.0, b.chance(rid, t + 1.0)])
        t += 5.0
    rec = b.record()
    return {"label": label, "prompts": stub.prompts, "results": out, "record": rec, "record_file": json.loads((Path(log) / "brain-record.json").read_text()),
            "fallbacks": sum(1 for e in b._planner.plan_events if e.get("event") == "random_fallback")}

cases = [("T0", dict(team="T0")), ("T1", dict(team="T1")), ("T2-r1", dict(team="T2")), ("T2-r2", dict(team="T2", leader="r2")),
         ("T2-r3", dict(team="T2", leader="r3")), ("T1-cap3", dict(team="T1", cap=3)), ("T2-cap3", dict(team="T2", cap=3)),
         ("T1-pre", dict(team="T1", pre_exchange=True)), ("T2-pre", dict(team="T2", leader="r2", pre_exchange=True)),
         ("T1-rev", dict(team="T1", option_order="reverse")), ("T0-rev", dict(team="T0", option_order="reverse"))]
dump = []
for label, c in cases:
    kw = dict(c); team = kw.pop("team")
    if switches:                                   # switch-ON run (only on the study tree): the check must then fail
        if "talk" in switches and (kw.get("pre_exchange") or kw.get("option_order") or kw.get("cap") is not None):
            continue                               # free talk replaces these routes (the brain refuses the combination)
        kw.update(switches if team != "T0" else {})
    dump.append(run(label, team, **kw))
ns = brain_server.parse_args(["--team", "T2", "--robots", "r1,r2,r3", "--port", "1", "--log-dir", "/x"])
old_args = {k: v for k, v in vars(ns).items() if k in ("team", "robots", "port", "log_dir", "max_calls", "leader", "model", "option_order", "temperature", "pre_exchange")}
print(json.dumps({"cases": dump, "goal": brain_server.GOAL, "default_args": {k: str(v) for k, v in old_args.items()}}, sort_keys=True, indent=1, default=str))
'''


def run_tree(tree, switches=None):
    out = subprocess.run([sys.executable, "-I", "-B", "-c", SCENARIO, str(tree), json.dumps(switches or {})], capture_output=True, text=True, cwd=tempfile.gettempdir())
    if out.returncode:
        raise SystemExit("scenario failed on %s:\n%s" % (tree, out.stderr[-3000:]))
    return out.stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("frozen"); p.add_argument("study"); p.add_argument("--keep")
    a = p.parse_args()
    a.frozen, a.study = str(Path(a.frozen).resolve()), str(Path(a.study).resolve())
    frozen, study = run_tree(a.frozen), run_tree(a.study)
    same = frozen == study
    n = json.loads(frozen)["cases"]
    prompts = sum(len(c["prompts"]) for c in n)
    print("cases: %d  prompts: %d  decide/chance results: %d  random fallbacks exercised: %d  dump bytes: frozen %d / study %d" %
          (len(n), prompts, sum(len(c["results"]) for c in n), sum(c["fallbacks"] for c in n), len(frozen), len(study)))
    print("sha256 frozen %s\nsha256 study  %s\nIDENTICAL: %s" % (hashlib.sha256(frozen.encode()).hexdigest(), hashlib.sha256(study.encode()).hexdigest(), same))
    # the check must be able to fail: a message cap of 16 for T1/T2 changes prompts (cap sentence) on the study tree
    on = run_tree(a.study, {"max_messages": 16})
    print("with --max-messages 16 ON the dump differs from frozen: %s" % (on != frozen))
    changed = {}
    for name, value in (("parser_fix", True), ("merge_calls", True), ("options_v2", True), ("idle_option", True), ("msg_delay_s", 5.0), ("msg_loss", 0.5), ("talk", "free")):
        changed[name] = run_tree(a.study, {name: value}) != frozen
    print("each other switch ON changes the dump: %s" % changed)
    on = on != frozen and all(changed.values())
    same = same and on
    if a.keep:
        out = Path(a.keep); out.mkdir(parents=True, exist_ok=True)
        (out / "frozen.json").write_text(frozen); (out / "study.json").write_text(study)
    raise SystemExit(0 if same else 1)


if __name__ == "__main__":
    main()
