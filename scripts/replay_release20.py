"""Saved 110613 RGB features/commands only; conditional replay, no physics."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.replay_release19 import load, verify_raw
from sim import release17, release20
from sim.lookaround_localization import Camera


def replay(raw):
    proofs = verify_raw(raw)
    result = json.loads(load(raw, 'result.json'))
    checks = []
    for index, check in enumerate(result['line_rechecks']):
        rows = [json.loads(v) for v in load(raw, 'teacher-'+check['robot']+'.jsonl').splitlines()]
        first = next(e for e in check['events'] if e['event']=='image')
        row = max((r for r in rows if r['t'] <= first['t']+1e-7), key=lambda r:r['t'])
        teacher = SimpleNamespace(rid=check['robot'], pwm={int(k):v for k,v in row['pwm'].items()},
                                  holding=False, reach_mid=lambda:.152, odometry_profile='yaw_cal_v1')
        a = release20.LineAlign(teacher,first['t'],camera=Camera(),undistort=lambda f:f,
                wheel_command=lambda *v:None,clearance=lambda *v:True,fov_step=release17.FOV_STEP)
        old_pulses = [e for e in check['events'] if e['event']=='line_ibvs']
        new_pulses = 0
        samples = []
        for e in check['events']:
            if e['event'] != 'image': continue
            f = {k:v for k,v in e.items() if k not in ('event','t')}
            step = a.choose_step(f, .1, e['t'])
            if step['kind'] != 'line_ibvs': continue
            samples.append(dict(t=e['t'], center_error=f['center_error'], error=step['error'],
                                decision=a.records[-1]))
            if step['aligned']: break
            for s,err in zip(a.settlers,step['error']): s.issued(err)
            new_pulses += 1
        flips = sum(x['yaw']*y['yaw'] < 0 for x,y in zip(old_pulses,old_pulses[1:]))
        checks.append(dict(index=index,robot=check['robot'],old_state=check['state'],old_failure=check['failure'],
                           old_pulses=len(old_pulses),old_yaw_reversals=flips,
                           pulses_before_settle=new_pulses,settle_declared=bool(samples and samples[-1]['decision']['aligned']),
                           samples=samples))
    return dict(schema='ugrp.release20.replay.v1',source_sha=result['source_sha'],source=proofs,
                scope='stored own-RGB feature sequence; static camera and issued command model; conditional decision replay only, no prediction of new physics or 0.3s stability',
                checks=checks)


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); result=replay(args.raw)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in c.items() if k!='samples'} for c in result['checks']]))

if __name__=='__main__':main()
