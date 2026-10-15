import json
from pathlib import Path
from replay import replay, RAW
out=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate15-8007db00')
rs=[]
for p in sorted(RAW.glob('crate-*-8007db00')):
 r=replay(p.name);r.pop('teachers');rs.append(r)
 (out/'baseline.json').write_text(json.dumps(rs,indent=2)+'\n')
 print(r,flush=True)
