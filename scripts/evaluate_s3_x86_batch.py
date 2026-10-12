"""Completed cohort evaluation and saved-RGB video, at most ten parallel jobs."""
import argparse,concurrent.futures,hashlib,json,os,platform,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def one(name,output):
    raw=Path.home()/'ugrp-sim/runs'/name/'raw'
    if not (raw.parent/'EXIT').exists():raise ValueError('unfinished source: '+name)
    target=output/name;target.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONPATH=str(ROOT))
    e10=ROOT/'experiments/2026-10-09-s3-no-prior/s3fix10/evaluate_probe.py'
    e8=ROOT/'experiments/2026-10-09-s3-no-prior/s3fix8/build_probe_delivery.py'
    with (target/'evaluation.log').open('w') as log:
        subprocess.run([sys.executable,str(e10),'--raw',str(raw),'--output',str(target/'evaluation')],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run([sys.executable,str(e8),'--raw',str(raw),'--report',str(target/'evaluation/report.json'),'--output',str(target/'delivery')],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    report=json.loads((target/'evaluation/report.json').read_text());b=json.loads((raw/'bundle.json').read_text())
    view=target/'delivery/result.json';v=json.loads(view.read_text())
    v.update(seed=b['seed'],host='oracle-x86',case=name,condition=b['servo_option'])
    v['policy']='x86 staged own RGB; '+b['stage_scope']
    v['offline_scalars'].update({'offline/physical_stops':int(report['status']=='PHYSICAL_STOP'),
        'offline/infrastructure_interruptions':0})
    if 'cyan_physics' in report:
        q=report['cyan_physics'];v['offline_scalars']['offline/contact_lift_xy_m']=q['max_xy_displacement_while_contact_lifted_m']
        v['offline_scalars']['offline/contact_lift_samples']=q['lift_with_both_fingers_samples']
    schedule=raw.parent/'scheduling.jsonl'
    if schedule.exists():v['scheduling']=[json.loads(s) for s in schedule.read_text().splitlines()];v['wall_comparison_excluded']=True
    view.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
    return dict(name=name,source_sha=b['source_sha'],seed=b['seed'],condition=b['initial_condition'],
        status=report['status'],sim_s=report['sim_s'],wall_s=report['wall_s'],robots=report['robots'],
        cyan_physics=report.get('cyan_physics'),frame_analysis=report['frame_analysis'],
        physical_stop=report.get('physical_stop'),artifact_verification=report['artifact_verification'],
        wall_comparison_excluded=schedule.exists(),report_path=str(target/'evaluation/report.json'),
        report_sha256=hashlib.sha256((target/'evaluation/report.json').read_bytes()).hexdigest())


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='append',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or platform.machine()!='x86_64':raise ValueError('Oracle x86 evaluation only')
    if len(a.run)!=len(set(a.run)):raise ValueError('duplicate run')
    a.output.mkdir(parents=True,exist_ok=False);rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures={pool.submit(one,name,a.output):name for name in a.run}
        for f in concurrent.futures.as_completed(futures):
            try:row=f.result()
            except Exception as e:row=dict(name=futures[f],evaluation_error=str(e))
            rows.append(row);print(json.dumps({k:row[k] for k in ('name','status','evaluation_error') if k in row}),flush=True)
    (a.output/'summary.json').write_text(json.dumps(sorted(rows,key=lambda r:r['name']),indent=2,allow_nan=False)+'\n')
    return int(any('evaluation_error' in r for r in rows))


if __name__=='__main__':raise SystemExit(main())
