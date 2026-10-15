"""Authorize fresh gate80 only after saved run-first recount passes, gcp2 only."""
from pathlib import Path
import copy, datetime, hashlib, json, sys
ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/release25'
def read(p):return json.loads(p.read_text())
short=read(Path(sys.argv[1]));sha=short['source_sha'];out=OPS/('release-short-analysis-'+sha[:8])
proof=out/'summary-with-candidates.json';s=read(proof)
assert s['source_sha']==sha and len(s['runs'])==6 and all(x['recount_success'] for x in s['runs'])
assert s['all_release25_mode'] and s['all_pinned_scene'] and s['false_accepts']==0
assert not s['hash_errors'] and not s['population_hash_errors']
for x in s['sources']:assert hashlib.sha256(Path(x['path']).read_bytes()).hexdigest()==x['sha256']
cfg=read(ROOT/'ops-reviews/gatesv5/release-gate-config.json')
for k in ('carry_forward_completed','previous_attempt'):cfg.pop(k,None)
table=out/'rejection_table-with-candidates.json';assert table.is_file()
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
cfg.update(pr=535,source_sha=sha,source_worktree='/Users/changmin/projects/ugrp-wt/release25',
    remote_pinned_source=str(ROOT/'src'/sha),operator='release25',plan=short['plan'],
    plan_sha256=short['plan_sha256'],stage='gate',max_parallel=16,attempt=1,max_host_total=40,
    approved=True,ready=True,review_passed=True,status='APPROVED_PINNED',scene_approved=True,
    review_detail='REVIEW_SKIPPED_BY_USER (10/15 run-first rule)',approved_utc=now,
    run_first_proof=str(proof),run_first_proof_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),
    rejection_table=str(table),rejection_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest(),
    submitted=False,prior_results_pooled=False)
priority={110633:0,88639:1,110622:2}
rows=sorted(copy.deepcopy(cfg['runs']),key=lambda r:(priority.get(r['seed'],3),r['seed'],r['candidate']))
assert len(rows)==80 and len({(r['seed'],r['candidate']) for r in rows})==80
assert all(sum(r['candidate']==c for r in rows)==40 for c in ('current_A','current_B'))
for r in rows:
    r.update(name=f"release25-gate-{r['candidate']}-{r['seed']}-{sha[:8]}",source_sha=sha,stage='gate',
             approved=True,enabled=True,ready=True,submitted=False,scheduled=False,executed=False)
    r['profile']['release_sweep_wall_aware']='release_sweep_wall_aware_v1'
cfg['runs']=rows
path=OPS/'gate-config.json';assert not path.exists()
path.write_text(json.dumps(cfg,indent=2)+'\n')
print(json.dumps(dict(config=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    source_sha=sha,review_detail=cfg['review_detail'],status=cfg['status'],first_six=[r['name'] for r in rows[:6]])))
