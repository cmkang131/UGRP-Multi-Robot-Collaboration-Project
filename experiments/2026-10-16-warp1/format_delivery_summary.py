"""Format already verified gcp2 calculations; no simulation or causal analysis."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
full=root/'summary-detail.json'
if not full.exists():(root/'summary.json').rename(full)
source=json.loads(full.read_text())
audit=source['input_audits']
assert all(a['invisible_measurements']==0 and a['held_world_reads']==0 for a in audit)
summary={k:source[k] for k in ('status','work_status','generated_utc','physics_backend','backend_default','PR','base_sha','teacher_sha','scope','nonphysics_tests','records','raw_hash_mismatches','gate_queue','remaining','prohibitions_observed','cost_scope','raw_backup')}
summary.update(detail_file=full.name,detail_sha256=hashlib.sha256(full.read_bytes()).hexdigest(),format_only_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),operations='operations.json',every_run_ledger='rejection_table.json',input_audits=dict(records=len(audit),invisible_measurements=0,held_world_reads=0,detail='summary-detail.json input_audits'))
summary['cohorts']=[dict(backend=c['backend'],host=c['host']['instance'],native_sleep=c['native_sleep'],nworld=c['nworld'],attempted_worlds=c['attempted_worlds'],returned_worlds=c['returned_worlds'],physical_success_worlds=c['physical_success_worlds'],cap_end_worlds=c['cap_end_worlds'],unique_seeds=c['unique_seeds'],successful_unique_seeds=c['successful_unique_seeds']) for c in source['cohorts']]
summary['throughput']=[{k:b[k] for k in ('run','nworld','world_cap_SIM_s','aggregate_SIM_s','cold_SIM_s_per_wall_s','loop_SIM_s_per_wall_s','estimated_SIM_s_per_USD')} for b in source['throughput']]
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
# Retain the exact downloaded content and make its local filename explicit.
receipt=root/'final-transfer-hashes.json';rows=json.loads(receipt.read_text())
for row in rows:
 name=Path(row['raw']).name
 row['local_name']='summary-detail.json' if name=='summary.json' else 'l4-results.json' if name=='l4-results-compact.json' else name
receipt.write_text(json.dumps(rows,indent=2)+'\n')
