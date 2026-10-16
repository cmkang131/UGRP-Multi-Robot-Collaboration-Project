"""gcp2 image-only boundary plates from saved RGB, never Mac rendering."""
import argparse,platform
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
from scripts.summarize_scene_tex3 import read,write,sha
from scripts.score_scene_tex5 import signal,ENC
from scripts.probe_scene_tex2 import pose_pwm_mode
from harness.scene_colour_boundary import ColourBoundaryState

def main(analysis,roots,out,cases=None):
    from harness.zone_pair_highpose import HIGH
    from scripts.zone_teacher import FOLDED
    out.mkdir(parents=True,exist_ok=False)
    groups=[]
    for root in roots:
        groups.append([dict(read(root/i['record']),raw_root=str(root)) for i in read(root/'index.json')])
    choices=[r for r in groups[0] if r['pose']=='drive' and r['view'] in (0,1) and r['robot']=='r1'][:6]
    if cases:choices=[r for r in groups[0] if r['case'] in cases]
    plate=Image.new('RGB',(400*len(groups),330*len(choices)),'white');draw=ImageDraw.Draw(plate)
    seen=[]
    for y,b in enumerate(choices):
        for x,rr in enumerate(groups):
            r=next(r for r in rr if r['case']==b['case']);root=Path(r['raw_root']);stem=r['case']+'--'+r['material']+'--'+r['quality']
            before=cv2.imread(str(root/r['encodings']['png']['file']))
            masks={s:cv2.imread(str(root/(stem+'--mask-'+s+'.png')),0)>0 for s in ('floor','wall')}
            pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
            state=ColourBoundaryState(r['material'],read(analysis/(r['material']+'-calibration.json'))) if r['material'].startswith('walls_floor_contrast_v5_') else None
            und,scan,cm,truth=signal(before,before,pwm,masks,state,return_scan=True)
            for j,u in enumerate(cm.columns):
                vs=np.flatnonzero(truth['wall'][:-1,u]&truth['floor'][1:,u])
                for v in vs:cv2.circle(und,(int(u),int(v)),1,(255,255,0),-1)
                v=scan['vb'][j,0]
                if np.isfinite(v):cv2.circle(und,(int(u),int(round(v))),2,(0,0,255),-1)
            im=Image.fromarray(cv2.cvtColor(und,cv2.COLOR_BGR2RGB));im.thumbnail((400,300));plate.paste(im,(400*x,330*y+30))
            draw.text((400*x+2,330*y+2),r['material'].replace('walls_floor_contrast_v5_','')+'/'+r['quality'],fill='black')
            draw.text((400*x+2,330*y+15),r['case'],fill='black')
            seen.append({'case':r['case'],'profile':r['material'],'encoding':'png','time':'SIM0 static'})
    plate.save(out/'boundary-review.jpg',quality=85)
    write(out/'review-index.json',{'frames':seen,'legend':'cyan=evaluation wall-floor contact; red=detector; undistorted own RGB','scope':'static t0; no motion timeline or dynamic video review'})
    write(out/'SHA256SUMS.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--analysis',type=Path,required=True);p.add_argument('--inputs',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cases',nargs='+');a=p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):p.error('gcp2 only')
    main(a.analysis,a.inputs,a.output,a.cases)
