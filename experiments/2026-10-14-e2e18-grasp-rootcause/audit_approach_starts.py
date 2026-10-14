"""Static start LOS admission: PLAN OUTPUT SAVED_GATE_ROOT. No dynamics/rendering."""
import hashlib,json,math,pathlib,sys,time
import mujoco,numpy as np
from types import SimpleNamespace
from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
from scripts.audit_grasp_act_visibility import BandVisibility
from sim.grasp_act_scene import make_scene
from sim.masterpi_camera_review_v3 import POSITION_M,QUAT_WXYZ
from scripts.zone_teacher import FOLDED
ROOT=pathlib.Path(__file__).resolve().parents[2]
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_forwardSkip','mj_inverse','Renderer'):
 def blocked(*a,_name=name,**kw):raise AssertionError('forbidden API '+_name)
 setattr(mujoco,name,blocked)

def check(plan,templates):
 out=[];sources=[];at=time.monotonic()
 for ep in plan['episodes']:
  raw=pathlib.Path(templates[ep['scenario_id']]);xml=(raw/'scene.xml').read_bytes()
  original=json.loads((raw/'plan.json').read_text())
  assert original['scenario_source_sha256']==ep['scenario_source_sha256'] and original['map_id']==ep['map_id']
  text=xml.decode().replace('/home/ugrp/ugrp-sim/src/23a2a1137e3907073001ce079dd3294419fb5b1b/',str(ROOT)+'/')
  model=mujoco.MjModel.from_xml_string(text);data=mujoco.MjData(model)
  vis=BandVisibility(model);scene=make_scene(ep)
  sources.append({'seed':ep['seed'],'template':str(raw/'scene.xml'),'sha256':hashlib.sha256(xml).hexdigest()})
  for cid in vis.cameras.values():model.cam_pos[cid]=POSITION_M;model.cam_quat[cid]=QUAT_WXYZ
  def place(joint,xyz,yaw=0.):
   q=model.jnt_qposadr[model.joint(joint).id];data.qpos[q:q+7]=[*xyz,math.cos(yaw/2),0.,0.,math.sin(yaw/2)]
  for rid,p in ep['spawns'].items():place(rid+'__base_free',p[:3],p[3])
  for o in scene.config['setup_only']['objects'].values():place(o['joint_name'],o['position_m'])
  for cargo in scene.cargo:
   p=cargo.pose
   if cargo.item_id=='beam_1':p=ep['beam_pose']
   place('cargo_'+cargo.item_id+'_free',[*p[:2],.0005],p[2])
  def pose(rid,pwm):
   # Pure SDK actuator mapping; no controller/world initialization.
   dummy=SimpleNamespace(physical_params={'servo6_center_pwm':1500})
   vals=MasterPiDynamicsV2.pulse_to_joint_targets(dummy,pwm)
   names={'yaw':'arm_yaw','shoulder':'shoulder','elbow':'elbow','wrist':'wrist_pitch'}
   for key,v in vals.items():
    joints=['left_gripper_close','right_gripper_close'] if key=='gripper' else [names[key]]
    for name in joints:
     jid=model.joint(rid+'__'+name).id;lo,hi=model.jnt_range[jid]
     data.qpos[model.jnt_qposadr[jid]]=max(lo,min(hi,v)) if model.jnt_limited[jid] else v
  for rid in ep['spawns']:pose(rid,{**FOLDED,6:ep['initial_pan'].get(rid,1500)})
  initial=data.qpos.copy();row={'seed':ep['seed'],'robots':{}}
  for rid,end in ep['roles'].items():
   best={'visible_probes':0};data.qpos[:]=initial
   # Match the previous 23a2a113 full-ray start admission: three pitches,
   # all 360 body headings, fixed XY and unchanged original camera/objects.
   for wrist,elbow in ((500,2500),(700,2440),(820,2320)):
    pose(rid,{**FOLDED,3:wrist,4:elbow,6:1500})
    for deg in range(360):
     place(rid+'__base_free',ep['spawns'][rid][:3],math.radians(deg))
     mujoco.mj_kinematics(model,data);mujoco.mj_camlight(model,data)
     v=vis.measure(data,rid,end)
     if v['visible_probes']>best['visible_probes']:best={**v,'yaw_deg':deg,'wrist':wrist,'elbow':elbow}
   row['robots'][rid]=best
  row['both_qualify']=all(x['visible_probes']>=5 for x in row['robots'].values());out.append(row)
  print(ep['seed'],row['both_qualify'],[x['visible_probes'] for x in row['robots'].values()],flush=True)
 return {'schema':'ugrp.grasp_goal_set.start_los.v1','scope':'Static initial geometry/kinematics and first-hit rays only; no physics stepping, forward dynamics, rendering, World or controller initialization. Same 3 pitches x 360 headings admission as 23a2a113; initial heading need not see target before search.', 'N':len(out),'both_qualify_n':sum(x['both_qualify'] for x in out),'minimum_visible_probes':min(x['visible_probes'] for r in out for x in r['robots'].values()),'forbidden_api_call_n':0,'rows':out,'templates':sources,'wall_s':time.monotonic()-at,'plan_sha256':hashlib.sha256(json.dumps(plan,indent=2).encode()+b'\n').hexdigest()}
if __name__=='__main__':
 plan=json.loads(pathlib.Path(sys.argv[1]).read_text());templates={}
 for p in sorted(pathlib.Path(sys.argv[3]).glob('cohort-*/episode-*/raw/plan.json')):
  old=json.loads(p.read_text())
  if (p.parent/'scene.xml').exists():templates.setdefault(old['scenario_id'],str(p.parent))
 result=check(plan,templates);pathlib.Path(sys.argv[2]).write_text(json.dumps(result,indent=2)+'\n')
 if result['both_qualify_n']!=result['N']:sys.exit(1)
