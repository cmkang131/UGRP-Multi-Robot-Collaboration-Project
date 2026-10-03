"""Finalize small review tables and bind them to the manifest (raw stays read-only)."""
from pathlib import Path
import csv,io,json,sqlite3,hashlib,collections,shutil,time
ROOT=Path('/Users/changmin/projects/ugrp/outputs');DEST=Path(__file__).resolve().parents[1];TMP=Path('/private/tmp/outputs-retention-r2')
c=sqlite3.connect(TMP/'files.sqlite');m=json.loads((DEST/'manifest.json').read_text());summary=json.loads((DEST/'summary.json').read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,data):
 (DEST/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def split_csv(name,folder):
 src=DEST/name;fields=None;buffer=[];size=0;part=0;entries=[]
 dest=DEST/folder;dest.mkdir(exist_ok=True)
 def flush():
  nonlocal part,buffer,size
  if not buffer:return
  part+=1;p=dest/f'{part:03d}.csv'
  with p.open('w') as f:
   w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(buffer)
  entries.append({'path':str(p.relative_to(DEST)),'sha256':sha(p)});buffer=[];size=0
 with src.open() as f:
  reader=csv.DictReader(f);fields=reader.fieldnames
  for row in reader:
   size+=sum(len(str(v).encode()) for v in row.values())+len(row)*4;buffer.append(row)
   if size>=800000:flush()
 flush();return entries
# Preserve complete per-directory data in small shards; manifest.csv is additive per-unit.
evidence=split_csv('manifest.csv','folder-details')
units={}
with (DEST/'manifest.csv').open() as f:
 for row in csv.DictReader(f):
  parts=row['folder'].split('/');unit='/'.join(parts[:2]) if parts[0]=='retired-worktrees' else parts[0] or '(outputs root files)'
  value=units.setdefault(unit,dict(path=unit,**{k:0 for k in ['before_bytes','after_bytes','before_allocated_bytes','after_allocated_bytes','files_before','delete_files','keep_files','delete_bytes','delete_allocated_bytes']},rule_ids=set(),thinning_rules=set()))
  for key in ['before_bytes','after_bytes','before_allocated_bytes','after_allocated_bytes','files_before','delete_files','keep_files','delete_bytes','delete_allocated_bytes']:value[key]+=int(row[key])
  value['rule_ids'].update(row['rule_ids'].split(','));
  if row['thinning_rule']:value['thinning_rules'].add('SIM_1Hz' if row['thinning_rule'].startswith('first') else 'unknown_time_at_most_10pct_plus_endpoints')
with (DEST/'manifest.csv').open('w') as f:
 fields=list(next(iter(units.values())));w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
 for row in sorted(units.values(),key=lambda r:r['path']):
  row['rule_ids']=','.join(sorted(row['rule_ids']-{''}));row['thinning_rules']=','.join(sorted(row['thinning_rules']));w.writerow(row)
shutil.copy2(DEST/'manifest.csv',DEST/'inventory.csv')
# Byte-identical JSON source mappings are explicit, every source is in keep batches.
json_evidence=split_csv('json-reconstruction.csv','json-reconstruction')
# Stream rules also exceed the single-file metadata budget at >20k streams.
thinning_evidence=split_csv('thinning.csv','thinning')
with (DEST/'thinning.csv').open('w') as f:
 w=csv.writer(f,lineterminator='\n');w.writerow(['rules_file','sha256'])
 for e in thinning_evidence:w.writerow([e['path'],e['sha256']])
evidence+=thinning_evidence
# Replace the large flat mapping by a small index (all rows remain in CSV shards).
with (DEST/'json-reconstruction.csv').open('w') as f:
 w=csv.writer(f,lineterminator='\n');w.writerow(['mapping_file','sha256'])
 for e in json_evidence:w.writerow([e['path'],e['sha256']])
evidence+=json_evidence
registry=json.loads(Path('configs/model_artifacts.json').read_text())['artifacts'];known={f['sha256']:a['id'] for a in registry if a.get('status')=='available' for f in a.get('files',[])}
models=[]
for p,size,stamp in c.execute("select path,size,mtime_ns from files where mode & 61440=32768 and (path like '%.safetensors' or path like '%.pt' or path like '%.pth' or path like '%.ckpt' or path like '%.onnx') order by path"):
 h=sha(ROOT/p);models.append({'path':p,'bytes':size,'sha256':h,'release_registry_match':known.get(h),'decision':'KEEP D4','unchanged_since_inventory':(ROOT/p).stat().st_mtime_ns==stamp})
write('checkpoint-audit.json',{'models':models,'unmatched_count':sum(x['release_registry_match'] is None for x in models),'loading_test_scope':'Read-only full file hash versus current configs/model_artifacts.json. No new release download or model loading.'})
# Requested JSON assessment, including records that could NOT be reconstructed.
json_types=collections.defaultdict(lambda:collections.Counter())
for p,size,allocated,action,rule in c.execute("select f.path,f.size,f.allocated,d.action,d.rule from files f join decisions d on f.path=d.path where f.path like '%.json'"):
 typ=Path(p).name
 if 'request' in typ or '/wire/' in p:typ='model_request_or_wire_record'
 values=json_types[typ];values['files']+=1;values['bytes']+=size;values['allocated_bytes']+=allocated
 if action=='delete':values['delete_bytes']+=size;values['delete_allocated_bytes']+=allocated;values['delete_files']+=1
write('json-audit-r2.json',{'method':'Full byte SHA-256 for all 129153 JSON files from inventory. D5 only if a bound retained source has identical bytes; reconstruct with byte copy, not JSON reserialization. No filename-only or partial-field reconstruction used.','largest_types':[{**v,'name':k} for k,v in sorted(json_types.items(),key=lambda x:-x[1]['bytes'])[:30]],'unique_field_examples':{'robots.json':'frames[].report, commanded_servo and exception; trace.jsonl is not a complete replacement','eval_only/host.json':'gt, frames_eval, contacts, kind_steps, retention, max_eq_active','result.json':'source, controller_events, localizer_log, localizer_stats, evaluation; individual logs do not reproduce the full document'},'reconstruction_files':[e['path'] for e in json_evidence]})
uncertain_reasons={'model_input_or_training_uncertain','unsequenced_image_uncertain','D4_model_or_unique_zip','hardlink_allocation_uncertain','reconstruction_source_not_frozen','changed_during_audit','unreadable_during_audit'}
with (DEST/'uncertain.csv').open('w') as f:
 w=csv.writer(f,lineterminator='\n');w.writerow(['unit','reason','keep_files','keep_bytes','keep_allocated_bytes'])
 for row in c.execute("select f.unit,d.reason,count(*),sum(f.size),sum(f.allocated) from decisions d join files f on f.path=d.path where d.action='keep' group by f.unit,d.reason order by f.unit,d.reason"):
  if row[1] in uncertain_reasons:w.writerow(row)
# Disjoint file-format accounting for the user-facing per-category table.
ext=collections.defaultdict(lambda:collections.Counter())
seen=set()
for p,size,allocated,dev,ino,action in c.execute('select f.path,f.size,f.allocated,f.dev,f.ino,d.action from files f join decisions d on f.path=d.path order by f.path'):
 k=Path(p).suffix.lower()
 if k in {'.jpg','.jpeg','.png'}:k='camera_images'
 elif k in {'.safetensors','.pt','.pth','.ckpt','.onnx'}:k='checkpoints'
 elif k not in {'.json','.jsonl','.zip','.npz','.mjb','.mp4'}:k='other_files'
 v=ext[k];v['before_files']+=1;v['before_bytes']+=size
 if (dev,ino) in seen:allocated=0
 seen.add((dev,ino));v['before_allocated_bytes']+=allocated
 if action=='delete':v['delete_files']+=1;v['delete_bytes']+=size;v['delete_allocated_bytes']+=allocated
for v in ext.values():
 for k in ['files','bytes','allocated_bytes']:v['after_'+k]=v['before_'+k]-v['delete_'+k]
summary['file_categories']={k:dict(v) for k,v in ext.items()};summary['remaining_to_40_gib']=max(0,summary['projected_allocated_bytes']/2**30-40)
write('summary.json',summary)
for name in ['thinning.csv','json-reconstruction.csv','sealed-cohorts.json','retired-records.json','checkpoint-audit.json','json-audit-r2.json','reference-audit-r2.json','boundary-audit.json','uncertain.csv']:
 evidence.append({'path':name,'sha256':sha(DEST/name)})
m['folder_summary']={'path':'manifest.csv','sha256':sha(DEST/'manifest.csv')};m['evidence_files']=evidence
m['keep_hash_format']='Each keep batch lists exact filenames (zlib+base64 JSON metadata) and binds SHA256 of newline canonical JSON [name,bytes,mtime_ns,full_file_sha256] for every file, in filename order. No raw file bytes copied.'
m['recent_keep_scope']='Recent/live files and infrastructure are excluded from immutable keep hash snapshots; they are never candidates. Every selected deletion and each old stable retained file is hash-bound.'
write('manifest.json',m)
print('units',len(units),'models',len(models),'unmatched',sum(x['release_registry_match'] is None for x in models),'manifest sha',sha(DEST/'manifest.json'))
