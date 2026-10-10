"""egomap67: fixed receive dispatch + own traversed footprint, 24-run DEV batch."""
import argparse
import json
import signal
import sys
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from harness.active_camera import bind
from harness.own_route_reference import Options, install
from scripts import run_own_route_references as ref

ROOT = ref.ROOT
PLAN = ROOT/'experiments/2026-10-11-own-route-traversed/prereg.json'
CONDITIONS = dict(baseline=Options(), progress_lookahead=Options(progress_lookahead=True),
    own_free_traversed=Options(return_own_free_astar=True),
    combined=Options(progress_lookahead=True, return_own_free_astar=True))


def registration():
    return json.loads(PLAN.read_text())


def traversed(condition):
    return 'footprint_history_v1' if CONDITIONS[condition].return_own_free_astar else 'off'


def bundle(seed, source, condition, mode):
    b = ref.previous.bundle(seed, source, 'baseline', mode)
    b['execution_bundle_id'] = f'egomap67-{mode}-{condition}-{seed}-v1'
    b['options'].update({k:'on_v1' if v else 'off' for k,v in asdict(CONDITIONS[condition]).items()})
    b['options']['traversed_free'] = traversed(condition)
    b['host_alarm_s'] = registration()['host_alarm_s']
    b['reference_parameters'] = registration()['fixed_parameters']
    b['admission'] = 'egomap67 same6 checkpoint DEV; default controller unchanged; passive sidecar for baseline'
    return b


def execution_audit(c, options, emit):
    """Passive all-condition sidecar; baseline's returned bytes are untouched."""
    original = c.receive
    count = 0
    def receive(**kw):
        nonlocal count
        result = original(**kw)
        count += 1
        trace = result[1]
        execution = trace.get('reference_navigation',{}).get('execution')
        active = any(asdict(options).values())
        row = dict(t=kw['t'], frame_id=kw['frame_id'], call=count, options=asdict(options),
                   receiver='ReferenceRoute.receive' if active else 'GoalRoute.receive',
                   execution=execution,
                   valid=(execution is not None and execution['calls']==count and
                          execution['dispatched']==asdict(options)) if active else execution is None)
        emit(row)
        if not row['valid']:
            raise RuntimeError('REFERENCE_RECEIVE_NOT_EXECUTED')
        return result
    c.receive = receive
    return c


def run(a):
    a.stage_schedule = ref.SCHEDULE
    a.profile = 'baseline'
    b = bundle(a.seed, ROOT.name, a.condition, a.mode)
    audit = []
    def load(path, out):
        backend,c,start,tick,cp = ref.old.checkpoint_load(path,out)
        install(c,CONDITIONS[a.condition],traversed_free=traversed(a.condition))
        ref.arrival_audit(c,audit)
        def emit(row):
            with (out/'execution-path.jsonl').open('a') as f:
                f.write(json.dumps(row,sort_keys=True)+'\n')
        execution_audit(c,CONDITIONS[a.condition],emit)
        return backend,c,start,tick,cp
    def alarm(n):
        return signal.alarm(b['host_alarm_s'] if n else 0)
    result = bind(ref.old.run,bundle=lambda *args:b,checkpoint_load=load,server_slot=ref.server_slot,
        install=ref.previous.previous.install,signal=SimpleNamespace(**{**vars(signal),'alarm':alarm}))(a)
    ref.old.dump(a.output/'arrival-gates.json',audit)
    return result


def jobs(out):
    result=[]
    for c in registration()['checkpoints']:
        for condition in CONDITIONS:
            name=f'egomap67-{c["seed"]}-{condition}'
            output=Path(out)/name
            result.append(dict(name=name,seed=c['seed'],condition=condition,profile='baseline',status='QUEUED',
                checkpoint=c['path'],output=str(output),checkpoint_sha256=c['sha256'],command=[sys.executable,
                '-m','scripts.run_own_route_traversed','--mode','stage','--seed',str(c['seed']),
                '--condition',condition,'--output',str(output)]))
    return result


def early_check(output,start_sim,age):
    result=ref.early_check(output,start_sim,age)
    markers=[r for r in ref.rows(Path(output)/'execution-path.jsonl') if r['t']>=start_sim]
    result['execution_path']=dict(frames=len(markers),valid=sum(r['valid'] for r in markers),
        first=markers[0] if markers else None)
    if (not markers or not all(r['valid'] for r in markers)) and result['anomaly'] is None:
        result['anomaly']='missing_or_invalid_execution_path'
    return result


def score_batch(plan,out):
    return bind(ref.score_batch,aggregate=bind(ref.aggregate,CONDITIONS=CONDITIONS))(
        plan,out,round_name='egomap67')


def batch(a):
    return bind(ref.batch,jobs=jobs,registration=registration,early_check=early_check,score_batch=score_batch)(
        a,required_free_gib=20)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=('stage','smoke','batch'),required=True)
    p.add_argument('--condition',choices=tuple(CONDITIONS),default='baseline')
    p.add_argument('--seed',type=int,choices=range(63001,63007),default=63001)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='batch':return batch(a)
    a.checkpoint=Path(next(c['path'] for c in registration()['checkpoints'] if c['seed']==a.seed))
    if a.mode=='smoke':a.mode='smoke_resume'
    r=run(a)
    print(json.dumps(r),flush=True)
    return 0 if r['status']=='RECORDED' else 1


if __name__=='__main__':
    raise SystemExit(main())
