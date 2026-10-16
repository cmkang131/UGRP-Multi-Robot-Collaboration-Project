from pathlib import Path
import subprocess,json,os,time
r=Path('/tmp/ugrp-warp3-offline-seed');m=json.loads((r/'manifest.json').read_text());canon=r/'git-shared.git';source=r/'test-source'
def run(argv,**kwargs):return subprocess.run(argv,check=True,**kwargs)
run(['git','init','--bare',str(canon)],stdout=subprocess.DEVNULL)
for key,value in [('core.repositoryformatversion','1'),('extensions.partialClone','origin'),('remote.origin.url','/tmp/ugrp-warp3-no-upstream'),('remote.origin.promisor','true'),('remote.origin.partialclonefilter','blob:none'),('uploadpack.allowFilter','true'),('gc.auto','0'),('maintenance.auto','false')]:
 run(['git','--git-dir',str(canon),'config',key,value])
with (r/'objects.pack').open('rb') as f:
 run(['git','--git-dir',str(canon),'index-pack','--stdin','--promisor','--threads=2'],stdin=f)
for label,sha in m['refs'].items():run(['git','--git-dir',str(canon),'update-ref','refs/heads/warp3-'+label,sha])
run(['git','--git-dir',str(canon),'symbolic-ref','HEAD','refs/heads/warp3-warm'])
run(['git','clone','--reference',str(canon),'--no-local','--filter=blob:none','--no-checkout',str(canon),str(source)])
verified=[]
for label,sha in m['refs'].items():
 run(['git','-C',str(source),'checkout','--detach',sha],stdout=subprocess.DEVNULL)
 actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 changes=subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=normal'],text=True)
 if actual!=sha or changes:raise RuntimeError('offline source identity/cleanliness mismatch')
 verified.append(dict(label=label,sha=sha,clean=True))
print(json.dumps(dict(offline_checkouts=verified,network_upstream_available=False)),flush=True)
(r/'offline-validation.json').write_text(json.dumps(dict(offline_checkouts=verified,network_upstream_available=False,clone_flags=['--reference','--no-local','--filter=blob:none','--no-checkout'],canonical_gc_auto=0,canonical_maintenance_auto=False),indent=2)+'\n')
