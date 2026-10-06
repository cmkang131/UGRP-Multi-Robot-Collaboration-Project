"""Offline audit of floor_light_nearclip_v1 side effects on SAVED frames (no simulation, 2026-10-05).

  gate      per-frame own-image gate measures (registered v98 values) of one robot's frames
  relation  grip-relation coverage/IoU of one frame at near_m = 22.2 mm (old render) and 4.4 mm (nearclip)
  nearm     expected-support pixel counts at near_m 22.2 / 4.4 / 0 mm for every distinct arm pose of a robot
  hover     pre-grasp hover-pose beam estimate (observe_beam / stationary_beam_estimate) of one robot
  overlay   side-by-side expected-support (red) / beam colour (blue) / both (green) overlay of two runs

Usage: python nearclip_side_effect_audit.py <cmd> <run_dir> <rid> [times...]   (run_dir holds robots/<rid>/frames.jsonl)
"""
import base64, collections, json, math, sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness import visual_arm_v3 as arm
from harness import zone_pair_vision as frozen
from harness.owncam_pair_beam_v2 import _valid, observe_beam
from harness.owncam_pair_lift_v3 import beam_colour_mask_low
from harness.owncam_view import _pixel_rays
from harness.zone_pair_grasp import stationary_beam_estimate
from sim.zone_cargo import kind

GATE = (1.0, .22)                        # registered v98 values: spread_min, std_min
OLD_NEAR_M, NEARCLIP_M = 0.02222497706328516, 0.0004*11.112488


def rows_of(run, rid):
    return [json.loads(line) for line in open(f'{run}/robots/{rid}/frames.jsonl')]


def gate_stats(path):
    v = cv2.cvtColor(cv2.imread(path, cv2.IMREAD_COLOR), cv2.COLOR_BGR2HSV)[..., 2]
    val = v[_valid()]
    lo, hi = np.percentile(val, [1, 99])
    dark = float((val <= frozen.dark_level(v)).mean())
    return dict(dark=dark, spread=float(hi-lo), std=float(val.std()), ok=bool(dark < .25 and hi-lo >= GATE[0] and val.std() >= GATE[1]))


def support(servo, near_m):
    xs, ys, normal, valid = _pixel_rays(4)
    origin, axes = arm.camera_extrinsics(servo)
    rays = np.column_stack((normal, np.ones(len(normal)))) @ np.asarray(axes)
    tool = arm.tool_pose(servo)
    yaw = math.radians(tool.yaw_left_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    rot = np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])
    origin = (np.asarray(origin)-np.array([tool.x_m, tool.y_m, tool.z_m])) @ rot
    rays = rays @ rot
    spec = kind('long_beam')
    origin = origin + np.asarray(spec.grasps[0].grip_xyz)
    entries = []
    for part in spec.parts:
        low, high = np.asarray(part.center)-part.size, np.asarray(part.center)+part.size
        with np.errstate(divide='ignore', invalid='ignore'):
            a, b = (low-origin)/rays, (high-origin)/rays
        enter, leave = np.minimum(a, b).max(axis=1), np.maximum(a, b).min(axis=1)
        entries.append(np.where(leave >= np.maximum(enter, 0.), enter, np.inf))
    entries = np.asarray(entries)
    expected = valid & np.isfinite(entries[0]) & (entries[0] >= near_m) & (entries.argmin(axis=0) == 0)
    return xs.astype(int), ys.astype(int), valid, expected


def frame_at(run, rid, t):
    r = min(rows_of(run, rid), key=lambda r: abs(r['sim_time']-t))
    return cv2.imread(f"{run}/{r['path']}"), {int(k): v for k, v in r['commanded_servo'].items()}, r['sim_time']


def main():
    cmd, run, rid, *rest = sys.argv[1:]
    if cmd == 'gate':
        for r in rows_of(run, rid):
            s = gate_stats(f"{run}/{r['path']}")
            if not s['ok'] or s['spread'] < 3:
                print(f"t={r['sim_time']:.2f} frame={r['frame_id']} {s}")
    elif cmd == 'relation':
        for t in map(float, rest):
            frame, servo, t = frame_at(run, rid, t)
            for near in (OLD_NEAR_M, NEARCLIP_M):
                xs, ys, valid, expected = support(servo, near)
                colour = beam_colour_mask_low(frame)[ys, xs] & valid
                n, ov = int(expected.sum()), int((expected & colour).sum())
                print(f"t={t:.2f} near={near*1000:.1f}mm expected={n} colour={int(colour.sum())} "
                      f"cov={ov/max(1, n):.3f} iou={ov/max(1, int((expected | colour).sum())):.3f}")
    elif cmd == 'nearm':
        seen = collections.OrderedDict()
        for r in rows_of(run, rid):
            seen.setdefault(tuple(sorted((int(k), v) for k, v in r['commanded_servo'].items())), r['sim_time'])
        diff = 0
        for key, t in seen.items():
            counts = [int(support(dict(key), m)[3].sum()) for m in (OLD_NEAR_M, NEARCLIP_M, 0.)]
            diff += counts[0] != counts[1]
        print(f'{len(seen)} distinct poses; expected support differs between near_m 22.2 and 4.4 mm in {diff}')
    elif cmd == 'hover':
        for r in rows_of(run, rid):
            s = {int(k): v for k, v in r['commanded_servo'].items()}
            if [s[k] for k in (3, 4, 5, 6)] == [807, 1897, 2187, 1500] and s[1] == 2000:
                image = base64.b64encode(open(f"{run}/{r['path']}", 'rb').read()).decode()
                b, est = observe_beam(image, s), stationary_beam_estimate({'image': image}, s)
                print(f"t={r['sim_time']:.2f} visible={b.get('visible')} end={b.get('end_visible')} reason={b.get('reason')} "
                      f"pts={b.get('points')} stationary_est={'OK' if est else None}")
    elif cmd == 'overlay':          # python ... overlay <run_a> <run_b> <t> <out.png>   (rid r1 for both)
        t, out_path, imgs = float(rest[0]), rest[1], []
        for r_dir in (run, rid):
            frame, servo, tt = frame_at(r_dir, 'r1', t)
            xs, ys, valid, expected = support(servo, OLD_NEAR_M)
            colour = beam_colour_mask_low(frame)[ys, xs] & valid
            img = frame.copy()
            for x, y, e, c in zip(xs, ys, expected, colour):
                if e or c:
                    img[y, x] = (0, 255, 0) if e and c else (0, 0, 255) if e else (255, 0, 0)
            imgs.append(np.hstack([frame, img]))
        cv2.imwrite(out_path, np.vstack(imgs))


if __name__ == '__main__':
    main()
