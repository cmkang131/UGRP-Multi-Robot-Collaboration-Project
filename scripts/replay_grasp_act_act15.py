"""Exact ACT14 command replay with a visible-only, non-executing expert.

The expert is the original SoloTeacher plus ACT11 command search. Its issued
PWM/history are synchronized to the replayed STUDENT commands after each query.
Labels after its first hover transition are marked invalid: its timed arm
sequence cannot certify that an off-policy student executed that sequence.
No expert action, phase, pose, contact, or score enters student execution.
"""
import argparse
import base64
from copy import deepcopy
import json
import math
from pathlib import Path

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_rows, sha256, write_json
from scripts.diagnose_grasp_act_act15 import command_errors


def existing(path):
    return path if path.exists() else path.with_suffix(path.suffix+'.zst')


class ShadowTeacher:
    def __init__(self, world, port, obj, initial, scene, *, plan, output, original):
        import numpy as np
        from scripts.audit_grasp_act_visibility import BandVisibility
        from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D
        from sim.grasp_act_solo_teacher import InputAudit, primitives
        from sim import grasp_act_solo_teacher as teacher_module
        from scripts.zone_teacher import plan_path, proportional_drive
        self.world, self.port, self.obj, self.plan = world, port, obj, plan
        self.output, self.original = output, original
        self.bodies = {x.item_id:x.body for x in scene.cargo}
        self.bodies.update({i:x['body_name'] for i,x in scene.config['setup_only']['objects'].items()})
        self.audit = InputAudit(); self.valid = True; self.first = None; self.n = 0
        self.labels = (output/'shadow-labels.jsonl').open('x')
        class ObjectEyes(BandVisibility):
            def __init__(eyes):
                eyes.np, eyes.model = np, world.model
                eyes.K, eyes.D = scaled_camera_matrix(640,480), np.array(CAMERA_FISHEYE_D)
                eyes.groups = np.array([1,1,1,1,0,0], dtype=np.uint8)
                eyes.near = float(world.model.vis.map.znear*world.model.stat.extent)
                eyes.cameras = {r:world.model.camera(r+'__robot_cam').id for r in ('r1','r2','r3')}
                eyes.body_gids = {}
        self.eyes = ObjectEyes()
        body = world.model.body(obj['body_name']).id
        self.gids = [g for g in range(world.model.ngeom) if world.model.geom_bodyid[g] == body and world.model.geom_contype[g]]
        self.body = body
        self.discs, self.rects = [], []
        def route(goal,context):
            path=plan_path((0.,0.),goal[:2],(-2.,2.,-2.,2.),self.discs,rects=self.rects,radius=.17)
            if not path:return 0.,0.,0.
            point=next((p for p in path if math.hypot(*p)>=.06),goal[:2])
            command=proportional_drive((0.,0.,0.),goal[:2],point,goal[2])
            return command['forward'],command['left'],command['turn']
        self.teacher = teacher_module.SoloTeacher(plan['object_kind'],plan['role'],{int(k):v for k,v in initial['pwm'].items()},
            profile='solo_visible_only_v1',held_object_hidden_v1=True,
            teacher_stability='align_relook_v1',reach_mode='pad_window_v2',ops=primitives(),route=route)

    def __call__(self, observation, jpeg, selected, done):
        import numpy as np
        world, teacher, rid = self.world, self.teacher, self.plan['robot_id']
        now = observation['t']; original = self.original[self.n] if self.original is not None else None
        if original is not None and ([r['sha256'] for r in observation['rgb']] != [r['sha256'] for r in original['rgb']]
                or observation['issued'] != original['issued']):
            raise ValueError('replay differs from original student inputs at '+str(self.n))
        n,N = self.eyes.region_visible(world.data,rid,self.gids) if self.valid else (0,0)
        def read_relative():
            b = world.data.body(self.obj['body_name']); rot=b.xmat.reshape(3,3)
            point=b.xpos+rot@np.array([0.,0.,teacher.spec.grip_z_m-.016])
            base=world.robot(rid).base_xyz();yaw=float(world.robot(rid).base_rpy()[2])
            dx,dy=point[0]-base[0],point[1]-base[1]
            return {'xyz':[float(math.cos(yaw)*dx+math.sin(yaw)*dy),float(-math.sin(yaw)*dx+math.cos(yaw)*dy),float(point[2])],
                'yaw':math.atan2(math.sin(math.atan2(rot[1,0],rot[0,0])-yaw),math.cos(math.atan2(rot[1,0],rot[0,0])-yaw))}
        measurement=self.audit.measure(teacher.phase,visible_n=n,probe_N=N,holding=teacher.holding,read_relative=read_relative)
        # The same visible obstacle refresh as the frozen teacher runner.
        if self.n%5==0 and self.valid:
            self.discs.clear(); self.rects.clear()
            base=world.robot(rid).base_xyz();yaw=float(world.robot(rid).base_rpy()[2]);co,si=math.cos(yaw),math.sin(yaw)
            for other in ('r1','r2','r3'):
                if other==rid:continue
                bid=world.model.body(other+'__robot').id
                n_,N_=self.eyes.region_visible(world.data,rid,self.eyes._body_geoms(bid))
                if N_ and n_>=math.ceil(N_/3):
                    xy=world.data.body(other+'__robot').xpos[:2]-base[:2]
                    self.discs.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],.17))
            for iid,name in self.bodies.items():
                if iid==self.plan['item_id']:continue
                bid=world.model.body(name).id
                gids=self.eyes._body_geoms(bid)
                n_,N_=self.eyes.region_visible(world.data,rid,gids)
                if N_ and n_>=math.ceil(N_/3):
                    xy=world.data.body(name).xpos[:2]-base[:2]
                    radius=max((float(np.linalg.norm(world.data.geom_xpos[g,:2]-world.data.body(name).xpos[:2]))+float(world.model.geom_rbound[g]) for g in gids),default=.2)
                    self.discs.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],radius))
            for g in range(world.model.ngeom):
                if 'wall' not in (world.model.geom(g).name or ''):continue
                n_,N_=self.eyes.region_visible(world.data,rid,[g])
                if N_ and n_>=math.ceil(N_/3):
                    xy=world.data.geom_xpos[g,:2]-base[:2];rot=world.data.geom_xmat[g].reshape(3,3)
                    a=math.atan2(rot[1,0],rot[0,0])-yaw
                    self.rects.append((co*xy[0]+si*xy[1],-si*xy[0]+co*xy[1],*map(float,world.model.geom_size[g,:2]),math.atan2(math.sin(a),math.cos(a))))
        phase=teacher.phase
        target = None
        if self.valid:
            target,_=teacher.step(now,measurement=measurement)
            if teacher.phase not in ('start','fold','approach','align','relook'):self.valid=False
        errors=command_errors(c.encode_action(selected,done=done),c.encode_action(target)) if target else None
        row={'sample_id':observation['sample_id'],'t':now,'teacher_phase':phase,'phase_after':teacher.phase,
             'label_valid':target is not None,'target_visible':measurement is not None,
             'teacher_command':target,'student_command':selected,'errors':errors,
             'rgb':observation['rgb'][-1]}
        self.labels.write(json.dumps(row,allow_nan=False)+'\n');self.labels.flush()
        # Synchronize ONLY actual issued commands. Never measured joints.
        teacher.sink.pwm.update({int(k):v for k,v in selected['pwm'].items()})
        teacher.arm.commanded.update(teacher.sink.pwm);teacher.remember_applied(selected)
        self.n += 1
        write_json(self.output/'shadow-progress.json',{'rows':self.n,'input_audit':self.audit.record(),
            'replay_rgb_and_issued_exact':True if original is not None else None,
            'labels_after_hover_invalid':True,'teacher_actions_executed':0})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('output','model','scene-source'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--root',type=Path)
    p.add_argument('--collect-plan',type=Path)
    p.add_argument('--actor-python',required=True)
    a=p.parse_args()
    if bool(a.root)==bool(a.collect_plan):p.error('choose saved replay or fresh student collection')
    raw=a.root/'raw' if a.root else None
    plan=json.loads(((raw/'plan.json') if raw else a.collect_plan).read_text())
    commands=read_rows(existing(raw/'commands.jsonl')) if raw else None
    original=read_rows(existing(raw/'student-inputs.jsonl')) if raw else None
    from scripts import run_grasp_act_student as runner
    from scripts.run_grasp_act_recovery import dependency_modules
    from harness.grasp_act_dart import recovery_hooks
    from harness.grasp_act_search import SEARCH_MODE
    calibration=json.loads((Path(__file__).resolve().parents[1]/'experiments/2026-10-15-act-train/act11-noise.json').read_text())
    class NoPerturbation:
        mode=SEARCH_MODE
        active=False
        def apply(self,clean,**kwargs):return deepcopy(clean),None
    class ReplayExecutor:
        def __init__(self,*args,**kwargs):self.i=0
        def step(self,obs,jpegs):
            row=commands[self.i];self.i+=1
            if abs(row['command']['t']-obs['t'])>1e-8:raise ValueError('replay time mismatch')
            return row['command'],row['done_requested']
    if raw:runner.ChunkExecutor=ReplayExecutor
    protocol={'closed_loop_seeds':[plan['seed']],'train_seeds':[],'validation_seeds':[]}
    with dependency_modules(a.scene_source):
        from sim import grasp_act_solo_teacher as teacher_module
        from harness import grasp_act_solo_recording as recorder_module
        with (a.output.parent/(a.output.name+'-shadow-hook.jsonl')).open('x') as ledger:
            with recovery_hooks(teacher_module,recorder_module,NoPerturbation(),ledger,
                                yaw_gain=calibration['rotation_calibration']['yaw_gain']):
                runner.run(plan,protocol,a.model,a.output,actor_python=a.actor_python,cap_s=90.,teacher_start_v1=True,
                    diagnostic_observer_factory=lambda w,p,o,i,s:ShadowTeacher(w,p,o,i,s,plan=plan,output=a.output,original=original))


if __name__=='__main__':main()
