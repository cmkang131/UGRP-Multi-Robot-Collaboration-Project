"""Setup-only S2 dock sampling; no path, B visibility, or task outcome selection."""
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-explore/code')]
from grid_world import load_layout
from diagnose_environment import rectangle_contacts
from run_grid import static_inputs
from harness.public_navigation.costmap import from_grid
from sim.zone_model_conventions import spawn_layout
from types import SimpleNamespace


def generate():
    rows, rejected = [], []
    for index in range(1,9):
        _, static, rects, sources = load_layout(index)
        spec = spawn_layout(static)
        candidates = list(spec['spawn_rows_y'])
        random.Random(5700+index).shuffle(candidates)
        accepted = []
        for y in candidates:
            dock = [spec['spawn_x'],y,0.]
            for step in range(6):
                pose = [spec['spawn_x']+.1*step,y,0.]
                contacts = rectangle_contacts(pose,rects,static['bounds_m'],half=(.14,.12))
                grid,_ = static_inputs(SimpleNamespace(static=static,start=pose))
                hits={c for c,v in grid.odds.items() if v>0}
                cm = from_grid(grid,[0.,0.,0.],static_hits=hits)
                # Costmap footprint clearing must not hide a static wall at the spawn.
                for cell in hits:
                    x,z=cm.world_to_map(grid.point(cell))
                    cm.raw[z,x]=254
                cm.costs=cm.inflate()
                ij = cm.world_to_map([0,0])
                valid = not contacts and cm.costs[ij[1],ij[0]]<253 and cm.pose_clear([0,0,0])
                if not valid:
                    rejected.append(dict(scenario=index,pose=pose,contacts=contacts,reason='footprint_or_inflation'))
                else:
                    accepted.append((pose,dock,.1*step))
                    break
        if len(accepted)<2:
            raise ValueError(f'HOST_SETUP_ERROR_s{index}_insufficient_valid_docks')
        for name,(pose,dock,shift) in zip(('I','J'),accepted[:2]):
            for seed in (5701,5702):
                rows.append(dict(scenario=index,start=name,seed=seed,pose=pose,dock_pose=dock,departure_shift_m=shift,sources=sources))
    paths=['sim/zone_model_conventions.py','sim/zone_start_dock.py','sim/zone_arena.py',str(Path(__file__).relative_to(ROOT))]
    return dict(rule='authored_S2_dock_seed5700_plus_scenario_valid_rectangle_and_costmap',
        seen_confirmation_seeds=[2701,2702,3701,3702,4701,4702],rows=rows,rejected=rejected,
        hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths})


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    value=generate()
    with a.output.open('x') as f:
        json.dump(value,f,indent=2)
        f.write('\n')
