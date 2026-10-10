"""OwnRoute S3 adapter diagnostic, never an E2E success. Oracle x86 only."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

from harness.e2e_environment import resolve
from harness.e2e_s3_route import compile_route, plan_from_route
from harness.e2e_test_route_provider import provide, WAYPOINTS
from harness.python_source_closure import source_closure
from harness.zone_s3_coarse_fine import attach_endpoint, OPTION as FINE
from harness.zone_s3_alignment_ownership import ALL
from harness.zone_s3_synchronized_carry import attach as carry, joint_plan, OPTION as CARRY
from harness.zone_s3_integer_carry import attach as integer, OPTION as INTEGER
from harness.zone_s3_setdown import attach as setdown
from harness.zone_s3_route_resume import attach as resume, CANDIDATES
from harness.zone_s3_reacquire_expanded import attach as reacquire, Options
from harness.zone_s3_checkpoint_correction import attach as correction
from scripts.run_final_environment_checks import write
from scripts.run_s3_host import artifact_manifest, environment_record

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ID = 'e2e-s3-ownroute-v179'
WORKFLOW_VERSION = '7.72.0'
TEMPLATE = 'configs/e2e_s3_test_runtime_v1.json'
PLAN = 'experiments/2026-10-11-e2e3-s3-route/registration.json'
WORKFLOW = 'configs/simulation_workflows.d/e2e_s3_ownroute_v179.json'


def bundle(sha,seed,option='off',candidate='visual',entrance='off'):
    from harness.e2e_s3_entrance import OPTIONS
    if entrance not in OPTIONS:raise ValueError('UNKNOWN_TEST_ENTRANCE')
    if seed not in (61001,61002) or option not in ('off','on_v1') or candidate not in ('recovery','visual'):
        raise ValueError('registered own-route option/candidate/two seeds required')
    b = json.loads((ROOT/TEMPLATE).read_text())
    static,registry,_ = resolve()
    b.update(schema='ugrp.e2e_s3_test.v179',execution_bundle_id=BUNDLE_ID,workflow_version=WORKFLOW_VERSION,
        source_sha=sha,seed=seed,provider_seeds={r:seed+i for i,r in enumerate(('r1','r2','r3'))},
        map_id=static['map_id'],map_sha256=registry['static_map_sha256'],scenario_id='e2e_one_beam_ownmap',
        case='pair',check='e2e3-test-route',robot_model='masterpi_v3',weld=False,model_calls=0,
        stage_probe=True,research_result=False,physical_success=None,E2E_success=False,
        own_route_adapter=option,route_source='test_route_provider',registered_route=copy.deepcopy(WAYPOINTS),
        test_entrance=entrance,
        route_case='e2e-beam-to-B',initial_condition=0,servo_option=FINE,cap_sim_s=900.,case_cap_s=900.,
        wall_cap_s=18000.,calibration_status='UNMEASURED_NEW_MAP',host='oracle-x86',render_backend='osmesa',
        legacy_authored_guard_provider=True,dialogue_connected=False,goal_rgb_inferred=False,
        controller_map_id='zone_wide_door_geometry_v3',
        controller_pose_prior=False,checkpoint_correction=dict(candidate=candidate,
            options=dict(release_epoch=True,expanded_backoff=True,visual_checkpoint=candidate=='visual')))
    paths=set(source_closure(ROOT,['scripts/run_e2e_s3_route.py','scripts/evaluate_e2e_s3_route.py',
                                  'scripts/run_e2e_s3_route_cohort.py','sim/e2e_s3_test.py']))|{TEMPLATE,PLAN,WORKFLOW,registry['file'],
            registry['parent_file'],'configs/e2e_environment_v1.json','configs/zone_study_dev/e2e_one_beam_ownmap.json',
            'experiments/2026-10-09-s3-no-prior/s3fix10/scene-setup.json',b['calibration']}
    paths.add('experiments/2026-10-09-s3-no-prior/s3fix8/alignment-phase.json')
    b['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def run(b,out):
    if b['own_route_adapter']!='on_v1':raise ValueError('OWN_ROUTE_ADAPTER_OFF: no physics started')
    from sim.e2e_s3_test import PhysicsBackend
    from harness.zone_s3_recovery_runtime import Runtime
    from harness.zone_s3_recovery_contract import inputs
    from harness.zone_s3_route_binding import configure
    from scripts.run_s3_alignment_probe import issue_stage_servos,assert_frame_commands
    out.mkdir(exist_ok=False,parents=True)
    write(out/'bundle.json',b);write(out/'environment.json',environment_record())
    result=dict(status='HOST_ERROR',source_sha=b['source_sha'],seed=b['seed'],model_calls=0,
        route_source='test_route_provider',E2E_success=False,research_result=False,gt_inputs=False)
    host=rt=None;eps={};states=[];audit={};bus={};entered=False;started=time.monotonic()
    try:
        for path,expected in b['source_sha256'].items():
            if hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=expected:raise ValueError('SOURCE_HASH_MISMATCH:'+path)
        host=PhysicsBackend(b,out,seed=b['seed']);host.states_getter=lambda:{r:ep.controller.state for r,ep in eps.items()}
        host.reset(b['reset_cap_s']);host.set_deadline(host.now+2.)
        from harness.owncam_pair_beam_v2 import pose_of
        for rid in ('r1','r2'):issue_stage_servos(host,rid,{1:2000,**pose_of('inspect')})
        host.advance_to(round(host.now+1.,9))
        start=host.now;host.set_deadline(start+b['cap_sim_s'])
        # New map has no admitted S3 provider. Keep the historical parent guard/
        # localizer explicitly diagnostic; only the route is supplied by OwnRoute.
        from harness.zone_final_environment import resolve as parent_resolve
        rt=Runtime(parent_resolve(b['controller_map_id'])[0],inputs()[2]['orders'],ROOT/b['calibration'],b['calibration_sha256'],
                   seed=b['seed'],config=b['controller_config'])
        rt.initial_commands(start,host.commands);rt.boot_finished_at=start
        for i in range(round(b['cap_sim_s']/.05)+1):
            now=host.now;host.eval_sample()
            if time.monotonic()-started>b['wall_cap_s']:raise TimeoutError('E2E3_WALL_CAP')
            frames=host.capture();assert_frame_commands(host,frames);rt.on_frames(now,frames)
            if not entered and now-start>=.5:
                obs=frames['r1'][0]
                ref=dict(robot_id='r1',frame_id=obs['frame_id'],t_sim=obs['sim_time'],sha256=obs['sha256'])
                supplied=provide(ref)
                compiled=compile_route(supplied['route'],now=now,observed=[ref],
                    profiles=rt.localizers['r1'].pulse_profiles,option='on_v1',source=supplied['source'])
                write(out/'test-route-provider.json',supplied);write(out/'ownroute-s3-plan.json',compiled)
                configure(rt,compiled['waypoints'],lambda plan,static,route:plan_from_route(plan,compiled))
                pair=rt.pair.producer
                pair.job_sim_limit_s=b['cap_sim_s']
                for actor in pair.actors.values():actor.job_sim_limit_s=b['cap_sim_s']
                for rid,peer in (('r1','r2'),('r2','r1')):
                    receipt=rt.links[rid].submit(rid,'cargoX','B',peer,now=now)
                    if not receipt['accepted']:raise ValueError('S3_TEST_CLAIM_REJECTED:'+str(receipt))
                pair.started=True;pair.submitted.update(('r1','r2'));eps=pair.team.sessions[0]['endpoints']
                for rid,ep in eps.items():
                    ctl=ep.controller;report=ep.own.last_report
                    ctl.driver.outcome='arrived'
                    ctl.claims['at_prestation']=dict(estimate=[report.x_m,report.y_m,report.yaw_rad],
                        std_xy_m=report.std_xy_m,looks=0,sim_time=now,source='test S3 entrance; own RGB estimate')
                    ctl.arm.events.clear();ctl.arm.until=now;ctl.arm.commanded=dict(ep.own.servo)
                    ctl.set('align_start',now,stage_probe_entry=True,source='test_route_provider')
                    attach_endpoint(ep,FINE,refinements=ALL,planner=joint_plan)
                    carry(ep,CARRY);integer(ep,INTEGER);setdown(ep,b['setdown']['option'])
                    resume(ep,CANDIDATES['combined']);reacquire(ep,Options(True,True,True))
                    correction(ep,b['checkpoint_correction']['options']['visual_checkpoint'],bus=bus,
                               motion=b['controller_config']['motion_model'])
                    audit[rid]=dict(reacquire=ctl.s3_reacquire,visual=getattr(ctl,'s3_checkpoint_correction',{}))
                    # The job deadline is independent of the probe horizon.
                    ep.own.job_sim_limit_s=b['cap_sim_s'];ctl.job_sim_limit_s=b['cap_sim_s']
                    ep.own.job.deadline=now+b['cap_sim_s']
                    from harness.e2e_s3_entrance import attach as entrance
                    entrance(ep,b['test_entrance'])
                entered=True
            if entered:
                pair=rt.pair.producer
                actions=pair.step(now)+pair.arm_step(now)
                current={r:dict(state=ep.controller.state,failure=ep.controller.failure,
                    blind_phase=getattr(ep.controller,'blind_phase',None),seg=ep.controller.seg,servo=dict(ep.own.servo)) for r,ep in eps.items()}
                states.append(dict(t=now,robots=current))
                for rid,action in actions:host.issue(rid,action);rt.on_command(rid,now,action)
                if any(v['failure'] for v in current.values()):break
                if all(getattr(ep.controller,'s3_first_release_complete',False) for ep in eps.values()):
                    # Preserve original physics for the released floor-stability witness.
                    for rid in ('r1','r2'):host.issue(rid,dict(kind='hold'))
                    for j in range(1,42):host.advance_to(now+j*.05);host.eval_sample()
                    result['stage_end']='final_route_release_commanded';break
            if i==round(b['cap_sim_s']/.05):break
            host.advance_to(start+(i+1)*.05)
        result.update(status='DEV_STAGE_FINISHED',check_sim_s=host.now-start,
            final={r:dict(state=ep.controller.state,failure=ep.controller.failure,seg=ep.controller.seg) for r,ep in eps.items()})
    except Exception:
        result['failure']=traceback.format_exc()
        if host is not None and 'start' in locals():result['check_sim_s']=host.now-start
        from sim.zone_s3_no_prior import PhysicalStop
        if 'PhysicalStop:' in result['failure']:result['status']='PHYSICAL_STOP'
        elif 'DEV_INITIAL_CHECK_STOP' in result['failure']:result['status']='EARLY_STOP'
    finally:
        write(out/'stage-states.json',states);write(out/'checkpoint-correction.json',dict(robots=audit,command_plan_bus=bus))
        if rt is not None:write(out/'student_record.json',rt.record());rt.close()
        if host is not None:host.close()
        result.update(wall_s=time.monotonic()-started,loadavg_end=os.getloadavg())
        write(out/'result.json',result);artifact_manifest(out)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,choices=(61001,61002),required=True)
    p.add_argument('--own-route-adapter',choices=('off','on_v1'),default='off')
    p.add_argument('--candidate',choices=('recovery','visual'),default='visual');p.add_argument('--execute',action='store_true')
    from harness.e2e_s3_entrance import OPTIONS
    p.add_argument('--entrance',choices=OPTIONS,default='off')
    a=p.parse_args()
    if not a.execute:print(json.dumps(dict(bundle_id=BUNDLE_ID,execution_started=False,adapter=a.own_route_adapter)));return 0
    if a.own_route_adapter=='off':raise ValueError('OWN_ROUTE_ADAPTER_OFF')
    from scripts.run_s3_x86_probe import archive_guard
    archive_guard(a.expected_source_sha,a.output)
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.seed,a.own_route_adapter,a.candidate,a.entrance),a.output)
    finally:undo()
    print(json.dumps(r));return int(r['status']!='DEV_STAGE_FINISHED')


if __name__=='__main__':raise SystemExit(main())
