"""Saved RGB/issued-command replay only. Eval is read after visual decisions."""
import argparse
import base64
import hashlib
import json
import runpy
from pathlib import Path
import cv2
import numpy as np
from harness.zone_solo_cyan_inhand import Evidence, VIEWS
from harness.zone_solo_cyan_scene_change import cyan
from harness.zone_solo_cyan_vision_v106 import CyanVision
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_solo_cyan_contract_v106 import CALIBRATION
from harness.zone_pair_highpose_contract import camera_record
from harness.zone_color_boxes import BOX_HALF_M


def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def audit(raw):
    record=read(raw/'student_record.json');frames=rows(raw/'robots/r3/frames.jsonl')
    lift=next(e['t'] for e in record['events'] if e['event']=='state' and e['state']=='lift')
    stop=next(e['t'] for e in record['events'] if e['event']=='cyan_scene_grasp_check')
    evidence=Evidence();all_areas=[]
    for f in frames:
        if not lift<=f['sim_time']<=stop:continue
        p=raw/f['path'];assert sha(p)==f['sha256']
        servo={int(k):v for k,v in f['commanded_servo'].items()}
        obs={k:f[k] for k in ('robot_id','camera','sim_time','frame_id','sha256')}
        obs['image']=base64.b64encode(p.read_bytes()).decode()
        evidence.add(obs,servo,f['sim_time'],'r3')
        all_areas.append(int(cyan(cv2.imread(str(p))).sum()))
    visual=evidence.result()
    ref=next(e['t'] for e in record['events'] if e['event']=='cyan_scene_reference_unavailable')
    f=min(frames,key=lambda x:abs(x['sim_time']-ref));p=raw/f['path']
    obs={**f,'image':base64.b64encode(p.read_bytes()).decode()}
    servo={int(k):v for k,v in f['commanded_servo'].items()}
    cal=camera_calibration(read(Path(CALIBRATION)));fit=CyanVision(cal).detect(obs,servo)[0]
    geom=runpy.run_path(str(Path(__file__).with_name('analyze_hover_projection.py')))
    # Hypothetical floor target from own RGB, static dimensions, command retreat.
    # No scene occlusion, measured motion or counterfactual post-pick RGB exists.
    center=fit['estimated_box_center_base_m']
    projections=[]
    for back in (0.,.05):
        tr=dict(robot_yaw_rad=0.,robot_xyz_m=[-back,0.,0.],cyan_xyz_m=center,
            cyan_rotation=np.eye(3).ravel().tolist(),box_half_m=list(BOX_HALF_M))
        q=geom['project'](tr,camera_record(cal,'unloaded',servo))
        projections.append(dict(commanded_retreat_m=back,**q))
    # Only this separate report section reads physical outcomes; never evidence.
    ev=read(raw/'result.json')['evaluation']
    return dict(raw=str(raw),seed=read(raw/'bundle.json')['task']['seed'],
        visual=visual,all_lift_frames=dict(count=len(all_areas),min_px=min(all_areas),
            max_px=max(all_areas),median_px=float(np.median(all_areas))),
        servo_feedback=dict(decision='unavailable',position_samples=0,current_samples=0,
            close_command_pwm=1500,reason='recorded pulses are issued commands, not measurements'),
        active_reobserve=dict(decision='unknown_unobserved_counterfactual',projections=projections,
            reason='no post-pick retreat/repeat-view RGB; lens-only geometry cannot prove floor visibility behind hand/load'),
        original_site=dict(status='unknown',samples=0),
        evaluation_only={k:ev.get(k) for k in ('lifted','inside','success')},
        source_sha256={n:sha(raw/n) for n in ('result.json','student_record.json','robots/r3/frames.jsonl')})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=dict(scope='exploratory saved replay; not fresh evidence or physical validation',runs=[audit(r) for r in a.raw])
    with a.output.open('x') as f:json.dump(out,f,indent=2);f.write('\n')
    print(json.dumps([dict(seed=r['seed'],status=r['visual']['status'],hits=r['visual']['hits'],iou=r['visual']['mask_iou'],shift=r['visual']['centroid_shift_px'],all_lift=r['all_lift_frames'],retreat=[dict(m=x['commanded_retreat_m'],pixels=x['valid_ray_pixels'],bbox=x['valid_bbox_xyxy']) for x in r['active_reobserve']['projections']]) for r in out['runs']],indent=2))
