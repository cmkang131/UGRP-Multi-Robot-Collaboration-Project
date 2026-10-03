from pathlib import Path
import sys,sqlite3,json,hashlib,re,collections,datetime,time,os,csv,gzip,subprocess,stat
sys.path.insert(0,str(Path.cwd()))
from scripts import outputs_prune as prune
OUT=Path('/Users/changmin/projects/ugrp/outputs');DEST=Path('experiments/2026-09-30-outputs-retention')
assert not DEST.resolve().is_relative_to(OUT.resolve()), 'outputs must remain read-only'
c=sqlite3.connect('/tmp/ugrp-retention-files.sqlite');now=time.time()
# SQLite stays outside the repository. It contains metadata, not raw bytes.
metadata=json.load(open('/tmp/ugrp-retention-metadata.json'))
refs=json.load(open('/tmp/ugrp-retention-refs.json'));tb=json.load(open('/tmp/ugrp-retention-tb.json'))
units={u['path']:u for u in metadata}
allocated=collections.Counter();logical=collections.Counter();hardlinked=set()
for unit,size,blocks in c.execute('select unit,size,allocated from files group by dev,ino'):
 allocated[unit]+=blocks;logical[unit]+=size
for dev,ino in c.execute('select dev,ino from files group by dev,ino having count(*)>1'):hardlinked.add((dev,ino))
for u in metadata:u['allocated_bytes']=allocated[u['path']]

def write_json(path,data,pretty=False):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(data,ensure_ascii=False,indent=2 if pretty else None,separators=None if pretty else (',',':'))+'\n')

def file_record(p):return {'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':prune.sha256(p)}

def compact_gz(name,data):
 data=(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n').encode()
 (DEST/name).write_bytes(gzip.compress(data,mtime=0))

ops=[];kept={};run_evidence=[];slim_units=set();serial=0
for run in sorted((OUT/'simulation-realtime-20260923').iterdir()):
 rgb=run/'rgb'
 if not rgb.is_dir():continue
 result=json.loads((run/'result.json').read_text());cfg=result.get('config',{});source=result.get('source_sha')
 assert result.get('llm_calls')==0 and cfg.get('carry_act_model') is None
 assert source and cfg.get('seed') is not None and cfg.get('plan_replay')
 subprocess.run(['git','cat-file','-e',source+'^{commit}'],check=True)
 jpg=sorted(p.name for p in rgb.glob('*.jpg'))
 preserve={n for n in jpg if any(t in n for t in ['planning','identity','reference'])}
 # Retain first/middle/last per pair phase/camera; every solo phase uses actual log entries.
 groups=collections.defaultdict(list)
 for n in jpg:
  if n.startswith('pair-'):
   key=re.sub(r'^pair-\d+-','pair-',n)
   key=re.sub(r'(phase-\d+)-\d+',r'\1-#',key)
   groups[key].append(n)
 for items in groups.values():
  items.sort(key=lambda n:int(re.search(r'pair-(\d+)',n)[1]))
  preserve.update(items[i] for i in {0,len(items)//2,len(items)-1})
 solo=run/'solo-decisions.json'
 if solo.exists():
  byphase=collections.defaultdict(list)
  for row in json.loads(solo.read_text()):byphase[(row.get('phase_before'),row.get('phase_after'))].append(row)
  for rows in byphase.values():
   for i in {0,len(rows)//2,len(rows)-1}:
    for name in re.findall(r'rgb/([^"\s]+\.jpg)',json.dumps(rows[i])):
     if name in jpg:preserve.add(name)
 # Team request/response inputs survive even for saved-plan replay records.
 for p in (run/'team').glob('*.json'):
  for name in re.findall(r'rgb/([^"\s]+\.jpg)',p.read_text()):
   if name in jpg:preserve.add(name)
 for n in jpg:
  st=(rgb/n).stat()
  if (st.st_dev,st.st_ino) in hardlinked:preserve.add(n)
 names=[n for n in jpg if n not in preserve]
 if not names:continue
 serial+=1;rel=str(rgb.relative_to(OUT));selection=DEST/'selections'/f'{serial:02d}.json'
 write_json(selection,{'directory':rel,'delete_glob':'*.jpg','keep_glob':'explicit kept_names; all non-JPEG entries','delete_names':names,'kept_names':sorted(preserve)})
 snapshot=prune.fingerprint(rgb)
 op={'path':rel,'kind':'selection','rule_id':'S2','reason':'사용자가 중단한 실시간 연구의 비모델 RGB 반복 캡처; 모델 요청·로그·모든 실행 영상·단계 예시는 보존',
     'bytes':sum((rgb/n).stat().st_size for n in names),'allocated_bytes':sum((rgb/n).stat().st_blocks*512 for n in names),'files':len(names),'directories':0,
     'delete_glob':'*.jpg EXCEPT selections/'+selection.name+':kept_names','keep_glob':'all non-JPEG entries and exact kept_names',
     'selection_file':{'path':str(selection.relative_to(DEST)),'sha256':prune.sha256(selection)},'snapshot':snapshot}
 ops.append(op);slim_units.add('simulation-realtime-20260923')
 for n in preserve:kept[rel+'/'+n]=file_record(rgb/n)
 # Every non-RGB file is retained and hashed, including logs and request JSON.
 for p in run.rglob('*'):
  if p.is_file() and not p.is_symlink() and rgb not in p.parents:kept[str(p.relative_to(OUT))]=file_record(p)
 run_evidence.append({'run':str(run.relative_to(OUT)),'source_sha':source,'source_commit_exists':True,'seed':cfg['seed'],
                      'config_in_result_sha256':prune.sha256(run/'result.json'),'llm_calls':0,'carry_act_model':None,
                      'replay_path_recorded':cfg['plan_replay'],'retained_stage_jpegs':len(preserve),'retained_video':str((run/'execution.mp4').relative_to(OUT)),
                      'exact_pixel_regeneration_claim':False})
 print('selected',run.name,len(names),flush=True)
# Cache candidates: no symlinks, no hard-linked file, no recent changes.
cache_roots=[]
for (rel,) in c.execute("select path from files where mode & 61440=16384 and path like '%/__pycache__'"):
 if rel.startswith('act-action-training-20260924/'):cache_roots.append(rel)
node=OUT/'status-video/remotion/node_modules'
for p in node.iterdir():
 if p.name in {'.bin'} or not p.is_dir() or p.is_symlink():continue
 if p.name.startswith('@'):
  cache_roots.extend(str(child.relative_to(OUT)) for child in p.iterdir() if child.is_dir() and not child.is_symlink())
 else:cache_roots.append(str(p.relative_to(OUT)))
cache_exclusions=[]
for rel in sorted(cache_roots):
 try:
  snapshot=prune.fingerprint(OUT/rel)
  if any((dev,ino) in hardlinked for dev,ino in c.execute('select dev,ino from files where path=? or path like ?',(rel,rel+'/%'))):
   raise prune.Refusal('hard-linked file; du projection not guaranteed')
 except (prune.Refusal,OSError) as e:
  cache_exclusions.append({'path':rel,'reason':str(e)});continue
 ops.append({'path':rel,'rule_id':'D2','reason':'재설치 가능한 의존성/파이썬 캐시; package-lock·소스·최종 영상과 모델은 유지',**snapshot})
 slim_units.add(rel.split('/')[0])
# Hash kept source/config/log/media outside the removable dependency tree.
for p in (OUT/'status-video').rglob('*'):
 if p.is_file() and not p.is_symlink() and 'node_modules' not in p.parts:kept[str(p.relative_to(OUT))]=file_record(p)
# Retained metadata of the training directory whose caches are pruned.
for p in (OUT/'act-action-training-20260924').rglob('*'):
 if p.is_file() and not p.is_symlink() and p.suffix.lower() in {'.json','.jsonl','.log','.txt','.md','.yaml','.yml','.csv','.tsv'} and '__pycache__' not in p.parts and '.git' not in p.parts:
  kept[str(p.relative_to(OUT))]=file_record(p)
for p in (OUT/'simulation-realtime-20260923').iterdir():
 if p.is_file() and not p.is_symlink():kept[str(p.relative_to(OUT))]=file_record(p)
# Keep-list shards each stay below the project per-file 1 MiB limit.
keep_rows=sorted(kept.values(),key=lambda x:x['path']);keep_lists=[]
for i,start in enumerate(range(0,len(keep_rows),1800),1):
 p=DEST/'keep'/f'{i:02d}.json';write_json(p,{'files':keep_rows[start:start+1800]});keep_lists.append({'path':str(p.relative_to(DEST)),'sha256':prune.sha256(p),'files':len(keep_rows[start:start+1800])})
# Evidence index: store references once, with numeric ref IDs.
ref_names=[r['ref'] for r in refs['refs']]+['live-view'];reference_index={}
for name,byref in refs['references'].items():
 records=collections.defaultdict(list)
 for ref,paths in byref.items():
  for p in paths:records[p].append(ref_names.index(ref))
 reference_index[name]=dict(records)
compact_gz('references.json.gz',{'refs':refs['refs'],'live_view_ref_id':len(refs['refs']),'references':reference_index})
compact_gz('tensorboard-audit.json.gz',tb)
compact_gz('metadata-audit.json.gz',metadata)
write_json(DEST/'run-evidence.json',run_evidence,True)
write_json(DEST/'cache-exclusions.json',cache_exclusions,True)
write_json(DEST/'duplicates.json',{'scope':'retired-worktrees regular files >= 1 MiB versus all non-retired outputs files, equal size then full SHA-256','matches':json.load(open('/tmp/ugrp-retention-duplicates.json'))},True)
write_json(DEST/'checkpoint-audit.json',{'models':[m for u in metadata for m in u['model_files']], 'loading_test_scope':'No new model loading or physics; registry hash matching only. Historical release verification is separately cited.'},True)
# Bind existing TensorBoard and version-video dependencies; no new snapshot is produced.
tb_by_unit=collections.defaultdict(list)
for item in tb:
 source=item.get('source') or ''
 if not isinstance(source,str):continue
 tail=source.rsplit('/outputs/',1)[-1] if '/outputs/' in source else source
 top=tail.split('/')[0]
 if top in units:tb_by_unit[top].append(item)
version_text=Path('docs/version_videos.md').read_text()+Path('experiments/2026-09-29-version-videos/README.md').read_text()
rows=[]
for unit,u in units.items():
 name=unit.split('/')[-1];lookup={name}
 if unit.startswith('retired-worktrees/') and (OUT/unit/'outputs').is_dir():lookup.update(p.name for p in (OUT/unit/'outputs').iterdir())
 evidence={ref:sorted({p for n in lookup for p in refs['references'].get(n,{}).get(ref,[])}) for ref in ref_names}
 substantive=[p for p in evidence['origin/main'] if not any(x in p for x in ['disk-', 'disk_management','worktree','footprint/'])]
 current_claim=any(p.startswith('docs/current_status.md:') for p in substantive)
 readmes=[p for p in substantive if p.endswith('.md:'+p.rsplit(':',1)[-1]) and '/README.md:' in p]
 # PR-only means an evidence blob absent from main, not merely inherited references.
 pr_only={ref:[p for p in paths if p not in evidence['origin/main'] and not any(t in p for t in ['disk-','worktree','footprint/'])] for ref,paths in evidence.items() if ref not in {'origin/main','live-view'}}
 pr_only={k:v for k,v in pr_only.items() if v}
 match=re.search(r'(2026)[-]?(0[1-9]|1[0-2])[-]?([0-3][0-9])',name)
 date=None;date_basis='mtime_not_run_date'
 if match:
  try:date=datetime.date(*map(int,match.groups())).isoformat();date_basis='folder_date_not_verified_start'
  except ValueError:pass
 if date is None:date=datetime.datetime.fromtimestamp(u['newest_mtime_ns']/1e9).date().isoformat()
 age=(datetime.date.today()-datetime.date.fromisoformat(date)).days
 recent24=u['newest_mtime_ns']>int((now-86400)*1e9)
 test=u['test_path_count']>0 or bool(re.search(r'(^|[-_/])(test|final|holdout|heldout|cohort|qualification)([-_/]|$)',unit))
 prereg=any(any(t in p.lower() for t in ['prereg','sealed']) for p in substantive)
 video=name in version_text
 sources=tb_by_unit.get(unit,[])
 if unit.startswith('retired-worktrees/'):
  for n in lookup:sources+=tb_by_unit.get(n,[])
 if unit.startswith('tensorboard') or unit in {'agent-locks','sim-slots','prune-receipts'}:rule='K0';tier='infrastructure';question=None
 elif recent24:rule='K2';tier='recent_or_unmerged';question='Q1' if not unit.endswith(('.log','.json','.md','.txt')) else None
 elif test or prereg:rule='K1';tier='test_or_prereg';question='Q2' if not substantive else None
 elif u['model_files'] or u['request_file_count'] or any(x in unit for x in ['training','vision-loc','owncam-loc']):rule='K3';tier='model_inputs_or_checkpoints';question='Q3' if any(not m['release_registry_match'] for m in u['model_files']) else None
 elif video:rule='K4';tier='report_media';question=None
 elif age<7 or pr_only:rule='K2';tier='recent_or_unmerged';question='Q1'
 elif unit=='experiment-archives-20260907':rule='U1';tier='unique_archive';question='Q4'
 elif u['bytes']<2**20 and not (OUT/unit).is_dir():rule='K5';tier='small_records';question=None
 else:rule='U1';tier='uncertain';question='Q2' if substantive else 'Q5'
 ownops=[o for o in ops if o['path']==unit or o['path'].startswith(unit+'/')]
 if ownops:rule='S2' if unit=='simulation-realtime-20260923' else 'D2';tier='retired_bulk' if rule=='S2' else 'cache_slim';question=None
 deleted=sum(o['allocated_bytes'] for o in ownops)
 row={'path':unit,'date':date,'date_basis':date_basis,'research_line':('retired worktree / '+name if unit.startswith('retired-worktrees/') else 'pair/own-camera' if any(x in name for x in ['pair','owncam','v6h','door','zone','seg-','vision']) else 'realtime/speed' if any(x in name for x in ['realtime','sim-speed','fine-gain']) else 'ACT/Jev/RGB/navigation' if any(x in name for x in ['act','jev','rgb','markerless','navigation','map-','dispatch','transport']) else 'infrastructure/records/unknown'),
      'bytes':u['bytes'],'allocated_bytes':u['allocated_bytes'],'projected_allocated_bytes':u['allocated_bytes']-deleted,'delete_allocated_bytes':deleted,
      'decision':'SLIM' if ownops else 'KEEP (uncertain)' if question else 'KEEP full','rule_id':rule,'tier':tier,'question_id':question,
      'newest_mtime_ns':u['newest_mtime_ns'],'recent_24h':recent24,'under_7_days_or_date_unknown':age<7 or date_basis.startswith('mtime'),
      'reference_keys':sorted(n for n in lookup if n in reference_index),'main_record_count':len(evidence['origin/main']),
      'open_pr_refs':[ref for ref in refs['refs'] if evidence[ref['ref']]],'pr_only_record_count':sum(map(len,pr_only.values())),
      'claim_evidence':'current_status_direct_reference' if current_claim else 'test_or_prereg_evidence_present' if test or prereg else 'README/reference_requires_scope_review' if readmes else 'not_established',
      'claim_record_examples':substantive[:3],'test_or_prereg':test or prereg,'representative_video_dependency':video,
      'tensorboard_snapshots':len(sources),'tensorboard_scalar_samples_read':sum(t.get('scalar_samples_read',0) for t in sources),'tensorboard_scope':'scalars do not replace raw; path attribution only; historical moved paths may not resolve',
      'model_checkpoints':len(u['model_files']),'registry_hash_matched_checkpoints':sum(bool(m['release_registry_match']) for m in u['model_files']),
      'request_named_files':u['request_file_count'],'request_scope':'filename signal only; no absence-of-model-input claim',
      'source_config_seed_status':'metadata has SHA and seed; full replay not verified' if u['sha_examples'] and u['seed_examples'] else 'incomplete or not applicable',
      'source_examples':u['sha_examples'],'metadata_files':u['metadata_count'],'state_signals':list(u['states'])[:6]}
 rows.append(row)
rows.sort(key=lambda x:x['path'])
# Top-level inventory plus retirement subfolders; parent is a separate non-additive summary.
retired=[r for r in rows if r['path'].startswith('retired-worktrees/')]
parent={'path':'retired-worktrees','allocated_bytes':sum(r['allocated_bytes'] for r in retired),'children':len(retired),'non_additive':True}
for i,start in enumerate(range(0,len(rows),220),1):write_json(DEST/'inventory'/f'{i:02d}.json',{'entries':rows[start:start+220]})
with (DEST/'inventory.csv').open('w',newline='') as f:
 fields=['path','date','date_basis','research_line','allocated_bytes','delete_allocated_bytes','projected_allocated_bytes','decision','rule_id','tier','question_id','recent_24h','main_record_count','pr_only_record_count','claim_evidence','test_or_prereg','representative_video_dependency','tensorboard_snapshots','tensorboard_scalar_samples_read','model_checkpoints','registry_hash_matched_checkpoints','request_named_files','source_config_seed_status']
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(rows)
with (DEST/'manifest.csv').open('w',newline='') as f:
 fields=['path','kind','rule_id','bytes','allocated_bytes','files','reason','delete_glob','keep_glob','selection_file']
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows({**o,'selection_file':o.get('selection_file',{}).get('path','')} for o in ops)
summary=collections.defaultdict(lambda:{'units':0,'allocated_bytes':0,'delete_allocated_bytes':0,'projected_allocated_bytes':0})
for r in rows:
 s=summary[r['tier']];s['units']+=1
 for k in ['allocated_bytes','delete_allocated_bytes','projected_allocated_bytes']:s[k]+=r[k]
base=sum(r['allocated_bytes'] for r in rows);savings=sum(o['allocated_bytes'] for o in ops)
questions={
 'Q1':'최근 실행/미병합 분석 또는 실행 날짜가 불명확하다. 분석 종료·대표 case·최소 7일 보존을 확인할 때까지 전체 유지. 40 GiB를 위해 이 대기 규칙을 바꿀지는 배치와 별도 결정 필요.',
 'Q2':'과거/현재 수치·그림 중 최종 보고서에 실제로 쓸 범위는 무엇인가? raw 필요성을 확정하기 전 전체 유지.',
 'Q3':'배포 registry와 맞지 않는 체크포인트 중 결과에 사용한 모델과 필수 추론 자산은 무엇인가? 식별·Release 검증 전 유지.',
 'Q4':'09-07 압축본은 유일 사본이다. 결과를 포기할 명시적 결정이 없는 한 유지. 외부 보관은 계획하지 않음.',
 'Q5':'참조·종료·모델 입력·SHA/config/seed 연결을 확정하지 못했다. 폐기 가능한 scratch인지 소유 작업의 판단이 필요하며 그 전에는 유지.'}
manifest={'schema':prune.SCHEMA,'outputs_root':str(OUT),'created_at':datetime.datetime.now().astimezone().isoformat(),'approval':'pending_user_review; no deletion executed','source_refs':refs['refs'],
 'snapshot_scope':'Read-only rolling inventory; APFS allocated bytes counted once per inode. Active work may grow after measurement.',
 'current_allocated_bytes':base,'delete_allocated_bytes':savings,'projected_allocated_bytes':base-savings,'target_allocated_bytes':40*2**30,'ideal_allocated_bytes':[25*2**30,30*2**30],
 'target_met':base-savings<=40*2**30,'shortfall_to_40_gib_bytes':max(0,base-savings-40*2**30),'top_level_entries':len({p.split('/')[0] for p in units}),'retirement_summary':parent,
 'tiers':dict(summary),'delete':ops,'keep_lists':keep_lists,'questions':questions,'run_evidence':'run-evidence.json','inventory_files':[str(p.relative_to(DEST)) for p in sorted((DEST/'inventory').glob('*.json'))],
 'execution_notes':['Only the coordinator may execute after user approval.','No writes or deletion under outputs occurred during this task.','Live locks block execution; manifest changes require renewed review.','S2 keeps every execution video and first/middle/last stage samples; exact past RGB audits are lost for removed frames.','No new TensorBoard export; existing event files read only.']}
write_json(DEST/'manifest.json',manifest,True)
write_json(DEST/'summary.json',{'current_allocated_bytes':base,'delete_allocated_bytes':savings,'projected_allocated_bytes':base-savings,'tiers':dict(summary),'questions':questions,'uncertain_units':sum(r['question_id'] is not None for r in rows),'tensorboard':{'manifests':len(tb),'snapshots_with_scalar_samples':sum(t.get('scalar_samples_read',0)>0 for t in tb),'scalar_samples_read':sum(t.get('scalar_samples_read',0) for t in tb),'errors':sum(bool(t.get('error')) for t in tb)},'keep_files':len(keep_rows),'delete_operations':len(ops),'delete_files':sum(o['files'] for o in ops),'retirement_summary':parent},True)
print(json.dumps({'current_gib':base/2**30,'delete_gib':savings/2**30,'projected_gib':(base-savings)/2**30,'keep_files':len(keep_rows),'ops':len(ops)},ensure_ascii=False),flush=True)
