import json, math, bisect, os, collections
import numpy as np
BASE='/Users/changmin/projects/ugrp/outputs/pair-stage-probes-b5234b7a-v6c-align/cases/'
def wrap(a): return (a+math.pi)%(2*math.pi)-math.pi
def half(a):  # into (-pi/2, pi/2]
    a=wrap(a)
    if a>math.pi/2: a-=math.pi
    if a<=-math.pi/2: a+=math.pi
    return a
rows=collections.defaultdict(list)
per_case={}
for case in sorted(os.listdir(BASE)):
    if not os.path.isdir(BASE+case): continue
    res=json.load(open(BASE+case+'/result.json'))
    tr=[json.loads(l) for l in open(BASE+case+'/eval_only/trace.jsonl')]
    ts=[x['t'] for x in tr]
    for rid in ('r1','r2'):
        posture='search'
        for e in res['controller_events'][rid]:
            if e['event']=='look_posture': posture=e['posture']
            if e['event']!='beam_obs' or e.get('axis_heading_rad') is None: continue
            i=min(bisect.bisect_left(ts,e['sim_s']),len(tr)-1)
            gx,gy,gyaw=tr[i]['robots'][rid]; by=tr[i]['beam_yaw']
            gt_head=half(by-gyaw)
            err=half(e['axis_heading_rad']-gt_head)
            rows[(rid,e.get('posture',posture))].append((err,e.get('visible_length_m'),case,e['sim_s'],gt_head))
for k,v in sorted(rows.items()):
    errs=np.array([x[0] for x in v]); L=np.array([x[1] or 0 for x in v])
    print(k,'n=%d'%len(v),'mean=%.3f std=%.3f med=%.3f  |err|>0.05: %.0f%%'%(errs.mean(),errs.std(),np.median(errs),100*np.mean(np.abs(errs)>0.05)),'L med=%.2f'%np.median(L))
    # bins by visible length
    for lo,hi in [(0,.1),(.1,.2),(.2,.4),(.4,2)]:
        m=(L>=lo)&(L<hi)
        if m.sum()>3: print('    L in [%.1f,%.1f) n=%d mean=%.3f std=%.3f'%(lo,hi,m.sum(),errs[m].mean(),errs[m].std()))

print('--- regression obs = a + k*gt (inspect, L in [.1,.25))')
for rid in ('r1','r2'):
    for post in ('inspect','p45','search'):
        v=[x for x in rows[(rid,post)] if x[1] and .1<=x[1]<.8]
        if len(v)<10: continue
        g=np.array([x[4] for x in v]); o=g+np.array([x[0] for x in v])
        A=np.vstack([np.ones_like(g),g]).T
        (a,k),*_=np.linalg.lstsq(A,o,rcond=None)
        print(rid,post,'n=%d a=%.3f k=%.2f  resid_std=%.3f  gt range [%.2f,%.2f]'%(len(v),a,k,np.std(o-A@np.array([a,k])),g.min(),g.max()))
# failing cases: last inspect obs error
print('--- last 5 inspect obs error per case (r1,r2)')
for case in sorted({x[2] for v in rows.values() for x in v}):
    line=case.replace('align_b-v6c_','')
    for rid in ('r1','r2'):
        v=[x for x in rows[(rid,'inspect')] if x[2]==case and x[1] and x[1]>=.1]
        if v:
            last=v[-6:]
            line+=' | %s err=%s gt=%.2f'%(rid,','.join('%.2f'%x[0] for x in last),last[-1][4])
    print(line)
