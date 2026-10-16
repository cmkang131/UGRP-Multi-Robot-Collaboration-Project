"""Source-host delivery ledger; reads fixed benchmark results, never steps physics."""
import hashlib
import json
from pathlib import Path
import platform
from collections import Counter

assert platform.node().startswith('ugrp-act-l4-gcp6')
raw=Path('/home/ugrp/ugrp-sim/runs/warpfit')
review=Path('/home/ugrp/ugrp-sim/ops-reviews/warpfit-ownhost')
out=review/'report-final-v1'
def dump(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
summary=json.loads((out/'summary.json').read_text())
assert summary['status']=='comparison_complete_with_rejections'
rows=[];capacities=[]
for p in sorted(raw.glob('R*/**/result.json')):
 r=json.loads(p.read_text());assert r['status'] in ('complete','HOST_ERROR')
 item={k:r.get(k) for k in ('engine','round','nworld','status','completed','HOST_ERROR','cap_end','source_sha','sim_s','error','fixture_sha256','xml_sha256')}
 item.update(path=str(p.parent),profile=r['profile']['profile'],reproduce_file=str(p),result_sha256=sha(p))
 rows.append(item)
 if r.get('capacity'):
  capacities.append(dict(path=str(p.parent),nworld=r['nworld'],model=r['model'],capacity=r['capacity'],
      derived_naconmax=r['capacity']['nconmax']*r['nworld'],max_ncon=r.get('max_ncon'),max_nefc=r.get('max_nefc'),
      effective_tolerance=r.get('effective_tolerance'),source='pinned io.py _resolve_batch_size1671..1676; nconmax x nworld'))
assert len(rows)==59
attempts=raw/'R2/attempts.json'
old=attempts.with_name('attempts.before-supervisor-reconciliation.json')
if not old.exists():
 old.write_bytes(attempts.read_bytes());a=json.loads(attempts.read_text())
 assert len(a)==1
 r=json.loads((Path(a[0]['output'])/'result.json').read_text());assert r['completed'] and r['sim_s']==13.7
 a[0].update(status='complete',reconciled_from='finished child result after superseded parent was terminated',exit_code=0)
 dump(attempts,a)
 dump(raw/'R2/funnel.json',dict(stages=[dict(gate='planned_original_long_suite',cumulative_pass=16,rejected=0),
  dict(gate='submitted_before_protocol_refinement',cumulative_pass=1,rejected=15),
  dict(gate='fixed_long_probe_complete',cumulative_pass=1,rejected=0)],
  reasons=[dict(category='withheld_before_submission',count=15,reason='superseded by requested fixed close/lift/hold primitives',
  blocked_object='original long workload',minimum_gap_m=None,gap_status='not_geometric')],
  raw=str(raw/'R2'),reproduce='see original queue.json and each child result.json reproduce argv',
  original_attempts_sha256=sha(old)))
managed=[]
for p in sorted(raw.glob('R*/**/*-managed/manifest.json')):
 m=json.loads(p.read_text());managed.append(dict(path=str(p),status=m['status'],
   source_changed=m.get('source_changed_during_run'),inputs_changed=m.get('inputs_changed_during_run'),
   finalization_errors=m.get('finalization_errors',[]),exit_code=m.get('exit_code')))
assert all(not m['source_changed'] and not m['inputs_changed'] and not m['finalization_errors'] for m in managed)
dump(out/'all-attempts.json',dict(runs=rows,managed=managed,counts=dict(total=59,
  completed=sum(bool(r['completed']) for r in rows),HOST_ERROR=sum(bool(r['HOST_ERROR']) for r in rows),
  cap_end=sum(bool(r['cap_end']) for r in rows)),reproduce='each reproduce_file contains exact source/fixture/profile/nworld argv'))
dump(out/'capacity-summary.json',dict(rows=capacities,basis='observed C/import/R1/R2 maxima and overflow rejection; no physics parameter retuning'))
funnel=json.loads((review/'analysis-final-v1/rejection_table.json').read_text())
for r in funnel['reasons']:r['unit']='world x hold frame' if 'count' in r else 'run'
gap=json.loads((raw/'primitive-v1/drive-clear-v1/fixture.json').read_text())['fixture_ablation']['before_gap']
funnel['reasons'] += [dict(category='initial_overlap_diagnostic',count=8,unit='batch run',
 reason='original N16 pulse cohort is unsuitable for normal-drive calibration',blocked_object='cargo_box_00',
 minimum_gap_m=gap['minimum_gap_m'],gap_status='C3.12 setup contact distance; same original reset',raw=str(raw/'R2-retry1'))]
funnel['primary_jobs']=[dict(gate='planned',cumulative_pass=28,rejected=0),
 dict(gate='terminal',cumulative_pass=28,rejected=0),dict(gate='fixed_work_complete',cumulative_pass=26,rejected=2)]
funnel['box_trial_funnels']=[dict(nworld=r['nworld'],profile=r['profile'],unit='selected fixed-initial-condition trajectory',
 stages=[dict(gate='requested_first30',cumulative_pass=r['selected'],rejected=30-r['selected']),
 dict(gate='loaded_contact_all_hold_frames',cumulative_pass=r['loaded_retained'],rejected=r['selected']-r['loaded_retained']),
 dict(gate='C_reference_temporal_quantiles',cumulative_pass=r['C_reference_quantile_pass'],rejected=r['loaded_retained']-r['C_reference_quantile_pass'])]) for r in summary['box30']]
funnel['queue_funnels']=[str(p) for p in sorted(raw.glob('R*/funnel.json'))]
funnel['reproduce']=['python -m scripts.warpfit_analyze --root '+str(raw)+' --assets '+str(raw/'inputs/src/drivecheck-renderer-5974a181')+' --output <new-analysis>',
 'python -m scripts.warpfit_report --analysis <new-analysis> --output <new-report>']
funnel['distribution']=[dict(category=k[0],unit=k[1],count=v) for k,v in Counter(
 {k:sum(r.get('count',1) for r in funnel['reasons'] if (r['category'],r['unit'])==k)
 for k in {(r['category'],r['unit']) for r in funnel['reasons']}}).items()]
dump(out/'rejection_table.json',funnel)
(out/'thresholds.json').write_bytes((review/'analysis-final-v1/thresholds.json').read_bytes())
(out/'environment.json').write_bytes((raw/'environment.json').read_bytes())
dump(review/'RUN_META.json',dict(schema='ugrp.run_meta.v1',**{'class':'milestone'},pr=562,branch='codex/warpfit',
 sha='7514029f96842e8d3b0582a363915004fc6b7d65',batch='warpfit-analysis',active=False))
print(json.dumps(dict(runs=len(rows),managed=len(managed),source_or_input_changes=0,primary=28,full_fixed_work=26)))
