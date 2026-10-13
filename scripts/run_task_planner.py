"""Standard CLI adapter: Gemma tasks -> existing own-camera zone skills.

Mac never runs physics/render here. Azure starts only through the supervisor;
this CLI verifies source/budget and owns no VM lifecycle operations.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.task_planner import MODE, CONDITIONS
from harness.task_planner_gemma import Gemma, Budget
from harness.task_planner_runtime import Runtime, EVENT_MAP
from harness.task_planner_zone import ZonePort

BUNDLE_ID = 'e2e18-v357'
WORKFLOW_VERSION = '7.250.0'


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def planner_option(options):
    value = options.get('planner', 'off')
    if value not in ('off', MODE): raise ValueError('UNKNOWN_TASK_PLANNER')
    return value


def strip_images(value):
    if isinstance(value, dict): return {k: strip_images(v) for k,v in value.items() if k != 'image_b64'}
    if isinstance(value, list): return [strip_images(v) for v in value]
    return value


def bundle(config, sha):
    from harness.python_source_closure import source_closure
    files = source_closure(ROOT, ('scripts/run_task_planner.py',))
    static = ['configs/simulation_workflows.d/e2e18_v357.json', config['prereg']]
    prereg = json.loads((ROOT/config['prereg']).read_text())
    episode = prereg['episodes'][config.get('episode_index', 0)]
    static += [episode['scenario'], prereg['student']['calibration']]
    hashes = {str(p): hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(set(files) | set(static))}
    return dict(schema='ugrp.task_planner.run.v1', execution_bundle_id=BUNDLE_ID,
                workflow_version=WORKFLOW_VERSION, e2e_options=dict(planner=planner_option(config.get('e2e_options', {}))),
                source_sha=sha, source_sha256=hashes, config=copy.deepcopy(config),
                research_result=False, physical_profile='existing_zone_owncam; separate from e2e18 ownmap beam scene',
                driver_profile='study_gemma4_31b_v1', weld=False)


def execute(config, out, *, sha, relay_url, horizon_s, wall_cap_s):
    if platform.system() == 'Darwin': raise RuntimeError('MAC_PHYSICS_AND_RENDER_FORBIDDEN')
    if planner_option(config.get('e2e_options', {})) != MODE: raise ValueError('PLANNER_OPT_IN_REQUIRED')
    if not 0 < horizon_s <= 120 or not 0 < wall_cap_s <= 1800: raise ValueError('SHORT_SCENE_BUDGET_REQUIRED')
    from scripts import run_zone_study_integration as runner
    from harness.zone_study_scenarios import bundle_for
    prereg = json.loads((ROOT/config['prereg']).read_text())
    episode = prereg['episodes'][config.get('episode_index', 0)]
    scenario = json.loads((ROOT/episode['scenario']).read_text())
    spec = runner.host_spec(scenario, episode, bundle_for(scenario))
    provider = runner.zi.pose_provider_spec(prereg['pose_provider'], map_id=episode['map'])
    budget = Budget(max_calls=90, max_usd=.5)
    models = {rid: Gemma(url=relay_url, budget=budget) for rid in ('r1','r2','r3')}
    host = runtime = None; started = time.monotonic(); result = dict(status='RUNNING', research_result=False)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'RUN_META.json', {'class':'dev','pr':None,'branch':subprocess.check_output(['git','branch','--show-current'],text=True).strip(),
                              'sha':sha,'batch':BUNDLE_ID})
    write(out/'runtime-bundle.json', bundle(config, sha))
    try:
        host = runner.StudyTeamHost(spec, prereg['student'], root=ROOT, provider_spec=provider, frames_dir=out/'own_frames')
        now = host.settle(float(prereg['t0_s'])); end = now+horizon_s
        roles = {'r1':'end_neg','r2':'end_pos'} if host.pairs is not None else {}
        ports = {r: ZonePort(s.executor, lambda api,*args,_r=r:host.call(_r,api,*args), pair_roles=roles)
                 for r,s in host.robots.items()}
        runtime = Runtime(arm=config['condition'], models=models, ports=ports,
                          snapshots={r:p.snapshot for r,p in ports.items()}, leader=config.get('leader','r1'))
        seen = set(); wait_since = {}
        while now < end:
            if time.monotonic()-started > wall_cap_s: raise TimeoutError('SCENE_WALL_CAP')
            runtime.step(now)
            for rid, port in ports.items():
                if port.immediate and port.active:
                    runtime.event(rid, dict(kind='job_done',reason=port.immediate),now);port.immediate=None
                ex = port.ex; job = ex.job
                if job is not None and job.phase == 'waiting_partner':
                    since = wait_since.setdefault(rid, now)
                    key = (rid,job.job_id,'s3')
                    if now-since >= 10 and key not in seen:
                        runtime.event(rid,dict(kind='partner_delayed',reason='Own rendezvous timer exceeded 10 s'),now);seen.add(key)
                else: wait_since.pop(rid,None)
                holding = ex.holding()
                if port.active and port.active['act']=='carry' and holding['answer']=='no' and ex.loaded:
                    key=(rid, getattr(job,'job_id',None),'grip')
                    if key not in seen:
                        runtime.event(rid,dict(kind='grip_anomaly',reason='Own RGB/command hold mismatch'),now);seen.add(key)
            events = host.advance_to(min(end,now+.1)); now = float(host.world.data.time)
            for event in events:
                rid=event['robot_id']; ev=ports[rid].event(event)
                if ev is None: continue
                if ev['kind'] in EVENT_MAP: runtime.event(rid,ev,now)
                if ev['kind']=='job_failed' and any(k in ev['reason'].lower() for k in ('not_found','missing','no_target')):
                    runtime.event(rid,dict(kind='item_missing',reason=ev['reason']),now)
                if ev['kind']=='blockage_seen' and event.get('passage_id'):
                    runtime.event(rid,dict(kind='corridor_occupied',reason='Own camera blockage at '+event['passage_id']),now)
            time.sleep(.001)  # yield to independent HTTP workers; never a physical speed claim
        result['status']='SCENE_BUDGET_COMPLETE'
    except Exception as exc:
        result.update(status='HOST_ERROR', failure_type=type(exc).__name__)
        raise
    finally:
        if runtime is not None:
            runtime.close()
            write(out/'planner-actors.json',strip_images({r:p.audit for r,p in runtime.planners.items()}))
            write(out/'planner-actions.json',runtime.audit);write(out/'planner-channel.json',runtime.channel.ledger)
        if host is not None:
            host.close_episode('task_planner_budget')
            write(out/'own-act-events.json',host.event_log)
            write(out/'eval_only.json',host.eval_only)
            host.close()
        result.update(wall_s=time.monotonic()-started,model_calls=budget.calls,
                      accounted_usd=budget.charged,unknown_cost_calls=budget.unknown)
        write(out/'summary.json',result)
        write(out/'sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in out.rglob('*') if p.is_file()})
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'configs/task_planner_v357.json')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true');p.add_argument('--relay-url',default='http://127.0.0.1:18424')
    p.add_argument('--horizon-s',type=float,default=30.);p.add_argument('--wall-cap-s',type=float,default=600.)
    a=p.parse_args();cfg=json.loads(a.config.read_text())
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if sha != a.expected_source_sha: raise SystemExit('SOURCE_SHA_MISMATCH')
    if a.execute:
        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(): raise SystemExit('CLEAN_FROZEN_SOURCE_REQUIRED')
        execute(cfg,a.output,sha=sha,relay_url=a.relay_url,horizon_s=a.horizon_s,wall_cap_s=a.wall_cap_s)
    else:
        a.output.mkdir(parents=True,exist_ok=False);write(a.output/'runtime-bundle.json',bundle(cfg,sha))
        write(a.output/'summary.json',dict(status='PREPARED_NOT_EXECUTED',physics_calls=0,model_calls=0))


if __name__=='__main__': main()
