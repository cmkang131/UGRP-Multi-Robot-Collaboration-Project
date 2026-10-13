"""Evaluation-only stage clock alignment and SE(2) trajectory metrics. Never import into control."""
import json,subprocess,math,bisect
from pathlib import Path
import numpy as np

def read(p,lines=False):
 if not p.exists():p=Path(str(p)+'.zst')
 data=subprocess.check_output(['zstd','-qdc',str(p)]).decode() if p.suffix=='.zst' else p.read_text()
 return [json.loads(l) for l in data.splitlines() if l] if lines else json.loads(data)
def wrap(x):return np.arctan2(np.sin(x),np.cos(x))
def align(a,b):
 ma,mb=a[:,:2].mean(0),b[:,:2].mean(0);u,s,vt=np.linalg.svd((a[:,:2]-ma).T@(b[:,:2]-mb));rot=vt.T@u.T
 if np.linalg.det(rot)<0:vt[1]*=-1;rot=vt.T@u.T
 dy=wrap(a[:,2]+math.atan2(rot[1,0],rot[0,0])-b[:,2]);err=np.linalg.norm((a[:,:2]-ma)@rot.T+mb-b[:,:2],axis=1)
 heading_demean=wrap(dy-np.angle(np.mean(np.exp(1j*dy))))
 def path(x):return np.linalg.norm(np.diff(x[:,:2],axis=0),axis=1).sum()
 return dict(xy_median_m=float(np.median(err)),xy_p95_m=float(np.quantile(err,.95)),yaw_median_deg=float(np.degrees(np.median(abs(dy)))),yaw_demeaned_median_deg=float(np.degrees(np.median(abs(heading_demean)))),path_own_m=float(path(a)),path_gt_m=float(path(b)),path_ratio=float(path(a)/path(b)) if path(b)>1e-6 else None)
