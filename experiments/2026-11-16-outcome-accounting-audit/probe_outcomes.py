"""Synthetic evaluator audit; run from the repository root, no simulator/model."""
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.visual_box_evaluation import evaluate_visual_box_transfer
from scripts.evaluate_camera_short_transport import evaluate_transport_samples
from harness.pair_llm_eval import judge as pair_judge


def box(position, stable=False, constraint=False):
    return {"cargo": {"box": {"position": list(position), "stable": stable,
                             "constraints_active": {"r1": constraint},
                             "evaluation": {"success": False}}}}


def box_fixture():
    return [box((0, 0, .015)), box((.30, 0, .015), stable=True),
            [box((.1, 0, .060))]]


def camera_sample(t, phase, x, *, y=0., z=.10, lift=.04,
                  held=True, floor=False, robot_contact=False):
    return {"sim_time_s": t, "phase": phase, "position_m": [x, y, z],
            "height_above_start_m": lift,
            "constraints_active": {"r1": False, "r3": False},
            "contacts": {rid: {"left": held, "right": held, "bilateral": held}
                         for rid in ("r1", "r3")},
            "payload_floor_contact": floor, "payload_robot_contact": robot_contact}


def camera_fixture(final_x=.20, final_y=0., release_drift=0.):
    # Same positive control phase sequence and hold durations as the existing
    # tests/test_camera_short_transport_evaluation.py fixture.
    rows = [camera_sample(i * .1, "grasp_hold", 0.) for i in range(21)]
    rows += [camera_sample(2.1, "carry", .00), camera_sample(2.2, "carry", .05),
             camera_sample(2.3, "carry", .10), camera_sample(2.4, "carry", .15),
             camera_sample(2.5, "carry_stop", .20)]
    rows += [camera_sample(2.6, "place_lower", final_x, y=final_y),
             camera_sample(2.7, "place_open", final_x, y=final_y,
                           lift=0, held=False, floor=True),
             camera_sample(2.8, "place_retract", final_x, y=final_y,
                           lift=0, held=False, floor=True)]
    rows += [camera_sample(2.9+i*.1, "release_hold", final_x+release_drift*i/10,
                           y=final_y, lift=0, held=False, floor=True)
             for i in range(11)]
    return rows


results = []


def record(name, expected, operation):
    try:
        verdict = operation()
        success = verdict.get("success", verdict.get("success_provisional"))
        result = {"case": name, "expected_success": expected,
                  "actual_success": success, "verdict": verdict}
    except Exception as exc:
        result = {"case": name, "expected_success": expected,
                  "actual_success": False, "error": f"{type(exc).__name__}: {exc}"}
    result["matches_expectation"] = result["actual_success"] == expected
    results.append(result)


record("box_normal_success", True, lambda: evaluate_visual_box_transfer(*box_fixture()))
f = box_fixture(); f[2][0]["cargo"]["box"]["position"][2] = .015
record("box_drag_no_lift", False, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture(); f[1]["cargo"]["box"]["position"][0] = .25
f[2][0]["cargo"]["box"]["position"][2] = .055
record("box_exact_lift_and_distance_boundary", True, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture(); f[1]["cargo"]["box"]["position"][0] = .249999
record("box_below_distance_boundary", False, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture(); f[2][0]["cargo"]["box"]["constraints_active"]["r1"] = True
record("box_known_active_constraint", False, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture(); del f[2][0]["cargo"]["box"]["constraints_active"]
record("box_middle_constraint_record_missing", False, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture()
for snapshot in [f[0], f[1], *f[2]]:
    snapshot["cargo"]["box"].pop("constraints_active")
record("box_all_constraint_records_missing", False, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture()
for snapshot in [f[0], f[1], *f[2]]:
    snapshot["cargo"]["box"]["constraints_active"] = {}
# Explicitly recorded zero constraints is distinct from missing telemetry;
# the public evaluator contract does not require a non-empty map.
record("box_explicit_empty_constraint_maps", True, lambda: evaluate_visual_box_transfer(*f))
f = box_fixture(); f[1]["cargo"]["box"].pop("stable")
record("box_missing_final_stability", False, lambda: evaluate_visual_box_transfer(*f))

record("camera_normal_success", True, lambda: evaluate_transport_samples(camera_fixture()))
r = camera_fixture(); r[23]["contacts"]["r3"]["bilateral"] = False
record("camera_one_robot_loses_contact", False, lambda: evaluate_transport_samples(r))
record("camera_exact_displacement_and_drift_boundary", True,
       lambda: evaluate_transport_samples(camera_fixture(final_x=.23, final_y=.03)))
record("camera_beyond_displacement_boundary", False,
       lambda: evaluate_transport_samples(camera_fixture(final_x=.230001)))
r = camera_fixture(); r[-1].pop("payload_floor_contact")
record("camera_missing_floor_evidence", False, lambda: evaluate_transport_samples(r))
r = camera_fixture()
for row in r[23:]:
    row["sim_time_s"] += 10.
record("camera_ten_second_gap_inside_carry", False, lambda: evaluate_transport_samples(r))
r = camera_fixture()
for row in r[21:]:
    row["sim_time_s"] += 10.
record("camera_ten_second_gap_before_carry", False, lambda: evaluate_transport_samples(r))
r = camera_fixture()
for row in r[26:]:
    row["sim_time_s"] += 10.
record("camera_ten_second_gap_before_place", False, lambda: evaluate_transport_samples(r))
r = camera_fixture()
for row in r[29:]:
    row["sim_time_s"] += 10.
record("camera_ten_second_gap_before_release_hold", False, lambda: evaluate_transport_samples(r))
r = camera_fixture(); r[26]["phase"], r[28]["phase"] = r[28]["phase"], r[26]["phase"]
record("camera_retract_before_lower", False, lambda: evaluate_transport_samples(r))
r = camera_fixture(); r[21]["phase"], r[25]["phase"] = r[25]["phase"], r[21]["phase"]
# The runner explicitly allows carry to resume after stationary confirmation.
record("camera_carry_stop_then_resume_is_allowed", True, lambda: evaluate_transport_samples(r))

static = {"regions": {"zone_B": {"center_m": [1., 0.], "half_extents_m": [.2, .2]}}}
pair_base = [{"t": 0., "beam_xyz_m": [0., 0., .03]},
             {"t": 1., "beam_xyz_m": [.5, 0., .10]},
             {"t": 2., "beam_xyz_m": [1., 0., .03]}]
record("pair_provisional_geometry_positive", True,
       lambda: pair_judge(pair_base, static_map=static, target_zone="B"))
record("pair_empty_trajectory", False,
       lambda: pair_judge([], static_map=static, target_zone="B"))
p = deepcopy(pair_base); p[1]["beam_xyz_m"][2] = float("inf")
record("pair_nonfinite_lift_sample", False,
       lambda: pair_judge(p, static_map=static, target_zone="B"))
p = deepcopy(pair_base); p[-1]["t"] = .5
record("pair_backwards_timestamp", False,
       lambda: pair_judge(p, static_map=static, target_zone="B"))

print(json.dumps({"scope": "synthetic unit-level evidence, zero physics/model calls",
                  "cases": results,
                  "matches": sum(row["matches_expectation"] for row in results),
                  "total": len(results)}, indent=2, ensure_ascii=False))
