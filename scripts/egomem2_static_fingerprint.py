"""Verify the opt-in servo-FK change and refresh the e2e18 static-view fingerprint.

The static-view cache is guarded by hashes of its inputs.  egomem2 adds an
opt-in `servo_fk_carry_v1` branch to harness/servo_camera_fk.py.  The existing
`servo_fk_v1` behavior must be unchanged before the guard is refreshed.

Run on a CPU (no simulator):
  git show origin/main:harness/servo_camera_fk.py > /tmp/old_servo_camera_fk.py
  python scripts/egomem2_static_fingerprint.py --old-source /tmp/old_servo_camera_fk.py \
      --output experiments/2026-10-17-egomem2/operations/static-fingerprint.json --update
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STATIC = ROOT / "configs/e2e18_static_views_v1.json"
SERVO = "harness/servo_camera_fk.py"
OLD_SHA256 = "0083e07af1a78b1da35cefb7f85011f65e1e2c61b5c21c03f337ceaff741a3b3"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The copied source is outside harness/, so point it at the same geometry.
    module.MODEL = ROOT / "harness/data/servo_camera_v3_chain.json"
    return module


def same(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return np.array_equal(np.asarray(a), np.asarray(b))
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    return a == b


def call(module, servo, pose):
    try:
        return ("ok", module.transform_from_commands(servo, camera_pose=pose))
    except Exception as exc:  # compare failure modes, not tracebacks
        return ("error", type(exc).__name__, str(exc))


def call_camera_output(module, servo, pose):
    sentinel = object()
    try:
        out = module.camera_output(sentinel, camera_pose=pose, servo=servo)
        return ("ok", "same_object" if out is sentinel else out)
    except Exception as exc:
        return ("error", type(exc).__name__, str(exc))


def call_commanded(module, servo):
    try:
        return ("ok", module.commanded_joints(servo))
    except Exception as exc:
        return ("error", type(exc).__name__, str(exc))


def cases():
    yaw = [1500, 1600, 1601, 2000]
    arm = [500, 700, 1000, 1500, 2000, 2300, 2500]
    for vals in itertools.product(yaw, arm, arm, arm, arm):
        yield {1: vals[0], 3: vals[1], 4: vals[2], 5: vals[3], 6: vals[4]}
    rng = random.Random(20261017)
    for _ in range(5000):
        yield {1: rng.choice(yaw), **{k: rng.randint(500, 2500) for k in (3, 4, 5, 6)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()
    old_sha = sha256(args.old_source)
    if old_sha != OLD_SHA256:
        raise SystemExit(f"unexpected old servo source sha256: {old_sha}")
    new_sha = sha256(ROOT / SERVO)
    if new_sha == old_sha:
        raise SystemExit("servo source did not change")
    old = load_module(args.old_source, "egomem2_old_servo_fk")
    new = load_module(ROOT / SERVO, "egomem2_new_servo_fk")
    record = json.loads(STATIC.read_text())
    other = {k: sha256(ROOT / k) for k in record["source_sha256"] if k != SERVO}
    other_match = other == {k: v for k, v in record["source_sha256"].items() if k != SERVO}
    mismatches = []
    checked = 0
    for servo in cases():
        checks = [("commanded_joints", call_commanded(old, servo), call_commanded(new, servo))]
        for pose in ("off", "servo_fk_v1"):
            checks.append((f"transform:{pose}", call(old, servo, pose), call(new, servo, pose)))
            checks.append((f"camera_output:{pose}", call_camera_output(old, servo, pose), call_camera_output(new, servo, pose)))
        for name, a, b in checks:
            checked += 1
            if not same(a, b):
                mismatches.append({"servo": servo, "check": name, "old": repr(a), "new": repr(b)})
                if len(mismatches) >= 5:
                    break
        if len(mismatches) >= 5:
            break
    result = {
        "status": "EXACT_COMPATIBILITY" if not mismatches and other_match else "MISMATCH",
        "servo_source": SERVO,
        "old_sha256": old_sha,
        "new_sha256": new_sha,
        "other_static_inputs_match": other_match,
        "cases_checked": checked,
        "mismatches": mismatches,
        "static_views": len(record["views"]),
        "static_top": record["top"],
        "scope": "transform_from_commands/camera_output for off and existing servo_fk_v1; new carry option not compared",
        "reproduction": [sys.executable, "scripts/egomem2_static_fingerprint.py", "--old-source", str(args.old_source), "--output", str(args.output)],
    }
    if mismatches or not other_match:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        raise SystemExit("behavior mismatch; static fingerprint not updated")
    if args.update:
        record["source_sha256"][SERVO] = new_sha
        STATIC.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
        result["fingerprint_updated"] = True
        result["static_file_sha256"] = sha256(STATIC)
    else:
        result["fingerprint_updated"] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
