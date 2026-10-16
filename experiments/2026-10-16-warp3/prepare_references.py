"""Finite Linux gcp2 preparation: independent source cases, no teacher rollout."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();source=a.source.resolve();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    teacher=Path('/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e')
    py='/home/ugrp/ugrp-sim/runs/simalt3/c-env/bin/python'
    plan=source/'experiments/2026-10-16-warp1/all-source-plans.json'
    episodes=json.loads(plan.read_text())['episodes']
    assert len(episodes)==len({r['seed'] for r in episodes})==40
    def one(i):
        folder=out/f'case-{i:02d}'
        cmd=[py,str(source/'scripts/run_warp_act_teacher.py'),'--teacher-source',str(teacher),
            '--plan',str(plan),'--episode',str(i),'--physics-backend','c_pilot_v1','--scene-v5-v1',
            '--native-sleep-policy-compat-v1','--export-compiled-only','--vm-hourly-usd','1.096','--out',str(folder)]
        with (out/f'case-{i:02d}.log').open('x') as log:
            result=subprocess.run(cmd,cwd=source,stdout=log,stderr=subprocess.STDOUT,
                env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'})
        if result.returncode:raise RuntimeError(f'reference export {i}: exit{result.returncode}; see log')
        report=json.loads((folder/'summary.json').read_text());xml=folder/'world-000/scene.xml'
        return dict(index=i,seed=episodes[i]['seed'],scenario=episodes[i]['scenario_id'],
            model_counts=report['model_counts'],xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
            actuator=str(folder/'compiled-312.json'),geometry=str(folder/'compiled-geometry312.npz'),
            source_sha=report['source_sha'],status=report['status'])
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(one,range(40)))
    (out/'inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
    refs={r['xml_sha256']:{k:r[k] for k in ('actuator','geometry')} for r in rows}
    (out/'per-world-references.json').write_text(json.dumps(refs,indent=2)+'\n')
    print(json.dumps(dict(cases=len(rows),counts=sorted({json.dumps(r['model_counts'],sort_keys=True) for r in rows}))))


if __name__=='__main__':main()
