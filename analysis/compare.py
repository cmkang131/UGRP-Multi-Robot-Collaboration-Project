#!/usr/bin/env python3
"""Offline team-plan and physical-result accounting (standard library only)."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import re
from statistics import median


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


PUT_DOWN = "put_down"   # choices[rid].dest when a robot set its held box down in place and finished (not a zone)


def sign(value):
    return re.sub(r"^zone[:_]", "", str(value)) if value is not None else None


def decisions(value):
    if isinstance(value, dict):
        return [dict(d, rid=rid) for rid, rows in value.items() for d in rows]
    return value if isinstance(value, list) else []


def assignments(choices, robots):
    result = {}
    for rid in robots:
        choice = choices.get(rid)
        if not isinstance(choice, dict) or "picked" not in choice:
            result[rid] = None
        elif choice["picked"] is None or sign(choice.get("dest")) == PUT_DOWN:
            result[rid] = []   # no pick, or a put-down: the box stays outside every sign zone, so it is an empty assignment
        else:
            result[rid] = [(choice["picked"], sign(choice.get("dest")))]
    return result


def judge(plan, scene):
    if scene is None or any(v is None for v in plan.values()):
        return None, None
    required = Counter()
    orders = {o["id"]: o for o in scene["orders"]}
    boxes = {b["id"]: b for b in scene["boxes"]}
    for order in orders.values():
        required[(order["colour"], "sign" + str(order["sign"]))] += order["count"]
    actual = Counter(pair for rows in plan.values() for pair in rows)
    oracle = {rid: Counter((boxes[bid]["colour"], "sign" + str(orders[oid]["sign"]))
                           for bid, oid in rows)
              for rid, rows in scene["oracle_plan"].items()}
    match = all(Counter(plan.get(rid) or []) == oracle.get(rid, Counter())
                for rid in set(plan) | set(oracle))
    return actual == required, match


def first_assignments(team, brain, robots):
    primary = decisions(team.get("decisions"))
    detailed = decisions(brain.get("decisions"))
    rows = primary if primary else detailed
    result, evidence = {}, {}
    for rid in robots:
        own = sorted((d for d in rows if d.get("rid") == rid),
                     key=lambda d: d.get("t", d.get("time", 0)))
        # Wait is not an assignment. Stop the first attempt at the next pick.
        picks = [(i, d) for i, d in enumerate(own)
                 if d.get("point") == "pick" and d.get("option") != "wait"]
        if not picks:
            result[rid] = None
            evidence[rid] = "no recorded selection"
            continue
        index, pick = picks[0]
        option = pick.get("option")
        if option == "none" or ("picked" in pick and pick["picked"] is None):
            result[rid], evidence[rid] = [], "explicit empty assignment"
            continue
        colour = pick.get("picked", pick.get("colour"))
        options = pick.get("options", [])
        if not any(isinstance(o, dict) for o in options):
            time = pick.get("t", pick.get("time", 0))
            matches = [d for d in detailed if d.get("rid") == rid
                       and d.get("point") == "pick" and d.get("option") == option
                       and abs(d.get("time", d.get("t", 0)) - time) < 0.051]
            if len(matches) == 1:
                options = matches[0].get("options", [])
        for entry in options:
            if isinstance(entry, dict) and entry.get("key") == option:
                match = re.search(r"<([^<>]+) box>", entry.get("text", ""))
                colour = entry.get("colour") or (match.group(1) if match else colour)
        stop = picks[1][0] if len(picks) > 1 else len(own)
        destinations = [d.get("option") for d in own[index + 1:stop]
                        if d.get("point") == "destination"
                        and (d.get("option") == PUT_DOWN
                             or str(d.get("option", "")).startswith(("zone:", "zone_", "sign")))]
        dest = sign(pick.get("dest") or (destinations[0] if destinations else None))
        if dest == PUT_DOWN:
            result[rid], evidence[rid] = [], "put down at the first destination decision"
            continue
        result[rid] = [(colour, dest)] if colour is not None else None
        evidence[rid] = {"option": option, "colour": colour, "dest": dest,
                         "t": pick.get("t", pick.get("time"))}
    return result, evidence


def analyze_run(path, scenes, brain_root=None, suffix=None):
    path = Path(path)
    name = path.name
    match = re.match(r"(t[012])-([^-]+)-", name)
    row = dict(run=name, scene=match[2] if match else "legacy", structure=match[1].upper()
               if match else ("ORACLE" if name.startswith("oracle-") else "FIXED_LEGACY"),
               status="missing", excluded="", warnings="")
    try:
        team = read_json(path / "team.json")
        if not isinstance(team, dict):
            raise ValueError("team.json is not an object")
    except (OSError, ValueError) as error:
        row["excluded"] = "missing/invalid team.json: " + str(error)
        return row
    row.update(scene=team.get("scene") or "legacy", status=team.get("status", "unknown"))
    if suffix and not name.endswith("-" + suffix):
        row["excluded"] = "outside comparison suffix -" + suffix
    elif team.get("status") == "running":
        row["excluded"] = "running (진행 중)"
    elif team.get("status") != "complete" or any(team.get(k) is None for k in
            ("correct_boxes", "required_boxes", "wrong_place_boxes", "end_s")):
        row["excluded"] = "missing completed result"
    if row["excluded"]:
        return row
    warnings = []
    brain = team.get("brain", {})
    if isinstance(brain, str):
        try:
            brain = json.loads(brain)
        except ValueError:
            warnings.append("invalid embedded brain JSON")
            brain = {}
    if not isinstance(brain, dict):
        brain = {}
    row["brain_source"] = "team.json:brain"
    if brain_root and (Path(brain_root) / name / "brain-record.json").exists():
        try:
            external = read_json(Path(brain_root) / name / "brain-record.json")
            if not isinstance(external, dict):
                raise ValueError("brain record is not an object")
            brain = external
            row["brain_source"] = "brain-record.json"
        except (OSError, ValueError):
            warnings.append("invalid external brain; using embedded record")
    robots = team.get("robots", ["r1", "r2"])
    last = assignments(team.get("choices", {}), robots)
    first, evidence = first_assignments(team, brain, robots)
    scene = scenes.get(team.get("scene"))
    row["physical_success"] = (team["correct_boxes"] == team["required_boxes"]
                               and team["wrong_place_boxes"] == 0)
    for key in ("correct_boxes", "required_boxes", "wrong_place_boxes", "end_s"):
        row[key] = team[key]
    row["plan_cover"], row["oracle_match"] = judge(last, scene)
    row["first_plan_cover"], row["first_oracle_match"] = judge(first, scene)
    row.update(last_assignments=last, first_assignments=first, first_evidence=evidence)
    if scene is not None and row["first_plan_cover"] is None:
        warnings.append("first assignment unresolved; not scored")
    if scene is None:
        warnings.append("scene unavailable; planning not scored")
    row["quadrant"] = ("P" + str(int(row["plan_cover"])) + "_S" + str(int(row["physical_success"]))) if row["plan_cover"] is not None else None
    row["first_quadrant"] = ("P" + str(int(row["first_plan_cover"])) + "_S" + str(int(row["physical_success"]))) if row["first_plan_cover"] is not None else None
    records = decisions(team.get("decisions"))
    if "messages" in brain and isinstance(brain["messages"], list):
        sent = brain["messages"]
    elif records and all("sent" in d for d in records):
        sent = [dict(m, **{"from": m.get("from", d.get("rid"))})
                for d in records for m in d["sent"]]
    else:
        sent = None
    for rid in robots:
        row["messages_" + rid] = sum(m.get("from") == rid for m in sent) if sent is not None else None
    row["messages"] = len(sent) if sent is not None else None
    row["llm_calls"] = brain.get("calls")
    if row["llm_calls"] is None and records and all("calls" in d for d in records):
        row["llm_calls"] = sum(d["calls"] for d in records)
    row["cost_usd"] = brain.get("cost_usd")
    if brain.get("kind") == "fixed_plan":
        row["llm_calls"], row["cost_usd"] = 0, 0
    if brain.get("unknown_cost_calls", 0):
        row["cost_usd"] = None
        warnings.append("unknown cost calls")
    if row["structure"] == "T0" and row["messages"]:
        warnings.append("T0_NONZERO_MESSAGES")
    diagnostics = []
    for rid in robots:
        try:
            summary = read_json(path / ("out-" + rid) / "summary.json")
        except (OSError, ValueError):
            summary = {}
            warnings.append(rid + " summary missing/invalid")
        nav = ((summary.get("carry_to") or {}).get("nav") or {}).get("outcome")
        regrasps = summary.get("regrasps", []) if summary else None
        count = len(regrasps) if isinstance(regrasps, list) else regrasps
        row["nav_" + rid], row["regrasps_" + rid] = nav, count
        row["not_holding_" + rid] = summary.get("not_holding")
        row["no_selection_" + rid] = summary.get("no_selection")
        if row["plan_cover"] and not row["physical_success"] and last.get(rid) and nav != "at_zone":
            diagnostics.append({"robot": rid, "nav.outcome": nav, "regrasps": count})
    if row["plan_cover"] and not row["physical_success"] and not diagnostics:
        diagnostics.append({"robot": "unknown", "reason": "physical attribution unavailable"})
    row["failure_diagnostics"] = diagnostics
    row["warnings"] = "; ".join(warnings)
    return row


def display(value):
    if value is None:
        return "NA"
    if isinstance(value, float):
        return format(value, ".10g")
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(display(v) for v in row) + " |" for row in rows]) + "\n"


def aggregate(rows):
    valid = [r for r in rows if not r["excluded"]]
    def rate(key):
        values = [r[key] for r in valid if r.get(key) is not None]
        return f"{sum(values)}/{len(values)}"
    def total(key):
        values = [r[key] for r in valid if r.get(key) is not None]
        return f"{display(sum(values)) if values else 'NA'} ({len(values)}/{len(valid)})"
    def timing(success):
        values = [r["end_s"] for r in valid if (not success or r["physical_success"])
                  and isinstance(r.get("end_s"), (int, float)) and math.isfinite(r["end_s"])]
        return f"{display(median(values)) if values else 'NA'} (n={len(values)})"
    return [len(valid), len(rows) - len(valid), rate("physical_success"), rate("plan_cover"),
            rate("oracle_match"), rate("first_plan_cover"), rate("first_oracle_match"),
            total("messages_r1"), total("messages_r2"), total("llm_calls"), total("cost_usd"),
            timing(True), timing(False)]


def write_outputs(rows, out):
    out.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r)) or ["run", "excluded"]
    with (out / "runs.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, sort_keys=True)
                             if isinstance(v, (dict, list)) else v for k, v in row.items()})
    headers = ["n", "excluded", "physical n/N", "cover last n/N", "oracle last n/N",
               "cover first n/N", "oracle first n/N", "messages r1 (known/n)",
               "messages r2 (known/n)", "calls (known/n)", "USD (known/n)",
               "median success s", "median all s"]
    structures = sorted({r["structure"] for r in rows})
    table = []
    for scene in sorted({r["scene"] for r in rows}):
        for structure in structures:
            group = [r for r in rows if r["scene"] == scene and r["structure"] == structure]
            table.append([scene, structure] + aggregate(group))
    excluded = markdown(["excluded run", "scene", "structure", "status", "reason"],
                        [[r[k] for k in ("run", "scene", "structure", "status", "excluded")]
                         for r in rows if r["excluded"]])
    warnings = markdown(["run", "warning"], [[r["run"], r["warnings"]] for r in rows if r["warnings"]])
    (out / "table.md").write_text(markdown(["scene", "structure"] + headers, table)
                                 + "\n" + excluded + "\n" + warnings, encoding="utf-8")
    summary = []
    for structure in structures:
        group = [r for r in rows if r["structure"] == structure]
        valid = [r for r in group if not r["excluded"]]
        cells = [sum(r.get("quadrant") == q for r in valid)
                 for q in ("P1_S1", "P1_S0", "P0_S1", "P0_S0")]
        summary.append([structure] + aggregate(group) + cells +
                       [sum(r.get("quadrant") is None for r in valid)])
    (out / "summary.md").write_text(markdown(["structure"] + headers +
        ["P1/S1", "P1/S0", "P0/S1", "P0/S0", "plan NA"], summary) + "\n" + excluded
        + "\n" + markdown(["run", "P1/S0 recorded diagnostics"],
        [[r["run"], json.dumps(r.get("failure_diagnostics"), ensure_ascii=False)]
         for r in rows if r.get("quadrant") == "P1_S0"]) + "\n" + warnings, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--scenes", type=Path, default=Path("data/scenes18b.json"))
    parser.add_argument("--brain", type=Path)
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    if not args.runs.is_dir():
        parser.error("runs directory does not exist")
    workspace = Path(__file__).resolve().parent
    target = args.out.resolve()
    if workspace not in target.parents or workspace / "data" == target or workspace / "data" in target.parents:
        parser.error("output must be inside this workspace and outside data/")
    scenes = {s["id"]: s for s in read_json(args.scenes)["scenes"]}
    suffix = {"team-llm26": "h", "team-llm25": "g", "team-llm23": "c"}.get(args.runs.name)
    rows = [analyze_run(p, scenes, args.brain, suffix)
            for p in sorted(args.runs.iterdir()) if p.is_dir()]
    write_outputs(rows, args.out)
    print(f"runs={len(rows)} included={sum(not r['excluded'] for r in rows)} "
          f"excluded={sum(bool(r['excluded']) for r in rows)} out={args.out}")


if __name__ == "__main__":
    main()
