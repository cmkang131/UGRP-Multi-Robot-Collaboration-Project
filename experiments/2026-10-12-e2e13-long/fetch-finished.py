"""Finite fetch-lite: media and image-bearing requests remain on VM/ARM."""
from pathlib import Path
import subprocess,json,time,sys
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True);done={};names=[f'e2e13-long-{b}-s{s}' for b,seeds in [('a',(61001,61002,61003,61004)),('b',(61001,61002))] for s in seeds]
until=time.time()+7.75*3600
while len(done)<len(names) and time.time()<until:
 try:
  text=subprocess.check_output(['ssh','azure2','cat ~/ugrp-sim/e2e13-long-archive-e2e13-long-a-s61001.json'],text=True,stderr=subprocess.DEVNULL)
  archives=json.loads(text);(out/'archive-verification.json').write_text(text)
 except subprocess.CalledProcessError:
  time.sleep(5);continue
 for name,record in archives.items():
  if name in done:continue
  try:
   exclusions=subprocess.check_output(['ssh','azure2',f'cat ~/ugrp-sim/runs/{name}/LITE_IMAGE_EXCLUSIONS.txt'],text=True)
   ep=out/(name+'-image-exclusions.txt');paths=[x for x in exclusions.splitlines() if x]
   ep.write_text('\n'.join(p+s for p in paths for s in ('','.zst'))+'\n')
   dest=Path('/Users/changmin/projects/ugrp/outputs/azure2-runs')/name;dest.mkdir(parents=True,exist_ok=True)
   flags=['--exclude='+x for x in ('*.png','*.jpg','*.jpeg','*.mp4','*.gif','*.npz','*.npy')]+['--exclude-from='+str(ep)]
   subprocess.run(['rsync','-aL',*flags,f'azure2:~/ugrp-sim/runs/{name}/',str(dest)+'/'],check=True)
   diff=subprocess.check_output(['rsync','-ancL','--out-format=%n',*flags,f'azure2:~/ugrp-sim/runs/{name}/',str(dest)+'/'],text=True)
   if diff.strip():raise RuntimeError('FETCH_CHECKSUM_CHANGED:'+name)
   done[name]=dict(run=name,path=str(dest),checksum_verified=True,excluded_embedded_images=len(paths),files=sum(p.is_file() for p in dest.rglob('*')),bytes=sum(p.stat().st_size for p in dest.rglob('*') if p.is_file()))
   (out/'fetch-lite-verification.json').write_text(json.dumps(done,indent=2)+'\n');print(json.dumps(done[name]),flush=True)
  except (subprocess.SubprocessError, OSError, RuntimeError) as exc:
   with (out/'fetch-errors.jsonl').open('a') as stream:stream.write(json.dumps(dict(run=name,unix=time.time(),error=type(exc).__name__))+'\n')
 time.sleep(5)
