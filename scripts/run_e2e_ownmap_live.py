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


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def bundle(sha,seed,profile,*,enabled=False,relook='off',options=Options()):
    if profile not in PROFILES or seed not in (61001,61002,61003,61004):raise ValueError('REGISTERED_MODEL_SEED_REQUIRED')
    if relook not in ('off','on_v1'):raise ValueError('UNKNOWN_RELOOK_TOGGLE')
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
            covariance_inflation='nees_frozen_v1' if enabled else 'off',
            setdown_reobserve='boundary_reobserve_v1' if enabled else 'off',setdown_only_when_relook=relook))
    from harness.python_source_closure import source_closure
    paths=set(source_closure(ROOT,['scripts/run_e2e_ownmap_live.py','sim/e2e_ownmap_live.py',
        'harness/e2e_live_transport.py','harness/e2e_live_mapping.py','harness/e2e_s4_live.py',
        'scripts/s4_proxy_relay.py','scripts/s4_reverse_tunnel.py','scripts/e2e_gemini_keychain.py',
        'scripts/evaluate_e2e_ownmap_live.py']))
    paths.update((WORKFLOW,RECORD+'/azure-plan.json','configs/e2e_s3_test_runtime_v1.json',
        'configs/s2_v133_full_template.json','configs/e2e_nees_egomap70_dev_v1.json',
        'configs/zone_study_dev/e2e_one_beam_ownmap.json'))
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
            map_frames=len(v.goal.e2e_observed),command=v.nav_command) for r,v in robots.items()},
        latest_route_wait=transport.last_route_error if transport else None)


def run(b,out,receipt,*,backend_factory=None):
    if not b['e2e_options']['enabled']:raise ValueError('E2E_LIVE_TOGGLE_OFF')
    from harness.e2e_live_mapping import Robot,Link
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
    def stop(*_):raise KeyboardInterrupt('EARLY_HEALTH_OR_TASK_STOP')
    previous=signal.signal(signal.SIGTERM,stop)
    try:
        for p,sha in b['source_sha256'].items():
            if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=sha:raise ValueError('SOURCE_HASH_MISMATCH:'+p)
        options=Options(**b['study_options'])
        cov=json.loads((ROOT/'configs/e2e_nees_egomap70_dev_v1.json').read_text())
        robots={r:Robot(r,b['seed']+i,cov,options,relook=b['e2e_options']['setdown_only_when_relook'])
                for i,r in enumerate(('r1','r2','r3'))}
        backend=(backend_factory or PhysicsBackend)(b,out,seed=b['seed'])
        backend.reset(b['reset_cap_s']);origin=backend.now
        backend.set_deadline(origin+b['case_cap_s'])
        for rid,robot in robots.items():
            for sid,pwm in SEARCH.items():
                a=dict(kind='look',pan_pulse=pwm) if sid==6 else dict(kind='arm',servo_id=sid,pulse=pwm)
                backend.issue(rid,a);robot.commanded(a,0.)
        profile=copy.deepcopy(load_registry()['driver_profiles'][b['driver_profile']])
        if digest(profile)!=b['driver_profile_sha256']:raise ValueError('MODEL_PROFILE_HASH_MISMATCH')
        profile.update(profile_id=b['driver_profile'],proxy_url=f'http://127.0.0.1:{PORTS[b["driver_profile"]]}/v1/chat/completions')
        profile['sha256']=digest(profile)
        budget=MainStudyBudget.create(out/'budget.sqlite');key=out.parent.name
        budget.register_cohort(key,token_cap=800000,unknown_usage_charge_tokens=16000,
            prereg_sha256=b['source_sha256'][RECORD+'/azure-plan.json'],source={'source_sha':b['source_sha']})
        budget.start_run(key,cohort_id=key,bundle_id=BUNDLE_ID,bundle_sha256=digest(b),record={'research_result':False})
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
                            setdown_only_when_relook=b['e2e_options']['setdown_only_when_relook'])
        host.trial.dialogue.motion_connected=True
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
                        remembered_B=robot.goal.entities.get('B'),stage=robot.goal.stage,command=robot.nav_command))
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
                if p['wall_s']>=b['initial_health_wall_s'] and not (p['first_model_response'] and p['own_map_B_generated']):
                    write(out/'initial-check.json',{**p,'passed':False,'reason':'MODEL_OR_OWN_B_STARTUP_MISSING'})
                    raise RuntimeError('INITIAL_HEALTH_FAILED')
                if p['first_model_response'] and p['own_map_B_generated'] and now>=10:
                    write(out/'initial-check.json',{**p,'passed':True})
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
        signal.signal(signal.SIGTERM,previous)
        if transport is not None:
            result.update(setdowns=transport.setdowns,controller_failure=transport.failure,
                own_map_completed=any(e['event']=='own_map_B_route_generated' for e in transport.events),
                start_to_finish_transport=transport.done)
            write(out/'transport-trace.json',transport.events)
        if host is not None:
            from harness.llm_completion import normal_completion
            saved=host.save(out/'llm');result.update(model_calls=len(host.trial.send_ledger.entries),
                model_usage=saved['model_usage'],response_wall_s=saved['response_wall_s'],
                LLM_operated=any(normal_completion(r.get('completion')) for r in host.trial.send_ledger.entries))
        for rid,robot in robots.items():
            write(out/f'{rid}-ownmap-final.json',robot.goal.snapshot())
            write(out/f'{rid}-relook.json',robot.goal.e2e_relook.events)
        if backend is not None:
            result['sim_s']=backend.now-origin
            for rid in robots:backend.issue(rid,dict(kind='hold'))
            backend.close()
            from scripts.evaluate_e2e_ownmap_live import evaluate
            evaluation=evaluate(out,result,transport.events if transport else [],origin)
            write(out/'evaluation.json',evaluation)
            result['start_to_finish_transport']=evaluation['start_to_finish_transport']
            result['drops']=evaluation['drops']
        result.update(wall_s=time.monotonic()-started,frames=frames_seen)
        result['E2E_success']=all(result[k] for k in ('LLM_operated','own_map_completed','start_to_finish_transport'))
        write(out/'result.json',result)
        hashes={}
        for p in out.rglob('*'):
            if p.is_file() and p.name!='artifacts.sha256.json':
                with p.open('rb') as stream:hashes[str(p.relative_to(out))]=hashlib.file_digest(stream,'sha256').hexdigest()
        write(out/'artifacts.sha256.json',hashes)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True)
    p.add_argument('--driver-profile',choices=PROFILES,required=True);p.add_argument('--relay-receipt',type=Path,required=True)
    p.add_argument('--e2e-live',action='store_true');p.add_argument('--event-driven-llm',action='store_true')
    p.add_argument('--compact-prompt',action='store_true');p.add_argument('--setdown-only-when-relook',choices=('off','on_v1'),default='off')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    b=bundle(a.expected_source_sha,a.seed,a.driver_profile,enabled=a.e2e_live,relook=a.setdown_only_when_relook,
             options=Options(a.event_driven_llm,a.compact_prompt,'en'))
    if not a.execute:print(json.dumps(b));return
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.environ.get('MUJOCO_GL')!='osmesa':
        raise ValueError('AZURE_X86_OSMESA_ONLY')
    if not a.output.resolve().is_relative_to(Path.home()/'ugrp-sim/runs'):raise ValueError('PERSISTENT_RUN_REQUIRED')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()!=a.expected_source_sha:raise ValueError('COMMITTED_SHA_REQUIRED')
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(b,a.output,a.relay_receipt)
    finally:undo()
    print(json.dumps(r));return int(r['status']!='FINISHED')


if __name__=='__main__':raise SystemExit(main())
