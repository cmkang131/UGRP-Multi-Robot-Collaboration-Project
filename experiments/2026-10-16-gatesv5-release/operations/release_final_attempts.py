"""Preserve each operating attempt separately from planned-case gate results."""
from pathlib import Path
import json,hashlib,subprocess,collections
R=Path('/home/ugrp/ugrp-sim');OPS=R/'ops-reviews/gatesv5'
def read(p):
 if not p.exists():p=Path(str(p)+'.zst')
 if not p.exists():return None
 return json.loads(subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes())
cfg=read(OPS/'release-gate-config.json');selected={r['name'] for r in cfg['runs']};rows=[]
for run in sorted((R/'runs').glob('gv5-release-*')):
 raw=run/'raw';d=read(raw/'result.json') or {};saved=d.get('status');stop=read(run/'SUPERVISOR_STOP.json');meta=read(run/'RUN_META.json') or {}
 category='success' if saved=='complete' and d.get('release_success') else 'supervisor_stop' if saved=='interrupted' else 'HOST_ERROR' if saved in ('running','HOST_ERROR') or not saved else 'cap_end' if d.get('termination_category')=='cap_end' else 'failure'
 p=raw/'result.json';p=p if p.exists() else Path(str(p)+'.zst')
 row=dict(run=run.name,raw=str(raw),source_sha=d.get('source_sha',meta.get('sha')),saved_status=saved,category=category,outcome=d.get('release_outcome'),error_type=d.get('error_type'),selected_for_final_planned80=run.name in selected,stop=stop,result_storage=dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) if p.exists() else None,manifest=str(raw/'manifest.json') if (raw/'manifest.json').exists() else None,incomplete_sha_manifest=str(run/'INCOMPLETE_MANIFEST.json') if (run/'INCOMPLETE_MANIFEST.json').exists() else str(raw/'INCOMPLETE_MANIFEST.json') if (raw/'INCOMPLETE_MANIFEST.json').exists() else None)
 if saved=='running':row['classification_basis']='original status preserved; owned supervisor stopped and no worker remains; finalization interrupted in attempt2'
 rows.append(row)
value=dict(schema='ugrp.gatesv5.operating-attempts.v1',rows=rows,counts_by_source_and_category=dict(collections.Counter((r['source_sha'] or 'unknown')[:8]+':'+r['category'] for r in rows)),scope='All gv5-release operating attempts, including setup errors and invalidated host attempts. Distinct from one result per final planned80 case. Short runs and old source attempts never contribute to gate success.',reproduce='/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python '+str(Path(__file__).resolve()))
(OPS/'release-final-attempt-ledger.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(dict(attempts=len(rows),counts=value['counts_by_source_and_category'])))
