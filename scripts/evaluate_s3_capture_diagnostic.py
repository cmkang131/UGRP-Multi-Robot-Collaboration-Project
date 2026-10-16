"""Offline frozen-rule evaluation, never imported by a student controller."""
import argparse
from collections import Counter, defaultdict
import hashlib
import itertools
import json
from pathlib import Path
import platform
import statistics

XY=(.012,.024)


def admissible_box(trials, bounds):
    """Finite tested-grid capture box only; no unmeasured success interpolation."""
    if len(trials)!=75:raise ValueError('complete75-point robot grid required')
    keys={(r['grid']['dx'],r['grid']['dy'],r['grid']['dyaw']) for r in trials}
    if len(keys)!=75:raise ValueError('duplicate capture point')
    nominal=next(r for r in trials if r['grid']['dx']==r['grid']['dy']==r['grid']['dyaw']==0.)
    candidates=[]
    for x,y in itertools.product(XY,XY):
        points=[r for r in trials if abs(r['grid']['dx'])<=x and abs(r['grid']['dy'])<=y]
        passed=all(r.get('grasp') and r.get('lift') and r['status']=='COLLECTED' for r in points)
        half=[.8*x,.8*y,.8*.14]
        candidates.append(dict(capture_halfwidth_m_m_rad=[x,y,.14],inner_halfwidth_m_m_rad=half,
            samples=len(points),all_capture=passed,step_fits=[h>=d for h,d in zip(half,bounds)],
            admissible=passed and all(h>=d for h,d in zip(half,bounds))))
    available=[c for c in candidates if c['all_capture']]
    chosen=min(available,key=lambda c:(-c['capture_halfwidth_m_m_rad'][0]*c['capture_halfwidth_m_m_rad'][1],
        *c['capture_halfwidth_m_m_rad'][:2])) if available else None
    return dict(nominal_capture=bool(nominal.get('grasp') and nominal.get('lift')),
                boxes=candidates,selected_capture_box=chosen,admissible=bool(chosen and chosen['admissible']))


def evaluate(cohort,plan):
    read=lambda p:json.loads(p.read_text())
    result=dict(host='oracle-x86',scope='evaluation-only DEV capture and pulse calibration; not confirmation',
        expected_capture_n=225,expected_pulse_jobs=6,runs=[],robots={},pulses=[])
    capture=defaultdict(list);pulses=defaultdict(list);hashes={}
    for job in plan['runs']:
        root=cohort/job['name'];raw=root/'raw'
        if not (root/'EXIT').is_file():raise ValueError('entire diagnostic batch must finish first')
        manifest=read(raw/'artifacts.sha256.json')
        for relative,want in manifest.items():
            path=raw/relative;actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if actual!=want:raise ValueError('raw hash mismatch '+str(path))
        hashes[job['name']]=dict(files=len(manifest),all_match=True,
            manifest_sha256=hashlib.sha256((raw/'artifacts.sha256.json').read_bytes()).hexdigest())
        value=read(raw/'result.json');b=read(raw/'bundle.json')
        if b['host']!='oracle-x86' or b['student_control'] is not False or b['seed']!=job['seed']:
            raise ValueError('host/control/seed receipt mismatch')
        result['runs'].append(dict(name=job['name'],kind=job['kind'],status=value['status'],
            source_sha=b['source_sha'],wall_s=value['wall_s'],sim_s=value.get('sim_s'),hashes=hashes[job['name']]))
        if job['kind']=='capture':
            for trial in value['results']:
                trial=dict(trial,source_result=str(raw/'result.json'))
                capture[trial['grid']['robot']].append(trial)
        else:
            if value['status']!='COLLECTED':raise ValueError('pulse job incomplete')
            for line in (raw/'pulse-responses.jsonl').read_text().splitlines():
                row=json.loads(line);a=row['action'];axis=next(k for k in ('forward','left','turn') if a[k])
                pulses[(axis,a[axis])].append(row)
    bounds={}
    for (axis,u),rows in sorted(pulses.items()):
        i=('forward','left','turn').index(axis);steps=[r['curve'][-1][i] for r in rows]
        magnitude=list(map(abs,steps));span=max(magnitude)-min(magnitude)
        final=[r['curve'][-1] for r in rows]
        stat=dict(axis=axis,speed=round(u*100),n=len(rows),median=statistics.median(steps),
            min=min(steps),max=max(steps),max_abs_step=max(magnitude),spread=span,
            conservative_step_bound=max(magnitude)+span,
            max_cross_xy_m=max(max(abs(v[j]) for j in (0,1) if j!=i) if i<2 else max(abs(v[0]),abs(v[1])) for v in final),
            all_expected_direction=all(s*u>0 for s in steps),
            hardware_admissible=abs(u)==.35,
            reason='recorded physical <=30 stationary;35 is existing floor',
            units='rad' if axis=='turn' else 'm')
        result['pulses'].append(stat)
        if abs(u)==.35:bounds[axis]=max(bounds.get(axis,0),stat['conservative_step_bound'])
    demand=[bounds[a] for a in ('forward','left','turn')]
    result['required_halfwidth_m_m_rad']=demand
    for rid,trials in sorted(capture.items()):
        q=admissible_box(trials,demand)
        reasons=Counter()
        for t in trials:
            if t['status']=='HOST_ERROR':reason='HOST_ERROR'
            elif t['status']=='PHYSICAL_STOP':reason='PHYSICAL_STOP'
            elif not t.get('grasp'):reason='NO_BILATERAL_PRELIFT_CONTACT'
            elif not t.get('lift'):reason='NO_SUSTAINED_CONTACT_LIFT'
            else:reason='CAPTURE'
            reasons[reason]+=1
        result['robots'][rid]=dict(n=len(trials),grasp_n=sum(bool(r.get('grasp')) for r in trials),
            lift_n=sum(bool(r.get('lift')) for r in trials),capture_n=sum(bool(r.get('grasp') and r.get('lift')) for r in trials),
            causes=dict(reasons),selection=q,trials=trials)
    result['all_raw_hashes_match']=True
    result['candidate_admissible']=len(result['robots'])==3 and all(r['selection']['admissible'] for r in result['robots'].values())
    result['decision']='ADMISSIBLE_DEV_PROFILE' if result['candidate_admissible'] else 'NOT_ADMISSIBLE_CURRENT_GRID'
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--cohort',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle x86 evaluation only')
    a.output.mkdir(parents=True,exist_ok=False)
    result=evaluate(a.cohort,json.loads(a.plan.read_text()))
    (a.output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    (a.output/'evaluator-sha256.txt').write_text(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+'\n')
    print(json.dumps(dict(decision=result['decision'],robots={r:{k:v for k,v in s.items() if k not in ('trials','selection')} for r,s in result['robots'].items()})))


if __name__=='__main__':raise SystemExit(main())
