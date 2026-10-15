"""Finite gcp2 experiment record, executed with simalt3/warp-env/bin/python."""
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np

ROOT=Path('/home/ugrp/ugrp-sim/runs/simalt4')
OLD=ROOT.parent/'simalt3'
REV=ROOT/'revf8'
PY=OLD/'warp-env/bin/python'

def result(name):
    return json.loads((ROOT/name/'result.json').read_text())

while result('warp-v2-grip')['status']=='running':
    time.sleep(5)

for case in ('side','turn','grip'):
    if result('warp-v2-'+case)['status']!='complete':
        continue
    cmd=[str(PY),str(ROOT/'scripts/simalt_step_analysis.py'),'--fixture',str(OLD/'fixture'),
         '--reference',str(ROOT/('c316-'+case)),'--candidate',str(ROOT/('warp-v2-'+case)),
         '--out',str(ROOT/('backend-'+case))]
    with (ROOT/f'backend-{case}-analysis.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)

cases=[]
for case in ('forward','side','turn','grip'):
    data=np.load(ROOT/f'c316-{case}/steps.npz')['records']
    cases.append({'name':case,'max_ncon':int(data[:,0].max()),
                  'max_nefc':int(data[:,1].max()),'raw_path':str(ROOT/f'c316-{case}/steps.npz')})
(ROOT/'dense-capacity.json').write_text(json.dumps({'dense_envelope':True,
    'basis':'every C3.16 physics step, allocator rounds observed maxima to power of two',
    'cases':cases},indent=2)+'\n')

rejections=json.loads((REV/'experiments/2026-10-16-simalt4/rejection_table.json').read_text())
rejections['same_version_backend']=[json.loads(p.read_text()) for p in sorted(ROOT.glob('backend-*/summary.json'))]
rejections['baseline_GPU_run_statuses']={case:result('warp-v2-'+case)['status'] for case in ('forward','side','turn','grip')}
(ROOT/'rejection-before-round2.json').write_text(json.dumps(rejections,indent=2)+'\n')

commands=[]
for case in ('forward','side','turn','grip'):
    commands.append([str(PY),'-u',str(REV/'scripts/simalt_step_probe.py'),'--enabled',
        '--fixture',str(OLD/'fixture'),'--out',str(ROOT/f'legacy-{case}'),'--engine','warp',
        '--case',case,'--sha','f8f0bdf7','--capacity-reference',str(ROOT/'dense-capacity.json'),
        '--dense-capacity-v1','--backend-mode','legacy-plane-v1','--record-own-rgb',str(OLD/'runtime/source')])
plan={'rejection_table':str(ROOT/'rejection-before-round2.json'),'round':2,
      'commands':commands,'source_sha':'f8f0bdf7','physics_overrides':{}}
(ROOT/'round2-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
assert Path(plan['rejection_table']).is_file()
for cmd in commands:
    out=Path(cmd[cmd.index('--out')+1])
    with (ROOT/(out.name+'.log')).open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,
                       env={**os.environ,'MUJOCO_GL':'osmesa','LP_NUM_THREADS':'1'},check=True)
    info=result(out.name)
    print(out.name,info['status'],info.get('error',''),flush=True)
    if info['status']!='complete':
        break
