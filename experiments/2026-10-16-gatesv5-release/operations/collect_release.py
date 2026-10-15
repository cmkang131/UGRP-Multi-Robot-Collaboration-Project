"""Retrieve only gcp2 summaries and bounded playback assets; verify stored bytes."""
from pathlib import Path
import subprocess,json,hashlib
root=Path('/Users/changmin/projects/ugrp')
ops=root/'outputs/e2e18-admin/gatesv5'
remote='/home/ugrp/ugrp-sim/ops-reviews/gatesv5/'
mapping={}
for local,rel in {
 'release-gate-summary.json':'release-gate-analysis-a41781dd-attempt3/summary-with-candidates.json',
 'release-gate-rejection_table.json':'release-gate-analysis-a41781dd-attempt3/rejection_table-with-candidates.json',
 'release-gate-candidate-funnels.json':'release-gate-analysis-a41781dd-attempt3/candidate-funnels.json',
 'release-gate-population-funnels.json':'release-gate-analysis-a41781dd-attempt3/population-funnels.json',
 'release-gate-first30-initial.json':'release-gate-a41781dd-attempt2/first30-speed.json',
 'release-gate-first30-resumed.json':'release-gate-a41781dd-attempt3/first30-speed.json',
 'release-gate-DONE.json':'release-gate-a41781dd-attempt3/DONE.json',
 'release-gate-final-analysis-DONE.json':'release-final-analysis-DONE-attempt3.json',
 'release-final-stop.json':'release-gate-a41781dd-attempt3/SUPERVISOR_STOP.json',
 'host-finalization-preservation-v2.json':'host-finalization-preservation-v2.json',
 'release-short-population-funnels.json':'release-short-population-funnel.json',
 'release-final-attempt-ledger.json':'release-final-attempt-ledger.json',
 'release-failure-analysis.json':'release-failure-analysis.json',
 'cleanup.json':'cleanup.json',
}.items():mapping[str(ops/local)]=remote+rel
for label,run in [
 ('success','gv5-release-gate-current_B-110600-a41781dd-retry1'),
 ('failure','gv5-release-gate-current_A-110633-a41781dd-retry1'),
 ('host-stop','gv5-release-gate-current_B-110614-a41781dd-retry1'),
]:
 folder=root/'outputs/e2e18-admin/playback'/('gatesv5-release-'+label)
 folder.mkdir(exist_ok=True,parents=True)
 code='from pathlib import Path\nimport json\np=Path('+repr(remote+'playback/release-'+run)+')\nassert (p/"review.json").exists(), "playback not finalized"\nprint(json.dumps([x.name for x in p.iterdir() if x.is_file() and (x.name.startswith(("full-","tail-")) or x.name in ("review.json","playback-3x.mp4"))]))'
 names=json.loads(subprocess.check_output(['ssh','gcp2','python3','-'],input=code.encode()))
 for name in names:mapping[str(folder/name)]=remote+'playback/release-'+run+'/'+name
 mapping[str(folder/'provenance.json')]=remote+'derived-release-replay/'+run+'/provenance.json'
code='from pathlib import Path\nimport json,hashlib\nmapping='+repr(mapping)+'\nprint(json.dumps({local:dict(remote=remote,sha256=hashlib.sha256(Path(remote).read_bytes()).hexdigest(),bytes=Path(remote).stat().st_size) for local,remote in mapping.items()}))\n'
folder=root/'outputs/e2e18-admin/playback/gatesv5-release-failure-event-native-tail'
folder.mkdir(exist_ok=True,parents=True)
rel='playback/release-failure-event-native-tail/'
listcode='from pathlib import Path\nimport json\np=Path('+repr(remote+rel)+')\nassert (p/"event-tail-provenance.json").exists()\nprint(json.dumps([x.name for x in p.iterdir() if x.is_file()]))'
for name in json.loads(subprocess.check_output(['ssh','gcp2','python3','-'],input=listcode.encode())):
 mapping[str(folder/name)]=remote+rel+name
code='from pathlib import Path\nimport json,hashlib\nmapping='+repr(mapping)+'\nprint(json.dumps({local:dict(remote=remote,sha256=hashlib.sha256(Path(remote).read_bytes()).hexdigest(),bytes=Path(remote).stat().st_size) for local,remote in mapping.items()}))\n'
expected=json.loads(subprocess.check_output(['ssh','gcp2','python3','-'],input=code.encode()))
rows=[]
for local,spec in expected.items():
 p=Path(local)
 if p.suffix=='.mp4':assert spec['bytes']<=8_000_000
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=spec['sha256']:
  subprocess.run(['scp','-q','gcp2:'+spec['remote'],local],check=True)
 digest=hashlib.sha256(p.read_bytes()).hexdigest()
 rows.append(dict(local=local,**spec,match=digest==spec['sha256'],local_sha256=digest))
result=dict(files_N=len(rows),mismatches=[x for x in rows if not x['match']],files=rows)
assert not result['mismatches']
(ops/'retrieval-verification-release.json').write_text(json.dumps(result,indent=2)+'\n')
print('retrieval SHA PASS',len(rows))
