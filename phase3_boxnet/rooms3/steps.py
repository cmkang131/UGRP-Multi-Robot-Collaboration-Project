"""One synchronous BoxNet step. Resolve all requests before running any motor stages."""
import math

from handover.records import StopTrial
from handover import criteria
from rooms3.board import differences, landed
from rooms3.maps import ROBOTS


def snapshot(scene, sensors):
    perceived, views = sensors.observe()
    truth, witnesses = sensors.referee()
    return {"perceived": perceived, "referee": truth, "views": views, "witnesses": witnesses,
            "differences": differences(scene, truth, perceived)}


def resolve(scene, perceived, rid, action):
    colour, dest = action["colour"], action["to"]
    candidates = [b for b in perceived["boxes"] if b["room"] == rid and b["colour"] == colour
                  and b["on_floor"] and not b["delivered"]]
    if not candidates:
        return None, "box_not_observed"
    if dest == "target":
        targets = perceived["remaining_targets"][rid]
        if targets is None or colour not in targets:
            return None, "target_not_observed"
    else:
        pad_name = f"{rid}_{dest}"
        if pad_name not in scene["pads"]:
            return None, "not_a_neighbour"
        if perceived["pads"][pad_name] >= scene["pads"][pad_name]["capacity"]:
            return None, "occupied_pad"
    return candidates[0], None


def referee_match(truth, track, radius):
    candidates = [(math.dist(b["xy"], track["xy"]), b["id"]) for b in truth["boxes"]
                  if b["room"] == track["room"] and b["colour"] == track["colour"] and b["on_floor"]
                  and not b["delivered"] and math.dist(b["xy"], track["xy"]) <= radius]
    return min(candidates)[1] if candidates else None


def release_held(policy, rid):
    from harness import grasp_act_contract as contract
    from harness.release_code_v1 import ReleaseCodeV1

    policy.stage = "release"
    world = policy.w
    p = world.witness()
    policy.rec.event("station_hold", robot=rid, rule="ignore", pose=p)
    if not criteria.held(p, rid, ignore_tilt=True):
        raise StopTrial("station_hold", "no bilateral hold and clearance at the station")
    world.carrying = None
    replay = ReleaseCodeV1(contract, world.pwm[rid])
    detached = False
    for _ in range(len(replay.rows)):
        row, _ = replay.step(policy.rec.now)
        world.control(rid, row)
        p = world.witness()
        if not detached and criteria.free(p):
            policy.rec.event("detached", robot=rid, pose=p, grip_pwm=row["pwm"]["1"])
            if row["pwm"]["1"] <= 1550:
                raise StopTrial("early_detach", "lost both contacts before gripper opening")
            detached = True
    rest = []
    for _ in range(10):
        policy.idle(rid)
        rest.append(world.witness())
    policy.rec.event("placement", robot=rid, rest=rest, frame=policy.photo("landed"))
    if not detached or not all(landed(p) for p in rest):
        raise StopTrial("unsettled_release", "box did not detach and rest on the floor")


def run_step(scene, requests, backend, *, before=None):
    if set(requests) - set(ROBOTS):
        raise ValueError("step contains an unknown robot")
    before = snapshot(scene, backend) if before is None else before
    rows, assignments = {}, {}
    for rid in ROBOTS:
        action = requests.get(rid)
        row = rows[rid] = {"requested": action, "status": "idle" if action is None else "not_doable"}
        if action is None:
            continue
        track, reason = resolve(scene, before["perceived"], rid, action)
        if reason:
            row["reason"] = reason
            continue
        pad = f"{rid}_{action['to']}"
        if pad in scene["pads"] and before["referee"]["pads"][pad] >= scene["pads"][pad]["capacity"]:
            row["reason"] = "occupied_pad"
            continue
        # The referee associates body identity only after the own camera has selected a track.
        # The motor backend receives just the observed track. Finger contact identifies the lifted body.
        row.update(track=track, expected_body=referee_match(before["referee"], track, backend.identity_radius))
        assignments[rid] = track

    for rid, track in assignments.items():
        row, action = rows[rid], requests[rid]
        pad = f"{rid}_{action['to']}"
        if pad in scene["pads"] and backend.referee()[0]["pads"][pad] >= scene["pads"][pad]["capacity"]:
            row["reason"] = "occupied_pad"   # An earlier physical move may have dropped a box here.
            continue
        row["status"] = "executed_failed"
        try:
            row["lifted_body"] = backend.move(rid, track, action["to"])
        except StopTrial as exc:
            if exc.stage == "room_limit":
                raise  # Stop integration immediately if a chassis centre ever crosses its room.
            row.update(reason=exc.stage, detail=str(exc))
            backend.recover(rid)

    after = snapshot(scene, backend)
    bodies = {b["id"]: b for b in after["referee"]["boxes"]}
    for rid in assignments:
        row = rows[rid]
        expected = row["expected_body"]
        b, dest = bodies.get(expected), requests[rid]["to"]
        if b is not None:
            row["measured_landing"] = b
            if dest == "target":
                at_goal = b["delivered"] and b["room"] == rid
            else:
                at_goal = b["pad"] == f"{rid}_{dest}"
            row["landed_as_requested"] = b["on_floor"] and at_goal
        if "reason" in row:
            continue
        if b is None or row["lifted_body"] != expected:
            row["reason"] = "grasp_identity"
        elif row["landed_as_requested"]:
            row["status"] = "moved"
        else:
            row["reason"] = "missed_landing"
    return {"before": before, "actions": rows, "after": after}
