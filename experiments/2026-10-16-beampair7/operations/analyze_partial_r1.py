"""Reconcile every started/supervisor-stopped R1 original, including missing adapters."""
from pathlib import Path
import json,sys,hashlib,collections
ROOT=Path('/home/ugrp/ugrp-sim');OPS=ROOT/'ops-reviews/beampair7'
sys.path.insert(0,str(ROOT/'src/ef284e92510ca4283f1db5de9aecd1dac5c17b0b'))
from scripts.audit_beampair1 import read,recount,ordered_funnel,verify_manifest
from scripts.analyze_beampair1 import rejection_rows,candidate_funnels
cfg=read(OPS/'gate40-queue-r1-attempt2.json');batch=OPS/cfg['batch_name'];done=read(batch/'DONE.json')
rows=[];rejections=[];candidate={};funnel_stages=collections.Counter()
for run in done['completed']:
 raw=Path(run['raw']);d=read(raw/'result.json')
 try:e=recount(raw)
 except Exception as error:e=dict(raw=str(raw),strict_success=False,visible_eligible=False,status=d.get('status'),analysis_error=repr(error))
 adapter=raw.parent/'adapter/beampair1-result.json'
 final=adapter.exists() or Path(str(adapter)+'.zst').exists()
 a=read(adapter) if final else None
 e.update(seed=run['seed'],supervisor_category=run['category'],adapter_finalized=final,
     adapter_sha=a['source_sha'] if a else None,adapter_manifest_verified_files=verify_manifest(adapter.parent) if final else None,
     held_object_hidden_v1=a['held_object_hidden_v1'] if a else None,held_world_reads=a['held_world_reads'] if a else None,
     input_audit_coverage='final raw and adapter' if final and d['status']=='complete' else 'partial; not a completed input audit')
 e['strict_eligible_success']=bool(e.get('strict_success') and e.get('visible_eligible') and a and a['held_object_hidden_v1'] and a['held_world_reads']==0)
 for stage,phases in [('both_align',('align','ready','pick','complete')),('both_ready',('ready','pick','complete')),('both_pick',('pick','complete')),('both_command_complete',('complete',))]:
  passed=len(d.get('teachers',{}))==2 and all(any(x.get('to') in phases for x in t.get('events',[])) for t in d['teachers'].values());funnel_stages[stage]+=int(passed)
 rs=rejection_rows(d)
 if run['category']=='supervisor_stop':rs.append(dict(reason='supervisor_stop',reason_category='supervisor_stop',blocked_object='none:supervisor_stop',min_gap_m=None,gap_scope='operational interruption after seed8318728 terminal; not geometric failure',population='terminal_run_events'))
 rejections += [dict(seed=run['seed'],**x) for x in rs];candidate[str(raw)]=candidate_funnels(d);rows.append(e)
n=sum(x['strict_eligible_success'] for x in rows);reasons=collections.Counter(x['reason_category'] for x in rejections);blockers=collections.Counter(x['blocked_object'] for x in rejections)
funnel=ordered_funnel(40,[('started',len(rows)),*[(k,funnel_stages[k]) for k in ('both_align','both_ready','both_pick','both_command_complete')],('joint_hold_3s',sum(bool(x.get('strict_success')) for x in rows)),('input_eligible_success',n)])
out=OPS/'analysis-gate-r1';out.mkdir(exist_ok=True)
report=dict(source_sha=cfg['source_sha'],planned_N=40,N=len(rows),n=n,terminal_failure_N=sum(r['supervisor_category']=='failure' for r in rows),supervisor_stop_N=sum(r['supervisor_category']=='supervisor_stop' for r in rows),HOST_ERROR_N=sum(r['supervisor_category']=='HOST_ERROR' for r in rows),cap_end_N=sum(bool(r.get('cap_end')) for r in rows),unstarted_N=40-len(rows),incomplete_N=sum(r['status']!='complete' for r in rows),input_audit_complete_N=sum(r['input_audit_coverage']=='final raw and adapter' for r in rows),runs=rows,reason_distribution=dict(reasons),blocked_object_distribution=dict(blockers),raw_root=str(ROOT/'runs'),reproduce='python3 '+str(Path(__file__).resolve()),scope='No interrupted/running result or missing adapter promoted to complete; statuses and original hashes retained')
(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
table=dict(source_sha=cfg['source_sha'],episode_funnel=funnel,reason_distribution=dict(reasons),blocked_objects=dict(blockers),candidate_populations=candidate,reproduce=report['reproduce'],missing_rejection_audit_N=sum(x.get('blocked_object') in ('not_recorded','') or not x.get('reason_category') for x in rejections))
(out/'rejection-table.json').write_text(json.dumps(table,indent=2)+'\n')
(out/'candidate-rejections.json').write_text(json.dumps(rejections,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('runs','reason_distribution','blocked_object_distribution')}))
