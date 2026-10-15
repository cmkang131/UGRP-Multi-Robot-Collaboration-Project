"""Saved-own-RGB audit of existing goal/obstacle/peer extraction and B gates."""
import argparse,platform
from pathlib import Path
from collections import defaultdict
import cv2,numpy as np
from scripts.summarize_scene_tex3 import read,write,sha
from scripts.probe_scene_tex2 import pose_pwm_mode
from scripts.score_scene_tex5 import BASE,ENC

def counts(image,pwm):
    from harness import visual_navigation as nav
    from harness.floor_goal import detect_floor
    from harness.e2e_rgb_gate import boundary,MARKER_OPTION_V2
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV);pixels=image.shape[0]*image.shape[1]
    result={f'visual_goal_{z}':len(nav._components(nav._mask(hsv,limits),max(180.,pixels*.001))) for z,limits in nav._GOAL_HSV.items()}
    result['visual_orange_obstacles']=len(nav._components(nav._mask(hsv,nav._ORANGE_HSV),max(100.,pixels*.0005)))
    result['visual_magenta_peers']=len(nav._components(nav._mask(hsv,nav._MAGENTA_HSV),max(70.,pixels*.0003)))
    rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
    try:
        patches,_,_=detect_floor(rgb,servo=pwm,profile='camera_v3');result['floor_goal_B_patches']=len(patches)
    except ValueError as exc:
        if str(exc)!='loaded_or_unknown_load_not_qualified':raise
        result['floor_goal_B_patches']=None;result['floor_goal_qualification']=str(exc)
    for option in ('off',MARKER_OPTION_V2):
        diagnostics={}
        try:
            boundary(rgb,pwm,np.zeros(3),diagnostics=diagnostics,marker_detect=option)
            result['B_quad_'+option]=diagnostics['accepted_candidates']
        except ValueError as exc:
            if str(exc)!='loaded_or_unknown_load_not_qualified':raise
            result['B_quad_'+option]=None;result['B_quad_qualification']=str(exc)
    return result

def main(inputs,out):
    from harness.zone_pair_highpose import HIGH
    from scripts.zone_teacher import FOLDED
    cv2.setNumThreads(1);out.mkdir(parents=True,exist_ok=False);groups=defaultdict(list);sources=[]
    for root in inputs:
        hashes=read(root/'SHA256SUMS.json')
        assert all(sha(root/f)==h for f,h in hashes.items())
        sources.append({'root':str(root),'verified_files':len(hashes),'summary_sha256':sha(root/'summary.json')})
        for idx in read(root/'index.json'):
            r=read(root/idx['record']);pwm=FOLDED if pose_pwm_mode(r['pose'])=='FOLDED' else {**HIGH,1:1500}
            item={'case':r['case'],'counts':{}}
            for e in ENC:item['counts'][e]=counts(cv2.imread(str(root/r['encodings'][e]['file'])),pwm)
            groups[(r['material'],r['quality'])].append(item)
        print('done',root,flush=True)
    reference={r['case']:r for r in groups[BASE]};reports=[]
    for key,rr in groups.items():
        assert len(rr)==88
        result={'material':key[0],'quality':key[1],'equal':{},'changes':{}}
        for e in ENC:
            changes=[{'case':r['case'],'v1':reference[r['case']]['counts'][e],'candidate':r['counts'][e]} for r in rr if r['counts'][e]!=reference[r['case']]['counts'][e]]
            result['equal'][e]=88-len(changes);result['changes'][e]=changes
        result['pass']=all(v==88 for v in result['equal'].values());reports.append(result)
        write(out/('--'.join(key)+'-cases.json'),rr)
    write(out/'summary.json',{'reports':reports,'sources':sources,'script_sha256':sha(Path(__file__)),
        'scope':'actual existing visual goal A/B/C, orange obstacle, magenta peer component counts, floor_goal B patches and B complete-quad/white-island gates; numeric ranges unchanged; own RGB and own commanded camera only',
        'other_scopes':'box/legacy dark beam already in main audit; teal/blue and archived colour rules are pixel-range support only; top camera not used'})
    write(out/'rejection-table.json',{'arms':[{'material':r['material'],'quality':r['quality'],'input_n':88,'cumulative_pass_n':min(r['equal'].values()),'rejected_n':88-min(r['equal'].values()),'category':'EXISTING_COLOUR_SEMANTIC_COUNTS','blocking_object':'wall/floor appearance','minimum_gap_m':None,'reason':'existing detector component/accepted-geometry count comparison','equal':r['equal']} for r in reports],'sources':sources,'reproduction':list(map(str,inputs))})
    write(out/'SHA256SUMS.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not platform.node().startswith('ugrp-sim-gcp2'):p.error('gcp2 only')
    main(a.inputs,a.output)
