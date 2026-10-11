"""egomap72: fresh continuous paired DEV, no checkpoint or external RGB bank."""
import argparse
import collections
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

from harness.active_camera import bind
from harness.own_route_reference import Options, install as route_install
from harness.turn_lateral_calibration import OPTION as MOTION, install as motion_install
from harness.own_rgb_reconfirmation import OPTION as RGB
from harness.egomap_covariance import OPTION as COV, install as covariance_install
from harness.own_route_reconfirmation import install as gate_install
from scripts import run_egomap_reconfirmation as old
from scripts import run_own_route_particle_round as fresh

ROOT = Path(__file__).resolve().parents[1]
SEEDS = tuple(range(63001, 63007))
OPTIONS = Options(return_own_free_astar=True)
EXP = ROOT / 'experiments/2026-10-11-egomap72-fresh'
dump = old.dump


def bundle(seed, condition, source):
    b = fresh.bundle(seed, source, 'baseline', 'full')
    b.update(execution_bundle_id=f'egomap72-full-{seed}-{condition}-v1', host='azure',
             host_alarm_s=2700, case_cap_s=810., stage_diagnostic=False,
             admission='fresh continuous DEV; original own B/box/home mission; no checkpoint')
    b['options'].update(return_own_free_astar='on_v1', traversed_free='footprint_history_v1',
        motion_model_turn_lateral_v2=MOTION,
        rgb_reconfirmation=RGB if condition == 'on' else 'off',
        covariance_inflation=COV if condition == 'on' else 'off',
        fresh_home='first_own_graph_frame_v1' if condition == 'on' else 'off')
    b['comparison'] = 'same seed/source/initial Scene; combined RGB+covariance toggles only'
    return b


def run(args):
    import cv2
    cv2.setNumThreads(1)
    cv2.setRNGSeed(args.seed)
    args.mode = 'full'; args.profile = 'baseline'; args.stage_schedule = 'off'
    b = bundle(args.seed, args.condition, ROOT.name)
    audit, controllers = [], []
    def controller(explorer):
        c = fresh.controller(explorer)
        route_install(c, OPTIONS, traversed_free='footprint_history_v1')
        motion_install(c, motion_model_turn_lateral_v2=MOTION)
        covariance_install(c, covariance_inflation=b['options']['covariance_inflation'])
        gate_install(c, rgb_reconfirmation=b['options']['rgb_reconfirmation'], fresh_home=args.condition == 'on')
        controllers.append(c)
        old.ref.arrival_audit(c, audit)
        def emit(row):
            if args.condition == 'on':
                row['valid'] = row['valid'] and c._rgb_reconfirmation_calls == row['call'] and c._covariance_inflation is not None
            row.update(rgb=b['options']['rgb_reconfirmation'], covariance=b['options']['covariance_inflation'])
            with (args.output / 'execution-path.jsonl').open('a') as f:
                f.write(json.dumps(row) + '\n')
            if not row['valid']:
                raise RuntimeError('EGOMAP72_REFERENCE_NOT_EXECUTED')
        old.previous.previous.execution_audit(c, OPTIONS, emit)
        return c
    continuous = SimpleNamespace(**{**vars(fresh.old.continuous), 'controller': controller})
    def alarm(n):
        return signal.alarm(b['host_alarm_s'] if n else 0)
    # Original full-run loop, initial Scene, warmup and natural task transitions.
    # No checkpoint admission, task reset, forced return or restored object state.
    result = bind(fresh.old.run, bundle=lambda *a: b, continuous=continuous,
        install=fresh.install, server_slot=old.server_slot,
        signal=SimpleNamespace(**{**vars(signal), 'alarm': alarm}))(args)
    result.update(host='azure', condition=args.condition, resumed=False, class_='dev', pr=405)
    dump(args.output / 'result.json', result)
    dump(args.output / 'arrival-gates.json', audit)
    if controllers:
        c = controllers[0]
        dump(args.output / 'rgb-reconfirmation.json', dict(
            rows=getattr(getattr(c, '_rgb_reconfirmation_gate', None), 'rows', []),
            acquisitions=getattr(c, '_rgb_reconfirmation_acquisitions', []),
            captures=getattr(c, '_rgb_reconfirmation_captures', 0), source='same_run_own_RGB'))
    dump(args.output / 'artifacts.sha256.json', {str(p.relative_to(args.output)): old.digest(p.read_bytes())
        for p in sorted(args.output.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def score(folder):
    """Post-run declarations only; GT missing is HOST_ERROR, never false success."""
    r = old.read_result(folder)
    events = json.loads((folder / 'utility-events.json').read_text())
    truth = old.ref.rows(folder / 'eval_only/trajectory.jsonl')
    own = old.ref.rows(folder / 'own-controller.jsonl')
    if not truth or not own:
        raise ValueError('MISSING_MEASURED_TRAJECTORY')
    by_t = {round(x['t'], 6): x for x in truth}
    origin = truth[0]['robot_xyz_m'][:2]
    B = json.loads((folder / 'inputs/static_map.json').read_text())['regions']['zone_B']
    declarations = []
    for e in events:
        if e['reason'] not in ('return_start_declared', 'goal_reached'):
            continue
        if e['reason'] == 'goal_reached' and e.get('entity') != 'B':
            continue
        g = by_t.get(round(e['t'], 6))
        if g is None:
            raise ValueError('DECLARATION_EVALUATION_MISSING')
        xy = g['robot_xyz_m'][:2]
        valid = (all(abs(v-c) <= h for v,c,h in zip(xy, B['center_m'], B['half_extents_m']))
                 if e['reason'] == 'goal_reached' else math.dist(xy, origin) <= .20)
        declarations.append(dict(t=e['t'], kind=e['reason'], valid=valid, evaluation_xy=xy))
    return dict(samples=len(own), declarations=declarations, stage=r.get('stage'),
        sim_s=r['total_sim_s']-r['start_sim_s'], commands=len(own),
        B_arrived=any(x['kind']=='goal_reached' and x['valid'] for x in declarations),
        returned=any(x['kind']=='return_start_declared' and x['valid'] for x in declarations),
        return_stage_entered=any(x.get('stage') in ('return', 'declared') for x in own),
        command_counts=dict(collections.Counter('turn' if x['command'].get('turn') else
            'translation' if x['command'].get('forward') or x['command'].get('left') else 'hold' for x in own)))


def summarize(plan, out):
    reports = []
    for job in plan:
        folder = Path(job['output']); r = old.read_result(folder)
        row = {k: job.get(k) for k in ('name', 'seed', 'condition', 'status', 'exit_code', 'pid', 'cpu', 'failure')}
        row.update(raw=str(folder), result_sha256=old.digest((folder/'result.json').read_bytes()) if r else None,
                   wall_s=r.get('wall_s'), model_calls=r.get('model_calls', 0))
        if r.get('status', '').startswith('HOST_ERROR'):
            row['status'] = r['status']
        if r.get('failure'):
            row['failure'] = r['failure']
        if r.get('start_sim_s') is not None:
            try:
                row.update(score(folder))
            except Exception as exc:
                row['scoring_error'] = repr(exc)
        row['host_error'] = row['status'].startswith('HOST_ERROR') or 'scoring_error' in row
        ds = row.get('declarations', [])
        row.update(false_return=sum(d['kind']=='return_start_declared' and not d['valid'] for d in ds),
                   false_B=sum(d['kind']=='goal_reached' and not d['valid'] for d in ds))
        reports.append(row)
    groups = {}
    for cond in ('off', 'on'):
        g = [r for r in reports if r['condition']==cond]
        measured = [r for r in g if r.get('samples') and not r.get('scoring_error')]
        complete = [r for r in measured if not r['host_error'] and r['status']=='RECORDED']
        group = dict(registered=6, attempted=sum(r['pid'] is not None for r in g), measured=len(measured),
            completed=len(complete), host_errors=sum(r['host_error'] for r in g),
            statuses=dict(collections.Counter(r['status'] for r in g)),
            true_B=sum(r['B_arrived'] for r in measured), true_return=sum(r['returned'] for r in measured),
            return_stage_entered=sum(r['return_stage_entered'] for r in measured),
            wall_s=sum(r['wall_s'] or 0 for r in g), commands=sum(r.get('commands',0) for r in measured), model_calls=0)
        for key,kind in [('false_return','return_start_declared'),('false_B','goal_reached')]:
            group[key] = dict(count=sum(r[key] for r in measured), runs_with_event=sum(r[key]>0 for r in measured),
                registered_run_denominator=6, measured_run_denominator=len(measured),
                completed_run_denominator=len(complete),
                declaration_denominator=sum(d['kind']==kind for r in measured for d in r['declarations']))
        groups[cond] = group
    prior_path = ROOT/'experiments/2026-10-11-egomap-reconfirmation/summary.json'
    prior = json.loads(prior_path.read_text())
    # Full prior failures retained as provenance, not combined with new performance.
    history = prior.get('host_errors', [])
    if not history:
        history = [r for r in prior.get('runs', []) if r.get('host_error') or 'HOST_ERROR' in r.get('status','')]
    report = dict(round='egomap72', source_sha=ROOT.name, host='azure', **{'class':'dev'}, pr=405,
        registered=12, paired_seeds=list(SEEDS), conditions=groups, runs=reports,
        host_errors=[r for r in reports if r['host_error']],
        prior_egomap71=dict(summary_path=str(prior_path.relative_to(ROOT)), sha256=old.digest(prior_path.read_bytes()),
                           host_errors=history, registered=12, measured=0),
        checkpoint_inputs=False, external_RGB_bank=False, control_static_map=False, control_GT=False,
        schedule='original continuous own B/box/home; 270s per leg, 810s maximum, no forced transition',
        confirmation=False, threshold_retuning=False, model_calls=0,
        scope='same six DEV seeds, both toggles combined; not separate effects or transport E2E')
    dump(out/'summary.json', report)
    return report


def jobs(out, cpus):
    return [dict(name=f'egomap72-{seed}-{cond}', seed=seed, condition=cond,
            output=str(out/f'egomap72-{seed}-{cond}'), status='QUEUED')
        for seed in SEEDS for cond in (('off','on') if seed%2 else ('on','off'))]


def batch(args):
    with old.server_slot():
        cpus = [int(c) for c in args.cpus.split(',')]
        if len(cpus) < 2 or len(cpus)%2 or len(set(cpus)) != len(cpus) or not set(cpus)<=os.sched_getaffinity(0):
            raise ValueError('PAIRED_AVAILABLE_CPU_LIST_REQUIRED')
        out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
        plan = jobs(out, cpus); queue = list(plan); running = []; started = time.monotonic(); stopped = False
        def interrupt(*_):
            nonlocal stopped
            stopped = True
        signal.signal(signal.SIGINT, interrupt); signal.signal(signal.SIGTERM, interrupt)
        dump(out/'batch-plan.json', dict(jobs=plan, cpus=cpus, wall_budget_s=args.wall_budget_s, source_sha=ROOT.name))
        while queue or running:
            expired = stopped or time.monotonic()-started >= args.wall_budget_s
            if expired:
                for j in queue:
                    j.update(status='HOST_ERROR_TASK_DEADLINE_NOT_STARTED', failure='finite_batch_budget')
                queue.clear()
            free = [c for c in cpus if c not in [j['cpu'] for j,p,f in running]]
            load, memory = old.ref.resources()
            # Pinned workers bound total CPU even when sibling threads inflate loadavg.
            if queue and len(free)>=2 and memory>=6 and shutil.disk_usage(out).free>=8*2**30:
                for cpu in free[:2]:
                    job=queue.pop(0); stream=(out/(job['name']+'.log')).open('x')
                    command=['taskset','-c',str(cpu),sys.executable,'-m','scripts.run_egomap_fresh_pair',
                             '--mode','full','--seed',str(job['seed']),'--condition',job['condition'],'--output',job['output']]
                    process=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
                    job.update(status='RUNNING',pid=process.pid,cpu=cpu,command=command,loadavg=list(os.getloadavg()),started=time.time())
                    running.append((job,process,stream))
            for job,process,stream in running.copy():
                if expired and process.poll() is None:
                    if 'deadline_at' not in job:
                        process.send_signal(signal.SIGALRM); job['deadline_at']=time.monotonic()
                    elif time.monotonic()-job['deadline_at']>60:
                        os.killpg(process.pid, signal.SIGKILL)
                if process.poll() is None:
                    continue
                stream.close(); job['exit_code']=process.returncode
                folder=Path(job['output']); folder.mkdir(parents=True,exist_ok=True)
                (folder/'EXIT').write_text(str(process.returncode)+'\n')
                result=old.read_result(folder)
                job['status']=result.get('status','HOST_ERROR_NO_RESULT')
                if process.returncode and job['status']=='RECORDED':
                    job['status']='HOST_ERROR_WRAPPER_EXIT'
                dump(folder/'RUN_META.json',dict(**{'class':'dev'},pr=405,branch='claude/ego-wall-map',sha=ROOT.name,batch=out.parent.name))
                running.remove((job,process,stream))
            dump(out/'batch-status.json',plan)
            if queue or running:
                time.sleep(5)
        result=summarize(plan,out)
        return 2 if result['host_errors'] else 0


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('full','batch'),required=True)
    p.add_argument('--condition',choices=('off','on'),default='off');p.add_argument('--seed',type=int,choices=SEEDS,default=SEEDS[0])
    p.add_argument('--output',type=Path,required=True);p.add_argument('--cpus',default='12,13,14,15')
    p.add_argument('--wall-budget-s',type=int,default=9000);a=p.parse_args()
    if not 1<=a.wall_budget_s<=9000:p.error('at most 9000s simulation; 1800s archive reserve')
    if a.mode=='batch':return batch(a)
    result=run(a);print(json.dumps(result),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':raise SystemExit(main())
