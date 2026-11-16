import json, math, collections, sys, os
import numpy as np
sys.path.insert(0,'/Users/changmin/projects/ugrp-wt/claude-v6d-align'); sys.path.insert(0,os.path.dirname(__file__))
from hreplay import half
rows=json.load(open(os.path.dirname(__file__)+'/fullreplay_v6d.json'))
by=collections.defaultdict(list)
for r in rows: by[(r['rid'],r['post'])].append(r)
def stats(v):
    v=np.array(v); return 'n=%d bias=%+.3f rms=%.3f p95=%.3f'%(len(v),v.mean(),np.sqrt((v**2).mean()),np.percentile(np.abs(v),95)) if len(v) else 'n=0'
for k,v in sorted(by.items()):
    print(k,len(v))
    for tag in 'dw':
        vis=[r for r in v if r[tag]['vis'] and r[tag]['L'] and r[tag]['L']>=.1]
        he=[half(r[tag]['h']-r['gt_h']) for r in vis]
        gx=[r[tag]['grip'][0]-r['gt_grip'][0] for r in vis if r[tag]['grip']]
        gy=[r[tag]['grip'][1]-r['gt_grip'][1] for r in vis if r[tag]['grip']]
        print('  %s visible(L>=.1)=%d/%d  yaw:%s | gx:%s | gy:%s'%(tag,len(vis),len(v),stats(he),stats(gx),stats(gy)))
        srcs=collections.Counter(r[tag]['src'] for r in v if r[tag]['vis']); print('     src',dict(srcs))
