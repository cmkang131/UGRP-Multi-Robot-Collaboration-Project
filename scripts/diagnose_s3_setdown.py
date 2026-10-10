"""Evaluation-only saved-qpos forward kinematics; no dynamics/render/control."""
import argparse,hashlib,json,math,platform
from pathlib import Path

def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
def read(p):return json.loads(p.read_text())
def diagnose(raw):
 import mujoco,numpy as np
 manifest=read(raw/'artifacts.sha256.json');files=['scene.xml','student_record.json','stage-states.json','eval_only/r1/render_camera.jsonl','eval_only/contacts.jsonl','eval_only/cooperative-dynamics.jsonl']+[f'robots/{r}/commands.jsonl' for r in ('r1','r2')]
 for f in files:assert hashlib.sha256((raw/f).read_bytes()).hexdigest()==manifest[f]
 state=read(raw/'stage-states.json');start=next(x['t'] for x in state if all(x['robots'][r]['state']=='lower' for r in ('r1','r2')));cmd={r:rows(raw/f'robots/{r}/commands.jsonl') for r in ('r1','r2')}
 model=mujoco.MjModel.from_xml_path(str(raw/'scene.xml'));data=mujoco.MjData(model)
 geoms={r:[model.geom(r+'__'+s+'_finger').id for s in ('left','right')] for r in ('r1','r2')};beam=model.body('cargo_beam_1').id
 pos=[]
 for x in rows(raw/'eval_only/r1/render_camera.jsonl'):
  if x['t']<start:continue
  data.qpos[:]=x['joint_qpos'];mujoco.mj_forward(model,data)
  height={r:float(np.mean([data.geom_xpos[g,2] for g in geoms[r]])) for r in geoms}
  pos.append(dict(t=x['t'],finger_height_m=height,beam_com_z_m=float(data.xipos[beam,2]),beam_body_z_m=float(data.xpos[beam,2]),beam_tilt_deg=math.degrees(math.acos(float(np.clip(data.xmat[beam,8],-1,1))))))
 contacts=[x for x in rows(raw/'eval_only/contacts.jsonl') if x['t']>=start]
 floor=[x['t'] for x in contacts if any('cargo_beam_1' in c['geom1']+c['geom2'] and any(n in c['geom1']+c['geom2'] for n in ('floor','ground','terrain')) for c in x['contacts'])]
 record=read(raw/'student_record.json')
 def find(x):
  if isinstance(x,dict):
   if x.get('event')=='coarse_fine_grasp_target':yield x
   else:
    for v in x.values():yield from find(v)
  elif isinstance(x,list):
   for v in x:yield from find(v)
 targets={x['robot_id']:x['path'][-1] for x in find(record)};final=state[-1]['robots']
 robots={}
 for r in geoms:
  speed=[(b['finger_height_m'][r]-a['finger_height_m'][r])/(b['t']-a['t']) for a,b in zip(pos,pos[1:])]
  open_cmd=next((x['t'] for x in cmd[r] if x['t']>=start and x.get('servo_id')==1 and x.get('pulse',0)>1500),None)
  target=targets[r];issued=final[r]['servo'];diff={k:[issued.get(k),v] for k,v in target.items() if k!='1' and issued.get(k)!=v}
  robots[r]=dict(height_start_m=pos[0]['finger_height_m'][r],height_end_m=pos[-1]['finger_height_m'][r],max_down_speed_m_s=max(-v for v in speed),first_open_change=open_cmd,grasp_target=target,last_issued=issued,floor_target_mismatch=diff)
 lc=contacts[-1];names={c[k] for c in lc['contacts'] if 'cargo_beam_1' in c['geom1']+c['geom2'] for k in ('geom1','geom2')}
 return dict(name=raw.parent.name,source_sha=read(raw/'bundle.json')['source_sha'],lower_start=start,lower_end=pos[-1]['t'],max_pair_finger_height_delta_m=max(abs(x['finger_height_m']['r1']-x['finger_height_m']['r2']) for x in pos),max_pair_velocity_delta_m_s=max(abs(((b['finger_height_m']['r1']-a['finger_height_m']['r1'])-(b['finger_height_m']['r2']-a['finger_height_m']['r2']))/(b['t']-a['t'])) for a,b in zip(pos,pos[1:])),max_beam_tilt_deg=max(x['beam_tilt_deg'] for x in pos),last_pose=pos[-1],first_floor_contact=min(floor,default=None),last_both_finger_contacts={r:all(r+'__'+s+'_finger' in names for s in ('left','right')) for r in geoms},robots=robots,source_files={f:manifest[f] for f in files},eval_only=True,physics_steps=0)

def main():
 p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('x86 diagnosis only')
 runs=[diagnose(a.cohort/f's3fix17-pair-c{n}-r2/raw') for n in range(6)];a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(dict(host='oracle-x86',physics_steps=0,runs=runs),indent=2,allow_nan=False)+'\n')
 for r in runs:print(json.dumps({k:r[k] for k in ('name','max_pair_finger_height_delta_m','max_pair_velocity_delta_m_s','max_beam_tilt_deg','first_floor_contact','last_both_finger_contacts','robots')}))
if __name__=='__main__':main()
