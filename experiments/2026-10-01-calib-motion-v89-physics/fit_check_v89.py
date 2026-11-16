import json,sys,importlib.util,numpy as np
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/phys-v89-motion')
from scripts.check_measurement_v2_identifiability import response
R='/Users/changmin/projects/ugrp/outputs/calib-motion-v89-eaeaaff0-20261001/zone_wide_two_doors_final_v3/'
cfg=json.load(open('/Users/changmin/projects/ugrp-wt/phys-v89-motion/configs/final_environment_measurement_v2.json'))
pose=[json.loads(l) for l in open(R+'eval_only/r1/pose.jsonl')]
P=np.array([p['base_position_m'] for p in pose]); Rm=np.array([p['base_rotation'] for p in pose])
T=np.array([p['t'] for p in pose])
# body-frame displacement relative to a fixed frame (initial yaw)
d=P-P[0]
fwd=d[:,0]*Rm[0][0][0]+d[:,1]*Rm[0][1][0]; lat=d[:,0]*Rm[0][0][1]+d[:,1]*Rm[0][1][1]
yaw=np.arctan2(Rm[:,1,0],Rm[:,0,0]); print('yaw range deg',np.degrees(yaw.min()),np.degrees(yaw.max()))
out={}
n0=int(round(cfg['initial_hold_s']/.05))
for ax,sig,off in (('forward',fwd,0),('left',lat,1)):
    segs=[(s['duration_s'],s['value']) for s in cfg['segments'] if s['axis']==('forward' if ax=='forward' else 'left')]
    tot=sum(s[0] for s in segs); n=int(round(tot/.05))
    a=n0+off*n
    y=sig[a:a+n+1]-sig[a]
    def gridfit(seglist,yy,taus,stops):
        td,ts=np.meshgrid(taus,stops,indexing='ij')
        x=response(seglist,.05,td.ravel(),ts.ravel())
        g=(yy@x)/np.sum(x*x,axis=0)
        rms=np.sqrt(np.mean((x*g-yy[:,None])**2,axis=0))
        return td.ravel(),ts.ravel(),g,rms
    taus=np.unique(np.r_[np.geomspace(.1,100,301)]); stops=np.array([.03,.05,.08,.12,.2,.3,.44,1.,2.])
    for label,seglist,yy in (('full',segs,y),):
        td,ts,g,rms=gridfit(seglist,yy,taus,stops); j=np.argmin(rms)
        ok=rms<=rms[j]*1.05
        print(ax,label,'best gain %.4f tau %.3f stop %.3f rms_mm %.4f'%(g[j],td[j],ts[j],rms[j]*1e3))
        print('  within +5%% of min: gain %.3f-%.3f tau %.3f-%.3f stop %.2f-%.2f n=%d'%(g[ok].min(),g[ok].max(),td[ok].min(),td[ok].max(),ts[ok].min(),ts[ok].max(),ok.sum()))
        # profile over tau (min over stop)
        for t in (1,1.44,2,3,5,10):
            k=np.argmin(np.abs(td-t)+ (ts!=ts[0])*1e3*0) 
        prof=[(t,min(rms[np.isclose(td,td[np.argmin(abs(td-t))])])*1e3, g[np.argmin(np.where(np.isclose(td,td[np.argmin(abs(td-t))]),rms,9))]) for t in (0.3,0.5,1,1.44,2,3,5,10,30)]
        print('  tau profile (tau, rms_mm, gain):',[(round(a,2),round(b,3),round(c,3)) for a,b,c in prof])
        # is tau at grid edge?
        print('  tau at grid edge?',td[j] in (taus[0],taus[-1]), 'stop edge?',ts[j] in (stops[0],stops[-1]))
    # steps only fit (first 6 steps+coast = 96 s) then PRBS prediction
    nst=int(round(96/.05))
    sst=segs[:12]
    td,ts,g,rms=gridfit(sst,y[:nst+1],taus,stops); j=np.argmin(rms)
    ok=rms<=rms[j]*1.05
    print(ax,'steps-only best gain %.4f tau %.3f stop %.3f rms_mm %.4f'%(g[j],td[j],ts[j],rms[j]*1e3),'| +5%% gain %.3f-%.3f tau %.3f-%.3f'%(g[ok].min(),g[ok].max(),td[ok].min(),td[ok].max()))
    full=response(segs,.05,np.array(td[j]),np.array(ts[j]))*g[j]
    # PRBS prediction residual (relative displacement within PRBS window)
    a2=nst; 
    pr=(y[a2:]-y[a2])-(full[a2:]-full[a2])
    print('   PRBS pred residual rms mm %.4f (PRBS displacement rms mm %.4f)'%(np.sqrt(np.mean(pr**2))*1e3,np.sqrt(np.mean((y[a2:]-y[a2])**2))*1e3))
    # steady state velocity last 3 s of each step
    v=np.gradient(y,.05); idx=0; ss=[]
    for dur,val in segs[:12]:
        m=int(round(dur/.05))
        if val!=0:
            ss.append((val,float(v[idx+m-60:idx+m].mean())/val))
        idx+=m
    print('   steady-state gain (last 3 s) per step:',[(s[0],round(s[1],3)) for s in ss])
    out[ax]=dict(best=[float(g[j]),float(td[j]),float(ts[j]),float(rms[j])])

print('=== deadband model: u_eff=sign(u)*max(|u|-d,0) ===')
for ax,sig,off in (('forward',fwd,0),('left',lat,1)):
    segs=[(s['duration_s'],s['value']) for s in cfg['segments'] if s['axis']==ax]
    n=int(round(sum(s[0] for s in segs)/.05)); a=n0+off*n; y=sig[a:a+n+1]-sig[a]
    taus=np.unique(np.r_[np.geomspace(.1,30,181)]); stops=np.array([.03,.05,.08,.12,.2,.3,.44,1.])
    td,ts=np.meshgrid(taus,stops,indexing='ij'); td=td.ravel(); ts=ts.ravel()
    res=[]
    for d in np.arange(0,.0121,.0005):
        s2=[(du,np.sign(v)*max(abs(v)-d,0)) for du,v in segs]
        x=response(s2,.05,td,ts); g=(y@x)/np.sum(x*x,axis=0); rms=np.sqrt(np.mean((x*g-y[:,None])**2,axis=0))
        j=np.argmin(rms); res.append((d,g[j],td[j],ts[j],rms[j]))
    res=np.array(res); b=np.argmin(res[:,4]); print(ax,'best d %.4f gain %.4f tau %.3f stop %.3f rms_mm %.4f'%(res[b,0],res[b,1],res[b,2],res[b,3],res[b,4]*1e3))
    # +5% box over all (d,gain,tau,stop)
    allp=[]
    for d in np.arange(0,.0121,.0005):
        s2=[(du,np.sign(v)*max(abs(v)-d,0)) for du,v in segs]
        x=response(s2,.05,td,ts); g=(y@x)/np.sum(x*x,axis=0); rms=np.sqrt(np.mean((x*g-y[:,None])**2,axis=0))
        ok=rms<=res[b,4]*1.05
        for k in np.flatnonzero(ok): allp.append((d,g[k],td[k],ts[k]))
    allp=np.array(allp)
    print('  within +5%% of min (n=%d): d %.4f-%.4f gain %.3f-%.3f tau %.3f-%.3f stop %.2f-%.2f'%((len(allp),)+tuple(v for c in range(4) for v in (allp[:,c].min(),allp[:,c].max()))))
    # steps-only fit then PRBS prediction
    nst=int(round(96/.05)); s_st=segs[:12]; 
    best=None
    for d in np.arange(0,.0121,.0005):
        s2=[(du,np.sign(v)*max(abs(v)-d,0)) for du,v in s_st]
        x=response(s2,.05,td,ts); yy=y[:nst+1]; g=(yy@x)/np.sum(x*x,axis=0); rms=np.sqrt(np.mean((x*g-yy[:,None])**2,axis=0)); j=np.argmin(rms)
        if best is None or rms[j]<best[0]: best=(rms[j],d,g[j],td[j],ts[j])
    _,d,g,t_,s_=best
    s2=[(du,np.sign(v)*max(abs(v)-d,0)) for du,v in segs]
    full=g*response(s2,.05,np.array(t_),np.array(s_)); pr=(y[nst:]-y[nst])-(full[nst:]-full[nst])
    print('  steps-only: d %.4f gain %.4f tau %.3f stop %.3f step rms_mm %.4f; PRBS pred residual rms %.4f mm (PRBS disp rms %.3f mm)'%(d,g,t_,s_,best[0]*1e3,np.sqrt(np.mean(pr**2))*1e3,np.sqrt(np.mean((y[nst:]-y[nst])**2))*1e3))
