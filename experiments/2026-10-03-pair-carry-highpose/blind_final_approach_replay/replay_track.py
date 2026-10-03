# 출처: blind final approach 설계 작업자(2026-10-04)의 오프라인 재생 스크립트. 입력은 자기 RGB·자기 명령 기록뿐이다.
"""Offline replay of the v98 resting beam track (own RGB + issued commands only)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3]))  # repo root
from harness.zone_final_pair_vision import PairVision
RUN = Path('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-3358372e')
RID, ANCHOR = 'r1', 1011
cal = json.load(open(RUN/'dev_pilot_calibration.json'))
track = PairVision(cal).beam_track()
case = RUN/'before_door'
frames = {json.loads(l)['frame_id']: json.loads(l) for l in open(case/f'robots/{RID}/frames.jsonl')}
cmds = [json.loads(l) for l in open(case/f'robots/{RID}/commands.jsonl')]
def obs_of(f):
    return {'image': open(case/f['path'], 'rb').read(), 'sim_time': f['sim_time'],
            'frame_id': f['frame_id'], 'sha256': f['sha256']}
servo = None
fa = frames[ANCHOR]
servo = {int(k): v for k, v in fa['actuator_state']['servo_pulses'].items()}
print('anchor ok', track.observe_standoff(obs_of(fa), servo, 0), {k: track.beam[k] for k in ('grip_base_m', 'axis_heading_rad', 'std_xy_m', 'std_yaw_rad')})
ci = [c for c in cmds if c['t'] > fa['sim_time']+1e-6]
for fid in range(ANCHOR+1, 1058):
    f = frames[fid]
    while ci and ci[0]['t'] <= f['sim_time']+1e-9:
        c = ci.pop(0)
        if c['kind'] in ('arm', 'look', 'drive', 'mecanum', 'hold'):
            track.command(c, servo)
            if c['kind'] == 'arm':
                servo[int(c['servo_id'])] = c['pulse']
            elif c['kind'] == 'look':
                servo[6] = c['pan_pulse']
    s = {int(k): v for k, v in f['actuator_state']['servo_pulses'].items()}
    try:
        est = track.estimate(f['sim_time'], obs_of(f), s, 0)
        out = None if est is None else {k: (round(v, 4) if isinstance(v, float) else v) for k, v in est.items()
                                        if k in ('std_xy_m', 'std_yaw_rad', 'partial_support_fraction', 'partial_cross_section_m')}
    except Exception as exc:
        out = f'unmeasured_posture({type(exc).__name__})'
    b = track.beam
    print(fid, round(f['sim_time'], 2), ','.join(str(s[k]) for k in (3, 4, 5)), 'track_std', None if b is None else (round(b['std_xy_m'], 4), round(b['std_yaw_rad'], 4)), 'estimate', out)
