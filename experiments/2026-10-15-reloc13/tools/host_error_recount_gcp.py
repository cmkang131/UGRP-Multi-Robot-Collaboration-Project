from pathlib import Path
from scripts.analyze_reloc11_selfmap import obj
import json,hashlib
out=[]
for p in sorted(Path('/home/ugrp/ugrp-sim/runs').glob('reloc12-r2-ransac-texture-*-ff1ccf27')):
 es=obj(p/'raw/executor-events.json');events=[e for e in es if e['reason'] in ['selfmap4_relocalization','selfmap4_relocalization_exhausted']]
 out.append(dict(run=p.name,events=events,classification='code recovery attempt limit, not external host failure',originals=[str(p/'raw/executor-events.json'),str(p/'raw/result.json')]))
Path('/tmp/reloc13-baseline-host-errors.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
