"""Offline replay of r1's beam track (own RGB frames + own issued commands only) for raise_high_align 3358372e."""
import base64, json, sys
sys.path.insert(0, '.')
from pathlib import Path
from harness import zone_pair_highpose_contract as c
from harness.zone_final_pair_vision import PairVision
from harness import zone_pair_grasp_entry_v6c as entry
from harness import zone_pair_beam_track as bt

RAW = Path('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-3358372e/before_door')
CAL = '/Users/changmin/projects/ugrp/outputs/v92-dev-pilot-c0zero-20261003T104043Z/result/calibration_dev_pilot.json'
SHA = '398372ae6b9b0fef7344d7f29146ce75b309d334b3ce31af527bc071c0e582f5'
cal = c.student_calibration(c.admitted_calibration(CAL, SHA, 'zone_wide_door_geometry_v3')) if hasattr(c, 'student_calibration') else None
vision = PairVision(cal)
frames = {json.loads(l)['frame_id']: json.loads(l) for l in (RAW/'robots/r1/frames.jsonl').open()}
cmds = [json.loads(l) for l in (RAW/'robots/r1/commands.jsonl').open()]
def obs(fid):
    f = frames[fid]
    img = (RAW/f['path']).read_bytes()
    return {**{k: f[k] for k in ('robot_id', 'frame_id', 'sim_time', 'sha256', 'camera', 'actuator_state')},
            'image': base64.b64encode(img).decode()}, {int(k): v for k, v in f['commanded_servo'].items()}
track = vision.beam_track()
o, servo = obs(1011)
print('standoff observed', track.observe_standoff(o, servo, 0), {k: track.beam[k] for k in ('std_xy_m', 'std_yaw_rad', 'grip_base_m')})
issued = dict(servo)
for row in cmds:
    if o['sim_time'] < row['t'] <= 54.1 + 1e-6:
        track.command(row, issued)
        if row['kind'] == 'arm': issued[int(row['servo_id'])] = row['pulse']
        if row['kind'] == 'look': issued[6] = row['pan_pulse']
o2, servo2 = obs(1057)
print('close frame', o2['frame_id'], o2['sim_time'], 'servo', servo2, 'issued', issued)
NOW = o2["sim_time"]; track.advance(NOW)
b = track.beam
print('after commands: std_xy', round(b['std_xy_m'], 4), 'std_yaw', round(b['std_yaw_rad'], 4), 'age', round(NOW - b['anchor_time_s'], 2), 'limits', 0.05, 0.0524)
pts, why = track._partial_points(o2, servo2)
print('partial points', None if pts is None else len(pts), why, 'MIN_POINTS', bt.v1.MIN_POINTS)
est = track.estimate(NOW, o2, servo2, 0)
print('estimate', None if est is None else {k: est[k] for k in ('partial_support_fraction', 'partial_cross_section_m') if k in est})
for fid in (1011, 1030, 1045, 1050, 1057):
    oo, ss = obs(fid)
    try: p = vision.points(oo["image"], ss)
    except Exception as exc: p = None; print("  points error", type(exc).__name__)
    print('frame', fid, round(oo['sim_time'], 2), 'servo3-5', ss.get(3), ss.get(4), ss.get(5), 'points', None if p is None else len(p))
