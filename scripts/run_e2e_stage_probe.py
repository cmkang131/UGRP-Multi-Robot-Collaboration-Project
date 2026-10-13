#!/usr/bin/env python3
"""Opt-in v387 staged own-map probe. Prepare is offline; run is Linux only."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import time
import traceback
from types import SimpleNamespace

from harness.e2e_stage_checkpoint import prepare, replay, digest, verify_recipe, own_map_record
from harness.e2e_result_writer import write, Finalizer

ROOT=Path(__file__).resolve().parents[1]
BASELINE_DIGEST='038b4b838c9e56335c42d0739de82e33d18c9a4affe0ed9ab9bc559da09e0fe9'
MODES={'v375':'off','v384':'regulated_v1','v385':'gaze_v1','v386':'track_gaze_v1'}


def read_json(path):
    data=Path(path).read_bytes()
    if Path(path).suffix=='.zst':data=subprocess.check_output(['zstd','-qdc',str(path)])
    return json.loads(data)


def save_recipe(path, recipe):
    data=(json.dumps(recipe,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n').encode()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if len(data)>65536 and path.suffix!='.zst':raise ValueError('LARGE_CHECKPOINT_REQUIRES_JSON_ZST')
    if path.suffix=='.zst':
        encoded=subprocess.check_output(['zstd','-q','-c'],input=data)
        if subprocess.check_output(['zstd','-q','-d','-c'],input=encoded)!=data:raise ValueError('COMPRESSION_ROUNDTRIP')
    else:encoded=data
    path.write_bytes(encoded)
    write(path.with_suffix(path.suffix+'.manifest.json'),dict(sha256=hashlib.sha256(encoded).hexdigest(),
        decoded_sha256=hashlib.sha256(data).hexdigest(),bytes=len(encoded),decoded_bytes=len(data)))


def stage_bundle(recipe, baseline, condition, seed, sha):
    if baseline['execution_bundle_id']!='e2e18-v375':raise ValueError('V375_BASELINE_REQUIRED')
    b=copy.deepcopy(baseline)
    b.update(schema='ugrp.e2e_stage_probe.v387',execution_bundle_id='e2e18-v387',workflow_version='7.280.0',
        parent_controller='e2e18-'+condition,source_sha=sha,seed=seed,case_cap_s=300.,
        source_checkpoint_sha256=recipe['checkpoint_sha256'],E2E_success_eligible=False)
    b['e2e_options']['grasp_once']=MODES[condition]
    if b['e2e_options'].get('body_controller','off')!='off':raise ValueError('STAGE_BODY_PROVIDER_UNSUPPORTED')
    # Never attach an ultrasonic/simulator observation provider in this adapter.
    b['stage_observations']=['own_RGB','static_map','own_issued_commands']
    b['source_sensors']=b.pop('sensors',None)
    b['stage_sensors']='none; source prefix admits only zero ultrasonic corrections'
    b['stage_success_criterion']='pair_stage_probe grasp_lift: bilateral positive-force contacts, >=0.03 m lift, <=10 deg tilt for 0.30 s'
    return b


def commands_for_stage(tr, now):
    if tr.state in ('mapping','align'):return tr.step(now)
    if tr.state in ('grasp_close','grasp_lift'):return tr._drain(now)
    raise ValueError('STAGE_ESCAPE:'+tr.state)


def stage_metrics(events, first, success, elapsed):
    starts={r:sum(e.get('event')=='own_pregrasp_acquisition_begin' and e.get('robot_id')==r for e in events) for r in ('r1','r2')}
    return dict(both_held=success,first_attempt_success=success and not any(starts.values()),
        # Conservative: any acquisition after staged align entry counts, even initial search.
        reacquisition_entries=starts,held_first_s=first,
        both_held_s=elapsed if success else None,censored_s=None if success else elapsed,
        held_gap_s=abs(first['r1']-first['r2']) if len(first)==2 else None)


def run(args):
    if not args.enable_stage:raise ValueError('STAGE_TOGGLE_OFF')
    if platform.system()!='Linux':raise ValueError('NO_MAC_PHYSICS_OR_RENDER')
    if not 0 < args.cap_s <=300 or abs(args.cap_s/.05-round(args.cap_s/.05))>1e-7:raise ValueError('STAGE_CAP_MAX_300_ON_50MS_TICKS')
    if not math.isfinite(args.wall_cap_s) or not 0<args.wall_cap_s<=1800:raise ValueError('FINITE_STAGE_WALL_CAP_MAX_1800')
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if sha!=args.expected_source_sha:raise ValueError('SOURCE_SHA_MISMATCH')
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT,text=True).strip():
        raise ValueError('DIRTY_EXECUTION_SOURCE')
    recipe=read_json(args.checkpoint);verify_recipe(recipe)
    baseline=read_json(args.baseline_bundle)
    if digest(baseline)!=BASELINE_DIGEST:raise ValueError('PINNED_R80_BASELINE_REQUIRED')
    b=stage_bundle(recipe,baseline,args.condition,args.seed,sha)
    tracked=subprocess.check_output(['git','ls-files','harness','sim','scripts','configs'],cwd=ROOT,text=True).splitlines()
    b['original_source_sha256']=b.pop('source_sha256',{})
    b['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in tracked if (ROOT/p).is_file()}
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    write(out/'bundle.json',b)
    write(out/'RUN_META.json',dict(schema='ugrp.run_meta.v1',**{'class':'dev'},pr=475,
        branch='claude/e2e18-grasp1',sha=sha,batch=args.batch))
    result=dict(source_sha=sha,status='HOST_ERROR',E2E_success_eligible=False,physical_hardware=False,
        checkpoint_sha256=recipe['checkpoint_sha256'],condition=args.condition,seed=args.seed,
        stage=recipe['stage'],source_run=recipe['source_run'],first_attempt_success=False,both_held=False)
    finalizer=Finalizer(out,result);finalizer.install()
    backend=None;tr=None;elapsed=0.;started=time.monotonic();physics_started=None
    command_count=0;cycle_counts=dict(r1=0,r2=0);previous_cycles=dict(r1=0,r2=0)
    from sim.e2e_stage_staging import HeldWindow
    held=HeldWindow()
    try:
        robots,receipt=replay(recipe,args.raw,grasp_once=MODES[args.condition])
        write(out/'own-restore.json',receipt)
        result['own_map_sha256']={rid:r['map_sha256'] for rid,r in receipt.items()}
        for rid,r in robots.items():write(out/f'{rid}-ownmap-entry.json',own_map_record(r))
        from scripts.run_e2e_ownmap_live import make_transport,ownmap_record
        tr=make_transport(b,robots,SimpleNamespace(approved=False,claims=set(),proposal=None))
        for rid,r in robots.items():
            if digest(own_map_record(r))!=receipt[rid]['map_sha256']:raise ValueError('OWN_MAP_HANDOFF_MISMATCH:'+rid)
        cutoff=recipe['cutoff_s'];tr.set(recipe['stage'],cutoff)
        tr.event(cutoff,'stage_probe_entry',setup='TEST_SETUP_GT',prior_protocol_omitted=True,
                 controller_feedback=False,checkpoint_sha256=recipe['checkpoint_sha256'])
        from sim.e2e_ownmap_live import PhysicsBackend
        from sim.e2e_stage_staging import apply,bilateral_contacts
        backend=PhysicsBackend(b,out,seed=args.seed);backend.reset(b['reset_cap_s'])
        staging=apply(backend,recipe['setup_only'],{r:v.servo for r,v in robots.items()})
        write(out/'eval_only/staging.json',staging)
        result['initial_physics_sha256']=staging['integration_sha256']
        origin=backend.now-cutoff;backend.set_deadline(backend.now+args.cap_s)
        backend.frame=max(f['frame_id'] for d in recipe['own_inputs'].values() for f in d['frames'])+1
        for rid,port in backend.ports.items():port._frame_id=backend.frame
        from harness.e2e_pulse_admission import Admission
        dispatch=Admission(b['e2e_options'].get('pulse_admission','off'))
        from harness.e2e_mapping_cadence import period
        from harness.e2e_observation_cadence import configure
        observation_ticks=round(period(b['e2e_options'].get('mapping_cadence','off'),tr.state)/.05)
        for r in robots.values():configure(r.goal,'on_v1',observation_ticks*.05)
        from harness.e2e_speed4 import processing_due
        from harness.e2e_camera_settle import receive
        from sim.e2e_stage_physics import update
        from harness.e2e_camera_hold import actions as camera_hold
        from harness.e2e_approach_efficiency import issued
        physics_started=time.monotonic()
        for tick in range(round(args.cap_s/.05)+1):
            now=round(backend.now-origin,8);elapsed=round(now-cutoff,8)
            if time.monotonic()-physics_started>args.wall_cap_s:raise TimeoutError('STAGE_WALL_CAP')
            backend.eval_sample()
            labels=bilateral_contacts(backend,recipe['setup_only']['beam']['z'])
            backend._append('eval_only/stage-held.jsonl',dict(t=elapsed,grasp_lift_labels=labels))
            if held.sample(elapsed,labels):result['status']='BOTH_HELD';break
            if elapsed>=args.cap_s-1e-8:result['status']='SIM_BUDGET_EXHAUSTED';break
            if tick%observation_ticks==0:
                frames=backend.capture()
                for rid,r in robots.items():
                    if not processing_due(r,now,tr.state):continue
                    obs,rgb=frames[rid];own={k:obs[k] for k in ('frame_id','sim_time','sha256','image')}
                    own['sim_time']=now
                    trace=receive(r,own,rgb,now,backend._append)
                    if trace is not None:backend._append(f'robots/{rid}/ownmap.jsonl',ownmap_record(r,obs,trace,now))
            commands=commands_for_stage(tr,now)
            for rid in cycle_counts:
                cycle=(getattr(robots[rid],'carrier_approach',None) or {}).get('cycle',0)
                cycle_counts[rid]+=max(0,cycle-previous_cycles[rid]);previous_cycles[rid]=cycle
            update(backend,tr.state)
            if tr.state=='mapping' and tick%4==0:
                from harness.e2e_pregrasp_acquire import mapping_commands
                commands+=mapping_commands(tr,now)
            if recipe['stage']=='mapping' and robots['r1'].packet is not None:
                result['status']='OWN_ROUTE_GENERATED';break
            commands=camera_hold(commands,robots,tr.state,b['e2e_options'].get('camera_hold','off'))
            commands=dispatch.step(now,tr.arm_clearance.filter(tr,now,commands))
            for rid,action in commands:
                command_count+=1
                backend.issue(rid,action);robots[rid].commanded(action,now);issued(tr,rid,action,now)
            if tr.failure:result['status']='CONTROLLER_STOP';break
            backend.advance_to(origin+cutoff+(tick+1)*.05)
            if tick%20==0:
                write(out/'progress.json',dict(sim_s=elapsed,phase=tr.state,wall_s=time.monotonic()-physics_started))
    except (Exception,KeyboardInterrupt) as exc:
        result.update(status='EARLY_STOP' if isinstance(exc,KeyboardInterrupt) else
            'PHYSICAL_STOP' if type(exc).__name__=='PhysicalStop' else 'HOST_ERROR',error=str(exc),traceback=traceback.format_exc())
    finally:
        finalizer.finalizing=True
        result.update(scan_cycles=cycle_counts,commands=command_count,model_calls=0,provider_cost_usd=0,wall_s=time.monotonic()-started,sim_s=elapsed,
            physics_wall_s=None if physics_started is None else time.monotonic()-physics_started)
        if tr is not None:finalizer.attempt('transport-trace',lambda:write(out/'transport-trace.json',tr.events))
        if backend is not None:finalizer.attempt('backend-close',backend.close)
        if tr is not None:result.update(stage_metrics(tr.events,held.first,result['status']=='BOTH_HELD',elapsed))
        finalizer.finish()
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--raw',type=Path,required=True)
    prep.add_argument('--stage',choices=('mapping','align'),default='align');prep.add_argument('--cutoff',type=float)
    prep.add_argument('--output',type=Path,required=True)
    r=sub.add_parser('run');r.add_argument('--enable-stage',action='store_true')
    r.add_argument('--checkpoint',type=Path,required=True);r.add_argument('--raw',type=Path,required=True)
    r.add_argument('--baseline-bundle',type=Path,required=True);r.add_argument('--condition',choices=MODES,required=True)
    r.add_argument('--seed',type=int,required=True);r.add_argument('--expected-source-sha',required=True)
    r.add_argument('--cap-s',type=float,default=300.);r.add_argument('--wall-cap-s',type=float,default=1800.)
    r.add_argument('--batch',required=True);r.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='prepare':
        recipe=prepare(a.raw,stage=a.stage,cutoff=a.cutoff);save_recipe(a.output,recipe)
        print(json.dumps({k:recipe[k] for k in ('source_run','stage','cutoff_s','checkpoint_sha256')}))
    else:
        result=run(a);print(json.dumps(result));return 0 if result['status'] in ('BOTH_HELD','OWN_ROUTE_GENERATED','SIM_BUDGET_EXHAUSTED','CONTROLLER_STOP','PHYSICAL_STOP') else 1
    return 0

if __name__=='__main__':raise SystemExit(main())
