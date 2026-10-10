"""Post-run evaluation only; no imports from physics or control constructors."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scripts.evaluate_s3_no_prior import metrics


def read(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def evaluate(out):
    result = metrics(out)
    student = read(out/'student_record.json')
    fixture = read(Path('tests/fixtures/s3_camera/s2-v141-first-camera.json'))['first']
    cameras = {}; localization = {}
    for rid in ('r1','r2','r3'):
        cam = lines(out/f'eval_only/{rid}/render_camera.jsonl')
        frames = lines(out/f'robots/{rid}/frames.jsonl')
        cameras[rid] = dict(rendered=len(cam),own_frames=len(frames),
            first=cam[0] if cam else None,
            first_own_frame={k:frames[0][k] for k in ('sim_time','frame_id','sha256','path')} if frames else None,
            all_mounts_equal_s2=bool(cam) and all(
                q['local_position_m']==fixture['camera_local_position_m'] and
                q['local_quat_wxyz']==fixture['camera_local_quaternion'] for q in cam),
            frame_time_matches=len(cam)==len(frames) and all(abs(q['t']-f['sim_time'])<1e-8 for q,f in zip(cam,frames)))
        truth=lines(out/f'eval_only/{rid}/trajectory.jsonl'); t=[q['t'] for q in truth]
        xy=np.array([q['robot_xyz_m'][:2] for q in truth]); yaw=np.unwrap([q['robot_yaw_rad'] for q in truth])
        rows=[]
        for p in student['localizers'][rid]['poses']:
            at=p['t_est']; pos=[np.interp(at,t,xy[:,i]) for i in (0,1)]
            angle=float(np.interp(at,t,yaw)); e=math.dist([p['x'],p['y']],pos)
            ey=abs(math.degrees(math.atan2(math.sin(p['yaw']-angle),math.cos(p['yaw']-angle))))
            sigma=p['std_xy_m']<=.05; sigma_yaw=p.get('std_yaw_rad',math.inf)<=math.radians(5)
            certificate=p.get('convergence_certificate',{})
            rows.append(dict(t=p['t'],t_est=at,xy_error_m=e,yaw_error_deg=ey,std_xy_m=p['std_xy_m'],
                std_yaw_rad=p.get('std_yaw_rad'),sigma_xy_pass=sigma,sigma_yaw_pass=sigma_yaw,
                accurate=e<=.25 and ey<=15,certificate=certificate))
        localization[rid]=dict(last=rows[-1] if rows else None,
            first_xy_sigma=next((q for q in rows if q['sigma_xy_pass']),None),
            first_accurate_xy_sigma=next((q for q in rows if q['sigma_xy_pass'] and q['accurate']),None),
            first_certificate=next((q for q in rows if q['certificate'].get('qualified')),None),
            sigma_pass_frames=sum(q['sigma_xy_pass'] for q in rows),
            certificate_pass_frames=sum(bool(q['certificate'].get('qualified')) for q in rows),
            accuracy_only_frames=sum(q['accurate'] for q in rows),frame_count=len(rows))
    return dict(schema='ugrp.s3next.posthoc.v1',source=read(out/'bundle.json')['source_sha'],
        evaluation=result,camera_contract=cameras,localization=localization,
        gt_use='post-run eval_only; never control',thresholds_changed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists(): raise FileExistsError(a.output)
    value=evaluate(a.raw)
    a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(value,ensure_ascii=False,allow_nan=False))
