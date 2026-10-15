"""Finite GCP-only long_beam teacher probe; no training RGB or student runs.

The grasp path is reused from a clean pinned dependency, not copied. The
default-off adapter adds v7 setup, held-cargo input suppression and mixed
command disturbances. It does not adopt any teacher as the ACT student.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
from importlib.machinery import PathFinder
from importlib.util import module_from_spec
import json
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace

from harness.beampair_teacher import (MODE, DEPENDENCY_SHA, HeldCargoGuard, validate_plan,
                                    perturb_model, defer_ready_during_probe, PairRecoveryPerturb)
from harness.grasp_act_data import write_json
from harness.json_encoding import dumps
from harness.grasp_act_peer_rendezvous import (PeerRendezvous, RendezvousTeacherMixin,
    MODE as RENDEZVOUS_MODE, BOUNDED_MODE)
from harness.beampair_approach import ApproachRepairMixin, MODE as APPROACH_MODE, BOUNDED_MODE as APPROACH_BOUNDED_MODE
from harness.failure_rgb_tail import FailureRGBTail
from harness.beampair_host import gcp2_identity
from harness.beampair_wall_layer import WallLayer, MODE as WALL_MODE
from harness.beampair_visible_rays import visible_rays

ROOT=Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/2026-10-15-beampair1'


@contextmanager
def recording_json(runner):
    """Bind every pinned-runner JSON/JSONL sink to the same strict encoder.

    The dependency remains clean and pinned. Replace only its module reference,
    never json.dumps globally, and restore both bindings even on HOST_ERROR.
    """
    original_json, original_write = runner.json, runner.write
    runner.json = SimpleNamespace(**{**vars(original_json), 'dumps': dumps})
    runner.write = write_json
    try:
        yield
    finally:
        runner.json, runner.write = original_json, original_write


@contextmanager
def dependency_modules(root):
    """Same package isolation as the ACT solo adapter; never import a fallback."""
    root=Path(root).resolve()
    if (subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=DEPENDENCY_SHA
            or subprocess.check_output(['git','status','--porcelain'],cwd=root)):
        raise ValueError('clean exact pinned pair dependency required')
    names=('harness','sim','scripts');owned=lambda n:n.split('.')[0] in names
    saved={n:m for n,m in sys.modules.copy().items() if owned(n)};search=sys.path[:]
    try:
        for n in saved:del sys.modules[n]
        sys.path.insert(0,str(root))
        for n in names:
            spec=PathFinder.find_spec(n,[str(root)])
            if spec is None:raise ImportError('missing dependency package '+n)
            package=module_from_spec(spec);sys.modules[n]=package
            if spec.loader is not None:spec.loader.exec_module(package)
            package.__path__=[str(root/n)]
        yield
    finally:
        for n in list(sys.modules):
            if owned(n):del sys.modules[n]
        sys.modules.update(saved);sys.path[:]=search


def profiles(candidate):
    values=dict(teacher_profile='visible_only',self_pose_source='issued',
        teacher_stability='align_relook_v1',teacher_search='search_body_scan_v2',
        approach_goal_set='approach_goal_set_v1',nominal_blocked_handoff='nominal_blocked_handoff_v1',
        approach_progress='approach_progress_v1',approach_recovery='progress_view_recovery_v3',
        handoff_observation='visible_handoff_v1',pregrasp_sampling='pregrasp_sampling_v1',
        obstacle_reobserve='obstacle_reobserve_v1',peer_reobserve='peer_reobserve_v1',
        search17_candidates='search17_candidates_v1',search17_escape='search17_escape_v1',
        search17_odometry='search17_fixed_v1',search18_start_plan='search18_start_plan_v1',
        search18_free_space='search18_free_space_v1',search19_motion='search19_motion_v1',
        search19_footprint='search19_footprint_v1',search20='search20_v1',search21='search21_v1',
        search22='search22_v1',search23='search23_v1',search24_irm='search24_irm_v1',
        search24_budget='search24_checks_v1',search25_budget='search25_checks_v1')
    if candidate=='soft':values['search25_inflation']='search25_soft_v1'
    return values


def setup_admission(plan,scenario):
    """Authored setup only, before physics; no setup coordinates enter actions."""
    import math
    from harness.zone_final_environment import resolve
    from harness.static_keepouts import keepout_rects
    from sim.grasp_act_search18 import body_clearance
    from sim.zone_cargo import kind
    from sim.zone_arena import BOX_HALF, COLORS
    static,_,_=resolve(scenario['map_id']);rects=keepout_rects(static,perimeter=True)
    placements=deepcopy(scenario['eval']['setup']['placements'])
    next(p for p in placements if p['item_id']=='beam_1')['pose_m']=plan['beam_pose']
    # Zero signed gap is geometric non-intersection. Authored cargo landing
    # envelopes and the existing chassis footprint introduce no tuned margin.
    discs=[]
    for p in placements:
        half=BOX_HALF[:2] if p['kind'] in COLORS else kind(p['kind']).landing_half_extents_m
        discs.append((p['item_id'],(*p['pose_m'][:2],math.hypot(*half))))
    rows=[]
    for rid,spawn in plan['spawns'].items():
        pose=(spawn[0],spawn[1],spawn[3])
        for name,disc in discs:
            gap=body_clearance(pose,[disc],[])
            rows.append(dict(robot=rid,blocked_object=name,min_gap_m=gap,
                reason_category='setup_overlap' if gap<0 else 'setup_clear'))
        gap=body_clearance(pose,[],rects,bounds=static['bounds_m'])
        rows.append(dict(robot=rid,blocked_object='static_map',min_gap_m=gap,
            reason_category='setup_overlap' if gap<0 else 'setup_clear'))
    if any(r['min_gap_m']<0 for r in rows):raise ValueError('setup overlap: '+dumps([r for r in rows if r['min_gap_m']<0]))
    return rows


def run(plan,out,dependency_root,*,mode='off',candidate='baseline',cap_s=60.,rendezvous='off',
        approach_repair='off',failure_tail=True,wall_layer='off'):
    if platform.system()!='Linux':raise RuntimeError('GCP Linux only; Mac physics/render forbidden')
    if mode!=MODE:raise ValueError('explicit beampair1_v1 opt-in required')
    if approach_repair not in ('off',APPROACH_MODE,APPROACH_BOUNDED_MODE):raise ValueError('unknown approach repair')
    if wall_layer not in ('off',WALL_MODE):raise ValueError('unknown wall layer')
    validate_plan(plan)
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('committed source required')
    scenario_path=EXP/'scenario-v7.json';scenario_bytes=scenario_path.read_bytes()
    if hashlib.sha256(scenario_bytes).hexdigest()!=plan['scenario_source_sha256']:
        raise ValueError('v7 scenario hash mismatch')
    scenario=json.loads(scenario_bytes)
    if any(p['kind'] in ('heavy_crate','tile','can') for p in scenario['eval']['setup']['placements']):
        raise ValueError('v7 cargo inventory required')
    guard=HeldCargoGuard();teachers={};models={};visible={};audit={};probe_rows=[]
    selected=profiles(candidate)
    ray_rows=[];current_rays={}
    with dependency_modules(dependency_root):
        from scripts.grasp_act_host import identity
        host=gcp2_identity(identity)
        setup_rows=setup_admission(plan,scenario)
        from scripts import run_grasp_act_teacher as runner
        from sim import grasp_act_scene as scene_module
        from sim.zone_scenario_scene import ScenarioFinalV3Scene
        from sim.render_profile import install
        from sim.final_pair_highpose_nearclip import wrap
        from sim import masterpi_camera_review_v3 as camera
        from sim.s2_servo_stiffness import transform_xml as stiffness
        from sim import grasp_act_visible_measurements as measurements_module
        from harness import grasp_act_visible_world as world_module
        from sim import grasp_act_teacher_v3 as teacher_module
        from harness import grasp_act_input_audit as audit_module
        original_measure=measurements_module.measurements
        original_world=world_module.VisibleWorld
        original_teacher=teacher_module.VisibleOnlyGraspTeacher
        original_apply=runner.apply
        original_audit=audit_module.new_input_audit
        original_make_scene=scene_module.make_scene
        original_snapshot=runner.snapshot
        tail=FailureRGBTail() if failure_tail else None
        def snapshot(world,*a,**kw):
            value=original_snapshot(world,*a,**kw)
            if tail is not None:tail.capture(world,plan['roles'],float(world.data.time))
            return value
        def make_scene(p):
            # Standard Scene API accepts an authored scenario dictionary; this
            # avoids modifying the dependency's v4/v6 registry. V7 only changes
            # cargo inventory; beam geometry/mass/contact remain byte-identical.
            scene=wrap(install(ScenarioFinalV3Scene.from_scenario(scenario,p['seed']),'floor_light_v1'))
            scene.config['setup_only']['spawns']=deepcopy(p['spawns'])
            original=scene.robot_transform
            def transform(xml,**kw):
                before=camera.transform_xml(original(xml,**kw),profile_id=camera.PROFILE_ID)
                for rid in ('r1','r2','r3'):before=stiffness(before,servo_stiffness='real_v1',robot_id=rid)
                after=scene_module.colors(before,p['end_color_scene'])
                scene.manifest['grasp_act_scene']={'version':MODE,'cargo_scene':'cargo_v7',
                    'scenario_id':p['scenario_id'],'scenario_sha256':p['scenario_source_sha256'],
                    'colors':p['end_color_scene'],'scene_xml_sha256':hashlib.sha256(after.encode()).hexdigest()}
                return after
            scene.robot_transform=transform
            return scene
        def measurements(world,evaluator,rid,role,bodies):
            current_rays[rid]=[]
            if not guard.active:
                ms=original_measure(world,evaluator,rid,role,bodies)
                if wall_layer!='off' and models[rid].wall_layer.active:
                    wall_tops=[2*m['xyz'][2] for m in [*ms,*models[rid].memory.values()] if m['kind']=='wall']
                    if wall_tops:current_rays[rid]=visible_rays(world,evaluator,rid,min(wall_tops))
                return ms
            guard.hidden_measurement_ticks+=1
            bands=evaluator.bands
            try:
                evaluator.bands={}
                return original_measure(world,evaluator,rid,role,{k:v for k,v in bodies.items() if k!='beam_1'})
            finally:evaluator.bands=bands
        class World(original_world):
            def __init__(self,rid,*a,**kw):
                super().__init__(rid,*a,**kw);models[rid]=self
                self.wall_layer=WallLayer()
            def observe(self,ms,now,**kw):
                guard.validate_measurements(ms)
                guard.sanitize_memory(self)
                visible[self.rid]=any(m['id']=='band_'+self.end and m['visible_n']>=5 for m in ms)
                w=guard.sanitize_world(super().observe(ms,now,**kw))
                if wall_layer!='off' and not guard.active:
                    from sim.grasp_act_gaze import camera_extrinsics
                    import numpy as np
                    pwm={int(k):v for k,v in self.previous['pwm'].items()} if self.previous else teachers[self.rid].sink.pwm
                    origin,axes=camera_extrinsics(pwm)
                    rays=[dict(origin=origin,end=(np.asarray(origin)+np.asarray(axes).T@ray['optical_end']).tolist(),
                               hit_wall=ray['hit_wall']) for ray in current_rays.get(self.rid,[])]
                    ray_rows.append(dict(t=now,robot=self.rid,rays=current_rays.get(self.rid,[]),
                        input='own visible optical endpoint + issued camera FK; no measured joints'))
                    w=self.wall_layer.update(w,self.rid,ms,rays)
                return w
        class Teacher(ApproachRepairMixin,RendezvousTeacherMixin,original_teacher):
            def __init__(self,rid,*a,**kw):
                super().__init__(rid,*a,**kw);teachers[rid]=self
                self.rendezvous=PeerRendezvous(rendezvous)
                self.approach_repair=approach_repair;self.approach_repair_log=[]
                self.wall_layer_mode=wall_layer
                ticks=plan['burst_ticks'] if rid=='r1' else 13-plan['burst_ticks']
                self.pair_perturb=PairRecoveryPerturb(perturb_model(ticks),seed=plan['seed']+(rid=='r2'))
            def _plan_approach(self,w,now):
                valid=super()._plan_approach(w,now)
                if wall_layer!='off' and not valid and not models[self.rid].wall_layer.active:
                    rows=[c for e in self.goal_set_log[-1:] for c in e.get('candidates',[])]
                    if rows and all(c['reason']=='blocked_goal' for c in rows):
                        models[self.rid].wall_layer.active=True
                        self.approach_repair_log.append(dict(t=now,event='wall_layer_activate',
                            reason_category='all_stances_blocked_goal',blocked_object='wall_layer',min_gap_m=None,
                            gap_scope='preceding candidate ledger; full grid marked from visible history'))
                        if self.reobserver.active:self.reobserver.finish(self,now,'wall_layer_hit_miss_replan')
                        self.next_plan=now
                return valid
            def step(self,w,now,**kw):
                if guard.active:
                    self.local_seen=None;self.last_seen_t=None
                    # Inputs for both robots were captured before either
                    # command was issued this tick. Re-sanitize the second
                    # robot if its peer just closed on this same tick.
                    w=guard.sanitize_world(dict(w))
                before=self.phase;before_t=self.phase_t
                clean,done=super().step(w,now,**kw)
                defer_ready_during_probe(self,before,before_t,self.pair_perturb.active)
                actual,disturbance=self.pair_perturb.apply(clean,phase_before=before,
                    phase_after=self.phase,holding=guard.active,visible=visible[self.rid])
                if disturbance:
                    self.sink.pwm.update({int(k):v for k,v in actual['pwm'].items()})
                    self.arm.commanded.update(self.sink.pwm)
                probe_rows.append({'t':now,'robot_id':self.rid,'target_visible':visible[self.rid],
                    'phase_before':before,'phase_after':self.phase,'held_hidden':guard.active,
                    'clean_teacher_command':clean,'issued_command':actual,'disturbance':disturbance,
                    'training_target':False})
                return actual,done
        def apply(port,value,now,previous):
            guard.issued(value)
            return original_apply(port,value,now,previous)
        def new_audit(*a,**kw):
            audit.update(original_audit(*a,**kw));return audit
        scene_module.make_scene=make_scene;measurements_module.measurements=measurements
        world_module.VisibleWorld=World;teacher_module.VisibleOnlyGraspTeacher=Teacher
        runner.apply=apply;audit_module.new_input_audit=new_audit
        runner.snapshot=snapshot
        report=None
        try:
            with recording_json(runner):
                report=runner.run(plan,out,cap_s=cap_s,record_training=False,noise=False,execution_host=host,**selected)
        finally:
            scene_module.make_scene=original_make_scene;measurements_module.measurements=original_measure
            world_module.VisibleWorld=original_world;teacher_module.VisibleOnlyGraspTeacher=original_teacher
            runner.apply=original_apply;audit_module.new_input_audit=original_audit
            runner.snapshot=original_snapshot
            # Separate adapter result, leaving the dependency's raw result and
            # manifest intact. Both full source SHAs are required for identity.
            adapter=out.parent/'adapter';adapter.mkdir(parents=True,exist_ok=False)
            if report is None:
                result_path=out/'result.json'
                if result_path.exists():report=json.loads(result_path.read_text())
                elif Path(str(result_path)+'.zst').exists():
                    report=json.loads(subprocess.check_output(['zstd','-qdc',str(result_path)+'.zst']))
            write_json(adapter/'beampair1-result.json',{'schema':'ugrp.beampair1.result.v1',
                'source_sha':source,'dependency_sha':DEPENDENCY_SHA,'candidate':candidate,
                'peer_rendezvous':rendezvous,
                'approach_repair':approach_repair,'failure_tail_recording':failure_tail,'wall_layer':wall_layer,
                'mode':mode,'held_object_hidden_v1':True,'held_world_reads':guard.held_world_reads,
                'first_close_t':guard.first_close_t,'hidden_measurement_ticks':guard.hidden_measurement_ticks,
                'input_audit':audit,'training_rgb':False,'profiles':selected,'result':report,
                'setup_admission':setup_rows,
                'probe_burst_ticks':{r:t.pair_perturb.ticks for r,t in teachers.items()},
                'probe_executed_ticks':{r:sum(x['robot_id']==r and x['disturbance'] is not None for x in probe_rows) for r in teachers}})
            if wall_layer!='off':
                write_json(adapter/'wall-layer.json',dict(mode=wall_layer,
                    events={rid:m.wall_layer.events for rid,m in models.items()},
                    activated={rid:m.wall_layer.active for rid,m in models.items()},
                    visible_ray_N=sum(len(r['rays']) for r in ray_rows),held_ray_N=0,
                    input='own camera visible intersections + own issued FK only; perfect perception teacher, not student'))
                (adapter/'wall-rays.jsonl').write_text(''.join(dumps(r)+'\n' for r in ray_rows))
            ledger=adapter/'beampair1-commands.jsonl'
            ledger.write_text(''.join(dumps(r)+'\n' for r in probe_rows))
            if tail is not None:
                tail.finish(adapter/'failure-tail',failed=not bool(report and report.get('physical_success')))
            runner.compress_logs(adapter)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--dependency-root',type=Path,required=True)
    p.add_argument('--mode',choices=['off',MODE],default='off')
    p.add_argument('--candidate',choices=['baseline','soft'],default='baseline');p.add_argument('--cap-s',type=float,default=60.)
    p.add_argument('--rendezvous',choices=['off',RENDEZVOUS_MODE,BOUNDED_MODE],default='off')
    p.add_argument('--approach-repair',choices=['off',APPROACH_MODE,APPROACH_BOUNDED_MODE],default='off')
    p.add_argument('--wall-layer',choices=['off',WALL_MODE],default='off')
    p.add_argument('--failure-tail',action=argparse.BooleanOptionalAction,default=True,
                   help='Recording only: retain last10 SIM seconds own RGB on failure/interruption')
    a=p.parse_args();run(json.loads(a.plan.read_text())['episodes'][a.episode],a.out,a.dependency_root,
                         mode=a.mode,candidate=a.candidate,cap_s=a.cap_s,rendezvous=a.rendezvous,
                         approach_repair=a.approach_repair,failure_tail=a.failure_tail,wall_layer=a.wall_layer)
