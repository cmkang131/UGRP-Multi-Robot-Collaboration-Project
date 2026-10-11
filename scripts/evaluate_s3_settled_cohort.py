"""Evaluate the completed frozen cohort together, never a controller input."""
import argparse
import concurrent.futures
import hashlib
import json
import platform
from pathlib import Path
from scripts.evaluate_s3_x86_batch import one
from scripts.run_s3_settled_cohort import PLAN


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


def evaluate(name, output):
    result=one(name,output)
    raw=Path.home()/'ugrp-sim/runs'/name/'raw'
    directory=output/name
    report=read(directory/'evaluation/report.json')
    for rid, robot in report['robots'].items():
        frames=rows(directory/f'evaluation/frames/{rid}-frames.jsonl')
        hit=lambda e: e is not None and abs(e[0])<=.003 and abs(e[1])<=.003 and (rid=='r3' or abs(e[2])<=.035)
        robot['first_tolerance_t']=next((f['t'] for f in frames if hit(f['errors_m_m_rad'])),None)
    truth={x['t']:x for x in rows(raw/'eval_only/referee_truth.jsonl')}
    both_lift=[]
    for frame in rows(raw/'eval_only/contacts.jsonl'):
        item=truth.get(frame['t'],{}).get('items',{}).get('beam_1',{})
        touched={c[k] for c in frame['contacts'] if 'cargo_beam_1' in c['geom1'] or 'cargo_beam_1' in c['geom2'] for k in ('geom1','geom2')}
        if item.get('z',0.)>.06 and all(r+'__'+side+'_finger' in touched for r in ('r1','r2') for side in ('left','right')):
            both_lift.append(frame['t'])
    report['beam_physics']=dict(four_finger_contact_above_06m_samples=len(both_lift),
        first_contact_lift_t=both_lift[0] if both_lift else None,
        max_com_z_m=max(x['items']['beam_1']['z'] for x in truth.values()),evaluation_only=True)
    report['host_timing']=read(raw/'host-timing.json')
    target=directory/'evaluation/report.json';target.write_text(json.dumps(report,indent=2)+'\n')
    view=directory/'delivery/result.json';value=read(view)
    value['offline_source']['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
    value['offline_scalars']['offline/beam_lift_contact_samples']=len(both_lift)
    for rid, robot in report['robots'].items():
        value['offline_scalars'][f'offline/{rid}/turn_reversals']=report['frame_analysis'][rid]['turn_reversals']
        if robot['first_tolerance_t'] is not None:
            value['offline_scalars'][f'offline/{rid}/first_tolerance_t']=robot['first_tolerance_t']
    view.write_text(json.dumps(value,indent=2)+'\n')
    result.update(robots=report['robots'],beam_physics=report['beam_physics'],host_timing=report['host_timing'],
                  report_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle x86 only')
    names=[r['name'] for r in read(PLAN)['runs']]
    for name in names:
        if not (Path.home()/'ugrp-sim/runs'/name/'EXIT').exists():raise ValueError('entire cohort must finish first')
    a.output.mkdir(parents=True,exist_ok=False);results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures={pool.submit(evaluate,n,a.output):n for n in names}
        for f in concurrent.futures.as_completed(futures):
            try:result=f.result()
            except Exception as e:result=dict(name=futures[f],evaluation_error=str(e))
            results.append(result);print(json.dumps({k:v for k,v in result.items() if k in ('name','status','evaluation_error')}),flush=True)
    (a.output/'summary.json').write_text(json.dumps(sorted(results,key=lambda r:r['name']),indent=2)+'\n')
    return int(any('evaluation_error' in r for r in results))


if __name__=='__main__':raise SystemExit(main())
