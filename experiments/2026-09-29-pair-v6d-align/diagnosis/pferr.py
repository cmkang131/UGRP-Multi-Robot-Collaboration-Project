import json,math,bisect,sys
BASE='/Users/changmin/projects/ugrp/outputs/pair-stage-probes-b5234b7a-v6c-align/cases/'
def wrap(a): return (a+math.pi)%(2*math.pi)-math.pi
def run(case,rid,t0,t1,step=1):
    tr=[json.loads(l) for l in open(BASE+case+'/eval_only/trace.jsonl')]
    ts=[x['t'] for x in tr]
    d=json.load(open(BASE+case+'/robots.json'))[rid]
    print('==',case,rid)
    last=-9
    for f in d['frames']:
        if not(t0<=f['t']<=t1) or f['t']-last<step-1e-6: continue
        last=f['t']
        i=min(bisect.bisect_left(ts,f['t']),len(tr)-1)
        gx,gy,gyaw=tr[i]['robots'][rid]
        r=f['report']; ex,ey,eyaw=r['xyyaw']
        q=r['observation_quality']
        print(round(f['t'],1),'pan',f['commanded_servo'].get('6'),'PF err xy=%.3f yaw=%.3f'%(math.hypot(ex-gx,ey-gy),wrap(eyaw-gyaw)),'dx=%.3f dy=%.3f'%(ex-gx,ey-gy),'std',round(r['std_xy_m'],3),'tags',r['last_valid_obs'].get('n_tags'),'inl',q.get('inlier_fraction'),'lost',q.get('lost'),'fixage',r['fix_age_s'] and round(r['fix_age_s'],1))
if __name__=='__main__':
    run(sys.argv[1],sys.argv[2],float(sys.argv[3]),float(sys.argv[4]),float(sys.argv[5]) if len(sys.argv)>5 else 1)
