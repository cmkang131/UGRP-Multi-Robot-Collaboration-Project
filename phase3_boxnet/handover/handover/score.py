"""Re-score raw event witnesses and chassis envelopes against the frozen twelve-row table."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handover import criteria, layout


class Failure(Exception):
    def __init__(self, stage, reason, at=0.):
        super().__init__(reason)
        self.stage, self.at = stage, at


def check(ok, stage, reason, at):
    if not ok:
        raise Failure(stage, reason, at)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-6)


def native_trace(trial, rows, run, events):
    previous_step, last = -1, 0.
    clear = next((e["sim_s"] for e in events if e["event"] == "donor_clear"), math.inf)
    rooms = {rid: layout.room(trial, rid) for rid in ("r1", "r2")}
    samples = {}
    for row in rows:
        step, t = int(row["step"]), float(row["sim_s"])
        check(math.isfinite(t) and close(t, step*run["dt"]) and step > previous_step
              and ((previous_step < 0 and step == 0) or (previous_step >= 0 and 0 < t-last <= .100001)),
              "room_trace", "gap or inconsistent native-step count", last)
        for rid, bounds in rooms.items():
            x, y, x0, x1, y0, y1 = (float(row[rid+"_"+k]) for k in ("x","y","xmin","xmax","ymin","ymax"))
            check(all(map(math.isfinite, (x,y,x0,x1,y0,y1))) and x0 <= x <= x1 and y0 <= y <= y1,
                  "room_trace", "invalid per-step position envelope", t)
            check(x0 > bounds[0] and x1 < bounds[1] and y0 > bounds[2] and y1 < bounds[3],
                  "room_limit", rid+" reached or crossed a room boundary", t)
            sx, sy = trial["starts"][rid][:2]
            if not step:
                check(math.dist((x,y), (sx,sy)) < .001, "room_trace", "wrong initial chassis position", t)
            if rid == trial["receiver"] and t <= clear+1e-7:
                check(max(math.hypot(xx-sx, yy-sy) for xx in (x0,x1) for yy in (y0,y1)) <= .035,
                      "receiver_wait", "receiver left its starting footprint before donor clear", t)
            samples[(step, rid)] = (x, y)
        previous_step, last = step, t
    check(previous_step >= 0 and previous_step == run["last_step"] and close(last, run["sim_s"]),
          "room_trace", "trace does not cover setup through episode end", last)
    return samples


def body_pose(pose, body_id):
    return (pose["body"] == layout.BODY and pose["body_id"] == body_id
            and all(math.isfinite(pose[k]) for k in ("x","y","z","yaw","tilt_deg","clearance_m","speed_m_s"))
            and 0 <= pose["tilt_deg"] <= 180 and pose["speed_m_s"] >= 0
            and set(pose["finger_n"]) == {"r1","r2"} and all(len(v) == 2 and all(math.isfinite(f) and f >= 0 for f in v)
                                                         for v in pose["finger_n"].values()))


def stable_lift(rows, now, start):
    return (len(rows) >= 31 and rows[0][0] >= start and close(rows[-1][0], now)
            and rows[-1][0] - rows[0][0] >= layout.LIFT_SECONDS-1e-6
            and all(close(b[0]-a[0], .1) for a,b in zip(rows, rows[1:]))
            and all(len(row) == 5 and all(map(math.isfinite, row)) and row[1] >= layout.LIFT_FLOOR
                    and 0 <= row[2] <= layout.TILT_TOL and min(row[3:]) >= layout.FINGER_N for row in rows))


def milestones(trial, events, run, samples, frame_ok):
    station_tilt = run.get("station_tilt", "strict")
    check(station_tilt in layout.STATION_TILT_MODES, "records", "unknown station tilt mode", 0.)
    stages = ["setup", "donor_pick", "release", "donor_clear", "receiver_seen", "receiver_pick",
              "sign_seen", "set_down", "complete"]
    index, previous, body = 0, 0., None
    attempts = {"r1": 0, "r2": 0}
    opened, replay_start, pending, scan = False, None, None, False
    tilted_at_station = False
    lost = None
    for seq, event in enumerate(events):
        t, name = event["sim_s"], event["event"]
        stage = stages[min(index, len(stages)-1)]
        rid = trial["donor"] if stage in ("donor_pick","release","donor_clear") else trial["receiver"]
        def need(ok, reason):
            check(ok, stage, reason, t)
        check(math.isfinite(t) and previous <= t <= run["sim_s"]+1e-6 and event["seq"] == seq,
              "records", "invalid event time or sequence", previous)
        previous = t
        if name in ("failure", "error"):
            raise Failure(event["stage"], event["reason"], t)
        if name in ("room_guard", "room_violation"):
            raise Failure("room_limit" if name == "room_violation" else name, event["robot"], t)
        if name == "carry_loss":
            raise Failure(event["stage"], event["robot"]+" dropped the box during transport", t)
        if name == "overhead_lost":
            check(lost is None and (event["stage"], event["robot"]) == (stage, rid),
                  "records", "unexpected overhead loss", t)
            lost = event
            continue
        if name in ("overhead_recovered", "overhead_timeout"):
            check(lost is not None and (event["stage"], event["robot"]) == (stage, rid)
                  and event["lost_seq"] == lost["seq"] and close(event["start_sim_s"], lost["sim_s"])
                  and close(event["duration_s"], t-lost["sim_s"]) and t > lost["sim_s"]
                  and type(event["missed_frames"]) is int and event["missed_frames"] > 0,
                  "records", "unpaired or inconsistent overhead interval", t)
            if name == "overhead_timeout":
                raise Failure(stage, event["reason"], t)
            lost = None
            continue
        check(lost is None, "records", "stage advanced with the overhead card still lost", t)
        if name in ("start", "checkpoint", "approach_end"):
            continue
        if "pose" in event:
            need(close(event["pose"]["sim_s"], t), "body observation is from another time")
        for field in ("frame","wrist_frame"):
            if field in event:
                need(frame_ok(event[field]), "referenced image missing or invalid")
        if name == "world_ready":
            need(index == 0 and event["welds"] == 0 and event["controllers"] == ["r1","r2"]
                 and event["body"] == layout.BODY and type(event["body_id"]) is int and event["body_id"] > 0
                 and 0 < event["dt"] <= .01 and close(event["dt"], run["dt"]), "invalid physics identity")
            body = event["body_id"]
            index += 1
        elif name == "attempt_start":
            need(stage in ("donor_pick", "receiver_pick") and event["robot"] == rid
                 and pending is None and attempts[rid] < 2 and event["attempt"] == attempts[rid]+1,
                 "unexpected or excess grasp attempt")
            pending = t
            attempts[rid] += 1
        elif name == "grasp_attempt":
            need(stage in ("donor_pick", "receiver_pick") and pending is not None and event["robot"] == rid
                 and event["attempt"] == attempts[rid], "unpaired grasp result")
            if event["outcome"] == "miss":
                need(attempts[rid] < 2, "two grasp attempts failed")
            else:
                need(event["outcome"] == "lift" and body_pose(event["pose"], body)
                     and criteria.held(event["pose"], rid) and stable_lift(event["lift_samples"], t, pending)
                     and "frame" in event, "same-body bilateral stable lift not established")
                index += 1
            pending = None
        elif name in ("release_start", "set_down_start"):
            pose = event["pose"]
            need(stage+"_start" == name and replay_start is None and event["robot"] == rid
                 and body_pose(pose, body) and criteria.held(pose, rid, ignore_tilt=station_tilt == "ignore"),
                 "box lost before placement")
            tilted_at_station = pose["tilt_deg"] > layout.TILT_TOL
            if stage == "release":
                need(math.dist(event["chassis"], layout.xy(trial["direction"], -layout.RELEASE_STAND, 0)) <= .09,
                     "replay did not start at the donor stand-off")
            if samples is not None:
                actual = samples.get((round(t/run["dt"]), rid))
                need(actual is not None and math.dist(actual, event["chassis"]) < .001, "release station disagrees with chassis trace")
            replay_start = t
        elif name in ("release_open", "set_down_open"):
            pose = event["pose"]
            need(stage+"_open" == name and replay_start is not None and not opened and event["robot"] == rid
                 and body_pose(pose, body) and criteria.free(pose) and "frame" in event,
                 "physical separation during the release is missing")
            if stage == "release":
                # Separation can precede settling. Keep the opening position and yaw checks.
                opening_check = criteria.aligned_with_mark if tilted_at_station else criteria.at_mark
                need(opening_check(trial, pose), "box missed the mark at opening")
            opened = True
        elif name in ("release", "set_down"):
            pose, rest = event["pose"], event["rest"]
            need(name == stage and opened and event["robot"] == rid and event["rows"] == 87
                 and close(t-replay_start, 9.7) and "frame" in event
                 and len(rest) == 10 and pose == rest[-1] and close(rest[-1]["sim_s"], t)
                 and all(close(b["sim_s"]-a["sim_s"], .1) for a,b in zip(rest, rest[1:]))
                 and all(body_pose(p, body) and criteria.resting(p) for p in rest),
                 "missing detached, settled body after release replay")
            if stage == "release":
                need(all(criteria.at_mark(trial, p) for p in rest), "release outside mark or orientation tolerance")
            else:
                delta = layout.sign_relative(trial, pose["x"], pose["y"])
                relative = layout.pose_at_sign(trial, pose)
                need(all(criteria.at_sign(trial, p) for p in rest) and math.dist(event["sign_relative"], delta) < 1e-6
                     and all(close(event["pose_at_sign"][k], v) for k,v in relative.items()),
                     "box outside destination sign area")
            index += 1
            opened, replay_start = False, None
        elif name == "donor_clear":
            need(stage == name and event["robot"] == rid and layout.park_clear(trial, *event["xy"])
                 and body_pose(event["pose"], body) and criteria.resting(event["pose"])
                 and criteria.at_mark(trial, event["pose"]), "donor did not clear with the free box left on the mark")
            if samples is not None:
                actual = samples.get((round(t/run["dt"]), rid))
                need(actual is not None and math.dist(actual, event["xy"]) < .001, "donor-clear pose disagrees with chassis trace")
            index += 1
        elif name == "scan_start":
            need(stage == "receiver_seen" and event["robot"] == rid and not scan and
                 math.dist(event["xy"], layout.xy(trial["direction"], layout.SCAN_STAND, 0)) < .09, "scan before clearance or outside station")
            if samples is not None:
                actual = samples.get((round(t/run["dt"]), rid))
                need(actual is not None and math.dist(actual, event["xy"]) < .001, "scan station disagrees with chassis trace")
            scan = True
        elif name == "receiver_seen":
            need(stage == name and scan and event["robot"] == rid and "frame" in event
                 and event["kind"] == ("cyan" if trial["colour"] == "blue" else "red")
                 and math.hypot(*event["observed_xy"]) <= .22, "receiver did not see the intended box at the mark")
            index += 1
        elif name == "sign_seen":
            need(stage == name and event["robot"] == rid and event["sign"] == trial["receiver_sign"] and "frame" in event
                 and len(event["corners_px"]) == 4 and all(len(p) == 2 and all(map(math.isfinite,p)) for p in event["corners_px"]),
                 "receiver did not read its destination sign")
            index += 1
        elif name == "complete":
            pose = event["pose"]
            need(index == len(stages)-1 and seq == len(events)-1 and close(t, run["sim_s"]), "incomplete timeline")
            check(body_pose(pose, body) and criteria.resting(pose) and criteria.at_sign(trial, pose),
                  "set_down", "missing final resting body at sign", t)
            index += 1
        else:
            raise Failure("records", "unknown event "+name, t)
    if index < len(stages):
        raise Failure(stages[index], "missing stage evidence", run["sim_s"])
    check(run["status"] == "finished", "records", "incomplete run", previous)


def score(trial, events, rows, run, frame_ok):
    counts = {r: sum(e.get("event") == "attempt_start" and e.get("robot") == trial[r] for e in events)
              for r in layout.ROLES}
    result = {"trial": trial["trial"], "retries": {r: max(0, n-1) for r,n in counts.items()},
              "evaluated": run["status"] in ("finished","failed") and run["dt"] is not None}
    failures, samples = [], None
    if run["dt"] is not None:
        try:
            samples = native_trace(trial, rows, run, events)
        except Failure as error:
            failures.append(error)
    try:
        milestones(trial, events, run, samples, frame_ok)
    except Failure as error:
        failures.append(error)
    if failures:
        error = min(failures, key=lambda e: e.at)
        if error.stage in ("records", "room_trace"):
            result["evaluated"] = False
        return dict(result, status="FAIL", stage=error.stage, reason=str(error))
    return dict(result, status="SUCCESS", stage="complete", reason="")


def score_dir(folder, table=None):
    trial_id, table_name = None, None
    try:
        trial = json.loads((folder / "trial.json").read_text())
        trial_id = trial["trial"]
        table_name = trial.get("trial_table", layout.TABLE.name)
        if table is None:
            table = layout.trials(table_name)
        run = json.loads((folder / "run.json").read_text())
        if trial != table[trial_id] or run["trial"] != trial_id or run["schema"] != "handover.run.v1":
            raise ValueError("trial definition or run identity differs from the preselected table")
        with (folder / "events.jsonl").open() as stream:
            events = [json.loads(line) for line in stream]
        def frame_ok(name):
            if Path(name).name != name or not name.endswith(".jpg"):
                return False
            path = folder / name
            if not path.is_file() or path.is_symlink():
                return False
            from PIL import Image
            try:
                with Image.open(path) as img:
                    if img.format != "JPEG":
                        return False
                    img.load()
                    return True
            except (OSError, ValueError):
                return False
        with (folder / "chassis.csv").open(newline="") as stream:
            return dict(score(trial, events, csv.DictReader(stream), run, frame_ok), trial_table=table_name)
    except (OSError, ValueError, KeyError, IndexError, TypeError, OverflowError, ArithmeticError) as exc:
        return {"trial": trial_id, "trial_table": table_name if table_name in layout.TRIAL_TABLES else None,
                "status": "FAIL", "stage": "records", "reason": str(exc),
                "evaluated": False, "retries": dict.fromkeys(layout.ROLES, 0)}


def aggregate(results):
    tables = {r.get("trial_table", layout.TABLE.name) for r in results} - {None}
    if len(tables) > 1:
        return 0, "INVALID (mixed trial tables)"
    ids = [r["trial"] for r in results]
    if len(set(ids)) != len(ids):
        return sum(r["status"] == "SUCCESS" and ids.count(r["trial"]) == 1 for r in results), "INVALID (duplicate trial ID)"
    passed = sum(r["status"] == "SUCCESS" for r in results)
    if set(ids) != set(range(1, 13)) or not all(r["evaluated"] for r in results):
        return passed, "PENDING"
    return passed, "PASS" if passed >= 10 else "FAIL"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("dirs", nargs="+", type=Path)
    args = p.parse_args(argv)
    results = [score_dir(folder) for folder in args.dirs]
    tables = sorted({r["trial_table"] for r in results if r["trial_table"]})
    print("trial table " + (", ".join(tables) or "unknown"))
    for folder, r in zip(args.dirs, results):
        print(f"trial {r['trial']}  {r['status']}  {r['stage']}  retries donor={r['retries']['donor']} "
              f"receiver={r['retries']['receiver']}  {r['reason']}  [{folder}]")
    passed, gate = aggregate(results)
    retries = {k: sum(r["retries"][k] for r in results) for k in layout.ROLES}
    print(f"{passed}/12 successes  |  {len({r['trial'] for r in results if r['evaluated']})} evaluated  |  "
          f"retries donor={retries['donor']} receiver={retries['receiver']}  |  gate {gate} (requires 10/12)")
    return 2 if gate.startswith("INVALID") else int(any(r["status"] != "SUCCESS" for r in results) and gate != "PASS")


if __name__ == "__main__":
    sys.exit(main())
