"""Diagnosis only: does the PF velocity model explain GT displacement for align pulses?"""
import json, math, bisect, glob, os, sys
import numpy as np
BASE='/Users/changmin/projects/ugrp/outputs/pair-stage-probes-b5234b7a-v6c-align/cases/'
ROOT='/Users/changmin/projects/ugrp-wt/claude-v6d-align/'
loop=json.load(open(ROOT+'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'))['params']
m1=json.load(open(ROOT+'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json'))['params']
PROFILES={'default':loop['motion'],'m1_fine':m1['motion_profiles']['fine']}
def wrap(a): return (a+math.pi)%(2*math.pi)-math.pi
def simulate(mp, cmds, t0, t1, dt=0.05):
    """deterministic body velocity integration -> list of (t, vel_body)"""
    gain=np.asarray(mp['gain'],float); vel=np.zeros(3); out=[]
    t=t0; cmd=np.zeros(3); exp=-1; ci=0
    cmds=sorted(cmds,key=lambda c:c['t'])
    while t<t1-1e-9:
        while ci<len(cmds) and cmds[ci]['t']<=t+1e-9:
            c=cmds[ci]; ci+=1
            if c['kind']=='mecanum': cmd=np.array([c['forward'],c['left'],c['turn']]); exp=c['t']+c['duration_s']
            else: cmd=np.zeros(3); exp=-1
        u=cmd if t<exp-1e-9 else np.zeros(3)
        target=gain@u
        tau=mp.get('tau_stop_s',mp['tau_s']) if not np.any(u) else mp['tau_s']
        if np.any(u) and 'tau_axis_s' in mp: alpha=1-np.exp(-dt/np.maximum(np.asarray(mp['tau_axis_s'],float),1e-6))
        else: alpha=1-math.exp(-dt/max(tau,1e-6))
        vel=vel+alpha*(target-vel)
        out.append((t,vel.copy())); t+=dt
    return out
def analyse(case,rid,t_start,t_end):
    tr=[json.loads(l) for l in open(BASE+case+'/eval_only/trace.jsonl')]
    ts=[x['t'] for x in tr]
    def gt(t):
        i=min(bisect.bisect_left(ts,t),len(tr)-1); return tr[i]['robots'][rid]
    cm=[c for c in json.load(open(BASE+case+'/commands.json'))[rid] if c['kind'] in('mecanum','hold','drive')]
    res={}
    for name,mp in PROFILES.items():
        traj=simulate(mp,cm,t_start,t_end)
        # body-frame displacement using GT yaw
        d=np.zeros(3)
        for t,v in traj:
            yaw=gt(t)[2]
            d+=np.array([v[0],v[1],v[2]])*0.05
        res[name]=d
    g0,g1=gt(t_start),gt(t_end)
    dx,dy=g1[0]-g0[0],g1[1]-g0[1]; yaw0=g0[2]
    body=np.array([math.cos(yaw0)*dx+math.sin(yaw0)*dy,-math.sin(yaw0)*dx+math.cos(yaw0)*dy,wrap(g1[2]-g0[2])])
    return body,res
if __name__=='__main__':
    tot={}
    for case in sorted(os.listdir(BASE)):
        if not os.path.isdir(BASE+case): continue
        r=json.load(open(BASE+case+'/result.json'))
        for rid in ('r1','r2'):
            ev=r['controller_events'][rid]
            # window: from first mecanum after align entry through last mecanum + 0.6
            cm=[c for c in json.load(open(BASE+case+'/commands.json'))[rid] if c['kind']=='mecanum']
            if not cm: continue
            t0=cm[0]['t']; t1=cm[-1]['t']+0.6
            body,res=analyse(case,rid,t0,t1)
            print(case.replace('align_b-v6c_',''),rid,'T=%.1f-%.1f'%(t0,t1),'GT body d=[%.3f %.3f %.3f]'%tuple(body),'| default=[%.3f %.3f %.3f]'%tuple(res['default']),'| m1_fine=[%.3f %.3f %.3f]'%tuple(res['m1_fine']))
