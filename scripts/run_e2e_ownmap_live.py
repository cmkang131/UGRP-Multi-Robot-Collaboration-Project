"""v185: bounded own RGB -> GoalRoute -> S4 dialogue -> S3 Azure execution."""
import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time
import traceback
from harness.zone_study_contract import digest
from harness.s4_event_policy import Options

ROOT=Path(__file__).resolve().parents[1]
BUNDLE_ID='e2e-ownmap-live-v185'
RECORD='experiments/2026-10-11-e2e-azure-first'
WORKFLOW='configs/simulation_workflows.d/e2e_ownmap_live_v185.json'
PROFILES=('study_gemma4_31b_v1','main_study_gemini_v1')
PORTS=dict(zip(PROFILES,(18393,18391)))


def relay_url(profile, decider='off'):
    # Paired Gemma/Jev uses the existing second loopback relay independently.
    port = 18391 if decider == 'jev_v1' else PORTS[profile]
    return f'http://127.0.0.1:{port}/v1/chat/completions'


from harness.e2e_result_writer import write, Finalizer

def bundle(sha,seed,profile,*,enabled=False,relook='off',options=Options(),decider='off',exploration_progress='off',pose_fix='off',path_follow='off',dev_light=False,wall_cap_s=12600.,stall_odometry='off',stall_recovery='off',stall_noise='off',stall_bundle=False,mapping_budget='off',exact_speedups=None,speed_bundle=False,runtime_registration='off'):
    if profile not in PROFILES or seed not in (61001,61002,61003,61004):raise ValueError('REGISTERED_MODEL_SEED_REQUIRED')
    if relook not in ('off','on_v1'):raise ValueError('UNKNOWN_RELOOK_TOGGLE')
    if decider not in ('off','jev_v1'):raise ValueError('UNKNOWN_DECIDER')
    if decider!='off' and profile!='study_gemma4_31b_v1':raise ValueError('JEV_GEMMA_REQUIRED')
    if exploration_progress not in ('off','frontier_progress_v1'):raise ValueError('UNKNOWN_EXPLORATION_PROGRESS')
    if pose_fix not in ('off','innovation'):raise ValueError('UNKNOWN_E2E_POSE_FIX')
    if path_follow not in ('off','rpp_v1'):raise ValueError('UNKNOWN_PATH_FOLLOW')
    if not 0 < wall_cap_s <= 12600:raise ValueError('FINITE_WALL_CAP_REQUIRED')
    if mapping_budget not in ('off','case_cap_v1'):raise ValueError('UNKNOWN_MAPPING_BUDGET')
    from harness.e2e_stall_odometry import Options as StallOptions
    stall=StallOptions(stall_odometry,stall_recovery,stall_noise)
    from harness.e2e_exact_speedups import Options as SpeedOptions
    speed=SpeedOptions(**(exact_speedups or {}))
    from harness.zone_study_llm_driver import load_registry
    b=json.loads((ROOT/'configs/e2e_s3_test_runtime_v1.json').read_text())
    # The template contributes physical/calibration constants only. Its authored
    # runtime config is never passed into the own-map controller.
    b.update(schema='ugrp.e2e_ownmap_live.v185',execution_bundle_id=BUNDLE_ID,workflow_version='7.78.0',
        source_sha=sha,seed=seed,scenario_id='e2e_one_beam_ownmap',map_id='zone_wide_door_e2e_b80_v1',
        case='pair',check='ownmap-live',host='azure',condition='peer_en',research_result=False,
        route_source='own_map',fixture_restore=False,weld=False,case_cap_s=1800.,wall_cap_s=12600.,
        initial_health_wall_s=240.,contact_profile='cargo_noslip_v1',
        pair_drop_guard='contact_com_v1',final_release_guard='supported_phase',
        driver_profile=profile,driver_profile_sha256=digest(load_registry()['driver_profiles'][profile]),
        study_options=dataclasses.asdict(options),
        e2e_options=dict(enabled=enabled,own_inputs='on_v1' if enabled else 'off',dialogue='on_v1' if enabled else 'off',
            pulse_budget='fractional_duration_v1' if enabled else 'off',
            own_route='goal_route_v1' if enabled else 'off',arrival_gate='rgb_geometry_v1' if enabled else 'off',
            goal_geometry='e2e_b80_v1' if enabled else 'off',
            covariance_inflation='nees_frozen_v1' if enabled else 'off',
            setdown_reobserve='boundary_reobserve_v1' if enabled else 'off',setdown_only_when_relook=relook))
    b['e2e_options'].update(decider=decider,exploration_progress=exploration_progress,pose_fix=pose_fix)
    if path_follow!='off' or dev_light:
        b['e2e_options'].update(path_follow=path_follow,dev_light=dev_light)
    b['wall_cap_s']=wall_cap_s
    if decider=='jev_v1':
        b.update(schema='ugrp.e2e_ownmap_live.v192',execution_bundle_id='e2e-ownmap-jev-v192',workflow_version='7.85.0')
    if exploration_progress!='off' or pose_fix!='off':
        b.update(schema='ugrp.e2e_ownmap_live.v194',execution_bundle_id='e2e-explore-posefix-v194',workflow_version='7.87.0')
    if path_follow!='off' or dev_light:
        b.update(schema='ugrp.e2e_ownmap_live.v197',execution_bundle_id='e2e-rpp-lookahead-v197',workflow_version='7.90.0')
    if stall.enabled or stall_bundle:
        b['e2e_options'].update(dataclasses.asdict(stall))
        b.update(schema='ugrp.e2e_ownmap_live.v198',execution_bundle_id='e2e-stall-odometry-v198',workflow_version='7.91.0')
    if mapping_budget!='off':
        b['e2e_options'].update(mapping_budget=mapping_budget,mapping_budget_s=b['case_cap_s'])
        b.update(schema='ugrp.e2e_ownmap_live.v199',execution_bundle_id='e2e-stall-budget-v199',workflow_version='7.92.0')
    if speed_bundle or any(vars(speed).values()):
        b['e2e_options']['exact_speedups']=dataclasses.asdict(speed)
        b.update(schema='ugrp.e2e_ownmap_live.v200',execution_bundle_id='e2e-exact-speed-v200',workflow_version='7.93.0')
    from harness.e2e_runtime_registration import register
    runtime_assets=register(b,runtime_registration)
    from harness.python_source_closure import source_closure
    paths=set(source_closure(ROOT,['scripts/run_e2e_ownmap_live.py','sim/e2e_ownmap_live.py',
        'harness/e2e_live_transport.py','harness/e2e_live_mapping.py','harness/e2e_s4_live.py',
        'scripts/s4_proxy_relay.py','scripts/s4_reverse_tunnel.py','scripts/e2e_gemini_keychain.py',
        'scripts/evaluate_e2e_ownmap_live.py']))
    paths.update((WORKFLOW,RECORD+'/azure-plan.json','configs/e2e_s3_test_runtime_v1.json',
        'configs/s2_v133_full_template.json','configs/e2e_nees_egomap70_dev_v1.json',
        'configs/zone_study_dev/e2e_one_beam_ownmap.json'))
    if decider=='jev_v1':paths.add('configs/simulation_workflows.d/e2e_ownmap_jev_v192.json')
    if exploration_progress!='off' or pose_fix!='off':
        paths.add('configs/simulation_workflows.d/e2e_explore_posefix_v194.json')
    if path_follow!='off' or dev_light:
        paths.add('configs/simulation_workflows.d/e2e_rpp_lookahead_v197.json')
    if stall.enabled or stall_bundle:paths.add('configs/simulation_workflows.d/e2e_stall_odometry_v198.json')
    if mapping_budget!='off':paths.add('configs/simulation_workflows.d/e2e_stall_budget_v199.json')
    if speed_bundle or any(vars(speed).values()):paths.add('configs/simulation_workflows.d/e2e_exact_speed_v200.json')
    paths.update(runtime_assets)
    b['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(paths)}
    return b


def health(robots,host,transport,sim_s,wall_s,frames):
    from harness.llm_completion import normal_completion
    ledger=host.trial.send_ledger.entries if host else []
    normal=[e for e in ledger if normal_completion(e.get('completion'))]
    r1=robots.get('r1')
    generated=bool(r1 and r1.goal.entities.get('B'))
    return dict(wall_s=wall_s,sim_s=sim_s,frames=frames,model_attempts=len(ledger),
        first_model_response=bool(normal),own_map_B_generated=generated,
        own_B_boundary_remembered=bool(r1 and 'B' in r1.goal.e2e_gate.references),
        own_route_generated=bool(r1 and r1.packet is not None),
        phase=transport.state if transport else 'boot',setdowns=transport.setdowns if transport else 0,
        robots={r:dict(pose_own_m=v.goal.explorer.local_pose.tolist(),stage=v.goal.stage,
            map_frames=len(v.goal.e2e_observed),command=v.nav_command,
            translation_commands=v.translation_commands) for r,v in robots.items()},
        latest_route_wait=transport.last_route_error if transport else None)


def startup_decision(progress, b):
    ok=progress['first_model_response'] and progress['own_map_B_generated']
    if b['e2e_options'].get('exploration_progress','off')!='off':
        ok=progress['first_model_response'] and all(
            progress['robots'][r]['map_frames']>1 and progress['robots'][r]['translation_commands']>0
            for r in ('r1','r2'))
    failed=progress['wall_s']>=b['initial_health_wall_s'] and not ok
    return dict(passed=bool(ok),would_stop=bool(failed),
                stop=bool(failed and not b['e2e_options'].get('dev_light',False)))


def run(b,out,receipt,*,backend_factory=None):
    if not b['e2e_options']['enabled']:raise ValueError('E2E_LIVE_TOGGLE_OFF')
    from harness.e2e_runtime_registration import require_current
    require_current(b,ROOT)
    from harness.e2e_live_mapping import Robot,Link
    from harness.e2e_exact_speedups import Options as SpeedOptions
    from harness.e2e_stall_odometry import Options as StallOptions
    from harness.e2e_live_transport import Transport
    from harness.e2e_s4_live import Host
    from harness.s4_tunnel_recovery import RecoveryLedger
    from harness.zone_study_llm_driver import load_registry,client_factory
    from harness.zone_study_integration import ModelAdapter
    from harness.zone_main_budget import MainStudyBudget
    from harness.zone_environment_registry import load_scenario,bundle_for
    from harness.zone_event_scheduler import CallPolicy
    from harness.zone_study_decisions import DecisionLimits
    from harness.active_camera import SEARCH
    from sim.e2e_ownmap_live import PhysicsBackend
    out.mkdir(parents=True,exist_ok=False);write(out/'bundle.json',b)
    result=dict(status='HOST_ERROR',source_sha=b['source_sha'],seed=b['seed'],model=b['driver_profile'],
        condition=b['condition'],options=b['e2e_options'],LLM_operated=False,own_map_completed=False,
        start_to_finish_transport=False,E2E_success=False,setdowns=0,model_calls=0,
        physical_hardware=False,route_source='own_map',host='azure',class_='dev',pr=433)
    started=time.monotonic();backend=host=transport=None;robots={};frames_seen=0;origin=0.
    milestones={};initial_recorded=False
    finalizer=Finalizer(out,result)
    finalizer.install()
    try:
        for p,sha in b['source_sha256'].items():
            if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha:raise ValueError('SOURCE_HASH_MISMATCH:'+p)
        options=Options(**b['study_options'])
        cov=json.loads((ROOT/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
        robots={r:Robot(r,b['seed']+i,cov,options,relook=b['e2e_options']['setdown_only_when_relook'],
                        goal_geometry=b['e2e_options']['goal_geometry'],
                        exploration_progress=b['e2e_options'].get('exploration_progress','off'),
                        pose_fix=b['e2e_options'].get('pose_fix','off'),
                        path_follow=b['e2e_options'].get('path_follow','off'),
                        stall_options=StallOptions(**{k:b['e2e_options'].get(k,'off') for k in ('stall_odometry','stall_recovery','stall_noise')}),
                        mapping_budget_s=b['e2e_options'].get('mapping_budget_s'),
                        exact_speedups=SpeedOptions(**b['e2e_options'].get('exact_speedups',{})))
                for i,r in enumerate(('r1','r2','r3'))}
        for robot in robots.values():robot.decider=b['e2e_options'].get('decider','off')
        offered=json.loads(receipt.read_text())
        if offered.get('decider','off')!=b['e2e_options'].get('decider','off'):
            raise ValueError('RELAY_DECIDER_MISMATCH')
        backend=(backend_factory or PhysicsBackend)(b,out,seed=b['seed'])
        backend.reset(b['reset_cap_s']);origin=backend.now
        backend.set_deadline(origin+b['case_cap_s'])
        for rid,robot in robots.items():
            for sid,pwm in SEARCH.items():
                a=dict(kind='look',pan_pulse=pwm) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pwm)
                backend.issue(rid,a);robot.commanded(a,0.)
        profile=copy.deepcopy(load_registry()['driver_profiles'][b['driver_profile']])
        if digest(profile)!=b['driver_profile_sha256']:raise ValueError('MODEL_PROFILE_HASH_MISMATCH')
        profile.update(profile_id=b['driver_profile'],proxy_url=relay_url(b['driver_profile'],b['e2e_options'].get('decider','off')))
        profile['sha256']=digest(profile)
        budget=MainStudyBudget.create(out/'budget.sqlite');key=out.parent.name
        budget.register_cohort(key,token_cap=800000,unknown_usage_charge_tokens=16000,
            prereg_sha256=b['source_sha256'][RECORD+'/azure-plan.json'],source={'source_sha':b['source_sha']})
        budget.start_run(key,cohort_id=key,bundle_id=b['execution_bundle_id'],bundle_sha256=digest(b),record={'research_result':False})
        ledger=RecoveryLedger(receipt=receipt,remote_url=profile['proxy_url'],store_dir=out/'wire',budget=budget,
            run_key=key,profile=profile,tunnel_recovery=True,retry_429=True)
        ledger.retry_snapshot=lambda:dict(sim_s=backend.now,frames=backend.frame)
        scenario=load_scenario('e2e_one_beam_ownmap')
        host=Host(scenario,condition='peer_en',links={r:Link.build(v,'peer_en') for r,v in robots.items()},
            seed=b['seed'],map_bundle=bundle_for(scenario),horizon_s=b['case_cap_s'],
            model_adapter=ModelAdapter(client_factory(profile),ledger),code_sha=b['source_sha'],
            e2e_own_inputs_v1='on_v1',e2e_dialogue_v1='on_v1',
            policy=CallPolicy(max_calls_per_actor=120,max_http_attempts_per_actor=120,max_attempts_total=300,max_retries=0),
            decision_limits=DecisionLimits(max_calls_total=300,max_utterances_per_actor=80,max_utterances_total=160))
        profiles=json.loads((ROOT/'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
        transport=Transport(robots,host.trial.dialogue,profiles,pulse_budget=b['e2e_options']['pulse_budget'],
                            setdown_only_when_relook=b['e2e_options']['setdown_only_when_relook'],
                            dev_light=b['e2e_options'].get('dev_light',False))
        host.trial.dialogue.motion_connected=True
        host.trial.provenance.update(provider=offered.get('upstream',host.trial.provenance['provider']),
            decider=b['e2e_options'].get('decider','off'))
        backend.authorize_pulse=lambda rid,a,t:transport.authorize(rid,a,round(t-origin,8))
        backend.final_segment_getter=lambda:bool(transport.plan and transport.seg==len(transport.plan['own_route']['legs'])-1)
        for tick in range(round(b['case_cap_s']/.05)):
            now=round(backend.now-origin,8)
            if time.monotonic()-started>b['wall_cap_s']:raise TimeoutError('E2E_WALL_CAP')
            backend.eval_sample()
            if tick%4==0:
                raw=backend.capture()
                for rid,robot in robots.items():
                    obs,rgb=raw[rid]
                    own_obs={k:obs[k] for k in ('frame_id','sim_time','sha256','image')}
                    own_obs['sim_time']=round(obs['sim_time']-origin,8)
                    trace=robot.receive(own_obs,rgb)
                    backend._append(f'robots/{rid}/ownmap.jsonl',dict(t=now,frame_id=obs['frame_id'],
                        sha256=obs['sha256'],pose_own_m=robot.goal.explorer.local_pose.tolist(),
                        remembered_B=robot.goal.entities.get('B'),stage=robot.goal.stage,command=robot.nav_command,
                        pose_continuity=trace.get('pose_continuity'),exploration=trace.get('exploration'),
                        navigation_status=trace.get('status'),pulse=trace.get('pulse'),stall_odometry=trace.get('stall_odometry')))
                frames_seen+=1
                if not host.started:
                    write(out/'e2e-progress.json',health(robots,host,transport,now,time.monotonic()-started,frames_seen))
                    backend.flush()
                    host.begin(now)
            if not host.started:continue
            if tick%20==0:
                write(out/'e2e-progress.json',health(robots,host,transport,now,time.monotonic()-started,frames_seen))
                backend.flush()
            host.step_to(now)
            commands=transport.step(now)
            if tick%4==0 and transport.state=='mapping':
                commands += [(r,v.nav_command) for r,v in robots.items() if r!='r3' and v.packet is None]
            for rid,action in commands:
                backend.issue(rid,action);robots[rid].commanded(action,now)
            if tick%20==0:
                p=health(robots,host,transport,now,time.monotonic()-started,frames_seen)
                write(out/'e2e-progress.json',p);backend.flush()
                print(json.dumps(p,ensure_ascii=False),flush=True)
                decision=startup_decision(p,b)
                if not initial_recorded and (decision['would_stop'] or decision['passed'] and now>=10):
                    write(out/'initial-check.json',{**p,**decision})
                    initial_recorded=True
                if decision['stop']:raise RuntimeError('INITIAL_HEALTH_FAILED')
                for stage,reached in dict(LLM=p['first_model_response'],B_boundary=p['own_B_boundary_remembered'],
                        route=p['own_route_generated'],**{transport.state:True}).items():
                    if reached and stage not in milestones:
                        milestones[stage]=dict(sim_s=now,wall_s=p['wall_s'])
                        write(out/'stage-milestones.json',milestones)
            if transport.failure:result['status']='CONTROLLER_STOP';break
            if transport.done:result['status']='FINISHED';break
            backend.advance_to(origin+(tick+1)*.05)
        else:result['status']='SIM_BUDGET_EXHAUSTED'
    except (Exception,KeyboardInterrupt) as exc:
        result.update(status='EARLY_STOP' if isinstance(exc,KeyboardInterrupt) or str(exc)=='INITIAL_HEALTH_FAILED' else
            'PHYSICAL_STOP' if type(exc).__name__=='PhysicalStop' else 'HOST_ERROR',failure_type=type(exc).__name__,
            failure=str(exc),traceback=traceback.format_exc())
        if host is not None:host.failed=exc
    finally:
        finalizer.finalizing=True
        result.update(wall_s=time.monotonic()-started,frames=frames_seen,stage_milestones=milestones)
        if backend is not None:result['sim_s']=backend.now-origin
        finalizer.checkpoint()
        if transport is not None:
            result.update(setdowns=transport.setdowns,controller_failure=transport.failure,
                own_map_completed=any(e['event']=='own_map_B_route_generated' for e in transport.events))
            finalizer.attempt('transport',lambda:write(out/'transport-trace.json',transport.events))
        if host is not None:
            from harness.llm_completion import normal_completion
            result.update(model_calls=len(host.trial.send_ledger.entries),
                LLM_operated=any(normal_completion(r.get('completion')) for r in host.trial.send_ledger.entries))
            def save_host():
                saved=host.save(out/'llm')
                result.update(model_usage=saved['model_usage'],response_wall_s=saved['response_wall_s'])
                write(out/'jev-guard-events.json',host.trial.jev_guard_events)
            finalizer.attempt('llm',save_host)
        for rid,robot in robots.items():
            finalizer.attempt(rid+'-map',lambda:write(out/f'{rid}-ownmap-final.json',robot.goal.snapshot()))
            finalizer.attempt(rid+'-relook',lambda:write(out/f'{rid}-relook.json',robot.goal.e2e_relook.events))
        if backend is not None:
            for rid in robots:
                finalizer.attempt(rid+'-hold',lambda:backend.issue(rid,dict(kind='hold')))
            finalizer.attempt('backend-close',backend.close)
            def evaluate_result():
                from scripts.evaluate_e2e_ownmap_live import evaluate
                evaluation=evaluate(out,{**result,'start_to_finish_transport':bool(transport and transport.done)},
                                    transport.events if transport else [],origin)
                write(out/'evaluation.json',evaluation)
                result['start_to_finish_transport']=evaluation['start_to_finish_transport']
                result['drops']=evaluation['drops']
            finalizer.attempt('evaluation',evaluate_result)
        result['E2E_success']=not result['finalization_errors'] and all(
            result[k] for k in ('LLM_operated','own_map_completed','start_to_finish_transport'))
        finalizer.finish()
        hashes={}
        for p in out.rglob('*'):
            if p.is_file() and p.name!='artifacts.sha256.json':
                with p.open('rb') as stream:hashes[str(p.relative_to(out))]=hashlib.file_digest(stream,'sha256').hexdigest()
        write(out/'artifacts.sha256.json',hashes)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--driver-profile',choices=PROFILES,required=True);p.add_argument('--relay-receipt',type=Path,required=True)
    p.add_argument('--e2e-live',action='store_true');p.add_argument('--event-driven-llm',action='store_true')
    p.add_argument('--compact-prompt',action='store_true');p.add_argument('--setdown-only-when-relook',choices=('off','on_v1'),default='off')
    p.add_argument('--decider',choices=('off','jev_v1'),default='off')
    p.add_argument('--exploration-progress',choices=('off','frontier_progress_v1'),default='off')
    p.add_argument('--pose-fix',choices=('off','innovation'),default='off')
    p.add_argument('--path-follow',choices=('off','rpp_v1'),default='off')
    p.add_argument('--stall-odometry',choices=('off','rgb_gate_v1','rgb_pulse_gate_v1'),default='off')
    p.add_argument('--stall-recovery',choices=('off','backup_replan_v1'),default='off')
    p.add_argument('--stall-noise',choices=('off','amcl_alpha_v1'),default='off')
    p.add_argument('--stall-bundle',action='store_true')
    p.add_argument('--mapping-budget',choices=('off','case_cap_v1'),default='off')
    p.add_argument('--dev-light',action='store_true')
    p.add_argument('--wall-cap-s',type=float,default=12600.)
    p.add_argument('--exact-provenance-index',action='store_true')
    p.add_argument('--exact-sha-cache',action='store_true')
    p.add_argument('--exact-omit-copy',action='store_true')
    p.add_argument('--exact-scalar-cells',action='store_true')
    p.add_argument('--exact-geometry-cache',action='store_true')
    p.add_argument('--exact-speed-bundle',action='store_true')
    p.add_argument('--measure-sim-s',type=float,default=0.,help='External measurement stop; bundle horizon unchanged')
    p.add_argument('--measure-profile',action='store_true')
    p.add_argument('--runtime-registration',choices=('off','reviewed_v1'),default='off')
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    b=bundle(a.expected_source_sha,a.seed,a.driver_profile,enabled=a.e2e_live,relook=a.setdown_only_when_relook,
             options=Options(a.event_driven_llm,a.compact_prompt,'en'),decider=a.decider,
             exploration_progress=a.exploration_progress,pose_fix=a.pose_fix,
             path_follow=a.path_follow,dev_light=a.dev_light,wall_cap_s=a.wall_cap_s,
             stall_odometry=a.stall_odometry,stall_recovery=a.stall_recovery,stall_noise=a.stall_noise,stall_bundle=a.stall_bundle,mapping_budget=a.mapping_budget,
             exact_speedups=dict(provenance_index=a.exact_provenance_index,sha_validation_cache=a.exact_sha_cache,omit_discarded_copy=a.exact_omit_copy,scalar_cells=a.exact_scalar_cells,geometry_cache=a.exact_geometry_cache),
             speed_bundle=a.exact_speed_bundle,runtime_registration=a.runtime_registration)
    if not a.execute:print(json.dumps(b));return
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.environ.get('MUJOCO_GL')!='osmesa':
        raise ValueError('AZURE_X86_OSMESA_ONLY')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=a.expected_source_sha:raise ValueError('COMMITTED_SHA_REQUIRED')
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:
        if a.measure_sim_s:
            from scripts.e2e_speed_measure import measured_run
            r=measured_run(run,b,a.output,a.relay_receipt,a.measure_sim_s,a.measure_profile)
        else:r=run(b,a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']!='FINISHED')


if __name__=='__main__':raise SystemExit(main())
