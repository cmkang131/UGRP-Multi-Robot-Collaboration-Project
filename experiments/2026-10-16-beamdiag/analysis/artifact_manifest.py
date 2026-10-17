from pathlib import Path
import hashlib,json
B=Path('/home/ugrp/ugrp-sim');O=B/'ops-reviews/beamdiag/v1';out=[]
roots=[]
for a,s in [('A',8329000),('A',8329001),('B',8329000),('B',8329001)]:roots.append((B/f'ops-reviews/beamact3/{a}/playback/seed-{s}',f'playback/beamdiag-{a}-{s}'))
roots.extend([(O/'playback-B-8329019','playback/beamdiag-B-8329019'),(B/'ops-reviews/beampair8/playback/8328003','playback/beamdiag-teacher-8328003'),(O/'montages','research/beamdiag-evidence/montages')])
for root,local in roots:
 for p in root.iterdir():
  if p.is_file() and not p.is_symlink():out.append(dict(remote=str(p),local_relative=local+'/'+p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
for p in O.glob('review-*.jpg'):out.append(dict(remote=str(p),local_relative='research/beamdiag-evidence/'+p.name,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(O/'media-transfer-manifest.json').write_text(json.dumps(out,indent=2)+'\n');print(len(out))
