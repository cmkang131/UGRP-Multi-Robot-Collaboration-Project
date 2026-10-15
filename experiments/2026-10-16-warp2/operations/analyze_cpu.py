"""Read-only gcp2 result/hash/command replay audit; no simulation or rendering."""
from pathlib import Path
import hashlib
import json
import statistics
import subprocess
import sys

ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/home/ugrp/ugrp-sim/runs/warp2-cpu-r1-70553d2f')
OLD=Path('/home/ugrp/ugrp-sim/runs/beampair6-r1-08f12921/round/diagnostic')
SEEDS=[8318726,8318620,8318600,8318604,8318611,8318631]


def raw(path):
    return path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-qdc',str(path)+'.zst'])


records=[];failures=[];files=0;first30=[]
for p in sorted(ROOT.glob('p*/summary.json')):
    report=json.loads(p.read_text());world=report['worlds'][0];seed=world['seed'];i=SEEDS.index(seed)
    for rel,sha in report['sha256'].items():
        data=(p.parent/rel).read_bytes();files+=1
        if hashlib.sha256(data).hexdigest()!=sha:failures.append(str(p.parent/rel))
    previous=OLD/f'episode-{i:03d}'/'adapter/beampair1-commands.jsonl'
    current=p.parent/'world-000/adapter/beampair1-commands.jsonl'
    before,after=raw(previous),raw(current)
    original_prefix=b'\n'.join(before.splitlines()[:len(after.splitlines())])+b'\n'
    adapter=json.loads(raw(p.parent/'world-000/adapter/beampair1-result.json'))
    native=json.loads(raw(p.parent/'world-000/raw/result.json'))
    if native.get('first30_speed'):first30.append(native['first30_speed']['wall_per_sim'])
    records.append(dict(run=p.parent.name,seed=seed,world=world,summary_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        hidden_measurement_ticks=adapter['hidden_measurement_ticks'],held_world_reads=adapter['held_world_reads'],
        command_bytes_equal_original_gcp2=before==after,command_prefix_equal_original_gcp2=original_prefix==after,
        command_sha256=hashlib.sha256(after).hexdigest(),
        raw=str(p.parent),original_raw=str(previous.parent)))
batch=json.loads((ROOT/'summary.json').read_text());sim=batch['aggregate_completed_sim_s'];wall=batch['wall_s'];price=batch['price_hourly_usd']
result=dict(schema='ugrp.warp2.cpu_comparison.v1',source_sha='70553d2f4235b28648c188b26f9b2a03fa32a19d',
    backend='c_pilot_v1',host='gcp2/ugrp-sim-gcp2/n4-highcpu-64',concurrency=16,
    physical_success=sum(r['world']['physical_success'] for r in records),N=len(records),unique_seeds=len({r['seed'] for r in records}),
    cap_end=sum(r['world']['cap_end'] for r in records),HOST_ERROR=0,
    aggregate_completed_sim_s=sim,batch_wall_s=wall,sim_s_per_wall_s=sim/wall,
    sim_s_per_usd_estimate=3600*sim/wall/price,vm_cost_usd_estimate=wall*price/3600,
    price_hourly_usd=price,price_basis=batch['price_basis'],co_tenancy_admission=str(ROOT/'admission.json'),
    first30=dict(N=len(first30),median=statistics.median(first30) if first30 else None,
        min=min(first30) if first30 else None,max=max(first30) if first30 else None),
    sha256_check=dict(files=files,mismatches=failures),
    commands_equal_original_gcp2_N=sum(r['command_bytes_equal_original_gcp2'] for r in records),
    command_prefix_equal_original_gcp2_N=sum(r['command_prefix_equal_original_gcp2'] for r in records),
    records=records,raw=str(ROOT),reproduce='python3 '+str(Path(__file__).resolve()),
    pooling=False,scope='new C backend comparison; repeated seeds are not independent trials; GPU results separate')
(ROOT/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
