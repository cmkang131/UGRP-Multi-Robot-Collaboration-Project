"""Diagnosis-only: full v2 observe_beam default vs hue_lo=25 on saved align frames vs eval-only GT."""
import json, math, bisect, os, sys, collections
import numpy as np, cv2
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/claude-v6d-align'); sys.path.insert(0,os.path.dirname(__file__))
from hreplay import half, wrap
from harness import owncam_pair_beam_v2 as v2, owncam_pair_beam as v1, owncam_pair_beam_v6d as w6
BASE='/Users/changmin/projects/ugrp/outputs/pair-stage-probes-b5234b7a-v6c-align/cases/'
POST={tuple(sorted(v2.pose_of(n).items())):n for n in v2.order()}
def gt_grip(tr_row, rid):
    x,y,yaw=tr_row['robots'][rid]; bx,by,_=tr_row['beam_xyz']; bY=tr_row['beam_yaw']
    best=None
    for sgn in (1,-1):
        gx=bx+sgn*0.27*math.cos(bY); gy=by+sgn*0.27*math.sin(bY)
        dx,dy=gx-x,gy-y
        b=(math.cos(yaw)*dx+math.sin(yaw)*dy, -math.sin(yaw)*dx+math.cos(yaw)*dy)
        if best is None or b[0]<best[0]: best=b
    return best, half(bY-yaw)
out=[]
for case in sorted(os.listdir(BASE)):
    if not os.path.isdir(BASE+case): continue
    rob=json.load(open(BASE+case+'/robots.json'))
    tr=[json.loads(l) for l in open(BASE+case+'/eval_only/trace.jsonl')]; ts=[x['t'] for x in tr]
    for rid in ('r1','r2'):
        for f in rob[rid]['frames']:
            pose={int(k):v for k,v in f['commanded_servo'].items()}
            name=POST.get(tuple(sorted(pose.items())))
            if name is None: continue
            img=cv2.imread(BASE+case+'/frames/%s/%05d.jpg'%(rid,f['frame']))
            if img is None: continue
            i=min(bisect.bisect_left(ts,f['t']),len(tr)-1)
            g,gh=gt_grip(tr[i],rid)
            row=dict(case=case,rid=rid,post=name,t=f['t'],gt_grip=g,gt_h=gh)
            for tag,hl in (('d',None),('w',25)):
                o=w6.observe_beam(img,pose,hl)
                row[tag]=dict(vis=bool(o.get('visible')),reason=o.get('reason'),src=o.get('grip_source'),
                    h=o.get('axis_heading_rad'),grip=o.get('grip_base_m'),L=o.get('visible_length_m'),endvis=o.get('end_visible'))
            out.append(row)
json.dump(out,open(os.path.dirname(__file__)+'/fullreplay_v6d.json','w'))
print(len(out))
