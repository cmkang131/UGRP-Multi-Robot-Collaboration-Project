from pathlib import Path
import subprocess,json,re,collections
root=Path('/Users/changmin/projects/ugrp/outputs');names={x.name for x in root.iterdir()}
for d in (root/'retired-worktrees').iterdir():
 names.add(d.name)
 if (d/'outputs').is_dir():names.update(x.name for x in (d/'outputs').iterdir())
names={x for x in names if len(x)>3};Path('/tmp/ugrp-retention-patterns.txt').write_text('\n'.join(sorted(names)))
prs=json.load(open('/tmp/ugrp-retention-prs.json'));refs=['origin/main']+['origin/'+p['headRefName'] for p in prs]
hits=collections.defaultdict(lambda:collections.defaultdict(set));snapshots=[];mainrows=[];cache={}
split=re.compile(r'[\s/\\"\x27<>`:,=\[\]{}]+')
for ref in refs:
 sha=subprocess.check_output(['git','rev-parse',ref],text=True).strip();snapshots.append({'ref':ref,'sha':sha})
 if ref=='origin/main':paths=['experiments','docs','configs','outputs/tensorboard-view.json'];rows=[]
 else:
  paths=subprocess.check_output(['git','diff','--name-only','origin/main',ref,'--','experiments','docs','configs','outputs/tensorboard-view.json'],text=True).splitlines();rows=[r for r in mainrows if r[0] not in paths]
 if paths:
  proc=subprocess.Popen(['git','grep','-l','-I','-F','-f','/tmp/ugrp-retention-patterns.txt',ref,'--',*paths],stdout=subprocess.PIPE,text=True)
  candidates=[]
  for line in proc.stdout:
   candidates.append(line.strip().split(':',1)[1])
   if len(candidates)%100==0:print(ref,'candidate files',len(candidates),flush=True)
  if proc.wait() not in (0,1):raise RuntimeError('git grep failed')
  print(ref,'grep done',len(candidates),flush=True)
  for i,file in enumerate(candidates):
   data=subprocess.check_output(['git','show',ref+':'+file]).decode('utf-8',errors='replace');found={}
   for n,line in enumerate(data.splitlines(),1):
    for token in set(split.split(line)) & names:
     found.setdefault(token,n)
   rows.extend((file,str(n),name) for name,n in found.items())
   if i%200==0:print(ref,'parsed',i,flush=True)
 if ref=='origin/main':mainrows=rows
 for file,number,name in rows:hits[name][ref].add(file+':'+number)
 print(ref,'done',len(rows),flush=True)
view=root/'tensorboard-view.json'
if view.is_file():
 for i,line in enumerate(view.read_text().splitlines(),1):
  for token in set(split.split(line)) & names:hits[token]['live-view'].add('outputs/tensorboard-view.json:'+str(i))
out={'refs':snapshots,'references':{n:{r:sorted(v) for r,v in refs.items()} for n,refs in hits.items()}}
Path('/tmp/ugrp-retention-refs.json').write_text(json.dumps(out,ensure_ascii=False));print('names with references',len(hits),flush=True)
