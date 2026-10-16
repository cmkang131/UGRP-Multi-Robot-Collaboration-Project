import json,sys,math,glob,os
import numpy as np
roots=sys.argv[1:]
def wrap(a): return (a+math.pi)%(2*math.pi)-math.pi
end=[];allr=[]
per=[]
for root,l in [(r,l) for r in roots for l in open(r+'/cases.jsonl')]:
    d=json.loads(l)
    cid=d['case_id']; d2=root+'/cases/'+cid.replace('@','_').replace(':','_')
    d2=d2.replace('/','_') if False else root+'/cases/'+os.path.basename(cid.replace('@','_').replace(':','_').replace('/','_'))
    tr=root+'/cases/'+cid.replace('@','_').replace(':','_').replace('/','_')+'/eval_only/trace.jsonl'
    if not os.path.exists(tr): print('missing',tr); continue
    rows=[json.loads(x) for x in open(tr)]
    tex=max(d['exit_sim_s'].values()) if d.get('exit_sim_s') else rows[-1]['t']
    ent=d['entry_sim_s']
    pr=[x for x in rows if 'pf' in x and x['t']<=tex+1e-6 and x['t']>=ent]
    for r in ('r1','r2'):
        samples=[]
        for x in pr:
            p=x['pf'][r]
            if not p.get('initialized'): continue
            g=x['robots'][r]
            e=np.array([g[0]-p['x'],g[1]-p['y'],wrap(g[2]-p['yaw'])])
            C=np.array(p['cov'])
            nees=float(e@np.linalg.solve(C,e))
            sd=np.sqrt(np.diag(C))
            samples.append((x['t'],nees,np.abs(e)/sd,sd,e))
        if not samples: continue
        allr+= [(s[1],s[2]) for s in samples]
        t,n,z,sd,e=samples[-1]
        end.append((cid,r,t,n,z,sd,e))
def summ(name,nees,z):
    nees=np.array(nees); z=np.array(z)
    print(name,'n=',len(nees),'meanNEES=%.2f'%nees.mean(),'median=%.2f'%np.median(nees),'cov2σ x/y/yaw=',(z<=2).mean(0).round(3))
summ('leg-end',[e[3] for e in end],[e[4] for e in end])
summ('all-stage-samples',[a for a,b in allr],[b for a,b in allr])
for e in end: print(e[0].split('@')[1][:40],e[1],'t=%.1f'%e[2],'nees=%.2f'%e[3],'z=',e[4].round(2),'sd_xy=%.3f sd_yaw_deg=%.2f'%(math.hypot(e[5][0],e[5][1])/math.sqrt(2),math.degrees(e[5][2])),'err_xy=%.3f err_yaw_deg=%.2f'%(math.hypot(e[6][0],e[6][1]),math.degrees(e[6][2])))
