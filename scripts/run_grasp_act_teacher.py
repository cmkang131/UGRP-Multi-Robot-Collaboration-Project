"""Finite teacher demonstration on an admitted host; weld always OFF.

Run only after host release and storage/speed gates. The optional noise is
DART-inspired until its covariance is estimated from a trained student's
residuals. Teacher labels and simulator truth never share the student file.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,math,os,platform,subprocess,sys,time
from collections import deque
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from harness.grasp_act_contract import SCHEMA,HISTORY,SERVOS,validate_observation,command,image_history


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def apply(port,value,now,previous):
    """Same continuous actuator path for teacher and student; zero stops wheels."""
    if 'wheels' in value:
        port.apply({'kind':'wheel_pulse','wheels':value['wheels'],'duration_s':value['duration_s']},now)
    elif any(value['drive']):
        port.apply(dict(kind='mecanum',**dict(zip(('forward','left','turn'),value['drive'])),duration_s=value['duration_s']),now)
    else:port.stop()
    for s in SERVOS:
        p=value['pwm'][str(s)]
        if p != previous['pwm'][str(s)]:
            port.apply({'kind':'look','pan_pulse':p} if s==6 else {'kind':'arm','servo_id':s,'pulse':p},now)


def snapshot(world,inst,roles,scene):
    import numpy as np
    from types import SimpleNamespace
    from scripts.cargo_formation_teacher import FormationTeacher
    body=world.data.body(inst.body);rot=body.xmat.reshape(3,3);pos=body.xpos
    yaw=math.atan2(rot[1,0],rot[0,0])
    ends={end:(pos+rot@np.array([x,0.,.024])).tolist() for end,x in (('teal',-.27),('blue',.27))}
    holder=SimpleNamespace(world=world,inst=inst,roles=roles)
    min_z=min(float((world.data.geom(inst.geom(p.name)).xpos +
        world.data.geom(inst.geom(p.name)).xmat.reshape(3,3)@np.array([sx*p.size[0],sy*p.size[1],sz*p.size[2]]))[2])
        for p in inst.spec().parts if p.collision for sx in (-1,1) for sy in (-1,1) for sz in (-1,1))
    objects={}
    for c in scene.cargo:
        b=world.data.body(c.body)
        objects[c.item_id]={'xy':list(map(float,b.xpos[:2])),
            'radius':math.hypot(*c.spec().landing_half_extents_m),
            'top_z_bound_m':max(float(world.data.geom(c.geom(p.name)).xpos[2])+float(world.model.geom_rbound[world.model.geom(c.geom(p.name)).id]) for p in c.spec().parts if p.collision)}
    for iid,c in scene.config['setup_only']['objects'].items():
        objects[iid]={'xy':list(map(float,world.data.body(c['body_name']).xpos[:2])),
            'radius':math.hypot(*c['half_extents_m'][:2]),
            'top_z_bound_m':float(world.data.body(c['body_name']).xpos[2])+math.sqrt(sum(float(x)**2 for x in c['half_extents_m']))}
    return {'objects':objects,'t':float(world.data.time),'beam':{'pose':[float(pos[0]),float(pos[1]),yaw],'ends':ends,
        'qpos':body.xquat.tolist(),'min_z':min_z,'tilt_deg':math.degrees(math.acos(float(np.clip(rot[2,2],-1.,1.))))},'robots':{rid:{'pose':[*map(float,world.robot(rid).base_xyz()[:2]),float(world.robot(rid).base_rpy()[2])],
        'xyz':list(map(float,world.robot(rid).base_xyz()))} for rid in ('r1','r2','r3')},
        'contacts':FormationTeacher.finger_forces(holder),'joints':world.data.qpos.tolist()}


def compress_logs(out):
    manifest={}
    for path in sorted(out.rglob('*')):
        if not path.is_file():continue
        b=path.read_bytes();entry={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
        if path.suffix in ('.json','.jsonl') and len(b)>65536:
            z=subprocess.check_output(['zstd','-q','-c'],input=b)
            assert subprocess.check_output(['zstd','-qdc'],input=z)==b
            target=Path(str(path)+'.zst');target.write_bytes(z);path.unlink();path=target
            entry={'sha256':hashlib.sha256(z).hexdigest(),'bytes':len(z),'decoded_sha256':entry['sha256']}
        manifest[str(path.relative_to(out))]=entry
    write(out/'manifest.json',manifest)
    path=out/'manifest.json';raw=path.read_bytes()
    if len(raw)>65536:
        compressed=subprocess.check_output(['zstd','-q','-c'],input=raw)
        assert subprocess.check_output(['zstd','-qdc'],input=compressed)==raw
        target=out/'manifest.json.zst';target.write_bytes(compressed);path.unlink()
        write(out/'manifest-compression.json',{'path':target.name,'bytes':len(compressed),
            'sha256':hashlib.sha256(compressed).hexdigest(),'decoded_sha256':hashlib.sha256(raw).hexdigest()})



def audit_visible_input(audit,rows):
    """Count delivered measurements, including rejected hidden rows; fail closed."""
    audit['measurement_rows']+=len(rows)
    bad=sum(m['visible_n']<(5 if m['kind']=='band' else max(1,math.ceil(m['probe_N']/3))) for m in rows)
    audit['invisible_measurements']+=bad
    if bad:raise ValueError('invisible measurement delivered to teacher')


def finalize_outcomes(teachers,*,strict,joint_held):
    """A pair stopped for map handoff has not timed out its unfinished peer.

    Preserve independent failures and completed physical hold failures; only
    unfinished peers receive the explicit administrative cancellation label.
    """
    search=any(t.outcome=='search_timeout_handoff' for t in teachers.values())
    approach=any(t.outcome=='approach_blocked_handoff' for t in teachers.values())
    for t in teachers.values():
        if strict and t.command_complete:
            t.outcome='success' if joint_held else 'no_stable_joint_hold_3s'
        elif t.outcome is None:
            t.outcome='peer_approach_handoff' if approach else 'peer_search_handoff' if search else 'episode_timeout'


def validate_recording_inputs(record_training,teacher_profile,self_pose_source):
    if record_training and (teacher_profile!='visible_only' or self_pose_source!='issued'):
        raise ValueError('recording requires visible_only and issued pose; GT labels forbidden')


def run(plan,out,*,cap_s=60.,noise=False,record_training=False,probe=False,teacher_profile="legacy",self_pose_source="issued",recording_proof=None,recording_probe=False,execution_host=None,teacher_stability="off",teacher_search="off",approach_goal_set="off",nominal_blocked_handoff="off",approach_progress="off",approach_recovery="off",approach_coordination="off",handoff_observation="off",pregrasp_sampling="off",obstacle_reobserve="off",peer_reobserve="off",search17_candidates="off",search17_escape="off",search17_odometry="off",search18_footprint="off",search18_start_plan="off",search18_free_space="off",search19_motion="off",search19_footprint="off",search20="off",search21="off",search22="off",search23="off",search24_irm="off",search24_budget="off",search25_inflation="off",search25_memory="off",search25_view="off",search25_budget="off",search23_rects="off",search26_circles="off",search26_circles_farfirst="off",search26_static_peer="off",search26_peer_memory="off",search26_reobserve="off",search26_reobserve_refresh="off",search26_reobserve_refresh_open="off",search26_commit_plan="off",search26_wide_rescue="off",search26_align_diag="off",search26_align_pulse="off",search26_wide_stance="off",pair_carry="off",carry_cap_s=110.,carry_lower="grasp_height",carry_route="straight_v1",student_eval=None,hybrid_carry=None,hybrid_smoke=None):
    validate_recording_inputs(record_training,teacher_profile,self_pose_source)
    from harness.pair_carry_teacher_warp import MODES as CARRY_MODES
    if pair_carry not in CARRY_MODES:raise ValueError('unknown pair carry mode')
    if pair_carry!='off':
        # P2 GT carry continues ONLY the visible_only two-robot joint hold.
        if teacher_profile!='visible_only' or sorted(plan.get('roles',{}).values())!=['blue','teal']:
            raise ValueError('pair carry requires the visible_only one-robot-per-end joint hold')
        if probe:raise ValueError('pair carry is not a probe mode')
        if not 0<carry_cap_s<=120:raise ValueError('finite carry cap required')
    if pair_carry!='off':
        # P3 (COLLECT_SPEC §4): v7 own clock (deadband 2) for both segments of a pair-carry episode
        from harness.pair_carry_recorder import DeadbandIssuedClock
    from harness.pair_carry_teacher_warp import LOWER_MODES
    if carry_lower not in LOWER_MODES:raise ValueError('unknown carry lower mode')
    if carry_lower!='grasp_height' and pair_carry=='off':raise ValueError('carry lower mode requires pair carry')
    from harness.pair_carry_teacher_warp import ROUTE_MODES
    if carry_route not in ROUTE_MODES:raise ValueError('unknown carry route mode')
    if carry_route!='straight_v1' and pair_carry=='off':raise ValueError('carry route mode requires pair carry')
    if student_eval is not None:
        # P5 (default off): the learned student issues every command; no teacher step, no GT to the student.
        from harness.pairact_student_eval import validate_config as validate_student
        validate_student(student_eval)
        if pair_carry=='off' or teacher_profile!='visible_only':raise ValueError('student eval requires the visible_only pair carry episode')
        if record_training or noise or probe:raise ValueError('student eval never records, perturbs or probes')
    if hybrid_carry is not None:
        # pairact hybrid (default off): student near field + code carry (harness/hybrid_carry.py) + student place
        from harness.hybrid_carry import validate_config as validate_hybrid
        validate_hybrid(hybrid_carry)
        if student_eval is None:raise ValueError('hybrid carry runs on top of the student eval episode')
    if hybrid_smoke is not None:
        # hybrid code-carry smoke (default off): teacher near field + code carry + teacher place; not learned
        from harness.hybrid_carry import validate_config as validate_hybrid
        validate_hybrid(hybrid_smoke,purpose='teacher_smoke')
        if student_eval is not None or hybrid_carry is not None:raise ValueError('hybrid smoke has no student')
        if pair_carry=='off' or teacher_profile!='visible_only':raise ValueError('hybrid smoke continues the visible_only pair joint hold')
        if record_training or noise or probe:raise ValueError('hybrid smoke never records, perturbs or probes')
    from sim.grasp_act_search15_modes import validate
    search15={'peer_reobserve':peer_reobserve,'search17_candidates':search17_candidates,'search17_escape':search17_escape,'search17_odometry':search17_odometry,'search18_footprint':search18_footprint,'search18_start_plan':search18_start_plan,'search18_free_space':search18_free_space,'search19_motion':search19_motion,'search19_footprint':search19_footprint,'search20':search20,'search21':search21,'search22':search22,'search23':search23,'search24_irm':search24_irm,'search24_budget':search24_budget,'search25_inflation':search25_inflation,'search25_memory':search25_memory,'search25_view':search25_view,'search25_budget':search25_budget,'search23_rects':search23_rects,'search26_circles':search26_circles,'search26_static_peer':search26_static_peer,'search26_peer_memory':search26_peer_memory,'search26_circles_farfirst':search26_circles_farfirst,'search26_reobserve':search26_reobserve,'search26_reobserve_refresh':search26_reobserve_refresh,'search26_reobserve_refresh_open':search26_reobserve_refresh_open,'search26_commit_plan':search26_commit_plan,'search26_wide_rescue':search26_wide_rescue,'search26_align_diag':search26_align_diag,'search26_align_pulse':search26_align_pulse,'search26_wide_stance':search26_wide_stance,'obstacle_reobserve':obstacle_reobserve,'pregrasp_sampling':pregrasp_sampling}
    validate(search15,recovery=approach_recovery,profile=teacher_profile,pose_source=self_pose_source,coordination=approach_coordination)
    if handoff_observation not in ('off','visible_handoff_v1'):
        raise ValueError('unknown handoff observation mode')
    if handoff_observation!='off' and (teacher_profile!='visible_only' or self_pose_source!='issued'):
        raise ValueError('visible handoff requires visible_only and issued pose')
    if record_training and teacher_profile=='visible_only' and handoff_observation!='visible_handoff_v1':
        raise ValueError('recording requires visible handoff observation; GT sample selection forbidden')
    if approach_coordination not in ('off','prioritized_approach_v1','observed_blocked_priority_v2'):raise ValueError('unknown approach coordination mode')
    if approach_coordination!='off' and (teacher_profile!='visible_only' or self_pose_source!='issued' or teacher_stability!='align_relook_v1' or approach_recovery!='off' or sorted(plan.get('roles',{}).values())!=['blue','teal']):
        raise ValueError('approach coordination requires visible_only issued baseline and one robot per end')
    if approach_coordination!='off':
        from sim.grasp_act_priority import require_baseline
        require_baseline(teacher_stability,teacher_search,approach_goal_set,nominal_blocked_handoff,approach_progress,approach_recovery)
    if teacher_stability!='off' and teacher_profile!='visible_only':raise ValueError('stability mode requires visible_only')
    if teacher_search!='off' and teacher_stability=='off':raise ValueError('search mode requires teacher stability')
    if approach_goal_set!='off' and (teacher_profile!='visible_only' or teacher_stability=='off' or self_pose_source!='issued'):
        raise ValueError('approach goal set requires visible_only, align_relook_v1 and issued pose')
    if nominal_blocked_handoff not in ('off','nominal_blocked_handoff_v1'):raise ValueError('unknown nominal blocked handoff mode')
    if nominal_blocked_handoff!='off' and (teacher_profile!='visible_only' or teacher_stability=='off' or self_pose_source!='issued'):
        raise ValueError('nominal blocked handoff requires visible_only, align_relook_v1 and issued pose')
    if approach_progress not in ('off','approach_progress_v1'):raise ValueError('unknown approach progress mode')
    if approach_progress!='off' and (teacher_profile!='visible_only' or teacher_stability=='off' or self_pose_source!='issued'):
        raise ValueError('approach progress requires visible_only, align_relook_v1 and issued pose')
    if approach_recovery in ('approach_recovery_v2','progress_view_recovery_v3') and approach_goal_set=='off':raise ValueError('approach recovery v2 requires approach goal set')
    if approach_recovery not in ('off','approach_recovery_v1','approach_recovery_v2','progress_view_recovery_v3'):raise ValueError('unknown approach recovery mode')
    if approach_recovery!='off' and (teacher_profile!='visible_only' or self_pose_source!='issued' or approach_progress=='off' or teacher_search!='search_body_scan_v2'):
        raise ValueError('approach recovery requires visible_only, issued, progress and search_body_scan_v2')
    if platform.system()=='Darwin':raise RuntimeError('Mac physics/render disabled; use admitted execution host')
    if record_training:
        from scripts.grasp_act_host import same_machine
        if not recording_proof or recording_proof.get('qualified') is not True:raise ValueError('qualified recording proof required')
        same_machine(recording_proof.get('execution_host'),execution_host)
    import mujoco
    import numpy as np
    from harness import grasp_act_contract as v5
    from harness import grasp_act_contract_v4 as v4
    contract=v5 if teacher_profile=='visible_only' else v4
    SCHEMA,HISTORY,command=contract.SCHEMA,contract.HISTORY,contract.command
    validate_observation,image_history=contract.validate_observation,contract.image_history
    observable=teacher_profile in ('observable_v2','visible_only')
    strict=teacher_profile=='visible_only'
    from sim.grasp_act_scene import make_scene
    from sim.grasp_act_teacher import GraspTeacher
    from sim.masterpi_drive_friction_v7 import build_world,PROFILE
    from sim.grasp_act_port import ContinuousActPort,DutyActPort
    from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher
    from harness.grasp_act_visible_world import VisibleWorld
    from harness.grasp_act_start_sync import GraspStartSync,GraspApproachSync,GraspConditionalApproachSync
    from sim.grasp_act_visible_measurements import measurements
    from harness.static_keepouts import keepout_rects
    rng=np.random.default_rng(plan['seed']);out.mkdir(parents=True,exist_ok=False)
    write(out/'plan.json',plan)
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):
        raise RuntimeError('committed source required')
    write(out/'RUN_META.json',{'class':'milestone' if record_training else 'dev','pr':484,'branch':'claude/e2e18-grasp-rootcause','sha':sha,'batch':plan['batch']})
    scene=make_scene(plan);world=None;streams=[];teachers={};start=time.monotonic()
    timings={k:0. for k in ('physics','rgb','evaluation','teacher','io')}
    from harness.grasp_act_input_audit import AuditedTeacherInput,new_input_audit
    report={'status':'running','source_sha':sha,'teacher_success_n':0,'teacher_N':len(plan['roles']),'execution_host':execution_host,
        'joint_held':None,'data_admitted':False,'assignment_source':plan['assignment_source'],
        'student_execution':False,'recording_mode':'training' if record_training else 'success_measurement',
        'episode_plan_sha256':hashlib.sha256((out/'plan.json').read_bytes()).hexdigest(),
        'physical_success':False,'teacher_profile':teacher_profile,'action_contract':SCHEMA,'loadavg_at_start':os.getloadavg(),'noise':'DART-inspired_fixed_pilot' if noise else 'off',
        'self_pose_source':self_pose_source,'recording_gate_proof':recording_proof,
        'teacher_stability':teacher_stability,'teacher_search':teacher_search,'approach_goal_set':approach_goal_set,'nominal_blocked_handoff':nominal_blocked_handoff,'approach_progress':approach_progress,'approach_recovery':approach_recovery,'approach_coordination':approach_coordination,'handoff_observation':handoff_observation,'pregrasp_sampling':pregrasp_sampling,'obstacle_reobserve':obstacle_reobserve,'peer_reobserve':peer_reobserve,'search17_candidates':search17_candidates,'search17_escape':search17_escape,'search17_odometry':search17_odometry,'search18_footprint':search18_footprint,'search18_start_plan':search18_start_plan,'search18_free_space':search18_free_space,'search19_motion':search19_motion,'search19_footprint':search19_footprint,'search20':search20,'search21':search21,'search22':search22,'search23':search23,'search24_irm':search24_irm,'search24_budget':search24_budget,'search25_inflation':search25_inflation,'search25_memory':search25_memory,'search25_view':search25_view,'search25_budget':search25_budget,'search23_rects':search23_rects,'search26_circles':search26_circles,'search26_static_peer':search26_static_peer,'search26_peer_memory':search26_peer_memory,'search26_circles_farfirst':search26_circles_farfirst,'search26_reobserve':search26_reobserve,'search26_reobserve_refresh':search26_reobserve_refresh,'search26_reobserve_refresh_open':search26_reobserve_refresh_open,'search26_commit_plan':search26_commit_plan,'search26_wide_rescue':search26_wide_rescue,'search26_align_diag':search26_align_diag,'search26_align_pulse':search26_align_pulse,'search26_wide_stance':search26_wide_stance,
        'start_nominal_goal_feasible':plan.get('start_nominal_goal_feasible','off'),
        'search_handoff':False,
        'input_audit':new_input_audit(strict,self_pose_source),
        'pair_carry':pair_carry,'carry_cap_s':carry_cap_s if pair_carry!='off' else 0.,
        **({'carry_lower':carry_lower} if pair_carry!='off' else {}),
        **({'carry_route':carry_route} if carry_route!='straight_v1' else {}),
        'criteria':{'min_z_m':.012,'max_tilt_deg':10.,'hold_s':3.} if strict else {'min_z_m':.012,'hold_s':1.}}
    write(out/'result.json',report)
    try:
        os.environ['UGRP_SIM_OBSERVER_WIDTH']='320'
        os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
        world=build_world(scene,drive_profile=PROFILE,seed=plan['seed'],width=640 if record_training else 320,height=480 if record_training else 240,render=True,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        if observable:
            from sim.s2_realism_camera_binding import bind_camera
            for controller in world.controllers.values():bind_camera(controller)
        scene.setup(world)
        # All remaining scenario cargo stays present. Only authorized randomized
        # initial placement changes, before the trial clock and any teacher step.
        from sim.zone_cargo import place, CargoInstance
        place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
        (out/'scene.xml').write_text(world.scene_xml);write(out/'scene.json',scene.manifest)
        report['observation_sampling']={'rgb_size':[640,480] if record_training else None,'rgb_hz':10 if record_training else 0,
            'review_tile_size':[320,240],'review_cameras':('own cameras only; top disabled' if search23!='off' else 'four authored static top views'),'review_hz':1,'control_hz':10,
            'aspect_ratio_unchanged':True,'camera_fov_and_pose_unchanged':True}
        ports={rid:(DutyActPort if strict else ContinuousActPort)(world,rid,allow_reverse=True,allow_mecanum=True) for rid in plan['roles']}
        # Setup-only pan target: no model/camera changes. All later motion is issued commands.
        for rid,port in ports.items():port.apply({'kind':'look','pan_pulse':plan['initial_pan'][rid]},float(world.data.time))
        until=float(world.data.time)+.5
        def advance(target):
            at=time.monotonic()
            while float(world.data.time)<target-1e-8:
                now=float(world.data.time)
                if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                for port in ports.values():port.tick(now)
                world._physics_step_for(world.robot('r1'))
            timings['physics']+=time.monotonic()-at
        advance(until)
        origin=float(world.data.time);previous={};history={};images={};writers={};teachers={};models={};clocks={}
        delays={rid:(0. if k==0 else float(rng.uniform(0,1.5))) for k,rid in enumerate(plan['roles'])}
        sync_cls=(GraspConditionalApproachSync if approach_coordination=='observed_blocked_priority_v2' else
                  GraspApproachSync if approach_coordination!='off' else GraspStartSync)
        sync=sync_cls(plan['roles'],delays) if strict else None
        report['grasp_start_delays_s']=delays if strict else {r:0. for r in plan['roles']}
        from scripts.audit_grasp_act_visibility import BandVisibility
        visibility=BandVisibility(world.model)
        object_bodies={c.item_id:c.body for c in scene.cargo}
        object_bodies.update({i:c['body_name'] for i,c in scene.config['setup_only']['objects'].items()})
        write(out/'camera-runtime.json',{'scope':'evaluation-only; actual runtime values, not XML assumptions',
            'binding':'v3' if observable else 'runtime_legacy',
            'cameras':{rid:{'pos':world.model.cam_pos[cid].tolist(),'quat':world.model.cam_quat[cid].tolist(),
                'intrinsic':world.model.cam_intrinsic[cid].tolist(),'resolution':world.model.cam_resolution[cid].tolist()}
                for rid,cid in visibility.cameras.items()}})
        for rid,end in plan['roles'].items():
            pwm={str(s):int(ports[rid]._servo_pulses[s]) for s in SERVOS}
            initial=command({'t':origin,'pwm':pwm,**({'wheels':[0.]*4,'duration_s':[0.]*4} if strict else {'drive':[0.]*3,'duration_s':0.})})
            previous[rid]=initial;history[rid]=deque([initial]*HISTORY,maxlen=HISTORY)
            search_kw={'teacher_search':teacher_search} if teacher_search!='off' else {}
            teachers[rid]=(VisibleOnlyGraspTeacher(rid,end,pwm,bounds=(-20,20,-20,20),teacher_stability=teacher_stability,approach_goal_set=approach_goal_set,nominal_blocked_handoff=nominal_blocked_handoff,approach_progress=approach_progress,approach_recovery=approach_recovery,approach_coordination=approach_coordination,**search15,**search_kw) if strict else
                GraspTeacher(rid,end,pwm,bounds=scene.config['static_map']['bounds_m'],rects=keepout_rects(scene.config['static_map']),profile=teacher_profile))
            if strict:models[rid]=VisibleWorld(rid,end,pose_source=self_pose_source,odometry=search17_odometry,search22=search22,search23=search23);clocks[rid]=v5.IssuedClock() if pair_carry=='off' else DeadbandIssuedClock()
            student=None
            if record_training:
                (out/'rgb'/rid).mkdir(parents=True)
                student=(out/f'student-{rid}.jsonl').open('w');streams.append(student)
            label=(out/f'teacher-{rid}.jsonl').open('w');streams.append(label);writers[rid]=(student,label)
        ev=(out/'eval-only.jsonl').open('w');streams.append(ev)
        (out/'eval-overview').mkdir()
        if observable:
            for rid in plan['roles']:(out/'eval-own'/rid).mkdir(parents=True)
            report['observation_sampling']['own_review_hz']=1
            report['observation_sampling']['own_review_size']=[320,240]
        inst=next(x for x in scene.cargo if x.item_id=='beam_1');i=0;written=0;both_since=None;all_done_since=None;max_hold=0.
        carry=None;carry_rows=[];carry_done_since=None;recorders={}
        student_ep=None;student_log=None;student_funnel=None;student_hold_t=None
        if student_eval is not None:
            from harness.pairact_student_eval import start as start_student,StudentFunnel
            from harness.grasp_act_start_sync import GraspStartSync
            student_ep,student_delays=start_student(student_eval,plan['roles'],plan['episode_id'],previous,seed=plan['seed'],factory=GraspStartSync)
            student_funnel=StudentFunnel();student_log=(out/'student-eval.jsonl').open('w');streams+=[student_log,student_ep.client]
            report.update(student_execution=True,student_eval={'mode':student_eval['mode'],'model':student_eval['model'],'protocol_delays_s':student_delays})
        hybrid=None
        if hybrid_carry is not None:
            from harness.hybrid_carry import HybridRun,NavZoneSensor
            from harness.pair_carry_teacher_warp import static_map_for as hybrid_static_map
            hybrid=HybridRun(hybrid_carry,plan['roles'],
                sensor=NavZoneSensor.from_config(hybrid_carry['nav']) if hybrid_carry['carry_mode']=='nav' else None,
                static_map=hybrid_static_map(scene.config) if hybrid_carry['carry_mode']=='map' else None,
                start_poses=plan.get('start_poses') if hybrid_carry['carry_mode']=='map' else None)
            report['hybrid']={'mode':hybrid_carry['mode'],'carry_mode':hybrid_carry['carry_mode']}
        smoke=None;smoke_on=False;smoke_t0=smoke_handback_t=smoke_done_since=None
        if hybrid_smoke is not None:
            from harness.hybrid_carry import HybridRun,NavZoneSensor
            from harness.hybrid_smoke_eval import tick_row as smoke_row
            from harness.pair_carry_teacher_warp import static_map_for as smoke_static_map,zone_of as smoke_zone_of
            smoke=HybridRun(hybrid_smoke,plan['roles'],sensor=NavZoneSensor.from_config(hybrid_smoke['nav']),purpose='teacher_smoke')
            smoke_zone=smoke_zone_of(smoke_static_map(scene.config))
            smoke_log=(out/'hybrid-drive.jsonl').open('w');streams.append(smoke_log)
            report['hybrid_smoke']={'mode':hybrid_smoke['mode'],'carry_mode':hybrid_smoke['carry_mode'],
                'label':'teacher 근거리 + 코드 운반, 학습 아님','near_field':'teacher','carry':'code','place':'teacher'}
        while float(world.data.time)-origin < (cap_s if carry is None and student_ep is None and not smoke_on else cap_s+carry_cap_s)-1e-8:
            now=float(world.data.time);at=time.monotonic()
            if search23!='off' and now-origin>=30.-1e-8 and 'first30_speed' not in report:
                report['first30_speed']={'sim_s':now-origin,'wall_s':time.monotonic()-start,
                    'scope':'first 30 SIM seconds including initialization; recording only'}
                report['first30_speed']['wall_per_sim']=report['first30_speed']['wall_s']/(now-origin)
                write(out/'first30-speed.json',report['first30_speed'])
            truth=snapshot(world,inst,plan['roles'],scene)
            truth['visibility']={rid:visibility.measure(world.data,rid,end) for rid,end in plan['roles'].items()}
            perceived={}
            if carry is not None or student_ep is not None or smoke_on:
                # GT carry / student eval: no teacher measurements; GT rows are eval-only.
                from harness.pair_carry_eval import eval_row
                carry_rows.append(eval_row(truth))
            elif strict:
                truth['visible_measurements']={}
                for rid,end in plan['roles'].items():
                    ms=measurements(world,visibility,rid,end,object_bodies)
                    audit_visible_input(report['input_audit'],ms)
                    truth['visible_measurements'][rid]=ms
                    v=truth['visibility'][rid];v['any_probe_visible']=v['visible'];v['visible']=v['visible_probes']>=5
                    perceived[rid]=AuditedTeacherInput(models[rid].observe(ms,now,comparison_pose=(truth['robots'][rid]['pose'] if self_pose_source=='perfect_self_comparison' else None)),report['input_audit'])
            elif observable:
                for rid in plan['roles']:
                    truth['visibility'][rid]['objects']=[iid for iid,b in object_bodies.items() if visibility.body_visible(world.data,rid,b)]
                    truth['visibility'][rid]['peers']=[peer for peer in ('r1','r2','r3') if peer!=rid and visibility.body_visible(world.data,rid,peer+'__robot')]
            ev.write(json.dumps(truth)+'\n')
            timings['evaluation']+=time.monotonic()-at
            if i % 10 == 0:
                # Reviewer evidence only; never referenced by a student observation.
                import io
                from PIL import Image
                at=time.monotonic();overview=Image.new('RGB',(640,480))
                for k,camera in enumerate([] if search22!='off' else scene.config['static_map']['top_cameras']):
                    frame=Image.open(io.BytesIO(world.render_team_jpeg(camera=camera['name'])))
                    overview.paste(frame.resize((320,240)),((k%2)*320,(k//2)*240))
                if search22=='off':overview.save(out/'eval-overview'/f'{i:06d}.jpg',quality=86)
                if observable:
                    for rid in plan['roles']:
                        jpg=base64.b64decode(ports[rid].capture()['image'])
                        Image.open(io.BytesIO(jpg)).resize((320,240)).save(out/'eval-own'/rid/f'{i:06d}.jpg',quality=86)
                timings['rgb']+=time.monotonic()-at
                write(out/'progress.json',{'sim_s':now-origin,'wall_s':time.monotonic()-start,
                    'phases':{rid:t.phase for rid,t in teachers.items()},'sample':i,'timings_s':timings})
                if search23!='off':
                    write(out/'diagnostic-snapshot.json',{'sim_s':now-origin,'source_sha':sha,
                        'input_audit':report['input_audit'],'teachers':{rid:t.diagnostic() for rid,t in teachers.items()},
                        'scope':'periodic unfinished diagnostic; never final acceptance'})
                for stream in streams:stream.flush()
            both=all(min(truth['contacts'][rid])>=.5 for rid in plan['roles']) and truth['beam']['min_z']>=.012
            if strict:both=both and truth['beam']['tilt_deg']<=10.
            both_since=(now if both_since is None else both_since) if both else None
            held_s=0. if both_since is None else now-both_since;max_hold=max(max_hold,held_s)
            if strict and carry is None:report['joint_held']=held_s>=3.
            if student_ep is not None and held_s>=3. and student_hold_t is None:student_hold_t=now
            elif len(plan['roles'])==2 and held_s>=1.:report['joint_held']=True
            permit=all(x.phase in ('ready','pick','verify','done') for x in teachers.values())
            if strict and carry is None and student_ep is None:
                if approach_coordination=='observed_blocked_priority_v2':
                    blocked={rid:t.request_coordination(perceived[rid],now) for rid,t in teachers.items()}
                    if sync.request(blocked,now):
                        for t in teachers.values():t.activate_coordination(now)
                ready={rid:t.prepare_signal(perceived[rid],now) for rid,t in teachers.items()}
                permits=sync.tick(ready,now)
            elif observable and carry is None and student_ep is None:
                permit=permit and all(x.phase!='ready' or truth['visibility'][rid]['visible_probes']>=3 for rid,x in teachers.items())
            hybrid_code=False
            if hybrid is not None and not hybrid.student_controls() and hybrid.segment()!='ABORT':
                # hybrid code segment: own frames -> code commands; the student only shadows (I7)
                hybrid_code=True;at=time.monotonic()
                frames={rid:ports[rid].capture()['image'] for rid in plan['roles']}
                code=hybrid.code_tick(now,{rid:base64.b64decode(v) for rid,v in frames.items()})
                applied_code={rid:command(json.loads(json.dumps(row))) for rid,row in code.items()}
                shadow=student_ep.client.request(hybrid.shadow_request(now,frames,applied_code))['robots']
                for rid,applied in applied_code.items():
                    apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
                    models[rid].issue(applied)
                student_log.write(json.dumps({'t':now,'hybrid_segment':hybrid.segment(),'code':applied_code,
                    'shadow_stage':{r:v['stage'] for r,v in shadow.items()},
                    'eval_passed':student_funnel.add(now,truth,plan['roles'],student_ep.ready,student_hold_t is not None)},allow_nan=False)+'\n')
                timings['teacher']+=time.monotonic()-at
            if smoke_on and carry is None and not smoke.student_controls() and smoke.segment()!='ABORT':
                # hybrid smoke code segment: own frames -> code commands (no student, no teacher step)
                at=time.monotonic()
                frames={rid:base64.b64decode(ports[rid].capture()['image']) for rid in plan['roles']}
                code=smoke.code_tick(now,frames)
                applied_code={rid:command(json.loads(json.dumps(row))) for rid,row in code.items()}
                for rid,applied in applied_code.items():
                    apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
                    models[rid].issue(applied)
                timings['teacher']+=time.monotonic()-at;at=time.monotonic()
                try:
                    cid=visibility.cameras[smoke.leader]
                    cam=(world.data.cam_xpos[cid].tolist(),world.data.cam_xmat[cid].reshape(-1).tolist())
                except (AttributeError,IndexError,KeyError,TypeError):cam=None
                row=smoke_row(now,smoke,applied_code,truth,camera=cam,zone=smoke_zone,
                    ground_point_robot=getattr(smoke.sensor,'project',None),gate=getattr(smoke.sensor,'gate_projection',None),
                    hfov_deg=hybrid_smoke['nav']['hfov_deg'])
                if cam is None:row['eval_only']['camera_unavailable']=True
                smoke_log.write(json.dumps(row,allow_nan=False)+'\n')
                timings['evaluation']+=time.monotonic()-at
            if student_ep is not None and not hybrid_code:
                at=time.monotonic()
                jpegs={rid:base64.b64decode(ports[rid].capture()['image']) for rid in plan['roles']}
                proposed,issued=student_ep.tick(now,jpegs,previous)
                for rid,row in issued.items():
                    applied=command(json.loads(json.dumps(row['command'])))
                    apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
                    models[rid].issue(applied)
                student_log.write(json.dumps({'t':now,'inputs':{r:v['observation'] for r,v in proposed.items()},
                    'ready':student_ep.ready,'issued':issued,
                    'eval_passed':student_funnel.add(now,truth,plan['roles'],student_ep.ready,student_hold_t is not None)},allow_nan=False)+'\n')
                if hybrid is not None:hybrid.after_student_tick(now,issued,{rid:previous[rid] for rid in issued})
                timings['teacher']+=time.monotonic()-at
            for rid,t in (teachers.items() if carry is None and student_ep is None and not smoke_on else ()):
                at=time.monotonic()
                sample_id=f"{plan['episode_id']}:{i}:{rid}"
                # Demonstration supervisor supplies the discrete wait command;
                # hidden peer readiness must not change a grasp action label
                # under an identical student instruction.
                allowed=permits[rid] if strict else permit
                coordinated_wait=strict and t.priority is not None and t.priority.waiting
                stationary_wait=coordinated_wait and (t.end=='teal' or t.priority.round==1)
                skill='wait' if (t.phase=='ready' and not allowed) or stationary_wait else 'grasp'
                if handoff_observation=='visible_handoff_v1':
                    from harness.grasp_act_handoff import visible_local_sample
                    local_before,local_distance=visible_local_sample(
                        perceived[rid],rid,t.end,handed_off=t.handoff,coordinated_wait=coordinated_wait)
                else:
                    local_distance=math.dist(truth['robots'][rid]['pose'][:2],truth['beam']['ends'][t.end][:2])
                    local_before=bool(strict and t.handoff and local_distance<=.8 and not coordinated_wait)
                elapsed={**clocks[rid].observe((skill,t.end,t.handoff),now,previous[rid]['pwm']),'destination_zone':'none'} if strict else {}
                if record_training:
                    capture=ports[rid].capture();jpg=base64.b64decode(capture['image']);path=f'rgb/{rid}/{i:06d}.jpg';(out/path).write_bytes(jpg)
                    ref={'path':path,'sha256':hashlib.sha256(jpg).hexdigest(),'t':now,'robot_id':rid}
                    images.setdefault(rid,deque(maxlen=max(HISTORY+1,math.ceil(contract.MEMORY_S/.1)+2))).append(ref)
                    obs={'schema':SCHEMA,'robot_id':rid,'sample_id':sample_id,'t':now,
                        'object_kind':'long_beam','skill':skill,'role':t.end,'rgb':image_history(list(images[rid]),now),'issued':list(history[rid]),**elapsed}
                    validate_observation(obs)
                    writers[rid][0].write(json.dumps(obs)+'\n')
                timings['rgb']+=time.monotonic()-at
                at=time.monotonic()
                if strict:t.skill_started=now-elapsed['skill_elapsed_s']
                clean,done=t.step(perceived[rid] if strict else truth,now,permit_pick=allowed)
                timings['teacher']+=time.monotonic()-at
                # Privileged navigation samples remain in raw but are excluded by the data admission loader.
                phase=t.phase;applied=json.loads(json.dumps(clean));perturbed=False
                if noise and phase not in ('done','complete','ready') and rng.random()<.05:
                    perturbed=True
                    if strict and any(applied['wheels']):applied.update(wheels=[0.]*4,duration_s=[0.]*4)
                    elif not strict and any(applied['drive']):applied.update(drive=[0.,0.,0.],duration_s=0.)
                    else:
                        sid=str(rng.choice([3,4,5]));applied['pwm'][sid]=int(np.clip(applied['pwm'][sid]+rng.normal(0,8),500,2500))
                command(applied)
                label={'sample_id':sample_id,'object_kind':'long_beam','skill':skill,'done':done,
                    'terminal_reason':('command_sequence_complete' if strict else 'skill_success') if done else None,'clean_teacher_command':clean,
                    **({'planning_compute':dict(t.search20_compute)} if search20!='off' else {}),
                    'applied_command':applied,'perturbed':perturbed,'teacher_phase':phase,
                    'local_skill_sample':(local_before and skill!='wait' and (phase!='complete' or not getattr(t,'done_recorded',False))) if strict else (teacher_profile=='observable_v2' or phase!='approach'),'assignment_source':plan['assignment_source'],
                    'skill_instruction_source':'GO_ACK_code_messages; demo own READY; runtime LLM skill' if strict else 'demo_privileged_pair_supervisor; student runtime instruction must come from LLM',
                    'local_distance_m':local_distance,
                    'local_distance_source':'visible_issued' if handoff_observation!='off' else 'legacy_evaluation_truth',
                    'handoff_distance_m':(math.dist(perceived[rid]['robots'][rid]['pose'][:2],perceived[rid]['beam']['ends'][t.end][:2]) if strict and perceived[rid]['beam'] is not None else None),
                    'segment':'local_grasp' if local_before else 'navigation_or_search' if strict else phase}
                apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
                if strict:
                    models[rid].issue(applied)
                    t.remember_applied(applied)
                    if done:t.done_recorded=True
                label['issued_native_wheels']=list(ports[rid]._motor_commands)
                writers[rid][1].write(json.dumps(label)+'\n')
            if carry is not None:
                at=time.monotonic()
                if record_training:
                    # P3: own camera + own v7 clock + own history only (same order as the grasp tick: observe, then act)
                    for rid in plan['roles']:
                        capture=ports[rid].capture();jpg=base64.b64decode(capture['image']);(out/f'rgb/{rid}/{i:06d}.jpg').write_bytes(jpg)
                        recorders[rid].add_frame(i,now,jpg)
                        writers[rid][0].write(json.dumps(recorders[rid].student_row(i,now,previous[rid]['pwm']))+'\n')
                    timings['rgb']+=time.monotonic()-at;at=time.monotonic()
                for rid,(clean,done) in carry.step(truth,now).items():
                    applied=command(json.loads(json.dumps(clean)))
                    label=recorders[rid].label_row(i,clean=clean,applied=applied,done=done,
                        phase=carry.phase,outcome=carry.outcome,assignment_source=plan['assignment_source'])
                    apply(ports[rid],applied,now,previous[rid]);previous[rid]=applied;history[rid].append(applied)
                    models[rid].issue(applied)
                    label['issued_native_wheels']=list(ports[rid]._motor_commands)
                    writers[rid][1].write(json.dumps(label)+'\n')
                timings['teacher']+=time.monotonic()-at
            written+=1
            if hybrid is not None and hybrid.segment()=='ABORT':break
            if student_ep is not None:
                if student_ep.finished:break
            elif smoke_on and carry is None:
                if smoke.segment()=='STUDENT_PLACE':
                    # hand-back at the set-down start: the GT teacher lowers/opens/retreats from the code's stop pose
                    from harness.pair_carry_teacher_warp import start_place_from_runner
                    from harness.pair_carry_recorder import CarryRecorder
                    carry=start_place_from_runner(plan,truth,now,scene,teachers,previous,carry_cap_s,lower_mode=carry_lower)
                    recorders={rid:CarryRecorder(rid,plan['roles'][rid],history=history[rid],
                        images=images.setdefault(rid,deque(maxlen=max(HISTORY+1,math.ceil(contract.MEMORY_S/.1)+2))),
                        episode_id=plan['episode_id'],clock=clocks[rid]) for rid in plan['roles']}
                    smoke_handback_t=now;report['hybrid_smoke']['handback_sim_s']=now-origin
                elif smoke.segment()=='ABORT':
                    smoke_done_since=now if smoke_done_since is None else smoke_done_since
                    if now-smoke_done_since>=1.5-1e-8:break
            elif carry is not None:
                if carry.done:
                    # keep 1.5 SIM s of passive rows so the evaluator sees the rest state
                    carry_done_since=now if carry_done_since is None else carry_done_since
                    if now-carry_done_since>=1.5-1e-8:break
            elif strict and all(t.command_complete for t in teachers.values()):
                all_done_since=now if all_done_since is None else all_done_since
                if smoke is not None and not smoke_on and not probe and report['joint_held']:
                    smoke.teacher_handover(now,previous);smoke_on=True;smoke_t0=now
                    report['carry_handover_sim_s']=now-origin
                if not probe and pair_carry!='off' and report['joint_held'] and smoke is None:
                    from harness.pair_carry_teacher_warp import start_from_runner
                    from harness.pair_carry_recorder import CarryRecorder
                    plan_started=time.monotonic()
                    carry=start_from_runner(plan,truth,now,scene,teachers,previous,carry_cap_s,lower_mode=carry_lower,route_mode=carry_route)
                    if carry_route!='straight_v1':
                        # -c4 (opt-in route modes only): persist route/route_info the moment it is
                        # planned, so a wall-capped or killed run still has it (result.json is final-only)
                        planned=dict(carry.route_record(),handover_sim_s=now-origin,plan_wall_s=time.monotonic()-plan_started)
                        report['carry_route_plan']=planned
                        write(out/'carry-route.json',planned)
                        try:write(out/'result.json',report)
                        except (TypeError,ValueError) as error:planned['result_json_midrun_error']=str(error)
                        print('CARRY_ROUTE_PLANNED '+json.dumps(dict(out=str(out),variant=planned['route_info'].get('variant'),
                            outcome=planned['outcome'],plan_wall_s=planned['plan_wall_s'],handover_sim_s=planned['handover_sim_s'])),
                            file=sys.stderr,flush=True)
                    recorders={rid:CarryRecorder(rid,plan['roles'][rid],history=history[rid],
                        images=images.setdefault(rid,deque(maxlen=max(HISTORY+1,math.ceil(contract.MEMORY_S/.1)+2))),
                        episode_id=plan['episode_id'],clock=clocks[rid]) for rid in plan['roles']}
                    report['carry_handover_sim_s']=now-origin
                elif not probe and (report['joint_held'] or now-all_done_since>=6.) and not smoke_on:break
            if not strict and not probe and all(t.outcome is not None for t in teachers.values()):
                all_done_since=now if all_done_since is None else all_done_since
                if len(teachers)==1 or report['joint_held'] is True or now-all_done_since>=3.:break
            if not probe and any(t.outcome not in (None,'success') for t in teachers.values()):break
            i+=1;advance(origin+i*.1)
        finalize_outcomes(teachers,strict=strict,joint_held=report['joint_held'])
        if student_ep is not None:
            from harness.pair_carry_eval import evaluate,zone_entry_t
            from harness.pair_carry_teacher_warp import static_map_for
            report['student_eval'].update(student_ep.summary(),joint_hold_t=student_hold_t,teacher_steps=0,gt_inputs_to_student=0)
            if student_hold_t is not None:
                static=static_map_for(scene.config)
                rows=[r for r in carry_rows if r['t']>=student_hold_t-1e-9]
                report['carry_eval']=evaluate(rows,static,list(plan['roles']),lower_start_t=zone_entry_t(rows,static),handover_t=student_hold_t)
                report['carry_eval']['setdown_boundary']='zone_entry_v1'
                write(out/'carry-eval.json',report['carry_eval'])
            report['student_eval']['funnel']=student_funnel.record(report.get('carry_eval'))
            if hybrid is not None:
                if student_ep.finished:hybrid.student_finished(now)
                report['hybrid'].update(hybrid.summary())
        if carry is not None:
            from harness.pair_carry_eval import evaluate,drive_response,phase_report
            lower=next((e['t'] for e in carry.events if e.get('event')=='phase' and e.get('to')=='lower'),None)
            report['carry']=carry.diagnostic()
            report['carry_eval']=evaluate(carry_rows,carry.static_map,list(plan['roles']),lower_start_t=lower,handover_t=carry.t0)
            # eval-only duty->GT body speed, reported apart from the teacher's phase timeouts
            report['carry_eval']['drive_response']=drive_response(carry_rows,carry.log,list(plan['roles']))
            report['carry_eval']['phase_report']=phase_report(report['carry'],report['carry_eval']['drive_response'])
            write(out/'carry-eval.json',report['carry_eval'])
        elif pair_carry!='off' and student_ep is None:
            report['carry']={'started':False,'reason':'no_joint_hold_3s'}
        if smoke is not None:
            # hybrid smoke: one evaluator over the carried episode (teacher handover -> code carry -> teacher place)
            report['hybrid_smoke'].update(smoke.summary())
            if smoke_on:
                from harness.pair_carry_eval import evaluate,drive_response
                from harness.pair_carry_teacher_warp import static_map_for
                rows=[r for r in carry_rows if r['t']>=smoke_t0-1e-9]
                place=carry.diagnostic() if carry is not None else None
                report['carry_eval']=evaluate(rows,static_map_for(scene.config),list(plan['roles']),lower_start_t=smoke_handback_t,handover_t=smoke_t0)
                report['carry_eval']['setdown_boundary']='hybrid_smoke_handback_v1'
                # eval-only: code-segment command vs GT body speed (same diagnostic as the GT teacher's)
                report['carry_eval']['code_drive_response']=drive_response(rows,smoke.log,list(plan['roles']))
                if carry is not None:report['carry_eval']['place_drive_response']=drive_response(rows,carry.log,list(plan['roles']))
                report['carry']={'started':True,'mode':'hybrid_smoke','outcome':(place or {}).get('outcome') if place else smoke.outcome,
                    'code_outcome':smoke.outcome or ('handed_back' if smoke_handback_t is not None else None),'place_teacher':place}
                write(out/'carry-eval.json',report['carry_eval'])
        if pair_carry!='off':
            from harness.pair_carry_recorder import recording_summary
            report['carry_recording']=recording_summary(recorders,clocks)
        if strict:
            report['max_stable_hold_s']=max_hold
            write(out/'start-protocol.json',{'source':('BLOCKED/READY/GO/ACK boolean messages; no peer poses' if approach_coordination=='observed_blocked_priority_v2' else 'READY/GO/ACK only; no peer probes'),'delays_s':delays,'events':sync.events})
        if len(plan['roles'])==2 and report['joint_held'] is None:report['joint_held']=False
        report.update(status='complete',sim_s=float(world.data.time)-origin,wall_s=time.monotonic()-start,
            teacher_success_n=sum(t.outcome=='success' for t in teachers.values()),
            teachers={rid:t.diagnostic() for rid,t in teachers.items()},samples_per_robot=written,
            first_attempt=True,weld='off',loadavg_at_end=os.getloadavg(),timings_s=timings)
        report['physical_success']=report['teacher_success_n']==report['teacher_N'] and (len(plan['roles'])==1 or report['joint_held'] is True)
        if pair_carry!='off':
            # grasp gate success stays in grasp_physical_success; carry is judged only by the eval-only evaluator.
            report['grasp_physical_success']=report['physical_success']
            report['carry_success']=bool((report.get('carry_eval') or {}).get('success'))
            if student_ep is not None:
                # P5: student success = joint hold reached AND the unchanged GT evaluator success.
                report['physical_success']=report['grasp_physical_success']=bool(student_hold_t is not None)
                report['physical_success']=report['physical_success'] and report['carry_success']
            elif record_training:
                # P3 admission (COLLECT_SPEC §5): a demo is admitted only if grasp AND carry succeeded.
                report['physical_success']=report['grasp_physical_success'] and report['carry_success']
        # Map code, not ACT, moves a robot that saw nothing in a full scan: counted apart, never training data.
        report['search_handoff']=any(t.outcome=='search_timeout_handoff' for t in teachers.values())
        report['approach_handoff']=any(t.outcome=='approach_blocked_handoff' for t in teachers.values())
        report['data_admitted']=bool(record_training and not recording_probe and report['physical_success'] and not report['search_handoff'] and not report['approach_handoff'])
        report['wall_per_sim']=report['wall_s']/max(.001,report['sim_s'])
        report['cap_end']=bool(report['sim_s']>=(cap_s if carry is None and student_ep is None and not smoke_on else cap_s+carry_cap_s)-1e-8)
        report['end_reason']='cap_end' if report['cap_end'] else 'teacher_terminal'
        # Pair whole-beam clearance is deliberately a separate, not-yet-evaluated metric.
        write(out/'result.json',report)
    except BaseException as error:
        if search23!='off':
            report['teachers']={rid:t.diagnostic() for rid,t in teachers.items()}
        from sim.grasp_act_search20 import PlanningSafetyCap
        safety_cap=isinstance(error,PlanningSafetyCap)
        report.update(status='complete' if safety_cap else 'HOST_ERROR' if not isinstance(error,KeyboardInterrupt) else 'interrupted',error_type=type(error).__name__,error=str(error),wall_s=time.monotonic()-start)
        if safety_cap:
            report.update(cap_end=True,end_reason='planning_wall_safety_cap',physical_success=False,
                          data_admitted=False,sim_s=float(world.data.time)-origin,teacher_success_n=0)
        write(out/'result.json',report)
        if not safety_cap:raise
    finally:
        for stream in streams:stream.close()
        if world is not None:world.close()
        compress_logs(out)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--episode',type=int,default=0)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cap-s',type=float,default=60.)
    p.add_argument('--noise',action='store_true');p.add_argument('--probe',action='store_true')
    p.add_argument('--teacher-profile',choices=('legacy','pi_geometry_v1','observable_v2','visible_only'),default='legacy')
    p.add_argument('--teacher-stability',choices=('off','align_relook_v1'),default='off')
    p.add_argument('--teacher-search',choices=('off','search_body_scan_v1','search_body_scan_v2'),default='off')
    p.add_argument('--approach-goal-set',choices=('off','approach_goal_set_v1'),default='off')
    p.add_argument('--nominal-blocked-handoff',choices=('off','nominal_blocked_handoff_v1'),default='off')
    p.add_argument('--approach-progress',choices=('off','approach_progress_v1'),default='off')
    p.add_argument('--approach-recovery',choices=('off','approach_recovery_v1','approach_recovery_v2','progress_view_recovery_v3'),default='off')
    p.add_argument('--approach-coordination',choices=('off','prioritized_approach_v1','observed_blocked_priority_v2'),default='off')
    p.add_argument('--handoff-observation',choices=('off','visible_handoff_v1'),default='off')
    p.add_argument('--self-pose-source',choices=('issued','perfect_self_comparison'),default='issued')
    p.add_argument('--execution-host',choices=('azure','gcp1'),default='azure')
    p.add_argument('--record-training',action='store_true');p.add_argument('--teacher-gate',type=Path)
    p.add_argument('--gate-plan',type=Path);p.add_argument('--recording-probe',action='store_true');p.add_argument('--recording-check',type=Path)
    from sim.grasp_act_search15_modes import add_arguments
    add_arguments(p)
    p.add_argument('--pair-carry',choices=('off','pair_carry_gt_v1'),default='off')
    p.add_argument('--carry-cap-s',type=float,default=110.)
    p.add_argument('--carry-lower',choices=('grasp_height','floor_contact_v1'),default='grasp_height')
    p.add_argument('--carry-route',choices=('straight_v1','detour_v1'),default='straight_v1')
    p.add_argument('--student-eval',type=Path,help='P5 student eval config JSON (default off)')
    # pairact P3 (default off): replace ONLY the >=38/40 gate requirement by a FROZEN collect prereg sha256
    p.add_argument('--recording-admission',choices=('teacher_gate_v1','pairact_p3_collect'),default='teacher_gate_v1')
    p.add_argument('--collect-prereg',type=Path);p.add_argument('--collect-prereg-sha256')
    a=p.parse_args();proof=None
    validate_recording_inputs(a.record_training,a.teacher_profile,a.self_pose_source)
    from scripts.grasp_act_host import identity,same_machine
    host=identity(a.execution_host)
    if a.recording_admission!='teacher_gate_v1' and not a.record_training:raise ValueError('collect recording admission requires --record-training')
    if a.recording_admission=='teacher_gate_v1' and (a.collect_prereg or a.collect_prereg_sha256):raise ValueError('collect prereg requires --recording-admission pairact_p3_collect')
    if a.record_training and a.recording_admission=='pairact_p3_collect':
        from harness.grasp_act_admission import collect_recording_admission,RECORDING_CHECK_MODES
        from sim.grasp_act_search15_modes import options
        if a.collect_prereg is None:raise ValueError('FROZEN collect pre-registration required before recording')
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        check=json.loads(a.recording_check.read_text()) if a.recording_check else None
        proof=collect_recording_admission(a.collect_prereg,a.collect_prereg_sha256,check,source_sha=source_sha,
            teacher_profile=a.teacher_profile,modes={k:getattr(a,k) for k in RECORDING_CHECK_MODES},
            search15_options=options(a),execution_host=host,recording_probe=a.recording_probe,
            check_sha256=hashlib.sha256(a.recording_check.read_bytes()).hexdigest() if a.recording_check else None)
    elif a.record_training:
        if a.teacher_gate is None:raise ValueError('verified >=38/40 teacher gate required before recording')
        from harness.grasp_act_admission import recording_admission
        gate=json.loads(a.teacher_gate.read_text())
        if a.gate_plan is None:raise ValueError('frozen measured gate plan required')
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        proof=recording_admission(gate,source_sha=source_sha,teacher_profile=a.teacher_profile,gate_plan=a.gate_plan,execution_host=host,teacher_stability=a.teacher_stability,teacher_search=a.teacher_search,approach_goal_set=a.approach_goal_set,nominal_blocked_handoff=a.nominal_blocked_handoff,approach_progress=a.approach_progress,approach_recovery=a.approach_recovery,approach_coordination=a.approach_coordination,handoff_observation=a.handoff_observation,pregrasp_sampling=a.pregrasp_sampling,obstacle_reobserve=a.obstacle_reobserve,peer_reobserve=a.peer_reobserve,search17_candidates=a.search17_candidates,search17_escape=a.search17_escape,search17_odometry=a.search17_odometry,search18_footprint=a.search18_footprint,search18_start_plan=a.search18_start_plan,search18_free_space=a.search18_free_space,search19_motion=a.search19_motion,search19_footprint=a.search19_footprint,search20=a.search20,search21=a.search21,search22=a.search22,search23=a.search23,search24_irm=a.search24_irm,search24_budget=a.search24_budget,search25_inflation=a.search25_inflation,search25_memory=a.search25_memory,search25_view=a.search25_view,search25_budget=a.search25_budget)
        proof['gate_sha256']=hashlib.sha256(a.teacher_gate.read_bytes()).hexdigest()
        if not a.recording_probe:
            if a.recording_check is None:raise ValueError('paired 640x480 recording-mode check required')
            check=json.loads(a.recording_check.read_text())
            from sim.grasp_act_search15_modes import match,options
            match(check,options(a),'recording-mode check')
            if check.get('qualified') is not True or check.get('N',0)<3 or check.get('n')!=check.get('N') or check.get('source_sha')!=source_sha or check.get('teacher_profile')!=a.teacher_profile or check.get('teacher_stability','off')!=a.teacher_stability or check.get('teacher_search','off')!=a.teacher_search or check.get('approach_goal_set','off')!=a.approach_goal_set or check.get('nominal_blocked_handoff','off')!=a.nominal_blocked_handoff or check.get('approach_progress','off')!=a.approach_progress or check.get('approach_recovery','off')!=a.approach_recovery or check.get('approach_coordination','off')!=a.approach_coordination or check.get('handoff_observation','off')!=a.handoff_observation:
                raise ValueError('unverified recording-mode equivalence')
            same_machine(check.get('execution_host'),host)
            proof['recording_check_sha256']=hashlib.sha256(a.recording_check.read_bytes()).hexdigest()
    if not 0<a.cap_s<=180:raise ValueError('finite cap required')
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    print(json.dumps(run(plan,a.out,cap_s=a.cap_s,noise=a.noise,record_training=a.record_training,probe=a.probe,teacher_profile=a.teacher_profile,self_pose_source=a.self_pose_source,recording_proof=proof,recording_probe=a.recording_probe,execution_host=host,teacher_stability=a.teacher_stability,teacher_search=a.teacher_search,approach_goal_set=a.approach_goal_set,nominal_blocked_handoff=a.nominal_blocked_handoff,approach_progress=a.approach_progress,approach_recovery=a.approach_recovery,approach_coordination=a.approach_coordination,handoff_observation=a.handoff_observation,pregrasp_sampling=a.pregrasp_sampling,obstacle_reobserve=a.obstacle_reobserve,peer_reobserve=a.peer_reobserve,search17_candidates=a.search17_candidates,search17_escape=a.search17_escape,search17_odometry=a.search17_odometry,search18_footprint=a.search18_footprint,search18_start_plan=a.search18_start_plan,search18_free_space=a.search18_free_space,search19_motion=a.search19_motion,search19_footprint=a.search19_footprint,search20=a.search20,search21=a.search21,search22=a.search22,search23=a.search23,search24_irm=a.search24_irm,search24_budget=a.search24_budget,search25_inflation=a.search25_inflation,search25_memory=a.search25_memory,search25_view=a.search25_view,search25_budget=a.search25_budget,search23_rects=a.search23_rects,search26_circles=a.search26_circles,search26_static_peer=a.search26_static_peer,search26_circles_farfirst=a.search26_circles_farfirst,search26_peer_memory=a.search26_peer_memory,search26_reobserve=a.search26_reobserve,search26_reobserve_refresh=a.search26_reobserve_refresh,search26_reobserve_refresh_open=a.search26_reobserve_refresh_open,search26_commit_plan=a.search26_commit_plan,search26_wide_rescue=a.search26_wide_rescue,search26_align_diag=a.search26_align_diag,search26_align_pulse=a.search26_align_pulse,search26_wide_stance=a.search26_wide_stance,pair_carry=a.pair_carry,carry_cap_s=a.carry_cap_s,carry_lower=a.carry_lower,carry_route=a.carry_route,student_eval=json.loads(a.student_eval.read_text()) if a.student_eval else None),ensure_ascii=False))
if __name__=='__main__':main()
