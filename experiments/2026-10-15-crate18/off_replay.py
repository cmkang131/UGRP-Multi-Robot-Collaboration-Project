"""Crate17 exact issued-command regression, no physics/render."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'experiments/2026-10-15-crate15'))
from replay import replay
out=[]
for candidate,motion in [('full','crate_motion_v17'),('no_clearance','crate_motion_v17_no_clearance')]:
    for seed in [77990,79314,79317]:
        r=replay(f'crate17-{candidate}-reproduction-{seed}-4eb7d472',options={'crate_motion':motion,'crate18':'off'})
        r.pop('teachers');out.append(r)
        print(json.dumps({k:r[k] for k in ('matched','total','mismatch') if k in r}),flush=True)
        assert r['matched']==r['total']
Path('experiments/2026-10-15-crate18/off-replay.json').write_text(json.dumps(out,indent=2)+'\n')
