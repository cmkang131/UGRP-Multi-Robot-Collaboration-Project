"""Finite follow-through for this authorized gate only."""
from pathlib import Path
import json,subprocess,time,datetime
R=Path('/home/ugrp/ugrp-sim');OPS=R/'ops-reviews/gatesv5';PY=str(R/'ugrp/.venv-sim/bin/python')
cfg=json.loads((OPS/'release-gate-config.json').read_text());batch=OPS/('release-gate-'+cfg['source_sha'][:8]+'-attempt'+str(cfg['attempt']))
while not (batch/'DONE.json').exists():time.sleep(2)
done=json.loads((batch/'DONE.json').read_text())
with (OPS/('release-final-analysis-attempt'+str(cfg['attempt'])+'.log')).open('w') as log:
 p=subprocess.run([PY,str(OPS/'analyze_release.py'),str(OPS/'release-gate-config.json')],stdout=log,stderr=subprocess.STDOUT)
failures=[r for r in done['completed'] if r['category'] in ('failure','cap_end')];reviews=[]
for row in failures[:2]:
 raw=Path(row['raw'])
 if not (raw/'evaluator-snapshots.jsonl').exists() and not Path(str(raw/'evaluator-snapshots.jsonl')+'.zst').exists():continue
 with (OPS/(row['name']+'-playback-preparation.log')).open('w') as log:
  q=subprocess.run([PY,str(OPS/'prepare_release_playback.py'),row['name']],stdout=log,stderr=subprocess.STDOUT)
 reviews.append(dict(run=row['name'],preparation_exit=q.returncode))
(OPS/('release-final-analysis-DONE-attempt'+str(cfg['attempt'])+'.json')).write_text(json.dumps(dict(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),analysis_exit=p.returncode,raw_batch=str(batch),failure_reviews=reviews),indent=2)+'\n')
