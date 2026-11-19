#!/usr/bin/env python3
"""Per-run metrics for the leader study, read from a finished run folder (team.json + brain/brain-record.json) and the scene file.
Read-only; standard library only. Prints one CSV row per run.

  python3 -I -B run_metrics.py --scenes scenes3_main.json RUNDIR [RUNDIR ...]   (RUNDIR = a results-*/<run_id> folder)

Columns
  R          max(0, correct - wrong_place) / required         (the study's main metric, same as analyze_main R)
  Rg         correct / required                                (no deduction for a box put at a wrong zone: 'gross' share)
  M          messages sent by all robots (brain-record `messages`)
  M_<rid>    messages sent by each robot
  cap_<rid>  that robot's cap (record `max_messages_by_robot` if present, else `max_messages_per_robot`)
  capped_n   robots that sent as many messages as their own cap
  same_box   number of physical boxes chosen (first/any pick decision) by two or more different robots
  pick_unresolved  pick decisions whose box could not be matched to one scene box (tolerance below); 0 = the count is trustworthy
  end_s      team.json end_s
  rounds, round_calls, plan_empty, syntax_errors   protocol rounds opened / model calls in them / rounds without a usable plan / unreadable plans
  random_fallback, parse_retry, halted, lost_msgs   parser random fallbacks, parser re-asks, halted robots (reason), message copies lost

same_box definition (the record does not name the physical box; it names the robot's own list entry):
  every pick decision (point 'pick', option 'box:<i>') carries the option text 'go grasp target object <colour box> in the box
  room, D m away, A deg left/right of me'. The robot's start pose is team.json `starts[rid]` = [x, y, z, yaw]. The chosen box's world
  position is  (x + D cos(yaw + A), y + D sin(yaw + A))  (A positive = left). It is matched to the scene box of the SAME colour that is
  nearest; the match counts only when that box is within TOL_M (distance and bearing are rounded to 0.1 m and 1 deg, so the error stays
  below about 0.06 m at 3 m). Two robots that resolve to the same scene box = one collision on that box.
"""
import argparse, csv, json, math, re, sys
from pathlib import Path

TOL_M = 0.15
OPT = re.compile(r"<(\w+) box> in the box room, ([\d.]+) m away, (?:straight ahead of me|(\d+)° (left|right) of me)")


def load_scenes(path):
    d = json.load(open(path))
    return {s["id"]: s for s in (d["scenes"] if isinstance(d, dict) else d)}


def picks(record, starts, boxes):
    """{robot: set(scene box ids)}, count of pick decisions that could not be resolved."""
    out, bad = {}, 0
    for rid, decisions in record["decisions"].items():
        for d in decisions:
            if d.get("point") != "pick" or not str(d.get("option", "")).startswith("box:"):
                continue
            text = next((o["text"] for o in d["options"] if o["key"] == d["option"]), "")
            m = OPT.search(text)
            if not m or rid not in starts:
                bad += 1
                continue
            colour, dist = m.group(1), float(m.group(2))
            bearing = 0 if m.group(3) is None else (1 if m.group(4) == "left" else -1) * int(m.group(3))
            x, y, _, yaw = starts[rid]
            a = yaw + math.radians(bearing)
            wx, wy = x + dist * math.cos(a), y + dist * math.sin(a)
            near = sorted((math.hypot(b["x"] - wx, b["y"] - wy), b["id"]) for b in boxes if b["colour"] == colour)
            if not near or near[0][0] > TOL_M:
                bad += 1
                continue
            out.setdefault(rid, set()).add(near[0][1])
    return out, bad


def metrics(rundir, scenes):
    rundir = Path(rundir)
    team = json.load(open(rundir / "team.json"))
    record = json.load(open(rundir / "brain" / "brain-record.json"))
    scene = scenes[team["scene"]]
    req, ok, wrong = team["required_boxes"], team["correct_boxes"], team["wrong_place_boxes"]
    robots = team["robots"]
    sent = {r: sum(1 for m in record["messages"] if m["from"] == r) for r in robots}
    base = record.get("max_messages_per_robot")
    caps = record.get("max_messages_by_robot") or {r: base for r in robots}
    chosen, bad = picks(record, team["starts"], scene["boxes"])
    owners = {}
    for rid, ids in chosen.items():
        for b in ids:
            owners.setdefault(b, set()).add(rid)
    row = {"run": rundir.name, "scene": team["scene"], "team": record["team"], "leader": record.get("leader"),
           "R": round(max(0, ok - wrong) / req, 4), "Rg": round(ok / req, 4), "M": len(record["messages"]),
           "capped_n": sum(1 for r in robots if caps.get(r) is not None and sent[r] >= caps[r]) if record["team"] in ("T1", "T2") else "",
           "same_box": sum(1 for v in owners.values() if len(v) >= 2), "pick_unresolved": bad, "end_s": round(team["end_s"], 1)}
    for r in robots:
        row["M_" + r], row["cap_" + r] = sent[r], caps.get(r)
    # second-experiment fields (blank for v38 runs)
    rounds = (record.get("conditions") or {}).get("protocol", {}).get("rounds", [])
    events = [e.get("event") for e in record.get("plan_events", [])]
    row.update(rounds=len(rounds) if rounds else "", round_calls=sum(x["calls"] for x in rounds) if rounds else "",
               plan_empty=sum(1 for x in rounds if x["status"] == "empty") if rounds else "", syntax_errors=sum(x["syntax_errors"] for x in rounds) if rounds else "",
               random_fallback=events.count("random_fallback"), parse_retry=events.count("parse_retry"),
               halted=";".join("%s:%s" % (k, v) for k, v in sorted((record.get("halted_by_robot") or {}).items()) if v),
               lost_msgs=sum(len(m.get("lost", [])) for m in record["messages"]))
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenes", required=True)
    p.add_argument("runs", nargs="+")
    a = p.parse_args()
    scenes = load_scenes(a.scenes)
    rows = [metrics(r, scenes) for r in a.runs]
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    w = csv.DictWriter(sys.stdout, fieldnames=keys)
    w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
