"""Read-only VM export of selected own RGB/command/map samples; no eval state."""
import argparse
import base64
import hashlib
import json
import subprocess
from pathlib import Path

def read(path):
    return path.read_text() if path.exists() else subprocess.check_output(['zstd','-dc',str(path)+'.zst'],text=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--times',default='30,76,120,220,360,490,515,545');p.add_argument('--robots',default='r1,r2')
    p.add_argument('--body-records',action='store_true')
    a=p.parse_args();out=[]
    phases=json.loads(read(a.raw/'transport-trace.json'))
    decisions=[json.loads(l) for l in read(a.raw/'body-decisions.jsonl').splitlines()] if a.body_records else []
    transitions=[x for x in phases if x['event']=='phase']
    for rid in a.robots.split(','):
        directory=a.raw/'robots'/rid
        maps=[json.loads(x) for x in read(directory/'ownmap.jsonl').splitlines()]
        frames={x['frame_id']:x for x in map(json.loads,read(directory/'frames.jsonl').splitlines())}
        commands=[json.loads(x) for x in read(directory/'commands.jsonl').splitlines()]
        origin=frames[maps[0]['frame_id']]['sim_time']-maps[0]['t']
        for target in map(float,a.times.split(',')):
            decision=min((r for r in decisions if r['robot_id']==rid),key=lambda r:abs(r['t']-target)) if decisions else None
            row=(next(r for r in maps if r['sha256']==decision['image_sha256']) if decision else min(maps,key=lambda r:abs(r['t']-target)))
            t=row['t'];frame=frames[row['frame_id']]
            jpeg=(a.raw/frame['path']).read_bytes();assert hashlib.sha256(jpeg).hexdigest()==row['sha256']
            prev=[dict(x,t=round(x['t']-origin,8)) for x in commands if x['t']<=t+origin]
            # Whitelist issued servo metadata, NEVER actuator_state from frames.
            servo=frame['commanded_servo']
            phase=next((x['state'] for x in reversed(transitions) if x['t']<=t),'mapping')
            start=next((x['t'] for x in reversed(transitions) if x['t']<=t),0.)
            history=[r for r in maps if t-21<=r['t']<=t]
            out.append(dict(rid=rid,t=t,phase=phase,phase_start=start,servo=servo,pose=row['pose_own_m'],
                beam_observation=row.get('own_beam_observation'),carrier_approach=row.get('carrier_approach'),
                sigma_xy_m=row.get('sigma_xy_m'),prev=prev[-30:],next=[row['command']],
                navigation_status=row.get('navigation_status'),explore_deadlock=row.get('explore_deadlock'),goal_stage=row.get('stage'),
                poses=[[r['t'],r['pose_own_m']] for r in history],
                context_history=[{k:r.get(k) for k in ('t','frame_id','own_beam_observation','carrier_approach')} for r in history],
                jpeg_b64=base64.b64encode(jpeg).decode(),frame_sha256=row['sha256'],
                source_rgb=str(a.raw/frame['path']),source_sha=json.loads(read(a.raw/'bundle.json'))['source_sha']))
            if decision:
                out[-1].update(decision_t=decision['t'],prior_decision=decision,
                    prior_decisions=[r for r in decisions if r['robot_id']==rid and r['t']<decision['t']][-10:])
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out)+'\n');print(json.dumps({'scenes':len(out),'bytes':a.out.stat().st_size,'sha256':hashlib.sha256(a.out.read_bytes()).hexdigest()}))


if __name__=='__main__':main()
