from pathlib import Path
import sqlite3,collections,json,re,hashlib,os,time
root=Path('/Users/changmin/projects/ugrp/outputs');c=sqlite3.connect('/tmp/ugrp-retention-files.sqlite')
c.execute('CREATE INDEX IF NOT EXISTS files_size ON files(size)');c.execute('CREATE INDEX IF NOT EXISTS files_top ON files(top)');c.commit()
units={};names={'result.json','manifest.json','run.json','report.json','config.json','meta.json','provenance.json','RETIRED.json'}
now=time.time()
for unit,size,allocated,newest,count in c.execute('select unit,sum(case when mode & 61440=32768 then size else 0 end),sum(allocated),max(mtime_ns),count(*) from files group by unit'):
 units[unit]={'path':unit,'bytes':size,'allocated_bytes':allocated,'newest_mtime_ns':newest,'node_count':count,'model_files':[],'metadata_count':0,'metadata_examples':[],'sha_examples':[],'seed_examples':[],'states':{},'splits':{},'request_file_count':0,'test_path_count':0,'metadata_errors':[]}
for p,unit,size,mode in c.execute('select path,unit,size,mode from files'):
 u=units[unit];path=Path(p);base=path.name
 if mode & 61440 != 32768:continue
 if re.search(r'(^|/)(test|heldout|holdout|confirmatory)([-_/]|$)',p):u['test_path_count']+=1
 if re.search(r'(request|response|prompt)',base,re.I) and path.suffix in {'.json','.jsonl','.txt'}:u['request_file_count']+=1
 if path.suffix.lower() in {'.safetensors','.pt','.pth','.ckpt','.onnx'}:
  u['model_files'].append({'path':p,'bytes':size,'sha256':hashlib.sha256((root/p).read_bytes()).hexdigest()})
 if unit.startswith('tensorboard') or base not in names:continue
 u['metadata_count']+=1
 if size>16*2**20:
  u['metadata_errors'].append({'path':p,'reason':'over_16MiB_not_parsed'});continue
 try:v=json.loads((root/p).read_text())
 except Exception:
  u['metadata_errors'].append({'path':p,'reason':'unreadable_or_invalid_json'});continue
 if len(u['metadata_examples'])<4:u['metadata_examples'].append(p)
 def walk(x,depth=0):
  if not isinstance(x,dict) or depth>5:return
  for k,v in x.items():
   if k in {'source_sha','code_sha','git_sha','head','sha','commit'} and isinstance(v,str) and re.fullmatch('[0-9a-f]{7,40}',v):
    if len(u['sha_examples'])<4 and v not in u['sha_examples']:u['sha_examples'].append(v)
   if k in {'seed','scene_seed','layout_seed'} and isinstance(v,(int,str)):
    if len(u['seed_examples'])<4 and v not in u['seed_examples']:u['seed_examples'].append(v)
   if k in {'state','status','split'} and isinstance(v,str) and len(v)<100:
    key='splits' if k=='split' else 'states';u[key][v]=u[key].get(v,0)+1
   if isinstance(v,dict):walk(v,depth+1)
 walk(v)
registry=json.load(open('configs/model_artifacts.json'))['artifacts']
known={f['sha256']:a['id'] for a in registry if a.get('status')=='available' for f in a.get('files',[])}
for u in units.values():
 for m in u['model_files']:m['release_registry_match']=known.get(m['sha256'])
Path('/tmp/ugrp-retention-metadata.json').write_text(json.dumps(list(units.values()),ensure_ascii=False))
print('units',len(units),'metadata',sum(u['metadata_count'] for u in units.values()),'model files',sum(len(u['model_files']) for u in units.values()),flush=True)
# Look only for large retired duplicates; preserve small files regardless.
cache={};dups=[]
def sha(p):
 if p not in cache:
  with (root/p).open('rb') as f:cache[p]=hashlib.file_digest(f,'sha256').hexdigest()
 return cache[p]
for p,size,mtime in c.execute("select path,size,mtime_ns from files where top='retired-worktrees' and size>=1048576 and mode & 61440=32768"):
 if mtime> (now-86400)*1e9:continue
 candidates=c.execute("select path from files where top!='retired-worktrees' and size=? and mode & 61440=32768",(size,)).fetchall()
 for (other,) in candidates:
  if sha(p)==sha(other):
   dups.append({'path':p,'retained_path':other,'bytes':size,'sha256':sha(p)});break
Path('/tmp/ugrp-retention-duplicates.json').write_text(json.dumps(dups,ensure_ascii=False));print('duplicates',len(dups),sum(x['bytes'] for x in dups)/2**30,flush=True)
