import sys,json,hashlib,subprocess,statistics
from pathlib import Path
from collections import Counter,defaultdict
sys.path.insert(0,str(Path.cwd()))
from scripts.analyze_grasp_act_search24 import read
from scripts.analyze_grasp_act_search25 import funnel
R=Path(sys.argv[1]);O=Path(sys.argv[2]);O.mkdir(parents=True,exist_ok=True)
def get(p):
 try:return json.loads(read(p) or b'{}')
 except Exception:return {}
def steps(kv):
 out=[];prev=None
 for k,n in kv:out.append({'gate':k,'cumulative_pass':n,'rejected_here':None if prev is None else prev-n});prev=n
 return out
outer=get(R/'diagnostic.json');rows=[]
for x in outer.get('rows',[]):
 raw=Path(x['raw']);d=get(raw/'result.json');p=get(raw/'plan.json');tch=d.get('teachers',{});c=Counter();events=Counter();frames=Counter();stages=defaultdict(Counter);pop=defaultdict(list);new=[];stats={}
 for rid,t in tch.items():
  stats[rid]=t.get('search27_stats',{})
  for e in t.get('search22_log',[]):
   cs=e.get('candidates',[])
   if not cs:continue
   events['events']+=1;events['any_endpoint_prefix_pass']+=any(r.get('reason') in ('endpoint_feasible','feasible') or r.get('reason','').startswith('connector') or r.get('reason')=='first_command_invalid' for r in cs)
   events['any_complete_pass']+=any(r.get('reason')=='feasible' for r in cs)
   for r in cs:
    reason=r.get('reason','missing');c[reason]+=1;pop[r.get('population','legacy_combined')].append(r)
  for e in t.get('search20_log',[]):
   if e.get('event') in ('start_geometry_invalid','start_escape_issued','command_feasibility_reject','final_command_reject'):new.append({'rid':rid,**e})
 labels={rid:[json.loads(s) for s in (read(raw/f'teacher-{rid}.jsonl') or b'').splitlines()] for rid in p.get('roles',{})}
 for i,s in enumerate((read(raw/'eval-only.jsonl') or b'').splitlines()):
  e=json.loads(s)
  for rid,end in p.get('roles',{}).items():
   frames['input_frames']+=1
   if i>=len(labels[rid]):continue
   frames['label_written']+=1
   if labels[rid][i].get('teacher_phase') not in ('approach','align','ready'):continue
   frames['approach_align_ready']+=1
   if e['visibility'][rid]['visible_probes']<5:continue
   frames['band_visible']+=1
   if any(m['id']=='band_'+end for m in e['visible_measurements'][rid]):frames['band_admitted']+=1
 actual={}
 for name,rr in pop.items():
  if name=='legacy_combined':actual[name]={'N':len(rr),'terminal_reasons':dict(Counter(r.get('reason') for r in rr)),'scope':'no explicit stage counters; zero on startup failure'};continue
  order=['IRM','jaw','bounds','goal','retreat']+(['view','pick_arm','endpoint'] if name=='endpoint' else ['path','body_path','view','pick_arm','connector','first_command','feasible'])
  actual[name]={'N':len(rr),'funnel':steps([('entered',len(rr)),*[(k,sum(k in r.get('passed_gates',[]) for r in rr)) for k in order]])}
 category='success' if d.get('status')=='complete' and d.get('physical_success') and x.get('exit')==0 else 'cap_end' if d.get('cap_end') else 'HOST_ERROR' if x.get('status')=='HOST_ERROR' or d.get('status')=='HOST_ERROR' else 'supervisor_stop' if x.get('exit')==130 or d.get('status') in ('running','interrupted') else 'teacher_failure'
 row={'index':x['index'],'seed':p.get('seed'),'scene':p.get('cargo_scene','off'),'category':category,'status':d.get('status',x.get('status')),'exit':x.get('exit'),'sim_s':d.get('sim_s'),'wall_per_sim':d.get('wall_per_sim'),'first30':d.get('first30_speed'),'input_audit':d.get('input_audit'),'outcomes':{rid:t.get('outcome') for rid,t in tch.items()},'raw':str(raw),'result_sha256':hashlib.sha256(read(raw/'result.json')).hexdigest() if read(raw/'result.json') else None,'reasons':dict(c.most_common()),'candidate_funnels':actual,'event_funnel':steps((k,events[k]) for k in ('events','any_endpoint_prefix_pass','any_complete_pass')),'frame_funnel':steps((k,frames[k]) for k in ('input_frames','label_written','approach_align_ready','band_visible','band_admitted')),'command_events':new,'cache_stats':stats}
 rows.append(row)
sha=(R/'SOURCE_SHA').read_text().strip() if (R/'SOURCE_SHA').exists() else get(R/'RUN_META.json').get('sha');counts=Counter(r['category'] for r in rows);reasons=Counter()
for r in rows:reasons.update(r['reasons'])
report={'source_sha':sha,'raw_root':str(R),'host':'gcp1','planned':outer.get('planned_N',6),'counts':dict(counts),'rows':rows,'reasons':dict(reasons.most_common()),'reproduce':f'cd {Path.cwd()} && .venv-sim/bin/python /home/ugrp/ugrp-sim/outputs/search27-report.py {R} {O}','no_pooling_between_scenes':True,'run_funnel':steps([('planned',outer.get('planned_N',6)),('started',len(rows)),('final_complete',sum(r['category'] in ('success','teacher_failure','cap_end') for r in rows)),('not_cap_end',sum(r['category'] in ('success','teacher_failure') for r in rows)),('physical_success',counts['success'])])}
manifest=R/'SHA256SUMS';report['remote_full_manifest_verified']=manifest.exists() and subprocess.run(['sha256sum','-c','--quiet',str(manifest)],cwd=R,capture_output=True).returncode==0
(O/'rejection_table.json').write_text(json.dumps(report,indent=2)+'\n');summary={k:v for k,v in report.items() if k!='rows'};summary['rows']=[{k:v for k,v in r.items() if k not in ('command_events','candidate_funnels','frame_funnel','event_funnel')} for r in rows];(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
md=[f'# search27 rejection table\n\nSource {sha}; raw {R}\n\nReproduce: `{report["reproduce"]}`\n','|gate|pass|reject|','|---|---:|---:|']
for s in report['run_funnel']:md.append(f'|{s["gate"]}|{s["cumulative_pass"]}|{s["rejected_here"]}|')
md+=['\nReason distribution (passes separate in JSON):',*['- '+k+': '+str(v) for k,v in reasons.most_common()]]
for r in rows:
 md += [f'\n## episode {r["index"]} / {r["seed"]} / {r["scene"]}: {r["category"]}\n']
 for key in ('candidate_funnels','frame_funnel','event_funnel'):md+=[key, '```json',json.dumps(r[key],ensure_ascii=False),'```']
(O/'rejection_table.md').write_text('\n'.join(md)+'\n');print(json.dumps({'counts':dict(counts),'reasons':dict(reasons.most_common(8)),'manifest_verified':report['remote_full_manifest_verified']}))
