# 출처: blind final approach 설계 작업자(2026-10-04)의 오프라인 재생 스크립트. 입력은 자기 RGB·자기 명령 기록뿐이다.
"""Offline replay of recorded v98 own frames (no physics, no controller).

Controller-side quantities use only own RGB + issued servo + measured calibration.
Ground truth (eval_only/trajectory.jsonl) is used ONLY in the section marked
OFFLINE EVALUATION to judge accuracy; it never feeds any estimate here.
"""
import json, math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3]))  # repo root
from harness import owncam_pair_beam as v1
from harness import owncam_pair_beam_v2 as v2
from harness.zone_final_pair_vision import PairVision, GRASP_RADIUS_M, grasp_postures
from harness.vision_pose_source_final import camera_key

RUN = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-3358372e')
RID = sys.argv[2] if len(sys.argv) > 2 else 'r1'
T0, T1 = float(sys.argv[3]) if len(sys.argv) > 3 else 51.5, float(sys.argv[4]) if len(sys.argv) > 4 else 54.2
cal = json.load(open(RUN/'dev_pilot_calibration.json'))
vision = PairVision(cal)
measured = set(cal['camera_models']['unloaded'])
case = RUN/'before_door'
frames = [json.loads(l) for l in open(case/f'robots/{RID}/frames.jsonl')]
traj = {round(r['t'], 3): r for r in map(json.loads, open(case/'eval_only/trajectory.jsonl'))}
hover, path = grasp_postures()
print('fixed postures: hover', hover, 'grasp', path[-1])
rows = []
for f in frames:
    if not T0 <= f['sim_time'] <= T1:
        continue
    servo = {int(k): v for k, v in f['actuator_state']['servo_pulses'].items()}
    image = open(case/f['path'], 'rb').read()
    frame = v1.decode(image)
    colour_px = int(v2.beam_colour_mask(frame).sum())
    lime_px = int(v1.lime_mask(frame).sum())
    key = camera_key(servo)
    row = {'frame_id': f['frame_id'], 't': round(f['sim_time'], 2), 'servo': key,
           'beam_colour_px': colour_px, 'lime_px': lime_px, 'measured_posture': key in measured}
    if key in measured:
        pts = vision.points(image, servo)
        row['grasp_range_points'] = int(len(pts))
        obs = {'image': image, 'sim_time': f['sim_time'], 'frame_id': f['frame_id'], 'sha256': f['sha256']}
        tr = vision.beam_track()
        b = tr._standoff(obs, servo)
        row['standoff'] = None if b is None else {'grip_base_m': [round(x, 4) for x in b['grip_base_m']],
                                                  'axis_heading_rad': round(b['axis_heading_rad'], 5),
                                                  'std_xy_m': round(b['std_xy_m'], 4), 'std_yaw_rad': round(b['std_yaw_rad'], 4),
                                                  'edge_strips': b['edge_strips'], 'edge_span_m': round(b['edge_span_m'], 3)}
        ob = vision.observe_beam(image, servo)
        row['observe'] = {k: ob.get(k) for k in ('visible', 'reason', 'end_visible', 'grip_source', 'points')}
        if ob.get('grip_base_m'):
            row['observe']['grip_base_m'] = [round(x, 4) for x in ob['grip_base_m']]
    # OFFLINE EVALUATION ONLY (ground truth): true end_neg grip in this robot's base frame.
    g = traj.get(round(f['sim_time'], 3))
    if g is not None:
        q = g['qpos']; off = {'r1': 0, 'r2': 17}[RID]
        x, y = q[off], q[off+1]; w, qx, qy, qz = q[off+3:off+7]
        yaw = math.atan2(2*(w*qz+qx*qy), 1-2*(qy*qy+qz*qz))
        R = np.array(g['beam_rotation']).reshape(3, 3)
        end = {'r1': -.27, 'r2': .27}[RID]
        grip_w = np.array(g['beam_xyz_m']) + R @ np.array([end, 0., 0.])
        d = grip_w[:2]-[x, y]; c, s = math.cos(yaw), math.sin(yaw)
        row['EVAL_true_grip_base_m'] = [round(c*d[0]+s*d[1], 4), round(-s*d[0]+c*d[1], 4)]
        row['EVAL_true_beam_yaw_rel_rad'] = round(math.atan2(R[1, 0], R[0, 0])-yaw, 4)
    rows.append(row)
for r in rows:
    print(json.dumps(r))
json.dump(rows, open(Path(sys.argv[5]) if len(sys.argv) > 5 else Path('/dev/null'), 'w'), indent=1)
