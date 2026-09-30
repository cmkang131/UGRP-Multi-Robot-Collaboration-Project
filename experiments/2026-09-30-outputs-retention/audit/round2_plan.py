"""Build coordinator D1-D5 proposal; NEVER writes anywhere inside raw outputs.

Requires collect_files/round2_evidence/round2_tensorboard. Explicit filename
batches carry a SHA-256 over (name, bytes, mtime_ns, full content SHA-256).
"""
from pathlib import Path
import os,sys,json,sqlite3,hashlib,collections,re,time,math,csv,statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from scripts import outputs_prune_stream as stream
from scripts.outputs_retention_rules import select_samples
from scripts.outputs_prune import protected,relative_path,sha256
ROOT=Path('/Users/changmin/projects/ugrp/outputs');TMP=Path('/private/tmp/outputs-retention-r2')
DEST=Path(__file__).resolve().parents[1]
assert not DEST.is_relative_to(ROOT)
c=sqlite3.connect(TMP/'files.sqlite');c.execute('PRAGMA journal_mode=WAL')
reuse='--reuse-classification' in sys.argv
now=json.loads((DEST/'summary.json').read_text())['measured_unix'] if reuse else time.time();cut=int((now-86400)*1e9)
# Fix cutoff at the time this plan is built, never loosen it during generation.
refs=dict(c.execute('select value,source from refs'));model_hash=dict(c.execute('select sha,source from model_hashes'));model_paths=dict(c.execute('select path,source from model_paths'))
tb=json.loads((TMP/'tensorboard-r2.json').read_text());refs.update(tb['paths']);tbhash=tb['hashes']
errors=list(c.execute('select path,reason from errors'))
boundary_paths={r[0] for r in c.execute('select path from boundaries')}
hardlinked_paths={r[0] for r in c.execute('select path from files where (dev,ino) in (select dev,ino from files group by dev,ino having count(*)>1)')}
print('metadata loaded; hashing raw read-only',flush=True)
sealed=[
 ('m1-owncam-20260926/test','experiments/2026-09-26-zone-m1-owncam/frozen_source.json','ca2fdb8; reported 4/6 incl ENOSPC'),
 ('owncam-memory-20260926/test-a1','experiments/2026-09-26-zone-owncam-memory/frozen_source.json','frozen ON/OFF seeds161-166; reported'),
 *[(f'zone-m2-pair-20260926/{name}','experiments/2026-09-26-zone-m2-pair/README.md','frozen and reported stage cohort; includes failures') for name in ['stage1-3fdf011','stage2-fa682a6','stage2b-ed15489','stage3-5f74873']],
 *[(f'zone-m2-pair-kiro-20260926/{name}','experiments/2026-09-26-zone-m2-pair/README.md','frozen and reported stage cohort; includes failures') for name in ['stage2b-ed15489-completion','stage2c-ca44f66']]]
retired=['simulation-realtime-20260923','sim-speed-20260926','retired-worktrees/codex-sim-speed-fix','retired-worktrees/kiro-sim-speed']
cache=json.loads((DEST/'audit/round1-cache-list.json').read_text())['paths']
cache_set=set(cache)
# These paths contain learned-policy datasets or historical model runtime inputs;
# missing request-to-frame linkage is an explicit uncertainty, not a negative proof.
input_prefixes=['vision-loc-20260926','seg-lightfloor-20260929','act-action-training-20260924']
input_pattern=re.compile(r'(^|/)(?:[^/]*training[^/]*|[^/]*dataset[^/]*|[^/]*inference[^/]*|act-inputs|act-requests)(/|$)',re.I)
request_pattern=re.compile(r'(request|response|payload|wire|prompt|actor[_-]samples|act[_-](input|inference)|model[_-]calls|llm[_-]decisions)',re.I)

def within(p,root):return p==root or p.startswith(root+'/')
def ancestor_in(p,roots):return next((r for r in roots if within(p,r)),None)
def reference(p):
 parts=p.split('/')
 for i in range(len(parts)):
  v='/'.join(parts[i:])
  if v in refs:return refs[v]
 return None

def protection(p,mtime,suffix):
 if p in hardlinked_paths:return 'hardlink_allocation_uncertain'
 if protected(relative_path(p)) or 'sim-slots' in p.split('/') or Path(p).name in {'RETIRED.json','MANIFEST.tsv'}:return 'infrastructure_or_receipt'
 if mtime>cut:return 'modified_within_24h'
 if ancestor_in(p,[x[0] for x in sealed]):return 'sealed_reported_cohort'
 if suffix in {'.safetensors','.pt','.pth','.ckpt','.onnx'} or within(p,'experiment-archives-20260907'):return 'D4_model_or_unique_zip'
 if request_pattern.search(p) and suffix in {'.json','.jsonl','.md','.txt'}:return 'model_request_records'
 if p in model_paths:return 'model_request_path'
 if p in boundary_paths and not ancestor_in(p,retired):return 'D1_leg_or_event_endpoint'
 if suffix in {'.jpg','.jpeg','.png'}:
  if reference(p):return 'tracked_or_tensorboard_image_reference'
  if ancestor_in(p,input_prefixes) or input_pattern.search(p) or re.search(r'(^|/)[^/]*(jev|gemini|act-recovery|act-pair|act-double)[^/]*(/|$)',p,re.I):return 'model_input_or_training_uncertain'
 return None

if not reuse:
 c.executescript('DROP TABLE IF EXISTS decisions; CREATE TABLE decisions(path TEXT PRIMARY KEY,folder TEXT,name TEXT,action TEXT,rule TEXT,reason TEXT,sha TEXT,t REAL,stream TEXT);')
# Exact duplicate JSON reconstruction uses a retained byte-identical source.
# No semantic/name-only comparisons; no deletion of original model payloads.
json_groups=collections.defaultdict(list)
for p,h,size,stamp in c.execute("select f.path,h.sha,f.size,f.mtime_ns from files f join hashes h on h.path=f.path where f.path like '%.json'"):
 json_groups[h].append((p,size,stamp))
duplicates={}
for h,items in json_groups.items():
 if len(items)<2:continue
 sources=[item for item in items if not ancestor_in(item[0],retired) and item[2]<=cut and not ancestor_in(item[0],cache)]
 if not sources:continue
 # Prefer already-protected evidence as the surviving copy.
 source=sorted(sources,key=lambda x:(not bool(protection(x[0],x[2],'.json')),len(x[0]),x[0]))[0][0]
 for p,size,stamp in items:
  if p!=source and not protection(p,stamp,'.json') and not ancestor_in(p,cache) and stamp<=cut:
   duplicates[p]={'source':source,'sha256':h,'bytes':size,'rule':'copy retained source bytes verbatim'}
# Limit retired research numeric records to 5 MiB per run, except immutable
# request payloads/receipts. Select one video per run before considering bulk.
retired_keep=set();retired_budgets=collections.defaultdict(lambda:{'bytes':0,'files':[],'video':None,'exceptions':[]})
byrun=collections.defaultdict(list)
for p,size,stamp in c.execute('select path,size,mtime_ns from files where mode & 61440=32768'):
 hit=ancestor_in(p,retired)
 if not hit:continue
 tail=p[len(hit):].strip('/').split('/');run=hit+'/'+tail[0] if len(tail)>1 else hit
 byrun[run].append((p,size,stamp))
record_ext={'.json','.jsonl','.md','.csv','.tsv','.log','.txt','.yaml','.yml','.xml'}
for run,items in byrun.items():
 videos=sorted((p,size) for p,size,stamp in items if Path(p).suffix.lower() in {'.mp4','.mov','.webm'})
 if videos:
  # Prefer execution.mp4, then shortest path. Each historical per-run video remains accessible.
  video=min(videos,key=lambda x:(Path(x[0]).name!='execution.mp4',len(x[0]),x[0]))[0]
  retired_keep.add(video);retired_budgets[run]['video']=video
 records=[x for x in items if Path(x[0]).suffix.lower() in record_ext]
 records.sort(key=lambda x:(Path(x[0]).name not in {'result.json','manifest.json','scene-manifest.json','config.json','profile.json','issued-commands.json','commands.json','committed-plan.json'},x[1],x[0]))
 for p,size,stamp in records:
  guard=protection(p,stamp,Path(p).suffix.lower())
  if guard:
   retired_keep.add(p);retired_budgets[run]['exceptions'].append({'path':p,'bytes':size,'reason':guard})
  elif retired_budgets[run]['bytes']+size<=5*1024*1024:
   retired_keep.add(p);retired_budgets[run]['bytes']+=size;retired_budgets[run]['files'].append(p)

if not reuse:
 stats=collections.Counter();hash_count=0
 nrows=c.execute('select count(*) from files').fetchone()[0]
 rows=c.execute('select path,size,allocated,mtime_ns,mode from files order by path')
 for i,(p,size,allocated,stamp,mode) in enumerate(rows,1):
  if mode & 61440!=32768:continue
  pp=Path(p);suffix=pp.suffix.lower();folder=str(pp.parent) if str(pp.parent)!='.' else '';name=pp.name
  rule='KEEP';reason=protection(p,stamp,suffix);action='keep';h=None;t=None;group=None
  if not reason:
   if ancestor_in(p,cache):action='delete';rule='D3';reason='round1_cache_list'
   elif ancestor_in(p,retired):
    if p in retired_keep:reason='retired_small_records_or_representative_video'
    else:action='delete';rule='D2';reason='retired_realtime_or_sim_speed_bulk'
   elif suffix in {'.jpg','.jpeg','.png'}:
    action='candidate';rule='D1';reason='rendered_non_request_frame'
   elif p in duplicates:action='delete';rule='D5';reason='byte_identical_json_reconstructible'
   else:reason='records_or_other_kept'
  # Hash old stable files, including each model/request/TensorBoard image.
  # Recent/live files are explicitly outside this immutable keep snapshot.
  if stamp<=cut and reason!='infrastructure_or_receipt':
   try:
    before=(ROOT/p).stat(follow_symlinks=False)
    cached=c.execute('select sha from hashes where path=?',(p,)).fetchone()
    if cached:h=cached[0]
    else:
     with (ROOT/p).open('rb') as streamfile:h=hashlib.file_digest(streamfile,'sha256').hexdigest()
    after=(ROOT/p).stat(follow_symlinks=False)
    if (before.st_size,before.st_mtime_ns)!=(size,stamp) or (after.st_size,after.st_mtime_ns)!=(size,stamp):
     action='keep';rule='KEEP';reason='changed_during_audit';h=None
    hash_count+=1
   except OSError as e:action='keep';rule='KEEP';reason='unreadable_during_audit';h=None;errors.append((p,str(e)))
  if suffix in {'.jpg','.jpeg','.png'} and h:
   if h in model_hash:action='keep';rule='KEEP';reason='model_payload_content_match'
   elif h in tbhash:action='keep';rule='KEEP';reason='tensorboard_image_content_match'
  if action=='candidate':
   # SIM timing joins robots.json/inputs/frames.jsonl/skill-inputs.jsonl/decisions.
   timing=c.execute('select t,source from times where path=?',(p,)).fetchone()
   if timing:t=float(timing[0])
   tick=re.fullmatch(r'tick-(\d+\.\d+)-(.+)\.(?:jpg|png)',name)
   if tick:t=float(tick[1]);group='tick-'+tick[2]
   elif re.fullmatch(r'\d+\.(jpg|png)',name):group='numbered_camera'
   elif re.match(r'(pair|solo)-\d+-',name):
    group=re.sub(r'^(pair|solo)-\d+-',r'\1-#-',name)
    group=re.sub(r'(phase-\d+)-\d+',r'\1-#',group)
    group=re.sub(r'(grasp|lift|release|carry|approach|transit|coarse)-\d+',r'\1-#',group)
   elif re.search(r'\d',name):group=re.sub(r'(?<![A-Za-z])\d+(?:\.\d+)?','#',name)
   else:action='keep';rule='KEEP';reason='unsequenced_image_uncertain'
  c.execute('INSERT INTO decisions VALUES(?,?,?,?,?,?,?,?,?)',(p,folder,name,action,rule,reason,h,t,group))
  stats[reason]+=allocated
  if i%20000==0:c.commit();print('classify/hash',i,'/',nrows,'hashes',hash_count,flush=True)
 c.commit();del rows
 c.execute('CREATE INDEX decisions_folder_stream ON decisions(folder,stream,action)');c.commit()
else:
 c.execute("update decisions set action='candidate',reason='rendered_non_request_frame' where rule='D1' and (action='delete' or reason='D1_sample_or_endpoint')")
 c.execute("update decisions set t=(select t from times where times.path=decisions.path) where action='candidate' and exists(select 1 from times where times.path=decisions.path)")
 c.execute("update decisions set action='keep',rule='KEEP',reason='D1_leg_or_event_endpoint' where action='candidate' and path in (select path from boundaries)")
 for path,name,group in c.execute("select path,name,stream from decisions where action='candidate'").fetchall():
  if not (group=='numbered_camera' or group.startswith(('tick-','pair-','solo-'))):
   c.execute('update decisions set stream=? where path=?',(re.sub(r'(?<![A-Za-z])\d+(?:\.\d+)?','#',name),path))
 c.commit()

# Per-stream first/last always survive, including separate episode/leg directories
# and filename phase groups. Unknown timing: >=90% removal before protected extras.
thinning=[]
for folder,group in c.execute("select distinct folder,stream from decisions where action='candidate' order by folder,stream").fetchall():
 items=c.execute("select path,name,t from decisions where folder=? and stream=? and action='candidate' order by name",(folder,group)).fetchall()
 items.sort(key=lambda row:[int(x) if x.isdigit() else x for x in re.split(r'(\d+)',row[1])])
 chosen,rule,cadence=select_samples(items)
 c.executemany("update decisions set action='keep',reason='D1_sample_or_endpoint' where path=?",[(p,) for p in chosen])
 c.execute("update decisions set action='delete' where folder=? and stream=? and action='candidate'",(folder,group))
 thinning.append({'folder':folder,'stream':group,'rule':rule,'source_median_interval_sim_s':cadence,'eligible_files':len(items),'sample_files':len(chosen),'first':items[0][1],'last':items[-1][1]})
 if len(thinning)%500==0:c.commit();print('thinning groups',len(thinning),flush=True)
c.commit()
# A reconstruction source must survive ALL other rules and have a fixed keep hash.
for p,dup in list(duplicates.items()):
 dec=c.execute('select action from decisions where path=?',(p,)).fetchone()
 if not dec or dec[0]!='delete':continue
 src=c.execute('select action,sha from decisions where path=?',(dup['source'],)).fetchone()
 if src!=('keep',dup['sha256']):
  c.execute("update decisions set action='keep',rule='KEEP',reason='reconstruction_source_not_frozen' where path=?",(p,))
c.commit()

# Exact keep/deletion lists: explicit names compressed as metadata only. Batches
# are bounded at 512; per-list files remain under 1 MiB. No raw bytes are copied.
lists={};totals={}
for action in ['delete','keep']:
 folderpath=DEST/('round2-'+action);folderpath.mkdir(exist_ok=True)
 for old in folderpath.glob('*.jsonl'):old.unlink()  # only this generated worktree artifact
 listentries=[];part=0;handle=None;part_bytes=0;part_batches=0;total=collections.Counter()
 def closepart():
  global handle
  if handle:
   handle.close();listentries.append({'path':str(outfile.relative_to(DEST)),'sha256':sha256(outfile),'batches':part_batches});handle=None
 cursor=c.execute('''select d.folder,d.name,f.size,f.allocated,f.mtime_ns,d.sha,d.rule,d.reason
 from decisions d join files f on f.path=d.path where d.action=? and d.sha is not null order by d.folder,d.name''',(action,))
 group=[];prior=None
 def writegroup(group):
  global part,handle,part_bytes,part_batches,outfile
  if not group:return
  folder=group[0][0];rule=group[0][6];reason=group[0][7]
  recs=[{'name':r[1],'bytes':r[2],'mtime_ns':r[4],'sha256':r[5]} for r in group]
  row={'folder':folder,'files':len(group),'bytes':sum(r[2] for r in group),'allocated_bytes':sum(r[3] for r in group),
       'names_zlib_base64':stream.pack_names([r[1] for r in group]),'content_sha256':stream.digest_records(recs)}
  if action=='delete':row.update(rule_id=rule,reason=reason)
  raw=stream.canonical(row)
  if not handle or part_bytes+len(raw)>900000:
   closepart();part+=1;outfile=folderpath/f'{part:03d}.jsonl';handle=outfile.open('wb');part_bytes=0;part_batches=0
  handle.write(raw);part_bytes+=len(raw);part_batches+=1
  for k in ['files','bytes','allocated_bytes']:total[k]+=row[k]
 for row in cursor:
  key=(row[0],row[6] if action=='delete' else '',row[7] if action=='delete' else '')
  if prior is not None and (key!=prior or len(group)>=512):writegroup(group);group=[]
  group.append(row);prior=key
 writegroup(group);closepart();lists[action+'_lists']=listentries;totals[action]=dict(total)
 print('batches',action,len(listentries),dict(total),flush=True)

# Every immediate directory, including untouched ones, has before/after counts.
folder_rules=collections.defaultdict(set)
for x in thinning:folder_rules[x['folder']].add(x['rule'])
folders={}
seen_inodes=set()
for p,size,allocated,mode,dev,ino in c.execute('select path,size,allocated,mode,dev,ino from files order by path'):
 if (dev,ino) in seen_inodes:allocated=0
 else:seen_inodes.add((dev,ino))
 folder=str(Path(p).parent);folder='' if folder=='.' else folder
 f=folders.setdefault(folder,{'folder':folder,'before_bytes':0,'before_allocated_bytes':0,'files_before':0,'delete_files':0,'delete_bytes':0,'delete_allocated_bytes':0})
 f['before_allocated_bytes']+=allocated
 if mode & 61440==32768:f['before_bytes']+=size;f['files_before']+=1
for folder,n,size,blocks in c.execute("select d.folder,count(*),sum(f.size),sum(f.allocated) from decisions d join files f on f.path=d.path where d.action='delete' group by d.folder"):
 folders[folder].update(delete_files=n,delete_bytes=size,delete_allocated_bytes=blocks)
fields=['folder','before_bytes','after_bytes','before_allocated_bytes','after_allocated_bytes','files_before','delete_files','keep_files','delete_bytes','delete_allocated_bytes','rule_ids','thinning_rule']
with (DEST/'manifest.csv').open('w') as file:
 w=csv.DictWriter(file,fieldnames=fields,lineterminator='\n');w.writeheader()
 for folder,f in sorted(folders.items()):
  f['after_bytes']=f['before_bytes']-f['delete_bytes'];f['after_allocated_bytes']=f['before_allocated_bytes']-f['delete_allocated_bytes'];f['keep_files']=f['files_before']-f['delete_files']
  f['rule_ids']=','.join(r[0] for r in c.execute("select distinct rule from decisions where folder=? and action='delete' order by rule",(folder,)))
  f['thinning_rule']='; '.join(sorted(folder_rules[folder]));w.writerow(f)
# Non-additive detailed stream rules live in a separate CSV.
with (DEST/'thinning.csv').open('w') as file:
 w=csv.DictWriter(file,fieldnames=list(thinning[0]) if thinning else ['folder'],lineterminator='\n');w.writeheader();w.writerows(thinning)
with (DEST/'json-reconstruction.csv').open('w') as file:
 w=csv.writer(file,lineterminator='\n');w.writerow(['deleted_path','retained_source','bytes','sha256','reconstruction_rule'])
 for p,d in sorted(duplicates.items()):
  r=c.execute('select action,rule from decisions where path=?',(p,)).fetchone()
  if r==('delete','D5'):w.writerow([p,d['source'],d['bytes'],d['sha256'],d['rule']])
category=[]
for rule,n,sz,alloc in c.execute("select d.rule,count(*),sum(f.size),sum(f.allocated) from decisions d join files f on f.path=d.path where d.action='delete' group by d.rule"):
 category.append({'rule_id':rule,'delete_files':n,'delete_bytes':sz,'delete_allocated_bytes':alloc})
kept_reasons=[]
for reason,n,sz,alloc in c.execute("select d.reason,count(*),sum(f.size),sum(f.allocated) from decisions d join files f on f.path=d.path where d.action='keep' group by d.reason"):
 kept_reasons.append({'reason':reason,'files':n,'bytes':sz,'allocated_bytes':alloc})
summary={'measured_unix':now,'cutoff_24h_unix_ns':cut,'before_allocated_bytes':sum(f['before_allocated_bytes'] for f in folders.values()),'before_bytes':sum(f['before_bytes'] for f in folders.values()),'categories':category,'kept_reasons':kept_reasons,'source_refs':json.loads((TMP/'source_refs.json').read_text()),'errors':errors,'hardlinks_note':'allocation counts each inode once; all multiply-linked paths kept conservatively','not_executed':True}
summary['projected_allocated_bytes']=summary['before_allocated_bytes']-totals['delete']['allocated_bytes']
manifest={'schema':stream.SCHEMA,'outputs_root':str(ROOT),'created_unix':now,'rules':{'D1':'non-request rendered frames: ~1Hz SIM or <=10% fallback + endpoints + referenced frames','D2':'retired realtime/sim-speed: <=5MiB records per run + one video; protected payloads/references override','D3':'round1 caches only','D4':'keep all checkpoints and unique 09-07 ZIP pending user decision','D5':'byte-identical JSON: restore by copying the bound retained source'},'source_refs':summary['source_refs'],'delete_totals':totals['delete'],'keep_totals':totals['keep'],**lists,'folder_summary':{'path':'manifest.csv','sha256':sha256(DEST/'manifest.csv')},'summary':{'before_allocated_bytes':summary['before_allocated_bytes'],'projected_allocated_bytes':summary['projected_allocated_bytes']},'coordinator_executes':True,'execution_approval':'not executed; coordinator validates this exact manifest; no blanket future cleanup authorization'}
for name,value in [('manifest.json',manifest),('summary.json',summary),('sealed-cohorts.json',{'final_four_condition_confirmatory':[],'scope':'No sealed-and-reported final-map four-condition cohort found; additionally preserve reported frozen component cohorts','preserved':[{'path':p,'evidence':e,'note':n} for p,e,n in sealed]}),('retired-records.json',dict(retired_budgets)),('reference-audit-r2.json',{'tracked_image_names':len(refs),'payload_image_hashes':len(model_hash),'payload_paths':len(model_paths),'tensorboard_images':tb['images'],'tensorboard_events':tb['events'],'tensorboard_errors':tb['errors'],'matched_hash_policy':'keep every image whose full byte SHA matches any payload or TensorBoard source image','source_refs':summary['source_refs']})]:
 (DEST/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
print('PROJECTED GiB',summary['before_allocated_bytes']/2**30,summary['projected_allocated_bytes']/2**30,flush=True)
