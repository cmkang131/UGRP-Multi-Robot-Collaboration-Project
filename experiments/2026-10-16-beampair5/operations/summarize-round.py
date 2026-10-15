"""gcp2-only summary, integrity and wall-update funnel; no raw state on Mac."""
import pathlib,sys,json,hashlib,collections,subprocess
r=pathlib.Path('/home/ugrp/ugrp-sim');ops=r/'ops-reviews/beampair5';round_id=sys.argv[1];sha=sys.argv[2];src=r/'src'/sha;sys.path.insert(0,str(src))
from scripts.audit_beampair1 import read,read_bytes,verify_manifest
analysis=ops/(round_id+'-analysis');report=read(analysis/'summary.json');table=read(analysis/'rejection-table.json')
blocks=collections.defaultdict(list);wall_reports={};integrity=[];first30=[]
for entry in report['runs']:
 raw=pathlib.Path(entry['raw']);result=read(raw/'result.json');adapter=raw.parent/'adapter'
 for rid,t in result['teachers'].items():
  for e in t['search22_log']:
   for c in e.get('candidates',[]):
    for d in c.get('failure_audit') or [v for v in c.get('collision_audit',[]) if v.get('blocked')]:
     blocks[(c['reason'],d.get('category'),d.get('id',d.get('object','missing')))].append(d.get('gap_m'))
 layers=read(adapter/'wall-layer.json');seeds={}
 for rid,events in layers['events'].items():
  seen=[e for e in events if e['active']]
  seeds[rid]=dict(active=layers['activated'][rid],scan_N=len(seen),ray_N=sum(e['ray_N'] for e in seen),miss_cell_updates=sum(e['miss_cell_N'] for e in seen),cleared_cell_updates=sum(e['cleared_cell_N'] for e in seen),cleared_by_object=dict(sum((collections.Counter(e['cleared_by_object']) for e in seen),collections.Counter())),last=events[-1])
 wall_reports[str(entry['seed'])]=dict(robots=seeds,visible_ray_N=layers['visible_ray_N'],held_ray_N=layers['held_ray_N'])
 ll={rid:[json.loads(x) for x in read_bytes(raw/f'teacher-{rid}.jsonl')[0].splitlines()] for rid in ('r1','r2')}
 origin=min(l[0]['applied_command']['t'] for l in ll.values());rows=[v for labels in ll.values() for v in labels if v['applied_command']['t']<origin+30-1e-8]
 first30.append(dict(seed=entry['seed'],through_sim_s=min(30,result.get('sim_s',max(l[-1]['applied_command']['t'] for l in ll.values())-origin)),commands_N=len(rows),nonzero_wheel_N=sum(any(v['applied_command']['wheels']) for v in rows),compute_budgets=dict(collections.Counter(v.get('planning_compute',{}).get('budget_kind','not_recorded') for v in rows)),model_calls=0,input_audit=result['input_audit'],timing=read(raw/'first30-speed.json') if (raw/'first30-speed.json').exists() else None))
 integrity.append(dict(seed=entry['seed'],raw_manifest_verified=verify_manifest(raw),adapter_manifest_verified=verify_manifest(adapter),sources={str(read_bytes(raw/n)[1]):read_bytes(raw/n)[2] for n in ('result.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl')},adapter_wall_layer_sha256=read_bytes(adapter/'wall-layer.json')[2]))
 # Keep only the reviewable summary fields needed by the queue's validator.
 keep=('seed','raw','status','sim_s','strict_success','legacy_success','cap_end','held_object_hidden_v1','held_world_reads','hidden_measurement_ticks','probe_executed_ticks','probe_burst_ticks','adapter_sha','dependency_sha','result_path','result_sha256','outcomes','max_strict_hold_s','audit','visible_eligible','event_funnel','frame_funnel','stages')
 for k in list(entry):
  if k not in keep:entry.pop(k)
table['blocker_occurrences']=[dict(reason=k[0],category=k[1],blocked_object=k[2],N=len(v),min_gap_m=min([x for x in v if x is not None],default=None),gap_scope='source candidate failure/collision audit; occurrences overlap') for k,v in sorted(blocks.items(),key=lambda kv:-len(kv[1]))]
table['wall_update_funnel']=wall_reports
report.update(wall_layer=wall_reports,HOST_ERROR_N=sum(e['status']=='HOST_ERROR' for e in report['runs']),round=round_id,cohort_scope='fresh beampair5, no previous versions/hosts pooled')
for name,value in [('summary',report),('rejection_table',table),('integrity',integrity),('first30',first30)]:
 p=ops/(round_id+'-'+name+'.json');p.write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('N','n','cap_end_N','HOST_ERROR_N','round')}))
