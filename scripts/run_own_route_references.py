"""egomap66 frozen six-checkpoint x six-condition batch; oracle-x86 only."""
import argparse
import contextlib
import hashlib
import json
import math
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace, MethodType
import numpy as np
from harness.active_camera import bind
from harness.own_route_reference import Options, install
from scripts import run_own_route_full_budget as previous
from scripts import run_own_route_particle_stages as old
from scripts.own_route_budget_schedule import OPTION as SCHEDULE, admit_checkpoint

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT/'experiments/2026-10-11-own-route-reference/prereg.json'
CONDITIONS = {'baseline': Options(), **{name: Options(**{name: True}) for name in asdict(Options())},
              'combined': Options(progress_lookahead=True, return_own_free_astar=True, arrival_verify_fsm=True)}


def registration():
    return json.loads(PLAN.read_text())


def resources():
    available = next(float(x.split()[1])/2**20 for x in Path('/proc/meminfo').read_text().splitlines()
                     if x.startswith('MemAvailable:'))
    return os.getloadavg()[0], available


@contextlib.contextmanager
def server_slot():
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or os.getenv('UGRP_EXECUTION_HOST') != 'oracle-x86':
        raise RuntimeError('ORACLE_ONLY_NO_MAC_PHYSICS')
    if os.getenv('MUJOCO_GL') != 'osmesa':
        raise RuntimeError('OSMESA_REQUIRED')
    while True:
        load, memory = resources()
        if load < 51 and memory >= 6:
            break
        time.sleep(5)
    yield 'resource_admitted'


def bundle(seed, source, condition, mode):
    b = previous.bundle(seed, source, 'baseline', mode)
    b['execution_bundle_id'] = f'egomap66-{mode}-{condition}-{seed}-v1'
    b['options'].update({k:'on_v1' if v else 'off' for k,v in asdict(CONDITIONS[condition]).items()})
    b['host_alarm_s'] = registration()['host_alarm_s']
    b['reference_parameters'] = registration()['fixed_parameters']
    b['admission'] = 'egomap66 preregistered DEV: frozen 100 particles, detector, motion, stage budgets'
    return b


def run(a):
    a.stage_schedule = SCHEDULE
    a.profile = 'baseline'
    b = bundle(a.seed, ROOT.name, a.condition, a.mode)
    audit = []
    def load(path, out):
        backend, c, start, tick, cp = old.checkpoint_load(path, out)
        install(c, CONDITIONS[a.condition])
        arrival_audit(c, audit)
        return backend, c, start, tick, cp
    def alarm(n):
        return signal.alarm(b['host_alarm_s'] if n else 0)
    result = bind(old.run, bundle=lambda *args:b, checkpoint_load=load, server_slot=server_slot,
                  install=previous.previous.install, signal=SimpleNamespace(**{**vars(signal),'alarm':alarm}))(a)
    old.dump(a.output/'arrival-gates.json',audit)
    return result


def arrival_audit(c, output):
    """Separate passive ledger; existing controller outputs remain byte-identical."""
    original = c._arrival
    def observed(self,t,frame_id,pose,box_visible):
        row = None
        if self.active == 'B':
            near = math.dist(pose[:2],self.entities['B']['center_m'])<=.20
            fresh = any(p.get('confirmed_t') is not None for p in self.current_patches)
            lower = 0 if self.labels is None else int(np.count_nonzero(self.labels[2*self.labels.shape[0]//3:]))
            row = dict(t=t,frame_id=frame_id,near=near,patches=len(self.current_patches),
                fresh_confirmed=fresh,lower_pixels=lower,reason='outside_20cm' if not near else
                'no_current_patch' if not self.current_patches else 'unconfirmed' if not fresh else
                'lower_pixels' if lower<self.explorer.goal.options.min_pixels else 'current_evidence')
        value = original(t,frame_id,pose,box_visible)
        if row is not None:
            row.update(streak=self.streak,reached='B' in self.reached)
            if hasattr(self,'_visual_reason') and self.reference_options.arrival_verify_fsm:
                row['reason']=self._visual_reason
            output.append(row)
        return value
    c._arrival=MethodType(observed,c)


def jobs(out):
    result = []
    for c in registration()['checkpoints']:
        for condition in CONDITIONS:
            name = f'egomap66-{c["seed"]}-{condition}'
            output = Path(out)/name
            result.append(dict(name=name, seed=c['seed'], condition=condition, profile='baseline', status='QUEUED',
                checkpoint=c['path'], output=str(output), checkpoint_sha256=c['sha256'], command=[sys.executable,
                '-m','scripts.run_own_route_references','--mode','stage','--seed',str(c['seed']),
                '--condition',condition,'--output',str(output)]))
    return result


def rows(path):
    if not path.exists():
        return []
    result = []
    with path.open() as f:
        for line in f:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # writer's incomplete final line, retried on next check
    return result


def early_check(output, start_sim, age):
    """Evaluation-only health check, never passes GT back to controller."""
    output = Path(output)
    own = [r for r in rows(output/'own-controller.jsonl') if r['t'] >= start_sim]
    truth = [r for r in rows(output/'eval_only/trajectory.jsonl') if r['t'] >= start_sim]
    sim = own[-1]['t']-start_sim if own else 0.
    commands = Counter('turn' if r['command'].get('turn',0) else 'forward' if
                       r['command'].get('forward',0)>0 else 'hold' for r in own)
    displacement = max((float(np.linalg.norm(np.asarray(r['robot_xyz_m'])[:2]-truth[0]['robot_xyz_m'][:2]))
                        for r in truth), default=0.)
    yaw_span = max((abs(float(np.arctan2(np.sin(r['robot_yaw_rad']-truth[0]['robot_yaw_rad']),
                                              np.cos(r['robot_yaw_rad']-truth[0]['robot_yaw_rad']))))
                    for r in truth), default=0.)
    reason = None
    if age>=180:
        if not own or sim<=0:
            reason = 'no_frame_or_sim_progress'
        elif not truth:
            reason = 'missing_evaluation_motion_record'
        elif sim>=10 and displacement<.01 and yaw_span<.01:
            reason = 'no_physical_motion'
        elif sim>=10 and commands['forward']==0 and commands['turn']>=.9*len(own):
            reason = 'turn_only_no_translation'
        elif own[-1].get('stage') not in ('approach','return','declared','budget_exhausted'):
            reason = 'core_stage_not_entered'
    return dict(wall_age_s=age, sim_s=sim, frames=len(own), commands=dict(commands),
                displacement_m=displacement, yaw_span_rad=yaw_span,
                stage=own[-1].get('stage') if own else None, anomaly=reason, gt_evaluation_only=True)


def score_batch(plan, out, *, round_name='egomap66'):
    from scripts.score_own_route_full_budget import score
    reports = []
    for j in plan:
        p = Path(j['output'])
        try:
            r = score(p) if (p/'result.json').exists() else dict(samples=0)
        except Exception as error:
            r = dict(samples=0, scoring_error=repr(error))
        start = json.loads((p/'result.json').read_text()).get('start_sim_s',float('inf')) if (p/'result.json').exists() else float('inf')
        own = [x for x in rows(p/'own-controller.jsonl') if x['t']>=start]
        route = json.loads((p/'route-map.json').read_text()) if (p/'route-map.json').exists() else {}
        cut = (r.get('return_transition') or {}).get('t',float('inf'))
        matches = [x for x in route.get('matches',[]) if x['t']>=cut]
        gates = json.loads((p/'arrival-gates.json').read_text()) if (p/'arrival-gates.json').exists() else []
        tail = next((x for x in reversed(own) if x.get('stage') in ('return','declared')),{})
        samples = (route.get('return_route') or {}).get('samples',[])
        r.update(visual_gate_failures=dict(Counter(x['reason'] for x in gates)),
                 match_accepted=sum(x['status']=='accepted' for x in matches), match_attempts=len(matches),
                 return_progress=tail.get('reference_navigation'),
                 legacy_cursor_ratio=tail.get('route',{}).get('cursor',0)/len(samples) if samples else None)
        reports.append(dict(r, seed=j['seed'], condition=j['condition'], status=j['status'], raw=str(p),
            early_checks=j.get('early_checks',[]), result_sha256=hashlib.sha256((p/'result.json').read_bytes()).hexdigest() if (p/'result.json').exists() else None))
    old.dump(out/'scores.json', reports)
    old.dump(out/'summary.json', dict(round=round_name,host='oracle-x86',source_sha=ROOT.name,
        registered=len(plan),conditions=aggregate(reports),runs=reports,thresholds_changed=False,
        raw_root=str(out),scores_sha256=hashlib.sha256((out/'scores.json').read_bytes()).hexdigest()))
    return reports


def aggregate(reports):
    groups = {}
    for condition in CONDITIONS:
        group = [r for r in reports if r['condition']==condition]
        measured = [r for r in group if r.get('samples',0)]
        commands, visual = Counter(), Counter()
        for r in measured:
            commands.update(r.get('command_audit',{}).get('counts',{}))
            visual.update(r.get('visual_gate_failures',{}))
        groups[condition] = dict(registered=6,attempts=len(group),measured=len(measured),
            statuses=dict(Counter(r['status'] for r in group)),
            B_arrived=sum(bool(r.get('B_arrived')) for r in measured) if measured else None,
            returned=sum(bool(r.get('returned')) for r in measured) if measured else None,
            false_declarations=sum(r.get('false_declarations',0) for r in measured) if measured else None,
            wall_contacts=sum(r.get('contacts',{}).get('wall',0) for r in measured),
            robot_contacts=sum(r.get('contacts',{}).get('robot',0) for r in measured),
            frames=sum(r['samples'] for r in measured),
            over3_frames=sum(r.get('over_3sigma',0) for r in measured),
            commands=dict(commands),turn_fraction=commands['turn']/sum(commands.values()) if commands else None,
            turn_reversals=sum(r.get('command_audit',{}).get('turn_sign_reversals',0) for r in measured),
            match_accepted=sum(r.get('match_accepted',0) for r in measured),
            match_attempts=sum(r.get('match_attempts',0) for r in measured),visual_gate_failures=dict(visual),
            final_error_median=float(np.median([r['final_error_m'] for r in measured])) if measured else None)
    return groups


def batch(a, *, required_free_gib=26):
    if platform.system() != 'Linux' or os.getenv('UGRP_EXECUTION_HOST') != 'oracle-x86':
        raise RuntimeError('ORACLE_ONLY_NO_MAC_PHYSICS')
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    plan = jobs(out)
    cp_by_seed = {c['seed']:c for c in registration()['checkpoints']}
    old.dump(out/'batch-plan.json', dict(source_sha=ROOT.name, host='oracle-x86', jobs=plan))
    if shutil.disk_usage(out).free < required_free_gib*2**30:
        # eg65 retained 11.1GiB/24 runs; reserve 20GiB for 36 + 6GiB shared
        # headroom. Do not start a knowingly disk-starved comparison or delete
        # anyone's existing raw to create space.
        for j in plan:
            j.update(status='BLOCKED_DISK_CAPACITY', required_free_gib=required_free_gib)
        old.dump(out/'batch-status.json',plan)
        score_batch(plan,out)
        return 3
    for j in plan:
        try:
            admit_checkpoint(Path(j['checkpoint']),j['seed'],SCHEDULE,ROOT)
        except Exception as error:
            j.update(status='BLOCKED_ADMISSION', failure=repr(error))
    queue = [j for j in plan if j['status']=='QUEUED']
    running, launches = [], []
    while queue or running:
        now = time.monotonic()
        launches = [v for v in launches if now-v<60]
        load, memory = resources()
        # Reserve for just-started workers before the load average/RAM catches
        # up; all 36 conditions stay in this one registered batch.
        if queue and load+2*len(launches)<51 and memory-1.5*len(launches)>=6 and shutil.disk_usage(out).free>=6*2**30:
            j = queue.pop(0)
            stream = (out/(j['name']+'.log')).open('x')
            p = subprocess.Popen(j['command'],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            j.update(status='RUNNING',pid=p.pid,launch_monotonic=now,early_checks=[])
            running.append((j,p,stream))
            launches.append(now)
        for j,p,stream in running.copy():
            age = now-j['launch_monotonic']
            if p.poll() is None and age>=180 and not j['early_checks']:
                check = early_check(j['output'],cp_by_seed[j['seed']]['sim_s'],age)
                log = (out/(j['name']+'.log')).read_text()
                if 'Traceback (most recent call last)' in log:
                    check['anomaly']='log_exception'
                j['early_checks'].append(check)
                if check['anomaly']:
                    # Only this batch's owned child process group. No other
                    # task's process is searched for or stopped.
                    os.killpg(p.pid,signal.SIGTERM)
                    j['early_stop']=check['anomaly']
            if p.poll() is None:
                continue
            stream.close()
            j['exit_code']=p.returncode
            folder=Path(j['output']);folder.mkdir(parents=True,exist_ok=True)
            (folder/'EXIT').write_text(str(p.returncode)+'\n')
            result=folder/'result.json'
            j['status']='EARLY_CHECK_STOP' if j.get('early_stop') else json.loads(result.read_text())['status'] if result.exists() else 'HOST_ERROR_NO_RESULT'
            if not j['early_checks']:
                j['early_checks'].append(early_check(folder,cp_by_seed[j['seed']]['sim_s'],age))
            running.remove((j,p,stream))
        old.dump(out/'batch-status.json',plan)
        if queue or running:
            time.sleep(2)
    score_batch(plan,out)
    return 0


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=('stage','smoke','batch'),required=True)
    p.add_argument('--condition',choices=tuple(CONDITIONS),default='baseline')
    p.add_argument('--seed',type=int,choices=previous.SEEDS,default=63001)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='batch':
        return batch(a)
    a.checkpoint=Path(next(c['path'] for c in registration()['checkpoints'] if c['seed']==a.seed))
    if a.mode=='smoke':
        a.mode='smoke_resume'
    result=run(a)
    print(json.dumps(result),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':
    raise SystemExit(main())
