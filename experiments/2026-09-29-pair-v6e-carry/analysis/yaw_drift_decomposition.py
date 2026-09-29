import json,math,collections,numpy as np
P='/Users/changmin/projects/ugrp/outputs/'
def wrap(a): return (a+math.pi)%(2*math.pi)-math.pi
out=collections.defaultdict(list)
for raw in ['pair-stage-probes-ece38792-cal','pair-stage-probes-a704ecc6-calB2','pair-stage-probes-a704ecc6-calB']:
    for l in open(P+raw+'/cases.jsonl'):
        d=json.loads(l)
        if d['cell']=='nominal' and d['seed']!=911: continue
        tr=P+raw+'/cases/'+d['case_id'].replace('@','_').replace(':','_').replace('/','_')+'/eval_only/trace.jsonl'
        rows=[json.loads(x) for x in open(tr)]
        tex=max(d['exit_sim_s'].values()) if d.get('exit_sim_s') else rows[-1]['t']
        pr=[x for x in rows if 'pf' in x and d['entry_sim_s']<=x['t']<=tex+1e-6]
        a,b=pr[0],pr[-1]; T=b['t']-a['t']
        for r in ('r1','r2'):
            gt=wrap(b['robots'][r][2]-a['robots'][r][2])/T*1000
            pf=wrap(b['pf'][r]['yaw']-a['pf'][r]['yaw'])/T*1000
            bm=wrap(b['beam_yaw']-a['beam_yaw'])/T*1000
            out[(d['cell'],d['leg'],r)].append((gt,pf,bm))
print('mrad/s  cell leg robot :  GT-robot-yaw-rate  PF-yaw-rate  beam-yaw-rate')
for k in sorted(out,key=lambda k:(k[0],k[2],k[1])):
    v=np.mean(out[k],0); print(k, '%+.2f %+.2f %+.2f'%tuple(v))
