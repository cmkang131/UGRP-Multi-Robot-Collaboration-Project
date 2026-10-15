from pathlib import Path
import json,collections,hashlib
root=Path('/home/ugrp/ugrp-sim');j=json.loads((root/'outputs/reloc14/round3-full.json').read_text());rows=[]
for r in j['runs']:
 if 'selfmap' not in r['run']:continue
 rows.append({k:r[k] for k in ['run','source_sha','funnel','registered_errors','drive_errors','termination','registration_frame_funnel','known_mode_measurement_funnel']})
for r in rows:
 d=r['registered_errors'];print(r['run'],r['funnel'],str(d)[:600])
report=dict(schema='ugrp.reloc15.rejection_table.v1',stage='before_control_changes',analysis_host='gcp1',source='reloc14/round3-full.json',source_sha256=hashlib.sha256((root/'outputs/reloc14/round3-full.json').read_bytes()).hexdigest(),selfmap=rows,carry_yaw='carry-yaw.json',ready=False,reproduce='python3 /tmp/reloc15-baseline.py')
(root/'outputs/reloc15/rejection-table.json').write_text(json.dumps(report,indent=2)+'\n')
