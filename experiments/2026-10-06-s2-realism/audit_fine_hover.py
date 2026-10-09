"""Post-run pulse/hover audit from immutable saved images and eval trajectories."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import cv2
import numpy as np
from harness import zone_color_boxes as colors


def read(p):
    return json.loads(p.read_text())


def lines(p):
    return [json.loads(x) for x in p.read_text().splitlines()]


def audit(raw):
    record=read(raw/'student_record.json');result=read(raw/'result.json')
    trace=lines(raw/'eval_only/trajectory.jsonl');frames=lines(raw/'robots/r3/frames.jsonl')
    nearest=lambda rows,key,t:min(rows,key=lambda x:abs(x[key]-t))
    hover=next(e['t'] for e in record['events'] if e['event']=='state' and e['state']=='hover')
    checks=[e for e in record['events'] if e['event']=='cyan_hover_check']
    pulses=record['alignment_pulse']['transformations'];measured=[]
    for i,u in enumerate(pulses):
        end=pulses[i+1]['t'] if i+1<len(pulses) else hover
        a=nearest(trace,'t',u['t']);b=nearest(trace,'t',end)
        dx,dy=np.array(b['robot_xyz_m'][:2])-a['robot_xyz_m'][:2];yaw=a['robot_yaw_rad']
        measured.append(dict(t=u['t'],end_t=end,issued=u['issued'],
            axis=next(k for k in ('forward','left','turn') if u['issued'][k]),
            body_delta_m=[math.cos(yaw)*dx+math.sin(yaw)*dy,-math.sin(yaw)*dx+math.cos(yaw)*dy],
            yaw_delta_deg=math.degrees(b['robot_yaw_rad']-yaw)))
    summary={}
    for axis in ('forward','left','turn'):
        values=[float(np.linalg.norm(x['body_delta_m'])) for x in measured if x['axis']==axis]
        if values:summary[axis]=dict(n=len(values),median_xy_m=float(np.median(values)),max_xy_m=max(values))
    images=[]
    for t in (hover,checks[0]['t'],checks[-1]['t']):
        f=nearest(frames,'sim_time',t);tr=nearest(trace,'t',t);p=raw/f['path']
        assert hashlib.sha256(p.read_bytes()).hexdigest()==f['sha256']
        image=cv2.imread(str(p));mask=colors._mask(cv2.cvtColor(image,cv2.COLOR_BGR2HSV),colors.OWN_ZONE_CYAN_HSV)
        ys,xs=np.nonzero(mask);dx,dy=np.array(tr['cyan_xyz_m'][:2])-tr['robot_xyz_m'][:2];yaw=tr['robot_yaw_rad']
        center=[math.cos(yaw)*dx+math.sin(yaw)*dy,-math.sin(yaw)*dx+math.cos(yaw)*dy]
        images.append(dict(t=t,frame=str(p),sha256=f['sha256'],area_px=len(xs),
            bbox_xyxy=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if len(xs) else None,
            eval_center_base_xy_m=center,commanded_servo=f['commanded_servo']))
    return dict(raw=str(raw),seed=read(raw/'bundle.json')['task']['seed'],source_sha=result['source_sha'],
        failure=result['failure'],alignment_entered_hover_s=hover,pulse_summary=summary,pulses=measured,
        hover_frames=images,checks=checks,scene_reference=[e for e in record['events'] if 'scene_reference' in e['event']],
        source_sha256={n:hashlib.sha256((raw/n).read_bytes()).hexdigest() for n in
            ('result.json','student_record.json','eval_only/trajectory.jsonl','robots/r3/frames.jsonl')},
        scope='offline eval scoring; no control feedback, no wrist/physics counterfactual, no retuning')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw',type=Path,action='append',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=[audit(raw) for raw in a.raw]
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps([dict(seed=r['seed'],failure=r['failure'],pulses=sum(v['n'] for v in r['pulse_summary'].values()),
        hover_s=r['alignment_entered_hover_s'],areas=[f['area_px'] for f in r['hover_frames']]) for r in result]))
