"""Diagnosis-only: replay saved align frames through beam heading estimators vs eval-only GT."""
import json, math, bisect, os, sys, collections
import numpy as np, cv2
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/claude-v6d-align')
from harness import owncam_pair_beam as v1
from harness.owncam_view import base_rays
BASE='/Users/changmin/projects/ugrp/outputs/pair-stage-probes-b5234b7a-v6c-align/cases/'
def wrap(a): return (a+math.pi)%(2*math.pi)-math.pi
def half(a):
    a=wrap(a)
    if a>math.pi/2: a-=math.pi
    if a<=-math.pi/2: a+=math.pi
    return a

def points(frame,pose,extra_dark=False,mask_fn=None):
    mask=v1.lime_mask(frame)
    if extra_dark:
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        dark=(hsv[...,2]<=60)&(hsv[...,1]<90)
        mask=mask|dark
    origin,rays,xs,ys,valid=base_rays(pose,v1.RAY_STEP)
    xi,yi=xs.astype(int),ys.astype(int)
    hit=valid&mask[yi,xi]&(rays[:,2]<-1e-6)
    s=(v1.BEAM_TOP_Z_M-origin[2])/rays[hit,2]
    pts=(origin+s[:,None]*rays[hit])[:,:2]
    ok=(s>0)&(np.linalg.norm(pts,axis=1)<2.5)
    return pts[ok],xi[hit][ok],yi[hit][ok]

def pca_heading(pts):
    mean=pts.mean(0); _,vecs=np.linalg.eigh(np.cov((pts-mean).T)); u=vecs[:,-1]
    if u@mean<0: u=-u
    return math.atan2(u[1],u[0]),mean,u

def slice_heading(pts,u0,mean,width=.01,minn=6):
    n=np.array([-u0[1],u0[0]])
    a=(pts-mean)@u0; c=(pts-mean)@n
    bins=np.floor(a/width).astype(int)
    xs=[];ys=[];ws=[]
    for b in np.unique(bins):
        m=bins==b
        if m.sum()<minn: continue
        xs.append(a[m].mean()); ys.append((c[m].min()+c[m].max())/2); ws.append(m.sum())
    if len(xs)<4: return None
    k=np.polyfit(xs,ys,1)[0]
    return math.atan2(u0[1]+k*n[1],u0[0]+k*n[0]) if False else math.atan2(u0[1],u0[0])+math.atan(k)

def edge_heading(pts,u0,mean,width=.01,minn=6,trim=0.0):
    n=np.array([-u0[1],u0[0]])
    a=(pts-mean)@u0; c=(pts-mean)@n
    bins=np.floor(a/width).astype(int)
    xs=[];lo=[];hi=[]
    for b in np.unique(bins):
        m=bins==b
        if m.sum()<minn: continue
        xs.append(a[m].mean()); lo.append(np.percentile(c[m],5)); hi.append(np.percentile(c[m],95))
    if len(xs)<4: return None
    k=(np.polyfit(xs,lo,1)[0]+np.polyfit(xs,hi,1)[0])/2
    return math.atan2(u0[1],u0[0])+math.atan(k)

def run():
    out=[]
    for case in sorted(os.listdir(BASE)):
        if not os.path.isdir(BASE+case): continue
        res=json.load(open(BASE+case+'/result.json'))
        rob=json.load(open(BASE+case+'/robots.json'))
        tr=[json.loads(l) for l in open(BASE+case+'/eval_only/trace.jsonl')]
        ts=[x['t'] for x in tr]
        for rid in ('r1','r2'):
            evs={round(e['sim_s'],2):e for e in res['controller_events'][rid] if e['event']=='beam_obs' and e.get('axis_heading_rad') is not None}
            for f in rob[rid]['frames']:
                key=round(f['t'],2)
                # beam_obs event sim_s is the 'now' at which look is called; frame t may differ slightly
                e=None
                for dk in (0,.1,-.1,.2,-.2):
                    e=evs.get(round(key+dk,2))
                    if e: break
                if not e: continue
                L=e.get('visible_length_m') or 0
                post=e['posture']
                if post=='search': continue
                img=cv2.imread(BASE+case+'/frames/%s/%05d.jpg'%(rid,f['frame']))
                if img is None: continue
                pose={int(k):v for k,v in f['commanded_servo'].items()}
                i=min(bisect.bisect_left(ts,f['t']),len(tr)-1)
                x,y,yaw=tr[i]['robots'][rid]; bY=tr[i]['beam_yaw']
                gh=half(bY-yaw)
                pts,px,py=points(img,pose)
                if len(pts)<v1.MIN_POINTS: continue
                h0,mean,u=pca_heading(pts)
                ests={'pca':h0}
                ests['pca_ev']=e['axis_heading_rad']
                # exclude points near inner border
                if v1._INNER is None: v1._INNER=v1._inner_valid()
                inner=v1._INNER[py,px]
                if inner.sum()>=v1.MIN_POINTS:
                    ests['pca_inner']=pca_heading(pts[inner])[0]
                ptsd,pxd,pyd=points(img,pose,extra_dark=True)
                ests['pca_dark']=pca_heading(ptsd)[0]
                ests['slice']=slice_heading(pts,u,mean)
                ests['edge']=edge_heading(pts,u,mean)
                if inner.sum()>=v1.MIN_POINTS:
                    u2=pca_heading(pts[inner])
                    ests['slice_inner']=slice_heading(pts[inner],u2[2],u2[1])
                    ests['edge_inner']=edge_heading(pts[inner],u2[2],u2[1])
                out.append(dict(case=case,rid=rid,posture=post,t=f['t'],L=L,gh=gh,ests=ests,gx=None))
    return out
if __name__=='__main__':
    out=run()
    json.dump(out,open(os.path.dirname(__file__)+'/hreplay.json','w'))
    by=collections.defaultdict(list)
    for o in out: by[(o['rid'],o['posture'])].append(o)
    for k,v in sorted(by.items()):
        print(k,len(v))
        names=sorted({n for o in v for n in o['ests']})
        for n in names:
            e=np.array([half(o['ests'][n]-o['gh']) for o in v if o['ests'].get(n) is not None])
            g=np.array([o['gh'] for o in v if o['ests'].get(n) is not None]); ob=g+e
            A=np.vstack([np.ones_like(g),g]).T
            (a,kk),*_=np.linalg.lstsq(A,ob,rcond=None)
            print('   %-12s n=%d bias=%+.3f std=%.3f  rms=%.3f | fit a=%+.3f k=%.2f resid=%.3f'%(n,len(e),e.mean(),e.std(),np.sqrt((e**2).mean()),a,kk,np.std(ob-A@np.array([a,kk]))))
