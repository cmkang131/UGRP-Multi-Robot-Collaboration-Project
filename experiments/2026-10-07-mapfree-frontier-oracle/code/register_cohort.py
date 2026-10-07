"""Pre-registered S2 dock sampling. No goal visibility/path/outcome selection."""
import hashlib
import json
from pathlib import Path
import random
import sys
import numpy as np

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-explore/code')]
from grid_world import load_layout
from diagnose_environment import rectangle_contacts
from harness.public_navigation_resolution import authored_inputs
from harness.public_navigation.costmap import from_grid
from sim.zone_model_conventions import spawn_layout
from run_grid import STARTS
from run_revision import NEW_STARTS


def generate():
    rows,rejected=[],[]
    prior=json.loads((ROOT/'experiments/2026-10-07-mapfree-navigation-recovery/cohort.json').read_text())
    # G/H from the pinned public-navigation cohort; A-F from their original modules.
    legacy=[*STARTS.values(),*NEW_STARTS.values(),[-.45,-2.30,np.pi/6],[1.20,.65,-np.pi/3]]
    for index in range(1,9):
        _,static,rects,sources=load_layout(index)
        spec=spawn_layout(static)
        ys=list(spec['spawn_rows_y'])
        random.Random(6700+index).shuffle(ys)
        accepted=[]
        for y in ys:
            dock=[spec['spawn_x'],y,0.]
            for step in range(6):
                shift=.05+.10*step
                pose=[spec['spawn_x']+shift,y,0.]
                contacts=rectangle_contacts(pose,rects,static['bounds_m'],half=(.14,.12))
                grid,_=authored_inputs(static,np.asarray(pose))
                hits={cell for cell,v in grid.odds.items() if v>0}
                cm=from_grid(grid,[0.,0.,0.],static_hits=hits)
                for cell in hits:
                    x,z=cm.world_to_map(grid.point(cell))
                    cm.raw[z,x]=254
                cm.costs=cm.inflate()
                ij=cm.world_to_map([0.,0.])
                valid=not contacts and cm.costs[ij[1],ij[0]]<253 and cm.pose_clear([0.,0.,0.])
                if not valid:
                    rejected.append(dict(scenario=index,pose=pose,contacts=contacts,reason='footprint_or_inflation'))
                else:
                    accepted.append((pose,dock,shift))
                    break
        if len(accepted)<2:
            raise ValueError(f'HOST_SETUP_ERROR_s{index}_insufficient_valid_docks')
        for start,(pose,dock,shift) in zip(('K','L'),accepted[:2]):
            # This is a rejection assertion, never a result-dependent resampling rule.
            assert not any(r['scenario']==index and np.allclose(pose,r['pose'],atol=1e-12,rtol=0) for r in prior['rows'])
            assert not any(np.allclose(pose,p,atol=1e-12,rtol=0) for p in legacy)
            for seed in (6701,6702):
                rows.append(dict(scenario=index,start=start,seed=seed,pose=pose,dock_pose=dock,
                                 departure_shift_m=shift,sources=sources))
    paths=['sim/zone_model_conventions.py','sim/zone_start_dock.py','sim/zone_arena.py',
           'harness/public_navigation_resolution.py',str(Path(__file__).relative_to(ROOT))]
    return dict(rule='S2_dock_shuffle6700_plus_scenario_departure005_plus010k_first2_valid',
        rows=rows,rejected=rejected,seen_confirmation_seeds=[2701,2702,3701,3702,4701,4702,5701,5702],
        source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})


if __name__=='__main__':
    with (EXP/'cohort.json').open('x') as f:
        json.dump(generate(),f,indent=2)
        f.write('\n')
