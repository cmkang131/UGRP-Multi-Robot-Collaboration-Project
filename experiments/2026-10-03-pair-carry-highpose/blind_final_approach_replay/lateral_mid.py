# 출처: blind final approach 설계 작업자(2026-10-04)의 오프라인 재생 스크립트. 입력은 자기 RGB·자기 명령 기록뿐이다.
import json, sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3]))  # repo root
from harness.zone_final_pair_vision import PairVision
RUN = Path('/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-3358372e')
cal = json.load(open(RUN/'dev_pilot_calibration.json')); v = PairVision(cal)
case = RUN/'before_door'
frames = {json.loads(l)['frame_id']: json.loads(l) for l in open(case/'robots/r1/frames.jsonl')}
anchor = {'grip_base_m': [0.20456722629722016, 0.00017956018667455336], 'axis_heading_rad': 0.00010383969111516539}
u = np.array([np.cos(anchor['axis_heading_rad']), np.sin(anchor['axis_heading_rad'])])
for fid in (1006, 1011, 1032, 1033, 1034):
    f = frames[fid]; s = {int(k): x for k, x in f['actuator_state']['servo_pulses'].items()}
    pts = v.points(open(case/f['path'], 'rb').read(), s)
    rel = pts - np.array(anchor['grip_base_m']); a, n = rel @ u, rel @ np.array([-u[1], u[0]])
    inside = (a > -.1) & (a <= .63) & (np.abs(n) <= .08)
    lo, hi = np.percentile(n[inside], [2, 98])
    print(fid, f['sim_time'], 'pts', len(pts), 'along range', np.round(np.percentile(a[inside], [1, 99]), 4), 'lateral mid mm', round(1000*(lo+hi)/2, 2), 'span mm', round(1000*(hi-lo), 1))
