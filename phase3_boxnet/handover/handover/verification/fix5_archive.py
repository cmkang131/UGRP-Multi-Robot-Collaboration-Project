"""Reproduce the S10 selection ledger from the planner and referee archives. CSV goes to stdout."""
import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def picks(records):
    return [r for r in records if r["point"] == "pick" and re.fullmatch(r"box:\d+", str(r.get("option")))]


def robot_rows(folder, team, rid):
    decisions = [r for r in team["decisions"] if r["rid"] == rid]
    chosen = picks(decisions)
    detailed = picks(team["brain"]["decisions"][rid])
    assert len(chosen) == len(detailed)
    out = folder / ("out-" + rid)
    summary = json.loads((out / "summary.json").read_bytes())
    with (out / "eval-only.jsonl").open() as stream:
        truth = [json.loads(line) for line in stream]
    origin = truth[0]["t"]
    assert all(b["t"] > a["t"] for a, b in zip(truth, truth[1:]))
    trips = summary["trips"] + [dict(approach=summary["approach_survey_v1"], carry_state=summary["carry_v1"],
                                     ended_at_s=math.inf)]
    # Each trip summary retains its *last* approach. Do not give it to an earlier, superseded pick.
    final_approaches = {}
    start = -1.
    for trip in trips:
        a = trip["approach"]
        before = [p["t"] for p in chosen if start < p["t"] <= trip["ended_at_s"]]
        if a["survey"]["selected_index"] is not None:
            final_approaches[before[-1]] = trip
        start = trip["ended_at_s"]

    for i, (pick, detail) in enumerate(zip(chosen, detailed)):
        t = pick["t"]
        until = chosen[i+1]["t"] if i+1 < len(chosen) else math.inf
        assert (round(detail["time"], 1), detail["option"]) == (t, pick["option"])
        label, = [o["text"] for o in detail["options"] if o["key"] == pick["option"]]
        colour = re.search(r"<(red|blue) box>", label)[1]
        failed = [d for d in decisions if t <= d["t"] < until and d.get("milestone") == "grasp_failed"]
        held = [r for r in summary.get("not_holding", []) if t <= r["at_s"] < until]
        assert len(failed) == len(held) <= 1
        failure = held[0] if held else {}
        rule = failure.get("rule", "")
        trip = final_approaches.get(t, {})
        approach = trip.get("approach", {})
        if approach:
            kind = approach["survey"]["entries"][approach["survey"]["selected_index"]]["kind"]
            assert colour == ("blue" if kind == "cyan" else "red")
        alignment = (approach.get("alignment") or {}).get("reason", "")
        if rule.startswith("blind grasp"):
            alignment = re.search(r"alignment ([^)]+)", rule)[1]
        if "no grasp was started" in rule:
            outcome, alignment = "pre_ACT", "no alignment"
        elif failure.get("dropped"):
            outcome = "carry_drop_report"
        elif failed:
            outcome = "ACT_failed_report"
        else:
            outcome = "no_failure_report"
        # The first evaluation row is at the solo origin. Planner seconds are rounded to 0.1.
        rows = [(n,e) for n,e in enumerate(truth,1) if t <= round(e["t"]-origin,1) < until]
        release = next((j for j,(_,e) in enumerate(rows) if e["skill"] == "release"), len(rows))
        grasp_end = failure.get("at_s", math.inf) if release == len(rows) else math.inf
        grasp = [(n,e) for n,e in rows[:release] if e["t"]-origin <= grasp_end+.00001]
        first_good = None
        last_target = None
        last_time = -math.inf
        stable_at = None
        for n,e in grasp:
            good = (team["boxes"][e["target_object"]]["colour"] == colour and not e["weld"] and
                    e["clearance"] >= .012 and e["tilt"] <= 10 and min(e["forces"]) >= .5)
            if e["target_object"] != last_target or e["t"] - last_time > .150001:
                first_good = None
            last_target = e["target_object"]
            last_time = e["t"]
            if not good:
                first_good = None
            else:
                if first_good is None:
                    first_good = e["t"]
                if stable_at is None and e["t"]-first_good >= 3.-1e-8:
                    stable_at = e["t"]
        end_line, end = grasp[-1]
        stop = trip.get("carry_state", {}).get("release_started_at_s")
        if stop is None:
            stop = failure.get("at_s")
        drop_line, loose_rows, carry_endpoint = "", 0, None
        if stable_at is not None and stop is not None:
            last_time = -math.inf
            for n,e in rows:
                if stable_at <= e["t"] <= origin + stop + .00001 and e["target_object"] == end["target_object"]:
                    carry_endpoint = e
                if e["t"] - last_time > .150001:
                    loose_rows = 0
                loose = (stable_at <= e["t"] < origin + stop and e["target_object"] == end["target_object"]
                         and e["clearance"] < .006 and max(e["forces"]) < .05)
                loose_rows = loose_rows + 1 if loose else 0
                last_time = e["t"]
                if loose_rows == 3 and not drop_line:
                    drop_line = n - 2
        yield dict(run=folder.name, robot=rid, pick_s=t, option=pick["option"], colour=colour,
                   failure_report_s=failed[0]["t"] if failed else "", category=outcome,
                   witness=rule or ("carry camera drop" if failure.get("dropped") else ""),
                   alignment=alignment, stable_in_grasp=int(stable_at is not None),
                   stable_world_s="" if stable_at is None else round(stable_at,1),
                   end_world_s=round(end["t"],1), eval_line=end_line, eval_target=end["target_object"],
                   eval_colour=team["boxes"][end["target_object"]]["colour"],
                   left_N=round(end["forces"][0],4) if outcome != "pre_ACT" else "",
                   right_N=round(end["forces"][1],4) if outcome != "pre_ACT" else "",
                   replay_start_or_failure_s="" if stop is None else round(stop,1), floor_unloaded_line=drop_line,
                   pre_replay_or_loss_left_N=round(carry_endpoint["forces"][0],4) if carry_endpoint else "",
                   pre_replay_or_loss_right_N=round(carry_endpoint["forces"][1],4) if carry_endpoint else "")


def main():
    rows = []
    for f in sorted((ROOT / "cloudrun/runs").glob("*/outroot/*S10*/team.json")):
        team = json.loads(f.read_bytes())
        for rid in team["robots"]:
            rows.extend(robot_rows(f.parent, team, rid))
    writer = csv.DictWriter(sys.stdout, fieldnames=rows[0], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
