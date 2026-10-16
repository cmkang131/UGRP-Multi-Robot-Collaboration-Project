"""gcp2 stored-image candidate remeasurement; preserves original RGB/LK rows."""
import argparse,hashlib,json,os,platform,subprocess
from pathlib import Path
import cv2


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--calibration',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith(('ugrp-sim-gcp2','ugrp-act-l4-gcp2')):p.error('gcp2 analysis only')
    from scripts.calibrate_warp5_perception import calibrate
    from scripts.score_scene_tex5 import signal
    from scripts.audit_scene_tex5_colours import counts
    from harness.scene_colour_boundary import ColourBoundaryState,RELOC16_OPTION
    from harness.warp5_perception import install
    from scripts.analyze_warp5_render import analyze
    root=a.input.resolve();a.output.mkdir(parents=True,exist_ok=False)
    cal_path=calibrate(root,a.calibration.resolve());cal=json.loads(cal_path.read_text())
    os.environ.update(UGRP_WARP5_PERCEPTION='rendered_v1',UGRP_SCENE_COLOUR_CALIBRATION=str(cal_path),
        UGRP_SCENE_COLOUR_CALIBRATION_SHA256=hashlib.sha256(cal_path.read_bytes()).hexdigest())
    install();cv2.setNumThreads(1)
    names=json.loads((root/'index.json').read_text())
    for name in names:
        r=json.loads((root/(name+'.json')).read_text());before=cv2.imread(str(root/(name+'--mjwarp.jpg')))
        masks={s:cv2.imread(str(root/(name+'--mjwarp--mask-'+s+'.png')),0)>0 for s in ('floor','wall')}
        state=ColourBoundaryState(cal['scene_profile'],cal,option=RELOC16_OPTION)
        scored=signal(before,before,r['pwm'],masks,state)
        for field in ('qualified','columns','residuals_px','false_columns','visible_boundary_columns','segments','reasons'):
            if field in scored:r['metrics']['mjwarp']['boundary'][field]=scored[field]
        r['metrics']['mjwarp']['colours']=counts(before,r['pwm'])
        r['rescoring']=dict(source_rgb=str(root/(name+'--mjwarp.jpg')),calibration=str(cal_path),
            source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            motion_LK='original measurements preserved; no new motion/render')
        (a.output/(name+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    meta=json.loads((root/'meta.json').read_text());meta.update(perception_profile='rendered_v1',calibration=str(cal_path),fitting_and_evaluation='same88 DEV; no independent holdout')
    (a.output/'meta.json').write_text(json.dumps(meta,indent=2)+'\n');(a.output/'index.json').write_text(json.dumps(names))
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in a.output.iterdir() if p.is_file()}
    (a.output/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n')
    gate=analyze(a.output);gate['original_rgb_raw']=str(root);gate['calibration']=str(cal_path)
    (a.output/'gate.json').write_text(json.dumps(gate,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(admitted=gate['admitted'],checks=gate['checks'],colour_equal_n=gate['colour_equal_n'])),flush=True)


if __name__=='__main__':main()
