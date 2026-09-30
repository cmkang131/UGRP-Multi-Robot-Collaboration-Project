"""Read-only raw/reference audit. Mutable SQLite and logs live only in /private/tmp."""
from pathlib import Path
import sqlite3, subprocess, json, re, os, hashlib, base64, time, collections
ROOT=Path('/Users/changmin/projects/ugrp/outputs')
TMP=Path('/private/tmp/outputs-retention-r2')
c=sqlite3.connect(TMP/'files.sqlite');c.execute('PRAGMA journal_mode=WAL')
c.executescript('''CREATE TABLE IF NOT EXISTS refs(value TEXT PRIMARY KEY,source TEXT);
CREATE TABLE IF NOT EXISTS model_hashes(sha TEXT PRIMARY KEY,source TEXT);
CREATE TABLE IF NOT EXISTS model_paths(path TEXT PRIMARY KEY,source TEXT);
CREATE TABLE IF NOT EXISTS hashes(path TEXT PRIMARY KEY,sha TEXT);
CREATE TABLE IF NOT EXISTS times(path TEXT PRIMARY KEY,t REAL,stream TEXT,source TEXT);
CREATE TABLE IF NOT EXISTS errors(path TEXT,reason TEXT);
''')
IMAGE=re.compile(r'(?<![\w./:+%-])[\w./:+%-]{1,500}\.(?:jpg|jpeg|png)',re.I)
HASH=re.compile(r'^[0-9a-f]{64}$')
refs=json.loads(subprocess.check_output(['gh','pr','list','--limit','100','--json','number,headRefName,headRefOid']))
sources=[{'ref':'origin/main','sha':subprocess.check_output(['git','rev-parse','origin/main']).decode().strip()}]+[{'ref':'origin/'+x['headRefName'],'sha':x['headRefOid'],'pr':x['number']} for x in refs if x['number']!=309]
(TMP/'source_refs.json').write_text(json.dumps(sources,indent=2)+'\n')
blobs={}
for entry in sources:
 print('source tree',entry['ref'],flush=True)
 data=subprocess.check_output(['git','ls-tree','-r','-z',entry['sha']])
 for line in data.split(b'\0'):
  if not line:continue
  meta,path=line.split(b'\t',1);path=path.decode();mode,kind,sha=meta.decode().split()
  if kind!='blob' or path.startswith('experiments/2026-09-30-outputs-retention/') or Path(path).suffix.lower() not in {'.md','.json','.jsonl','.csv','.tsv','.txt','.py','.yaml','.yml'}:continue
  if path.startswith(('experiments/','docs/','configs/','tests/')) or path in {'README.md','AGENTS.md'}:
   blobs.setdefault(sha,entry['ref']+':'+path)
p=subprocess.Popen(['git','cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
print('unique text blobs',len(blobs),flush=True)
for n,(sha,source) in enumerate(blobs.items(),1):
 p.stdin.write((sha+'\n').encode());p.stdin.flush();header=p.stdout.readline().split();size=int(header[2]);raw=p.stdout.read(size);p.stdout.read(1)
 text=raw.decode('utf-8',errors='replace')
 values=[]
 for v in IMAGE.findall(text):
  v=v.replace('\\/','/').lstrip('./')
  if '/outputs/' in v:v=v.split('/outputs/',1)[1]
  elif v.startswith('outputs/'):v=v[8:]
  if '*' in v or '{' in v or v.startswith('http'):continue
  values.append((v,source))
 c.executemany('INSERT OR IGNORE INTO refs VALUES(?,?)',values)
 if n%1000==0:c.commit();print('tracked blobs',n,'/',len(blobs),flush=True)
p.stdin.close();p.wait();c.commit();print('references',c.execute('select count(*) from refs').fetchone(),flush=True)

def addpaths(text,rel,table):
 parent=Path(rel).parent
 for value in IMAGE.findall(text):
  if '/outputs/' in value:choices=[value.split('/outputs/',1)[1]]
  elif value.startswith('outputs/'):choices=[value[8:]]
  elif value.startswith('/'):continue
  else:choices=[str(par/value) for par in [parent,*parent.parents]]
  # No filesystem writes and no symlink traversal; database inventory is authoritative.
  for choice in choices:
   if c.execute('select 1 from files where path=?',(choice,)).fetchone():
    c.execute(f'INSERT OR IGNORE INTO {table} VALUES(?,?)',(choice,rel));break

def payloads(value,source,key=''):
 if isinstance(value,dict):
  for k,v in value.items():payloads(v,source,k)
 elif isinstance(value,list):
  for v in value:payloads(v,source,key)
 elif isinstance(value,str):
  if HASH.fullmatch(value) and any(t in key.lower() for t in ('hash','sha')):
   c.execute('INSERT OR IGNORE INTO model_hashes VALUES(?,?)',(value,source))
  elif len(value)>128 and (value.startswith('data:image/') or value.startswith('/9j/') or value.startswith('iVBORw0KGgo')):
   try:
    data=base64.b64decode(value.split(',',1)[1] if value.startswith('data:') else value,validate=True)
    c.execute('INSERT OR IGNORE INTO model_hashes VALUES(?,?)',(hashlib.sha256(data).hexdigest(),source))
   except Exception as e:c.execute('INSERT INTO errors VALUES(?,?)',(source,'invalid image payload: '+str(e)))

# Timing comes from recorded SIM timestamps, never wall duration or guessed fps.
def timing(value,rel):
 parent=Path(rel).parent;name=parent.name
 if Path(rel).name=='robots.json' and isinstance(value,dict):
  for rid,v in value.items():
   if isinstance(v,dict):
    for fr in v.get('frames',[]):
     if isinstance(fr,dict) and isinstance(fr.get('frame'),int) and isinstance(fr.get('t'),(int,float)):
      path=str(parent/'frames'/rid/f'{fr["frame"]:05d}.jpg')
      c.execute('INSERT OR IGNORE INTO times VALUES(?,?,?,?)',(path,fr['t'],rid,rel))
  return
 def walk(v,t=None):
  if isinstance(v,dict):
   t=next((v[k] for k in ['observed_at_s','sim_time_s','sim_time','timestamp_s','t'] if isinstance(v.get(k),(int,float))),t)
   if t is not None:
    for k in ['path','file','image_path','rgb_path']:
     s=v.get(k)
     if isinstance(s,str) and IMAGE.fullmatch(s):
      for par in [parent,*parent.parents]:
       candidate=str(par/s)
       if c.execute('select 1 from files where path=?',(candidate,)).fetchone():
        c.execute('INSERT OR IGNORE INTO times VALUES(?,?,?,?)',(candidate,t,'',rel));break
   for x in v.values():
    if isinstance(x,(dict,list)):walk(x,t)
  elif isinstance(v,list):
   for x in v:walk(x,t)
 walk(value)

rows=c.execute("select path,size,mtime_ns from files where mode & 61440=32768 and (path like '%.json' or path like '%.jsonl') order by path").fetchall()
for i,(rel,size,stamp) in enumerate(rows,1):
 pth=Path(rel);base=pth.name;path=ROOT/rel
 ismodel=bool(re.search(r'(request|response|payload|wire|prompt|actor[_-]samples|act[_-](input|inference)|model[_-]calls|llm[_-]decisions)',rel,re.I))
 # Stored request summaries and responses are kept even if they contain no images.
 istiming=base in {'robots.json','frames.jsonl','skill-inputs.jsonl','solo-decisions.json','pair-decisions.json','observations.jsonl'}
 istb=rel.startswith('tensorboard') and base=='manifest.json'
 try:
  if pth.suffix=='.json':
   raw=path.read_bytes();c.execute('INSERT OR REPLACE INTO hashes VALUES(?,?)',(rel,hashlib.sha256(raw).hexdigest()))
   if not (ismodel or istiming or istb):continue
   values=[json.loads(raw)]
  elif ismodel or istiming:values=(json.loads(line) for line in path.open() if line.strip())
  else:continue
  for value in values:
   if ismodel:
    payloads(value,rel);addpaths(json.dumps(value),rel,'model_paths')
   if istiming:timing(value,rel)
   if istb:
    for v in IMAGE.findall(json.dumps(value)):
     if '/outputs/' in v:v=v.split('/outputs/',1)[1]
     elif v.startswith('outputs/'):v=v[8:]
     c.execute('INSERT OR IGNORE INTO refs VALUES(?,?)',(v,rel))
 except (OSError,ValueError,TypeError) as e:c.execute('INSERT INTO errors VALUES(?,?)',(rel,str(e)[:300]))
 if i%2000==0:c.commit();print('raw json',i,'/',len(rows),flush=True)
c.commit()
for t in ['hashes','times','model_hashes','model_paths','refs','errors']:print(t,c.execute(f'select count(*) from {t}').fetchone(),flush=True)
