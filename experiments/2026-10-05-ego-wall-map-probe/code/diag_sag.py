"""Is the pose-dependent camera elevation error gravity droop of the position servos? (offline, no physics)

Refs #216. **Physical simulation runs: 0** (``mj_forward`` only, recorded ``qpos``, no ``mj_step``).

The detector's camera pitch is forward kinematics of the COMMANDED pulses plus a fixed bias
(``harness.visual_arm.camera_extrinsics``). MuJoCo renders from the camera on the ACTUAL joints, and
``sim/masterpi_dynamics_v2.py`` drives them with position actuators (kp shoulder 7, elbow 6, wrist 3.5 N m/rad)
under gravity. A position servo of stiffness kp holding a static gravity torque tau settles at
``q = target + tau/kp``. For each sampled unloaded frame this prints

  measured   sum of the three joint deflections (q - target) = the camera elevation error the arm adds,
             and the camera elevation error itself, true render camera minus FK without bias
  predicted  sum of ``-qfrc_bias[dof] / kp`` over the three joints at the TARGET pose (gravity of the arm's own
             links; no carried load)

Agreement means the error is a compliance of the commanded pose, not a calibration constant: a fixed
``SEED_BIAS`` can only be exact at one pose.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'experiments/2026-09-26-markerless-probe'))
sys.path.insert(0, str(HERE))

import markerless_probe as mp  # noqa: E402
import wall_probe as wp  # noqa: E402
import true_camera as tc  # noqa: E402
from harness.visual_arm import SERVO_DEVIATION, PULSE_PER_DEGREE  # noqa: E402

JOINTS = ('shoulder', 'elbow', 'wrist_pitch')
ACTUATOR = {'shoulder': 'servo_shoulder', 'elbow': 'servo_elbow', 'wrist_pitch': 'servo_wrist'}


def joint_targets(s):
    """Commanded pulses -> joint targets, as ``sim/masterpi_dynamics_v2.pulse_to_joint_targets`` (radians)."""
    nom = lambda k: s[k] - SERVO_DEVIATION.get(k, 0)
    return {'shoulder': math.radians(90 - (nom(5) - 1500)/PULSE_PER_DEGREE),
            'elbow': math.radians(-(nom(4) - 1500)/PULSE_PER_DEGREE),
            'wrist_pitch': math.radians((nom(3) - 1500)/PULSE_PER_DEGREE),
            'arm_yaw': math.radians((s[6] - 1500)/PULSE_PER_DEGREE)}


def run(args):
    ep = Path(args.episode)
    cam = tc.TrueCamera(ep, args.robot)
    model, data = cam.model, cam.data
    frames, _ = wp.resolve_frames(ep, args.robot)
    jid = lambda n: mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f'{args.robot}__{n}')
    adr = {n: int(model.jnt_qposadr[jid(n)]) for n in (*JOINTS, 'arm_yaw')}
    dof = {n: int(model.jnt_dofadr[jid(n)]) for n in JOINTS}
    kp = {n: float(model.actuator_gainprm[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR,
                                                              f'{args.robot}__{ACTUATOR[n]}')][0]) for n in JOINTS}
    rows = []
    for idx in range(0, len(frames), args.stride):
        s = {int(k): int(v) for k, v in frames[idx]['commanded_servo'].items()}
        if wp.is_loaded(s):
            continue
        tgt = joint_targets(s)
        origin, r_true, _ = cam.at(idx)                              # also leaves data at the recorded state
        meas = {n: math.degrees(float(cam.traj[idx]['qpos'][adr[n]]) - tgt[n]) for n in JOINTS}
        # gravity torque on each joint with the joints AT THE TARGETS, everything else as recorded
        data.qpos[:] = np.asarray(cam.traj[idx]['qpos'], float)
        for n in (*JOINTS, 'arm_yaw'):
            data.qpos[adr[n]] = tgt[n]
        data.qvel[:] = 0.
        mujoco.mj_forward(model, data)
        pred = {n: math.degrees(-float(data.qfrc_bias[dof[n]])/kp[n]) for n in JOINTS}
        _, r_fk = mp.camera_in_base(s)
        rows.append({'frame_index': idx + 1, 's3': s.get(3), 's4': s.get(4), 's5': s.get(5),
                     'measured_sum_deg': sum(meas.values()), 'predicted_sum_deg': sum(pred.values()),
                     'camera_elev_err_deg': tc.elevation_deg(r_true) - tc.elevation_deg(np.asarray(r_fk, float)),
                     **{f'measured_{n}': meas[n] for n in JOINTS}, **{f'predicted_{n}': pred[n] for n in JOINTS}})
    meas = np.array([r['measured_sum_deg'] for r in rows])
    pred = np.array([r['predicted_sum_deg'] for r in rows])
    cam_err = np.array([r['camera_elev_err_deg'] for r in rows])
    summary = {
        'episode': str(ep), 'frames_sampled_unloaded': len(rows), 'kp_N_m_per_rad': kp,
        'measured_minus_predicted_deg': {'median': float(np.median(meas - pred)), 'p10': float(np.percentile(meas - pred, 10)),
                                         'p90': float(np.percentile(meas - pred, 90)), 'max_abs': float(np.max(np.abs(meas - pred)))},
        'camera_elev_err_minus_measured_deg': {'median': float(np.median(cam_err - meas)), 'max_abs': float(np.max(np.abs(cam_err - meas)))},
        'camera_elev_err_deg': {'min': float(cam_err.min()), 'median': float(np.median(cam_err)), 'max': float(cam_err.max())},
        'seed_bias_unloaded_deg': math.degrees(wp.SEED_BIAS['unloaded']),
        'note': 'unloaded frames only; the carry pose (gripper closed on the beam) is not modelled here',
    }
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out/'summary.json').write_text(json.dumps(summary, indent=2))
    import csv
    with open(out/'frames.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--episode', required=True)
    ap.add_argument('--robot', default='r1')
    ap.add_argument('--output', required=True)
    ap.add_argument('--stride', type=int, default=20)
    run(ap.parse_args())
