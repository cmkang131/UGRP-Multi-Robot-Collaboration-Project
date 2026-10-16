"""Read-only saved-RGB ABI equality for the shared selfmap modules() hook."""
import argparse,ast,hashlib,json,os,platform
from pathlib import Path
import cv2,numpy as np
from scripts.summarize_scene_tex3 import read,write,sha
from scripts.zone_teacher import FOLDED
from harness.scene_colour_boundary import ColourBoundaryState,detect,OPTION
from harness.active_wall_vision import modules

def main(raw,analysis,output):
    rows=[read(raw/i['record']) for i in read(raw/'index.json')]
    rows=[r for r in rows if r['pose'] in ('drive','paint_B') and r['view']==0 and r['robot']=='r1']
    assert len(rows)==8
    profile=rows[0]['material'];calpath=analysis/(profile+'-calibration.json');cal=read(calpath)
    # Capture the exact default module object before selecting the new facade.
    os.environ.pop('UGRP_SCENE_COLOUR_BOUNDARY',None);modules.cache_clear();mp,original,_=modules()
    state=ColourBoundaryState(profile,cal)
    os.environ.update(UGRP_SCENE_COLOUR_BOUNDARY=OPTION,UGRP_SCENE_RENDER_PROFILE=profile,
        UGRP_SCENE_COLOUR_CALIBRATION=str(calpath),UGRP_SCENE_COLOUR_CALIBRATION_SHA256=sha(calpath))
    modules.cache_clear();mp,backend,_=modules()
    assert backend is not original and backend.link_segments is original.link_segments
    from harness.active_camera import transform
    origin,rotation=transform(FOLDED)
    cm=mp.ColumnModel(tuple(sorted(FOLDED.items())),0.,mp.column_positions(96,2),camera_transform=(origin,rotation))
    params=dict(floor_patch_max_m=.81,run_step_window=3,top_edge_px=4);checks=[]
    for r in rows:
        for e,entry in r['encodings'].items():
            bgr=cv2.imread(str(raw/entry['file']));assert sha(raw/entry['file'])==entry['sha256']
            und=mp.undistort(bgr)
            a=detect(original,und,cm,params=params,loaded=False,state=state)
            b=backend.detect(und,cm,params=params,loaded=False)
            same=all(np.array_equal(a[k],b[k],equal_nan=True) for k in a)
            checks.append({'case':r['case'],'encoding':e,'same':same})
            assert same
    output.mkdir(parents=True,exist_ok=False)
    write(output/'summary.json',{'status':'PASS','checked_encoded_frames':len(checks),'checks':checks,
        'source_script_sha256':sha(Path(__file__)),'boundary_source_sha256':sha(Path('harness/scene_colour_boundary.py')),
        'shared_frontend_sha256':sha(Path('harness/active_wall_vision.py')),'calibration_sha256':sha(calpath),
        'scope':'8 same saved poses x3; shared modules()->hfw.detect facade exactly equals R3 explicit boundary function; no renderer, physics, new candidate or fourth round',
        'downstream':'ColumnModel96/strip2, original link_segments, scan keys/shape unchanged; source facade instance-local; default-off equivalence covered by frozen RGB unit tests'})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,required=True);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):p.error('gcp2 only')
    main(a.raw,a.analysis,a.output)
