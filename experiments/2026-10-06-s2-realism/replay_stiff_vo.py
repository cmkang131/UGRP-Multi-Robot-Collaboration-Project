"""Stiffness-on PR405 own-RGB finite pulse VO replay; no evaluation inputs."""
import argparse,copy,hashlib,json,subprocess
from pathlib import Path
import cv2
from harness import zone_solo_cyan_contract_v106 as c
from harness.zone_solo_cyan_augmented_start import Runtime as Previous
from harness.s2_stiff_camera_calibration import runtime_class
from harness.zone_solo_cyan_ground_vo import observed_pulse
from harness.zone_solo_cyan_pulse_cal import profile_key
ROOT=Path(__file__).resolve().parents[2];E=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise ValueError('new output required')
 criteria=json.loads((E/'ground-vo-criteria.json').read_text());b=json.loads((Path(criteria['legacy_raw'])/'bundle.json').read_text())
 omit=('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')
 kw={k:v for k,v in b['options'].items() if k not in omit}
 kw.update(motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],extrinsic_calibration=b['extrinsic_calibration'],floor_appearance=b['floor_appearance'],camera_pitch='stiff_target_v1',servo_stiffness='real_v1',stiff_camera_table=json.loads((ROOT/'configs/calibration/s2_camera_stiff_target_v1.json').read_text()))
 r=runtime_class(Previous)(c.hp.resolve(c.MAP_ID)[0],ROOT/c.CALIBRATION,c.CALIBRATION_SHA,seed=1052,**kw)
 pf=r.pose.provider.loc._pf;allrows=[];sources={}
 try:
  for case in ('stiff-north','stiff-south'):
   raw=Path('/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1')/case
   plant=json.loads((raw/'bundle.json').read_text());assert plant['options']['servo_stiffness']=='real_v1'
   read=lambda name:[json.loads(l) for l in (raw/name).read_text().splitlines()]
   frames=read('robots/r3/frames.jsonl');commands=read('robots/r3/commands.jsonl')
   def image(f):
    path=raw/f['path'];data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256']
    return cv2.cvtColor(cv2.imread(str(path)),cv2.COLOR_BGR2RGB)
   for cmd in commands:
    if cmd['kind']!='mecanum':continue
    key=profile_key(cmd,False);profile=copy.deepcopy(b['pulse_calibration']['profiles'][key]);start=cmd['t'];end=start+profile['times'][-1]
    before=min(frames,key=lambda f:abs(f['sim_time']-start));assert abs(before['sim_time']-start)<1e-7
    pose={int(k):v for k,v in before['commanded_servo'].items()};cm=pf.column_model_for(pose)
    selected=[f for f in frames if start+1e-8<f['sim_time']<=end+.15]
    item=dict(profile=profile,t=start,key=key,before=(start,image(before)),cm=cm,pose=pose,command=cmd)
    _,row=observed_pulse(item,[(f['sim_time'],image(f)) for f in selected],b['floor_appearance'],.3)
    row.update(case=case,raw=str(raw),sampled_end=any(abs(f['sim_time']-end)<1e-7 for f in frames),plant='real_v1',frame_dt_s=.1)
    allrows.append(row)
   for name in ('bundle.json','robots/r3/frames.jsonl','robots/r3/commands.jsonl'):sources[str(raw/name)]=hashlib.sha256((raw/name).read_bytes()).hexdigest()
 finally:r.close()
 a.output.write_text(json.dumps(dict(schema='ugrp.s2.stiff_vo.replay.v1',rows=allrows,sources=sources,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),gt_inputs=False,camera_pitch='stiff_target_v1',pitch_scale_bound_deg=.3,scope='PR405 on-plant unloaded SEARCH only; not S2 carry',physics_runs=0),indent=2)+'\n')
 print(json.dumps(dict(pulses=len(allrows),measured=sum(r['prediction_replaced'] for r in allrows),missing_exact_end=sum(not r['sampled_end'] for r in allrows))))
if __name__=='__main__':main()
