"""gcp2 saved88 MJWarp pixel percentile calibration; no simulator import."""
import argparse,hashlib,json,os,platform
from pathlib import Path
import cv2,numpy as np


def calibrate(root,out):
    from scripts import score_scene_tex5 as old
    from scripts.probe_warp5_render import PROFILE
    rows=[];aliases=out/'inputs';aliases.mkdir(parents=True,exist_ok=False)
    for name in json.loads((root/'index.json').read_text()):
        row=json.loads((root/(name+'.json')).read_text());stem=name+'--mjwarp--native'
        image=root/(name+'--mjwarp.jpg')
        for surface in ('floor','wall'):
            (aliases/(stem+'--mask-'+surface+'.png')).symlink_to(root/(name+'--mjwarp--mask-'+surface+'.png'))
        (aliases/image.name).symlink_to(image)
        rows.append(dict(case=name,material='mjwarp',quality='native',raw_root=str(aliases),encodings={'pil82':dict(file=image.name,sha256=hashlib.sha256(image.read_bytes()).hexdigest())}))
    # Same scene-tex5 percentile estimator, one real PIL82 image per pose.
    prior=old.ENC;old.ENC=('pil82',)
    try:cal=old.calibrate(rows,PROFILE)
    finally:old.ENC=prior
    hsv=[]
    for row in rows:
        n=row['case'];im=cv2.imread(str(root/(n+'--mjwarp.jpg')))
        mask=cv2.imread(str(root/(n+'--mjwarp--mask-wall.png')),0)>0
        hsv.append(cv2.cvtColor(im,cv2.COLOR_BGR2HSV)[cv2.erode(mask.astype(np.uint8),np.ones((5,5),np.uint8))>0])
    values=np.concatenate(hsv)
    cal['wall_value_v2']=dict(p00=float(values[:,2].min()),p100=float(values[:,2].max()))
    cal.update(renderer_profile='warp5_native_visual_v1',sample_count=88,encoding='pil82',
               renderer_source_sha256=hashlib.sha256((Path(__file__).parent/'warp5_render.py').read_bytes()).hexdigest(),
               original_root=str(root),wall_value_v2_basis='original MJWarp wall interior V p00/p100; same existing v2 brightness envelope rule',
               qualification='DEV same88 fitting; independent holdout/motion/pose/E2E not measured')
    path=out/'colour-calibration.json';path.write_text(json.dumps(cal,indent=2)+'\n');return path


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith(('ugrp-sim-gcp2','ugrp-act-l4-gcp2')):p.error('gcp2 analysis only')
    calibrate(a.input.resolve(),a.output.resolve())


if __name__=='__main__':main()
