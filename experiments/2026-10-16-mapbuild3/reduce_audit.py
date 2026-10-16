"""gcp2 CPU only: concise table, A/B setup identity proof, original row links."""
import csv,hashlib,json,sys
from pathlib import Path
base=Path(sys.argv[1]);out=Path(sys.argv[2]);cases=Path(sys.argv[3]);out.mkdir(exist_ok=False)
read=lambda p:json.loads(p.read_text())
rows=read(base/'audit-rows.json');summary=read(base/'summary.json');queue=read(cases)
A=queue[::2];B=queue[1::2]
assert len(A)==len(B)==40 and all(a['plan']==b['plan'] for a,b in zip(A,B))
assert all({k:v for k,v in a['profile'].items() if k!='release_profile'}=={k:v for k,v in b['profile'].items() if k!='release_profile'} for a,b in zip(A,B))
proof=dict(cases=str(cases),sha256=hashlib.sha256(cases.read_bytes()).hexdigest(),plans_identical=40,
    profiles_difference_only='release_profile: release18_v1 vs release19_v1; frozen run_grasp_act_release before first advance is identical',
    source_sha='8e81b7d96c0c73171635348c90631462adfe1eb0',scope='shared authored starts, not independent simulation or saved tick0 proof')
for r in list(rows):
    if r['cohort']=='warp8_release_A':rows.append({**r,'cohort':'warp8_release_B','state_scope':r['state_scope'],'same_start_alias':'warp8_release_A; setup identity proof'})
for r in list(summary['counts']):
    if r['cohort']=='warp8_release_A':summary['counts'].append({**r,'cohort':'warp8_release_B','same_start_alias':True})
summary['release_AB_setup_identity']=proof
with (out/'seed-overlap-table.csv').open('w') as f:
    fields=['cohort','seed','state_scope','original_task_tick0','accepted','pair_count','rejected_contact_points_n','minimum_gap_m','gap_status','same_start_alias']
    w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
    for r in rows:w.writerow(r)
(out/'overlap-details.json').write_text(json.dumps([r for r in rows if not r['accepted']],indent=2)+'\n')
(out/'audit-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'rejection_table.json').write_text(json.dumps(dict(raw=str(base),reproduction=sys.argv,
    cohorts=summary['counts'],release_AB_identity=proof,rejection_fields='raw audit-rows.json rejections: category/reason/blocked_object/minimum_gap_m/penetration_depth_m'),indent=2)+'\n')
(out/'source-receipt.json').write_text(json.dumps(dict(script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    inputs={p.name:dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in base.iterdir() if p.is_file()}),indent=2)+'\n')
