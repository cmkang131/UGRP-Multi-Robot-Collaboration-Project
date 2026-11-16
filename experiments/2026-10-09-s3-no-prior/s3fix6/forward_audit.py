"""Evaluation-only same-window forward-pulse audit; never imported by control."""
import json, math, hashlib
from collections import Counter
from pathlib import Path
import numpy as np
from harness.zone_solo_cyan_pulse_cal import profile_key, response
from harness.zone_s2_realism_contract_v122 import PULSE_MODEL
ROOT=Path('/Users/changmin/projects/ugrp/outputs')

def rows(p):return [json.loads(s) for s in p.read_text().splitlines()]
def audit(raw,rid,own):
    model=json.loads(Path(PULSE_MODEL).read_text())
    commands=rows(raw/f'robots/{rid}/commands.jsonl')
    truthpath=raw/('eval_only/trajectory.jsonl' if own else f'eval_only/{rid}/trajectory.jsonl')
    truth=rows(truthpath); ts=np.array([r['t'] for r in truth]);xy=np.array([r['robot_xyz_m'][:2] for r in truth]);yaw=np.unwrap([r['robot_yaw_rad'] for r in truth])
    def pose(t):return np.r_[[np.interp(t,ts,xy[:,i]) for i in range(2)],np.interp(t,ts,yaw)]
    contacts=rows(raw/'eval_only/contacts.jsonl')
    hit=[]
    for r in contacts:
        pairs=[c for c in r['contacts'] if (c['geom1'].startswith(rid+'__') or c['geom2'].startswith(rid+'__')) and
            not (c['geom1']=='floor' or c['geom2']=='floor') and not (c['geom1'].startswith(rid+'__') and c['geom2'].startswith(rid+'__'))]
        if pairs:hit.append((r['t'],pairs))
    motion=[c for c in commands if c['kind'] in ('drive','mecanum') and any(c.get(k,0) for k in ('forward','left','turn'))]
    data=[];servo={}
    for i,c in enumerate(motion):
        if not c.get('forward'):continue
        p=model['profiles'][profile_key(c,False)]; t=c['t'];end=min(t+p['times'][-1],motion[i+1]['t'] if i+1<len(motion) else ts[-1],ts[-1])
        a,b=pose(t),pose(end);co,si=np.cos(a[2]),np.sin(a[2]);actual=np.array([[co,si],[-si,co]])@(b[:2]-a[:2]);pred=response(p,end-t)
        before=motion[i-1] if i else None
        cs=[(tt,pair) for tt,pair in hit if t-1e-8<=tt<=end+1e-8]
        data.append(dict(t=t,end=end,duration=c['duration_s'],u=c['forward'],yaw=float(a[2]),
            gap=None if before is None else round(t-before['t'],6),previous_axis=None if before is None else next(k for k in ('forward','left','turn') if before.get(k)),
            contact=bool(cs),contact_pairs=sorted(set(c['geom1']+'|'+c['geom2'] for _, pairs in cs for c in pairs)),
            pred=pred[:2].tolist(),actual=actual.tolist(),distance=float(np.linalg.norm(actual)),
            residual_x=float(pred[0]-actual[0])))
    def summary(v):
        p=sum(np.linalg.norm(r['pred']) for r in v);a=sum(r['distance'] for r in v)
        return dict(n=len(v),predicted_m=p,actual_m=a,ratio=None if not a else p/a,residual_x_m=sum(r['residual_x'] for r in v))
    groups={'all':data,'contact':[r for r in data if r['contact']],'no_contact':[r for r in data if not r['contact']]}
    for axis in ('forward','turn'):
        for gap in (.2,.4):groups[f'no_contact_prev_{axis}_gap_{gap}']=[r for r in data if not r['contact'] and r['previous_axis']==axis and r['gap']==gap]
    for k in range(4):groups[f'no_contact_yaw_quadrant_{k}']=[r for r in data if not r['contact'] and int((r['yaw']%(2*math.pi))/(math.pi/2))==k]
    return dict(raw=str(raw),robot=rid,groups={k:summary(v) for k,v in groups.items()},
        pulse_vocabulary=dict(Counter(str((r['u'],r['duration'])) for r in data)),gap_counts=dict(Counter(str(r['gap']) for r in data)),
        drive_sha256=hashlib.sha256((raw/'eval_only/drive-v7.json').read_bytes()).hexdigest(),
        truth_sha256=hashlib.sha256(truthpath.read_bytes()).hexdigest()),data

if __name__=='__main__':
    out=ROOT/'s3fix6-20261010/forward-audit-v2';out.mkdir(exist_ok=False)
    table=[]
    for key,raw,rid,own in [('v149',ROOT/'s3-sweep-b73ce193-s14201-v149','r2',False),('55001',ROOT/'goal-route-motion-audit-v1/seed55001','r3',True),('55002',ROOT/'goal-route-motion-audit-v1/seed55002','r3',True)]:
        result,data=audit(raw,rid,own);table.append(dict(case=key,**result));(out/f'{key}-pulses.json').write_text(json.dumps(data)+'\n')
    (out/'summary.json').write_text(json.dumps(table,indent=2)+'\n');print(json.dumps(table,indent=2))
