import json,glob,os,numpy as np,colorsys
from PIL import Image
P='/Users/changmin/projects/ugrp/outputs/'
res=[]
for raw in ['pair-stage-probes-ece38792-cal','pair-stage-probes-a704ecc6-calB','pair-stage-probes-d08818ef-cal2','pair-stage-probes-a704ecc6-smokeC']:
    for cd in sorted(glob.glob(P+raw+'/cases/*/')):
        rj=cd+'robots.json'
        if not os.path.exists(rj): continue
        rb=json.load(open(rj))
        for r in ('r1','r2'):
            for f in rb[r]['frames']:
                if f['report'].get('load_state')!='loaded': continue
                if f['frame']%12: continue
                im=np.asarray(Image.open(cd+f'frames/{r}/{f["frame"]:05d}.jpg').convert('HSV')).astype(int)
                H,S,V=im[...,0],im[...,1],im[...,2]
                # inside fisheye active region: V>=8 or beam; use central crop away from black corners
                crop=(slice(60,420),slice(60,580))
                h,s,v=H[crop],S[crop],V[crop]
                green=(h>40)&(h<90)&(s>100)&(v>60)
                struct=(~green)&(v>45)
                res.append((raw,os.path.basename(cd[:-1]),r,f['frame'],green.mean(),struct.mean(),v[~green].mean() if (~green).any() else 0,f['report'].get('since_tag_s')))
print(len(res))
a=np.array([(x[4],x[5],x[6]) for x in res])
print('beam-green fraction: mean %.3f min %.3f max %.3f'%(a[:,0].mean(),a[:,0].min(),a[:,0].max()))
print('non-beam structured (V>45) fraction: mean %.5f max %.5f ; frames with >1%% =%d'%(a[:,1].mean(),a[:,1].max(),(a[:,1]>.01).sum()))
print('mean V of non-beam pixels: mean %.1f max %.1f'%(a[:,2].mean(),a[:,2].max()))
bad=[x for x in res if x[5]>.01]
for x in bad[:8]: print(x)
