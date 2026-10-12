"""Saved-frame provenance validation only; no RGB decoding, model or physics."""
import cProfile, hashlib, json, pstats, statistics, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.e2e_own_inputs import rgb_ref
source=Path('/Users/changmin/projects/ugrp/outputs/azure-runs/e2e11-b-s61001-r2/raw/robots/r1/frames.jsonl.zst')
frames=[json.loads(x) for x in subprocess.check_output(['zstd','-dc',str(source)]).splitlines()]
origin=frames[0]['sim_time']
refs=[dict(robot_id='r1',frame_id=f['frame_id'],t_sim=round(f['sim_time']-origin,8),sha256=f['sha256']) for f in frames]
rows=[]
for n in (51,151,301,601,901,1201,1351):
    observed=refs[:n];samples=[]
    for _ in range(5):
        t=time.perf_counter()
        for ref in observed:rgb_ref(ref,'r1',observed[-1]['t_sim'],observed)
        samples.append(time.perf_counter()-t)
    rows.append(dict(n=n,sim_s=observed[-1]['t_sim'],median_s=statistics.median(samples),list_membership_comparisons=n*(n+1)//2))
profile=cProfile.Profile();profile.enable()
for ref in refs[:1351]:rgb_ref(ref,'r1',270.,refs[:1351])
profile.disable();stats=pstats.Stats(profile)
functions=[dict(file=k[0],line=k[1],name=k[2],calls=v[1],self_s=v[2],cumulative_s=v[3]) for k,v in stats.stats.items()]
result=dict(scope='Mac saved-text microbenchmark, NOT historical Azure RBPF or total map time; no controller change',source=dict(path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest()),samples=rows,profile=sorted(functions,key=lambda x:x['cumulative_s'],reverse=True)[:10],source_sha256=hashlib.sha256((ROOT/'harness/e2e_own_inputs.py').read_bytes()).hexdigest())
Path(__file__).with_name('saved-ref-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(rows))
