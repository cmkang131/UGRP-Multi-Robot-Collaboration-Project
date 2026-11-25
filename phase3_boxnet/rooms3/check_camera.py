"""Exercise the FIX4 camera checks in the generated three-room MJCF, without an actor."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import math
import os
from pathlib import Path
import sys

from rooms3.maps import ROBOTS
from rooms3.runtime import configure


def select_in_room(entries, kind, origin, bounds):
    from handover.layout import margin

    for index, entry in enumerate(entries):
        if entry["kind"] == kind and margin(bounds, *absolute(origin, entry["x"], entry["y"])) > 0:
            return index
    return None


def absolute(origin, x, y):
    a, b, yaw = origin
    return [a + x * math.cos(yaw) - y * math.sin(yaw), b + x * math.sin(yaw) + y * math.cos(yaw)]


def run(bundle, out, record):
    import cv2
    import mujoco
    from PIL import Image
    from harness import grasp_act_contract as contract, overhead_v1 as overhead, robot_tags_v1 as tags
    from harness.approach_survey_v1 import FAR_POSTURE, SurveyApproach
    from harness.approach_survey_v1_parts import ground_projection
    from rooms3.camera_rig import CameraRig

    scene = json.loads((bundle / "map.json").read_bytes())
    if scene != overhead._MAP or scene != tags._MAP:
        raise ValueError("frozen camera readers loaded a different map")
    cv2.setNumThreads(1)
    record.update(mujoco=mujoco.__version__, opencv=cv2.__version__, stage="compile_and_bind")
    with ExitStack() as stack:
        world = CameraRig(bundle, scene, stack)
        record.update(stage="camera_observations", calibration_status=world.calibration_status)
        for _ in range(10):
            world.tick({})
        own = world.positions()
        for name, image in world.last_ceiling_frames.items():
            Image.fromarray(image).save(out / f"{name}.png")
        if set(own) != set(ROBOTS):
            # The same crop decoder and the same undisturbed sensor frames used for FIX4 recovery.
            from harness.handover_policy import MagnifiedMarkers
            reader = overhead.OverheadReader()
            reader.detector = MagnifiedMarkers(reader.detector)
            recovered = reader.read(world.last_ceiling_frames)
            for rid, pose in recovered.items():
                own.setdefault(rid, pose)
        record["ceiling_poses"] = own
        if set(own) != set(ROBOTS):
            raise ValueError(f"ceiling cameras missed {sorted(set(ROBOTS) - set(own))}")
        reference_poses = {rid: world.actual_pose(rid) for rid in ROBOTS}
        metres_per_pixel = (overhead.HEIGHT_M - overhead.BASE_Z - overhead.CARD_AT[2]) / world.reader.f
        yaw_limit = math.atan2(1, 12 - 2)  # same 12-pixel centre-card budget as the hand-over check
        xy_limit = math.sqrt(2) * metres_per_pixel + 2 * abs(overhead.CARD_AT[0]) * math.sin(yaw_limit / 2)
        record.update(ceiling_xy_tolerance_m=xy_limit, ceiling_yaw_tolerance_rad=yaw_limit)
        checks, surveys = {}, {}
        record["robots"] = checks
        sign_reader = tags.TagReader(ground_projection.K, ground_projection.D)
        for rid in ROBOTS:
            room = scene["rooms"][rid]
            boxes = [b for b in scene["boxes"] if b["room"] == rid]
            if len(boxes) != 1:
                raise ValueError("the acceptance maps require one box initially in each room")
            cargo = boxes[0]
            kind = {"blue": "cyan", "red": "red"}[cargo["colour"]]
            def chooser(entries, kind=kind, origin=own[rid], bounds=room["bounds"]):
                return select_in_room(entries, kind, origin, bounds)
            survey = SurveyApproach(contract, chooser, survey_fast=True, align_fast=True, approach_visual=True)
            surveys[rid] = survey
            jpg = world.wrist(rid)
            (out / f"{rid}-first.jpg").write_bytes(jpg)
            first = survey.student.Survey(survey.baseline)
            first.observe(jpg, FAR_POSTURE)
            checks[rid] = {"kind": kind, "box": cargo["id"], "colour": cargo["colour"],
                           "sign_id": room["sign"], "sign_frame": None,
                           "first_xy": [absolute(own[rid], *t["points"][0]) for t in first._tracks
                                        if t["kind"] == kind]}
        for step in range(100):
            rows = {}
            for rid, survey in surveys.items():
                if survey.index is not None or survey.arrived:
                    continue
                jpg = world.wrist(rid) if survey.needs_frame() else b""
                check = checks[rid]
                if jpg and check["sign_frame"] is None:
                    for method in (sign_reader.read, sign_reader.read_signs_raw):
                        tag = next((t for t in method(jpg) if t.get("sign") == check["sign_id"]), None)
                        if tag:
                            path = f"{rid}-sign-{step}.jpg"
                            (out / path).write_bytes(jpg)
                            check.update(sign_frame=path, sign_reader=method.__name__, sign_corners=tag["corners_px"])
                            break
                rows[rid] = survey.step(jpg, float(world.data.time))
            if not rows:
                break
            world.tick(rows)

        failures = []
        for rid, survey in surveys.items():
            check = checks[rid]
            # Only the comparison below receives physical poses. The chooser above received own RGB tracks.
            target = world.data.body(check["box"]).xpos[:2].tolist()
            actual = reference_poses[rid]
            tolerance = survey.baseline.POS_GATE_M
            matched = survey.entries[survey.index] if survey.index is not None else None
            xy = absolute(own[rid], matched["x"], matched["y"]) if matched else None
            check.update(entries=survey.entries, selected=survey.index, selected_xy=xy, physical_xy=target,
                         identity_radius_m=tolerance, base_xy_error_m=math.dist(own[rid][:2], actual[:2]),
                         base_yaw_error_rad=abs(math.remainder(own[rid][2] - actual[2], 2 * math.pi)))
            checks_ok = {
                "ceiling_pose": check["base_xy_error_m"] <= xy_limit and check["base_yaw_error_rad"] <= yaw_limit,
                "sign": bool(check["sign_frame"]),
                "first_wrist": any(math.dist(x, target) <= tolerance for x in check["first_xy"]),
                "own_selection": matched is not None and matched["kind"] == check["kind"]
                                 and math.dist(xy, target) <= tolerance,
            }
            check["checks"] = checks_ok
            failures.extend(f"{rid}/{name}" for name, ok in checks_ok.items() if not ok)
        if failures:
            raise ValueError("camera checks failed: " + ", ".join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", required=True, type=Path, help="directory containing map.json and scene.xml")
    parser.add_argument("--out", required=True, type=Path, help="fresh evidence directory")
    args = parser.parse_args()
    bundle, out = args.scene.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {"schema": "rooms3.camera-check.v1", "scene": bundle.name, "status": "error", "stage": "inputs"}
    cwd = Path.cwd()
    try:
        record.update(seed=json.loads((bundle / "map.json").read_bytes())["source"]["seed"],
                      xml_sha256=hashlib.sha256((bundle / "scene.xml").read_bytes()).hexdigest(),
                      stage="load_runtime")
        configure(bundle, out)
        os.chdir(out)
        run(bundle, out, record)
        record.update(status="passed", stage="complete")
    except Exception as error:
        record["reason"] = f"{type(error).__name__}: {error}"
    finally:
        os.chdir(cwd)
        (out / "check.json").write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")
    print(record["status"], record.get("reason", bundle.name))
    return 0 if record["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
