"""Static-frame renders for the carry-relocalization design memo: NO controller, NO physics experiment.

What it does (mj_setState / mj_forward only; the standard scene builder settles ~1.3 SIM s once at world construction, no controller runs):
  * builds the final-environment-like scene (zone_wide_door_tags_v3: walls_v3 0.40 m; every AprilTag geom hidden -> tag free)
  * restores a recorded carry state (a stage-probe `staged_before_submit.npz`: teacher-lifted beam held by r1 and r2, leg k)
  * puts the idle third robot r3 at chosen map poses, sets its arm to an unloaded look posture without stepping
    (set_servo_pulses(forward_only=True)), and renders r3's wrist camera (the observer view) and the two carriers' wrist cameras.
Everything is an audit picture. No image here reaches a controller.

usage: python render_views.py <cases_root> <out_dir> [--legs 1 ...]
"""
import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

import cv2
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from harness.zone_own_team_host import OwnCamTeamHost  # noqa: E402
from scripts.run_pair_stage_probes import CALIBRATION, order_for  # noqa: E402
from scripts.zone_pair_dev_runtime import make_scene  # noqa: E402

MAP_FINAL_LIKE = 'zone_wide_door_tags_v3'          # walls_v3 (0.40 m), same footprint as the door map
CASE_DIR = {0: 'carry_b-v6e_teacher_nominal_s911_pE2E_Vcal', **{k: f'carry_b-v6e_teacher_nominal_s911_pE2E_L{k}_Vcal' for k in range(1, 7)}}
LEG_HEADING_DEG = {0: 0, 1: 0, 2: 0, 3: -90, 4: -90, 5: -90, 6: 0, 7: 0}    # travel direction of each route leg (harness route: x, x, x, -y, -y, -y, x, x)
LOOK = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}     # harness.owncam_drive.SEARCH_POSE, pan centre (the unloaded look)


def build(cases_root, tmp):
    case = json.load(open(Path(cases_root) / CASE_DIR[1] / 'case.json'))
    spec = {'map': MAP_FINAL_LIKE, 'seed': 911, 'goal': {'B': {'cyan': 1}}, 'pair_policy': 'v5h',
            'team_cargo': [{'item_id': 'cargoX', 'kind': 'long_beam', 'pose': list(case['beam_xyyaw'])}],
            'pair_order_sheets': {'cargoX': case['coarse_order_sheet']}, 'order_sheet': order_for('B'),
            'contact_profile': 'cargo_noslip_v1', 'job_sim_limit_s': 900.}
    student = {'mode': 'm1', 'calibration': CALIBRATION, 'skill_module': 'harness.wrist_zone_skill_v9', 'skill_class': 'WristZoneDeliveryV9'}
    scene = make_scene(spec)
    host = OwnCamTeamHost.__new__(OwnCamTeamHost)
    OwnCamTeamHost.__init__(host, spec, student, root=ROOT, study_layer=lambda *a: None, frames_dir=Path(tmp) / 'frames', scene=scene)
    m = host.world.model
    hidden = 0
    for i in range(m.ngeom):
        name = mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or ''
        if name.startswith('tag_'):
            m.geom_rgba[i, 3] = 0.0
            hidden += 1
    return host, hidden


def restore(host, cases_root, leg):
    npz = np.load(Path(cases_root) / CASE_DIR[leg] / 'checkpoints' / 'staged_before_submit.npz')
    state = npz['mj_state_integration']
    m, d = host.world.model, host.world.data
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    if state.size != mujoco.mj_stateSize(m, spec):
        raise RuntimeError('state size differs between the recorded scene and this scene')
    mujoco.mj_setState(m, d, state, spec)
    mujoco.mj_forward(m, d)


def place(host, rid, x, y, yaw, servo=None):
    r = host.world.robot(rid)
    z = float(r.base_xyz()[2])
    r.set_base_pose_for_test((x, y, z), yaw)
    if servo:
        r.set_servo_pulses(servo, forward_only=True)
        mujoco.mj_forward(host.world.model, host.world.data)


def truth(host, rid):
    r = host.world.robot(rid)
    xyz, rpy = r.base_xyz(), r.base_rpy()
    return [round(float(xyz[0]), 3), round(float(xyz[1]), 3), round(float(rpy[2]), 4)]


def shot(host, rid, path):
    img = host.world.render_rgb(robot_id=rid, camera='robot_cam')
    bgr = cv2.cvtColor(np.ascontiguousarray(img), cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(path), bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return bgr, hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cases_root')
    ap.add_argument('out_dir')
    ap.add_argument('--legs', type=int, nargs='*', default=[1])
    ap.add_argument('--observers', default=HERE.joinpath('observer_poses.json').as_posix())
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    poses = json.load(open(a.observers))
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        host, hidden = build(a.cases_root, tmp)
        print('tag geoms hidden:', hidden, 'world t =', float(host.world.data.time))
        t_before = float(host.world.data.time)
        for leg in a.legs:
            restore(host, a.cases_root, leg)
            t_state = float(host.world.data.time)
            base = {rid: truth(host, rid) for rid in ('r1', 'r2', 'r3')}
            body = host.world.data.body(host.scene.cargo[0].body)
            beam = [float(v) for v in body.xpos]
            mat = body.xmat.reshape(3, 3)
            beam_yaw = math.atan2(float(mat[1, 0]), float(mat[0, 0]))
            for rid in ('r1', 'r2'):
                _, sha = shot(host, rid, out / f'leg{leg}_{rid}_carry.jpg')
                rows.append({'leg': leg, 'view': f'{rid}_carry', 'robot_pose': base[rid], 'sha256': sha})
            heading = math.radians(LEG_HEADING_DEG[leg])
            for name, p in poses.items():
                # observer placed in the pair's travel frame (along = + travel direction, across = + left of travel), always facing the beam centre
                x = beam[0] + p['along'] * math.cos(heading) - p['across'] * math.sin(heading)
                y = beam[1] + p['along'] * math.sin(heading) + p['across'] * math.cos(heading)
                yaw = math.atan2(beam[1] - y, beam[0] - x)
                place(host, 'r3', x, y, yaw, {int(k): v for k, v in p['servo'].items()})
                _, sha = shot(host, 'r3', out / f'leg{leg}_r3_{name}.jpg')
                rows.append({'leg': leg, 'view': f'r3_{name}', 'robot_pose': truth(host, 'r3'), 'beam_xyz': [round(v, 3) for v in beam], 'beam_yaw': round(beam_yaw, 4),
                             'r3_servo': {int(k): int(v) for k, v in host.world.robot('r3').servo_command_pulses.items()},
                             'carriers': {r: base[r] for r in ('r1', 'r2')}, 'sha256': sha, 'spec': p})
        assert float(host.world.data.time) == t_state, 'physics advanced while rendering'
        host.world.close()
    json.dump({'map': MAP_FINAL_LIKE, 'tag_geoms_hidden': hidden, 'world_time_after_build_s': t_before,
               'note': 'restored recorded states; no stepping after the scene was built', 'rows': rows}, open(out / 'render_manifest.json', 'w'), indent=1)
    print(len(rows), 'frames ->', out)


if __name__ == '__main__':
    main()
