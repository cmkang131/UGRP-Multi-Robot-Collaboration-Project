"""Static-only frozen-source inventory. Does not import a simulator."""
import ast,hashlib,json,subprocess
from pathlib import Path
TEACHER='6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'
STUDENT='686cccb6e31342a9edfadb30a8047ad57ceb9291'
paths={TEACHER:['scripts/run_solo_grasp_act_teacher.py','scripts/audit_grasp_act_visibility.py','sim/grasp_act_solo_teacher.py','sim/grasp_act_solo_evaluation.py','sim/grasp_act_solo_lookaround.py','sim/grasp_act_solo_lookback.py','sim/grasp_act_port.py','sim/camera_robot_port.py','sim/s2_realism_camera_binding.py','sim/masterpi_camera_profile.py','harness/grasp_act_solo_recording.py'],STUDENT:['scripts/run_grasp_act_student.py','scripts/grasp_act_student_worker.py','harness/grasp_act_rollout.py','harness/grasp_act_input.py','harness/grasp_act_policy.py','scripts/train_grasp_act.py']}
fields={'qpos','qvel','qacc','ctrl','xpos','xmat','geom_xpos','geom_xmat','cam_xpos','cam_xmat','contact','ncon','eq_active','time'}
files=[]
for sha,names in paths.items():
 for path in names:
  source=subprocess.check_output(['git','show',f'{sha}:{path}'],text=True);lines=source.splitlines();rows=[];calls=[]
  class Scan(ast.NodeVisitor):
   stack=[]
   def visit_FunctionDef(self,node):
    self.stack.append(node.name);self.generic_visit(node);self.stack.pop()
   def visit_Call(self,node):
    name=ast.unparse(node.func)
    if name.split('.')[-1] in {'base_xyz','base_rpy','mj_contactForce','mj_ray','_physics_step_for','capture','render_jpeg','render_team_jpeg','mj_kinematics','mj_forward'}:
     calls.append({'line':node.lineno,'function':'.'.join(self.stack),'call':name,'statement':lines[node.lineno-1].strip()})
    self.generic_visit(node)
   def visit_Attribute(self,node):
    if node.attr in fields:
     expr=ast.unparse(node)
     if node.attr in {'xpos','xmat'} or 'data' in expr or expr.startswith(('d.','mjd.')):
      rows.append({'line':node.lineno,'function':'.'.join(self.stack),'field':node.attr,'expression':expr,'statement':lines[node.lineno-1].strip()})
    self.generic_visit(node)
  Scan().visit(ast.parse(source))
  files.append({'sha':sha,'file':path,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'direct_state_candidates':sorted(rows,key=lambda r:r['line']),'indirect_state_or_camera_calls':sorted(calls,key=lambda r:r['line'])})
out=Path(__file__).with_name('mjdata-read-inventory.json')
out.write_text(json.dumps({'scope':'static direct-state candidates including indexed setup writes; manually classified by design.md; absence is not a whole-program noninterference proof','frozen_teacher':TEACHER,'act15_student':STUDENT,'camera_port_same_blob_as_backend_base':'63a44a8faf0d0a62bdbc55648a347d7160c77c04','files':files},indent=2)+'\n')
