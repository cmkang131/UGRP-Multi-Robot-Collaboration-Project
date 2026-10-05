"""Static geometry check of grip.support() vs the actual camera/beam (eval side).

Reuses the headless driver's nominal physics (reviewer's commands, 52 SIM s,
no render, weld OFF). At chosen instants, expresses in the robot's own frame:
the controller's command-model camera (visual_arm_v3.camera_extrinsics) and
assumed beam pose (grip.support) versus the actual MuJoCo robot_cam pose and
beam bar pose. Writes stand-in / expected-mask PNGs and one JSON. Diagnostic
of the projection model only; no controller decision is made here.
"""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
import headless_grip_monitor as hg  # noqa: E402
from harness import zone_final_pair_contract as c  # noqa: E402
from harness import zone_pair_highpose_grip as grip  # noqa: E402
from harness import visual_arm_v3 as arm  # noqa: E402
from harness.owncam_view import _pixel_rays  # noqa: E402

TIMES = (8.0, 10.0, 16.0, 20.0, 30.0, 40.0)


def robot_frame(m, d, rid):
    bid = m.body(rid+'__robot').id
    R = d.xmat[bid].reshape(3, 3)
    p = d.xpos[bid].copy()
    # floor frame: robot body origin projected to the floor (z = 0)
    return R, np.array([p[0], p[1], 0.])


def main(out):
    import cv2
    p = hg.probe()
    rays4 = _pixel_rays(4)
    events = sorted(copy.deepcopy(p.commands()), key=lambda r: r['t'])
    bundle = c.bundle('zone_wide_two_doors_final_v3', 'calibration-loaded')
    out.mkdir(parents=True, exist_ok=False)
    backend = p.Headless(bundle, out/'raw', seed=911)
    rows = []
    try:
        backend.reset(5.)
        start = backend.now
        backend.set_deadline(start+52.)
        m, d = backend.world.model, backend.world.data
        j = 0
        for i in range(int(max(TIMES)/.05)+1):
            t = round(i*.05, 8)
            if any(abs(t-x) < 1e-6 for x in TIMES):
                for rid in hg.CARRIERS:
                    servo = hg.issued_servo(events, rid, t, False)
                    R, o = robot_frame(m, d, rid)
                    cam = d.camera(rid+'__robot_cam')
                    act_origin = R.T @ (cam.xpos-o)
                    act_axes = (R.T @ (cam.xmat.reshape(3, 3) @ np.diag([1., -1., -1.]))).T   # rows: x,y,z optical
                    mod_origin, mod_axes = arm.camera_extrinsics(servo)
                    gid = m.geom('cargo_beam__bar').id
                    bar_c = R.T @ (d.geom_xpos[gid]-o)
                    bar_x = R.T @ d.geom_xmat[gid].reshape(3, 3)[:, 0]
                    site = R.T @ (d.site(rid+'__grip_site').xpos-o)
                    tool = arm.tool_pose(servo)
                    img = hg.stand_in(m, d, rid, rays4)
                    xs, ys, valid, expected = grip.support(servo)
                    rel = grip.relation(img, servo)
                    exp_img = np.full((120, 160), 0, np.uint8)
                    exp_img.reshape(-1)[expected] = 255
                    cv2.imwrite(str(out/f'{rid}_{t:05.1f}_standin.png'), img)
                    cv2.imwrite(str(out/f'{rid}_{t:05.1f}_expected.png'), cv2.resize(exp_img, (640, 480), interpolation=cv2.INTER_NEAREST))
                    rows.append({'t': t, 'rid': rid, 'servo': {k: servo.get(k) for k in (1, 3, 4, 5, 6)},
                        'camera_origin_actual': act_origin.tolist(), 'camera_origin_model': list(mod_origin),
                        'camera_axes_actual': act_axes.tolist(), 'camera_axes_model': [list(a) for a in mod_axes],
                        'axis_angle_deg': [math.degrees(math.acos(max(-1, min(1, float(np.dot(a, b)/np.linalg.norm(b))))))
                                           for a, b in zip(act_axes, np.asarray(mod_axes))],
                        'grip_site_actual': site.tolist(), 'tool_model': [tool.x_m, tool.y_m, tool.z_m],
                        'tool_yaw_left_deg': tool.yaw_left_deg,
                        'bar_center_actual': bar_c.tolist(), 'bar_axis_actual': bar_x.tolist(),
                        'relation': {k: v for k, v in rel.items() if k != 'reason'}})
            if t >= max(TIMES):
                break
            while j < len(events) and events[j]['t'] <= t+1e-8:
                backend.issue(events[j]['robot_id'], events[j]['action'])
                j += 1
            backend.advance_to(start+(i+1)*.05)
    finally:
        backend.close()
    (out/'projection_check.json').write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(json.dumps({k: (np.round(v, 4).tolist() if isinstance(v, list) else v) for k, v in r.items()}))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
