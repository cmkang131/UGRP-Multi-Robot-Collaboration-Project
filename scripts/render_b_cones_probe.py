"""Render-only probe for b_marker_style=corner_cones_v1 (run on a sim VM; no controller, no run bundle).

Places robot r1 at fixed map poses (setup only), renders its own RGB (robot_cam, SEARCH arm), runs the cones_v1 detector
on the pixels + commanded SEARCH servo only, and writes frames + a detection file. Ground truth (the placement poses and the
authored B) is used only in the separate evaluation file.
"""
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0, '.')
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
from sim.zone_arena import digest
from harness.active_camera import SEARCH
from harness import e2e_b_cones as C
from harness.e2e_rgb_gate import default_cone_layout, boundary

static = json.loads(Path('maps/zones_e2e/zone_wide_door_e2e_b80_cones_v1.json').read_text())
from scripts._calib_world import build_world
world, definition = build_world(static_map=static)  # E2E-faithful: v3 camera, real_v1 servo stiffness (arm sag)
import mujoco
poses = []
for x in (2.5, 2.9, 3.3, 3.7):
    for y in (-2.1, -1.8, -2.4):
        for yd in (0, 10, -10):
            poses.append((x, y, math.radians(yd)))
poses += [(4.6, -0.2, -math.pi/2), (4.0, -0.2, -math.pi/2-.3), (3.2, -0.9, -math.pi/4), (3.4, -3.0, math.pi/3)]
layout = default_cone_layout()
det, ev = [], []
for i, (x, y, yaw) in enumerate(poses):
    world.robot('r1').set_base_pose_for_test((x, y, .032355118817659255), yaw)
    mujoco.mj_forward(world.model, world.data)
    world._team_joint_move_servos({'r1': dict(SEARCH)}, 1.5, settle_s=2.0)
    world.robot('r1')._sync_real_camera_mount(); mujoco.mj_forward(world.model, world.data)
    if i == 0:  # camera mount check against the commanded-servo FK the detector uses
        cid = mujoco.mj_name2id(world.model, mujoco.mjtObj.mjOBJ_CAMERA, 'r1__robot_cam')
        fwd = -world.data.cam_xmat[cid].reshape(3, 3)[:, 2]
        from harness.active_camera import pitch, transform
        print('cam world z', float(world.data.cam_xpos[cid][2]), 'sim pitch deg', math.degrees(math.asin(fwd[2])),
              'FK pitch deg', pitch(SEARCH), 'FK origin', transform(SEARCH)[0].tolist(), 'sim cam xy rel base', (world.data.cam_xpos[cid][:2]-[x, y]).tolist(), 'yaw', yaw, 'fwd', fwd.tolist(), flush=True)
    jpg = world.render_jpeg(robot_id='r1', camera='robot_cam', quality=95)
    (OUT/f'f{i:03d}.jpg').write_bytes(jpg)
    rgb = np.asarray(Image.open(OUT/f'f{i:03d}.jpg').convert('RGB'))
    d = {}
    fit = C.detect_cones(rgb, SEARCH, (0., 0., 0.), layout, diagnostics=d)
    det.append(dict(frame=i, accepted=fit is not None, n_blobs=d.get('cone_blobs'), reason=d.get('cone_fit_reason'),
                    rejects=[r['reason'] for r in d.get('cone_rejects', [])],
                    cone_ranges=[round(c['range_m'], 2) for c in d.get('cones', [])],
                    center_robot_m=fit and fit['center_robot_m'], yaw_robot_rad=fit and fit['yaw_robot_rad'], rms_m=fit and fit['rms_m']))
    if fit:  # evaluation only: true B centre in the robot frame from the authored map
        c, s = math.cos(yaw), math.sin(yaw); b = static['regions']['zone_B']['center_m']
        true = [c*(b[0]-x)+s*(b[1]-y), -s*(b[0]-x)+c*(b[1]-y)]
        det[-1]['pos_err_m'] = float(np.hypot(fit['center_robot_m'][0]-true[0], fit['center_robot_m'][1]-true[1]))
    ev.append(dict(frame=i, robot=[x, y, yaw], range_to_B_m=math.hypot(4.6-x, -2.1-y)))
json.dump(dict(static_map_sha256=digest(static), detections=det), open(OUT/'detections.json', 'w'), indent=1)
json.dump(dict(placements=ev), open(OUT/'evaluation_ground_truth.json', 'w'), indent=1)
print(json.dumps(dict(frames=len(poses), accepted=sum(d['accepted'] for d in det),
                      errs=[round(d['pos_err_m'], 3) for d in det if 'pos_err_m' in d])))
world.close()
