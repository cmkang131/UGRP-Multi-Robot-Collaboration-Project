"""Frozen observed-input replay, not a replay of the new physical trajectory."""
import copy
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

BASE=Path(__file__).parent
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE.parents[1]))
from analyze_release8 import RAW, read, rows, integrated
from harness.zone_final_environment import resolve
from sim.global_landmark_localization import GlobalLandmarkMatcher, wrap


def main():
    records=[]; unchanged=[]
    for no in range(8):
        raw=RAW/f'release7-diagnostic-{no:02d}-a2314b16/raw'
        result=read(raw/'result.json.zst');plan=read(raw/'plan.json')
        for rid in ('r1','r2'):
            t=rows(raw/f'teacher-{rid}.jsonl.zst');times=np.array([r['t'] for r in t])
            old=integrated(t);new=integrated(t,yaw_sign=-1)
            loc=result['lookaround_result'][rid]
            if no not in (3,7):
                assert np.array_equal(old,new)
                unchanged.append(dict(seed=plan['seed'],robot=rid,ticks=len(t)))
                continue
            # End of first full unloaded panorama. Later physical decisions
            # would change; never label them a corrected-source trajectory.
            sweep=next(s for s in loc['evaluation']['sweeps'] if s['t0']<73 and s['t0']+s['sim_s']>72)
            end=sweep['t0']+sweep['sim_s']; views=copy.deepcopy([v for v in loc['localizer']['views'] if v['t']<=end+1e-6])
            anchor=np.array(result['handoff_estimates'][rid]);assert abs(anchor[2])<1e-10
            for v in views:
                i=int(np.argmin(abs(times-v['t'])))
                assert np.allclose(v['command_pose'],old[i]+anchor,atol=1e-10)
                v['command_pose']=(new[i]+anchor).tolist()
            current=new[int(np.argmin(abs(times-end)))]+anchor
            matcher=GlobalLandmarkMatcher(resolve(plan['map_id'])[0])
            decision=matcher.fit(views,current)
            # Only AFTER fitting, join the separate evaluation truth.
            truth=np.array(sweep['after']['truth']);proposed=np.array(decision['proposed'])
            records.append(dict(seed=plan['seed'],robot=rid,t=end,input_count=len(views),
                decision=decision,error_xy_m=float(np.linalg.norm(proposed[:2]-truth[:2])),
                error_yaw_deg=math.degrees(wrap(proposed[2]-truth[2])),
                original_accepted=sweep['decision']['accepted'],
                original_error_xy_m=sweep['after']['error_xy_m'],original_error_yaw_deg=sweep['after']['error_yaw_deg']))
    out=dict(scope='Same stored pixels/detections and issued wheels, sign-corrected registration ONLY. New inverse turns change images; no new success claim.',
             unchanged_nonrotating_robot_runs=unchanged,first_rotating_sweep=records,
             matcher_source_sha256=hashlib.sha256((BASE.parents[1]/'sim/global_landmark_localization.py').read_bytes()).hexdigest())
    (BASE/'release8-replay.json').write_text(json.dumps(out,indent=2)+'\n')
    for r in records:print(r['seed'],r['robot'],r['decision']['accepted'],r['error_xy_m'],r['error_yaw_deg'])


if __name__=='__main__':main()
