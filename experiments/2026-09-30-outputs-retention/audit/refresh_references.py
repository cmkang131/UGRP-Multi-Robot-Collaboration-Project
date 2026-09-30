from pathlib import Path
import json,subprocess,re,collections
old=json.load(open('/tmp/ugrp-retention-refs.json'));names=set(old['references'])|set(Path('/tmp/ugrp-retention-patterns.txt').read_text().splitlines());prs=json.load(open('/tmp/ugrp-retention-prs-final.json'))
mainrows=[]
for name,refs in old['references'].items():
 for value in refs.get('origin/main',[]):
  file,line=value.rsplit(':',1);mainrows.append((file,line,name))
main_sha=old['refs'][0]['sha'];current_main=subprocess.check_output(['git','rev-parse','origin/main'],text=True).strip()
ref_list=['origin/main']+['origin/'+p['headRefName'] for p in prs];split=re.compile(r'[\s/\\"\x27<>`:,=\[\]{}]+');result=collections.defaultdict(lambda:collections.defaultdict(set));snapshots=[]
for ref in ref_list:
 sha=subprocess.check_output(['git','rev-parse',ref],text=True).strip();snapshots.append({'ref':ref,'sha':sha})
 base=main_sha if ref=='origin/main' else current_main
 paths=subprocess.check_output(['git','diff','--name-only',base,sha,'--','experiments','docs','configs','outputs/tensorboard-view.json'],text=True).splitlines();rows=[x for x in mainrows if x[0] not in paths]
 if paths:
  p=subprocess.run(['git','grep','-l','-I','-F','-f','/tmp/ugrp-retention-patterns.txt',ref,'--',*paths],capture_output=True,text=True)
  if p.returncode not in (0,1):raise RuntimeError(p.stderr)
  for line in p.stdout.splitlines():
   file=line.split(':',1)[1];text=subprocess.check_output(['git','show',ref+':'+file],text=True);found={}
   for n,line in enumerate(text.splitlines(),1):
    for name in set(split.split(line))&names:found.setdefault(name,n)
   rows.extend((file,str(n),name) for name,n in found.items())
 if ref=='origin/main':mainrows=rows
 for file,line,name in rows:result[name][ref].add(file+':'+line)
 print(ref,'done',len(rows),flush=True)
for name,refs in old['references'].items():
 if 'live-view' in refs:result[name]['live-view'].update(refs['live-view'])
Path('/tmp/ugrp-retention-refs-final.json').write_text(json.dumps({'refs':snapshots,'references':{n:{r:sorted(p) for r,p in v.items()} for n,v in result.items()}},ensure_ascii=False))
