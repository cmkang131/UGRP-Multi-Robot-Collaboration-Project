from pathlib import Path
import json,hashlib,urllib.request,urllib.parse
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
root=Path('/Users/changmin/projects/ugrp/outputs/s4grip2-offline');snap=Path('/Users/changmin/projects/ugrp/outputs/tensorboard/1010-s4grip2')
checked=[]
for path in sorted((root/'views').iterdir()):
 expected=json.loads((path/'result.json').read_text())['offline_scalars'];run=snap/path.name
 event=EventAccumulator(str(run));event.Reload();observed={t:event.Scalars(t)[-1].value for t in event.Tags()['scalars']}
 assert all(abs(observed[t]-v)<1e-6 for t,v in expected.items())
 for tag in ['offline/true_positive_episodes','offline/false_positive_hold_episodes']:
  url='http://127.0.0.1:6006/data/plugin/scalars/scalars?'+urllib.parse.urlencode(dict(run='1010-s4grip2/'+path.name,tag=tag))
  vals=json.load(urllib.request.urlopen(url));assert vals[-1][2]==expected[tag]
 checked.append(dict(run=path.name,scalar_tags=len(observed),values=observed))
media=[]
for p in Path('/Users/changmin/projects/ugrp/outputs/tensorboard/1010-s4grip2-media').glob('*/manifest.json'):
 m=json.loads(p.read_text());assert m['complete']
 for v in m['videos']:
  url='http://127.0.0.1:6007/video/'+v['id']
  res=urllib.request.urlopen(url);assert res.status==200
  media.append(dict(id=v['id'],url=url,path=v['path'],sha256=hashlib.sha256(Path(v['path']).read_bytes()).hexdigest(),http_status=res.status))
r=dict(snapshot=str(snap),event_runs=len(checked),scalars=sum(x['scalar_tags'] for x in checked),http_verified_runs=len(checked),runs=checked,media=media)
(root/'tensorboard-verification.json').write_text(json.dumps(r,indent=2)+'\n');print(dict(runs=len(checked),scalars=r['scalars'],media=len(media)))
