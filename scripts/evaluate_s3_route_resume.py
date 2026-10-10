"""Post-batch saved numerical records; GT appears only in this evaluator."""
import argparse
import json
import math
from pathlib import Path
from scripts.evaluate_s3_integer_carry import evaluate as previous
from scripts.evaluate_s3_synchronized_carry import rows, read


def events(value):
    if isinstance(value, dict):
        if 'event' in value:
            yield value
        else:
            for x in value.values():
                yield from events(x)
    elif isinstance(value, list):
        for x in value:
            yield from events(x)


def post_release_alignment(ev):
    """A single endpoint's new hover is not a joint regrasp readiness receipt."""
    result = {}
    for rid in ('r1','r2'):
        release = next((e['sim_s'] for e in sorted(ev,key=lambda e:e.get('sim_s',0.))
            if e.get('event')=='checkpoint_open' and e.get('robot_id')==rid), None)
        result[rid] = release is not None and any(e.get('event')=='coarse_fine_aligned'
            and e.get('robot_id')==rid and e['sim_s']>release for e in ev)
    return result


def evaluate(raw):
    r = previous(raw)
    b = read(raw/'bundle.json')
    record = read(raw/'student_record.json')
    route = record['pair']['pair'][0]['plan']['route']
    assert route == b['registered_route']
    ev = list({json.dumps(e,sort_keys=True):e for e in events(record)}.values())
    plans = sorted((e for e in ev if e.get('event')=='synchronized_carry_plan'
        and e.get('robot_id')=='r1'), key=lambda e:e['seg'])
    states = read(raw/'stage-states.json')
    truth = rows(raw/'eval_only/referee_truth.jsonl')
    legs = []
    for p in plans:
        start = p['sim_s']
        end = next((s['t'] for s in states if s['t']>start
            and any(v['state']!='carry' for v in s['robots'].values())),None)
        point = next(t['items']['beam_1'] for t in reversed(truth)
            if t['t'] <= (end if end is not None else truth[-1]['t']))
        error = math.dist([point['x'],point['y']], route[p['seg']+1])
        legs.append(dict(seg=p['seg'],start_sim_s=start,end_sim_s=end,
            endpoint_error_m=error,endpoint_reached=end is not None and error<=.02))
    releases = sorted((e for e in ev if e.get('event')=='checkpoint_open'
        and e.get('robot_id')=='r1'),key=lambda e:e['sim_s'])
    realigned = post_release_alignment(ev)
    expected = len(route)-1
    early = (r['status']=='DEV_STAGE_FINISHED' and r['sim_s']<b['cap_sim_s']-1e-8
        and len(legs)<expected and not r['controller_failures'])
    unmeasured = 'UNMEASURED_V3_CAMERA_POSTURE' in read(raw/'result.json').get('failure','')
    horizon = r['sim_s']>=b['cap_sim_s']-1e-8 and len(legs)<expected
    r.update(candidate=b['route_resume']['candidate'],seed=b['seed'],route_case=b['route_case'],
        route_applied=True,planned_legs=expected,legs=legs,
        second_leg_started=any(l['seg']==1 for l in legs),
        reentry=bool(releases),realigned_by_robot=realigned,
        realigned_after_release=all(realigned.values()),
        premature_complete=early,unmeasured_camera_host=unmeasured,
        probe_horizon=horizon,full_route_success=len(legs)==expected
            and all(l['endpoint_reached'] for l in legs) and r['setdown'],
        cause='camera_posture_contract' if unmeasured else 'premature_complete' if early
            else 'probe_horizon' if horizon else 'other_host_error' if r['status']=='HOST_ERROR'
            else 'physical_or_controller_failure' if r['controller_failures'] or r['status']=='PHYSICAL_STOP' else None)
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    cc = read(a.cohort/'cohort.json')
    assert len(cc)==24
    rr = [dict(name=c['name'],**evaluate(a.cohort/c['name']/'raw')) for c in cc]
    metrics = ('reentry','realigned_after_release','second_leg_started','premature_complete',
        'unmeasured_camera_host','probe_horizon','full_route_success','setdown')
    by = {c:dict(n=len(rs),**{k:sum(bool(r[k]) for r in rs) for k in metrics},
        host_errors=sum(r['status']=='HOST_ERROR' for r in rs),
        drop_aborts=sum(r['drop_aborts'] for r in rs),tilt_aborts=sum(r['tilt_aborts'] for r in rs))
        for c in ('baseline','completion','inspect','combined')
        for rs in [[r for r in rr if r['candidate']==c]]}
    summary = dict(host='oracle-x86',n=24,runs=rr,by_candidate=by,
        scope='DEV 60 SIM-second routes, not complete route confirmation',
        initial_checks_healthy=sum(r['initial_check']['healthy'] for r in rr))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}))


if __name__=='__main__':
    raise SystemExit(main())
