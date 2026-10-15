"""Read-only Git/local saved-remote inventory; no host connection."""
import hashlib,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
ADMIN=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')
OUT=ADMIN/'crate14-audit'
PAT=re.compile(rb'(?<![0-9A-Za-z.])794[0-9]{2}(?![0-9A-Za-z.])')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 prs=json.loads((OUT/'open-prs.json').read_text())
 refs=[{'name':'origin/main','sha':subprocess.check_output(['git','rev-parse','origin/main'],text=True).strip()}]+[{'name':f"PR#{p['number']}",'sha':p['headRefOid']} for p in prs]
 hits=[]
 for ref in refs:
  proc=subprocess.run(['git','grep','-n','-I','-E','(^|[^[:alnum:].])794[0-9]{2}([^[:alnum:].]|$)',ref['sha'],'--','configs','experiments','scripts','docs'],cwd=ROOT,capture_output=True)
  if proc.returncode not in (0,1):raise RuntimeError(proc.stderr.decode())
  for line in proc.stdout.splitlines():
   # Keep only matching seed numbers and path, not arbitrary file contents.
   hits.append({'source':ref['name'],'path':line.decode(errors='replace').split(':',2)[1],'values':[int(x) for x in PAT.findall(line)]})
 queue=[]
 for p in sorted((ADMIN/'vm3-queue').glob('*.json')):
  b=p.read_bytes();queue.append({'path':str(p),'sha256':sha(p)})
  if PAT.search(b):hits.append({'source':'queue','path':str(p),'values':[int(x) for x in PAT.findall(b)]})
 remote=[]
 for p in sorted((ADMIN/'gcp-reports').rglob('*remote*inventory*.json')):
  b=p.read_bytes();remote.append({'path':str(p),'sha256':sha(p),'mtime_ns':p.stat().st_mtime_ns})
  if PAT.search(b):hits.append({'source':'saved_remote_inventory','path':str(p),'values':[int(x) for x in PAT.findall(b)]})
 # Local run inventory and existing local plans include work not pushed yet.
 for base in (ROOT/'experiments',Path('/Users/changmin/projects/ugrp/experiments')):
  for p in base.rglob('*.json'):
   if 'crate14' in p.name:continue
   b=p.read_bytes()
   if PAT.search(b):hits.append({'source':'local_plan','path':str(p),'values':[int(x) for x in PAT.findall(b)]})
 names=[p.name for p in Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs').iterdir() if PAT.search(p.name.encode())]
 report={'range_checked':[79400,79499],'git_heads':refs,'existing_queues':queue,'saved_remote_inventories':remote,'conflicts':hits,'local_run_names':names,
  'live_remote_checked':False,'scope':'Current fetched main/open PR heads + all existing queue JSON + local saved remote inventories. Live VM access forbidden; inventory snapshot freshness not guaranteed.'}
 (OUT/'seed-check.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'git_heads':len(refs),'queues':len(queue),'remote_snapshots':len(remote),'conflict_count':len(hits),'local_runs':names}))
if __name__=='__main__':main()
