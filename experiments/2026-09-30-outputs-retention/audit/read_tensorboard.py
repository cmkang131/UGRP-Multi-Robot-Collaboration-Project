import sqlite3,json,hashlib,collections
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
root=Path('/Users/changmin/projects/ugrp/outputs');con=sqlite3.connect('/tmp/ugrp-retention-files.sqlite')
rows=[]
for (rel,) in con.execute("select path from files where top like 'tensorboard%' and path like '%/manifest.json'"):
 p=root/rel
 try:m=json.loads(p.read_text())
 except Exception as e:rows.append({'manifest':rel,'error':str(e)});continue
 source=m.get('source',''); scalar_samples=0;scalar_tags=[];error=None
 if list(p.parent.glob('events.out.tfevents.*')):
  try:
   ev=EventAccumulator(str(p.parent),size_guidance={'scalars':0,'tensors':0,'images':1,'histograms':1,'compressedHistograms':1}).Reload()
   scalar_tags=ev.Tags().get('scalars',[])
   scalar_samples=sum(len(ev.Scalars(t)) for t in scalar_tags)
  except Exception as e:error=str(e)
 rows.append({'manifest':rel,'manifest_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source':source,'complete':m.get('complete'),'reported_counts':m.get('counts',{}),'scalar_samples_read':scalar_samples,'scalar_tags':scalar_tags,'videos':[v.get('path') for v in m.get('videos',[])],'error':error})
print('manifests',len(rows),'samples',sum(x.get('scalar_samples_read',0) for x in rows),'errors',sum(bool(x.get('error')) for x in rows))
Path('/tmp/ugrp-retention-tb.json').write_text(json.dumps(rows,ensure_ascii=False))
