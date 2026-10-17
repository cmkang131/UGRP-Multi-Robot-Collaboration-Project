from pathlib import Path
import json,subprocess,hashlib
from concurrent.futures import ThreadPoolExecutor
B=Path('/home/ugrp/ugrp-sim');O=B/'ops-reviews/beamdiag/v1';D=O/'montages';D.mkdir(exist_ok=True)
def one(task):
 a,s=task;r=B/f'ops-reviews/beamact3/{a}/heldout20-v1/seed-{s}';rows=json.loads((r/'review/manifest.json').read_text());p=json.loads((r/'plan.json').read_text());indices=[round((len(rows)-1)*k/5) for k in range(6)];out=D/f'{a}-{s}.jpg'
 seq=O/'montage-sequences'/f'{a}-{s}'
 args=[];filters=[]
 for j,rid in enumerate(('r1','r2')):
  dd=seq/rid;dd.mkdir(parents=True,exist_ok=True)
  for i,k in enumerate(indices):
   dest=dd/f'{i:03d}.jpg'
   if not dest.exists():dest.symlink_to(r/'review'/rows[k]['own'][rid])
  args+=['-framerate','1','-i',str(dd/'%03d.jpg')]
  f=f'[{j}:v]scale=320:240,setsar=1'
  for i,k in enumerate(indices):
   txt=f'{a} {s} t={rows[k]["sim_s"]:.1f}s {rid}={p["roles"][rid]}'
   f+=f",drawtext=text='{txt}':x=4:y=4:fontsize=13:fontcolor=white:box=1:boxcolor=black@0.7:enable='eq(n,{i})'"
  filters.append(f+f'[v{j}]')
 filters.append('[v0][v1]hstack=inputs=2,tile=2x3:padding=3:margin=3[v]')
 subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-threads','1',*args,'-filter_complex_threads','1','-filter_complex',';'.join(filters),'-map','[v]','-frames:v','1','-q:v','2',str(out)],check=True)
 return dict(arm=a,seed=s,raw=str(r),times=[rows[k]['sim_s'] for k in indices],frame_N=12,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),bytes=out.stat().st_size,path=str(out))
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,[(a,s) for a in ('A','B') for s in range(8329000,8329020)]))
(O/'montages.json').write_text(json.dumps(results,indent=2)+'\n')
print('created',len(results),flush=True)
