"""Single registered v5 run; original development gate before unopened32."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-stop-geometry/code'),
              str(ROOT/'experiments/2026-10-07-mapfree-navigation-persistence/code')]
import run_outline as v4
old=v4.old
from harness.public_navigation_resolution import ResolutionActor,authored_inputs,RESOLUTION

SETTINGS={**v4.SETTINGS,'navigation':'public_ros_v5','resolution_m':RESOLUTION,
          'static_raster_half_cell_margin_m':RESOLUTION/2}


def hashes():
    out=v4.hashes()
    for p in [Path(__file__),ROOT/'harness/public_navigation_resolution.py']:
        out[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def actor_factory(condition,static_grid=None,static_goal=None,*,navigation):
    if navigation!='public_ros_v3':raise ValueError('LEGACY_FACTORY_CONTRACT')
    return ResolutionActor(condition,static_grid,static_goal,navigation='public_ros_v5')


def serialized_grid(value):
    # Frozen runner writes resolution_m=.1 literally. Correct the metadata BEFORE
    # the first write, never modify a saved raw record or the grid's cell values.
    if set(value)!={'resolution_m','cells'}:raise ValueError('GRID_SERIALIZATION_SCHEMA_CHANGED')
    return {**value,'resolution_m':RESOLUTION}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--navigation',default='off',choices=['off','public_ros_v5'])
    p.add_argument('--cohort',required=True,choices=['diagnostic','confirmation'])
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gate-development',type=Path)
    p.add_argument('--freeze',type=Path)
    args=p.parse_args()
    if args.navigation=='off':p.error('Default off: explicitly select public_ros_v5')
    current=hashes()
    if args.cohort=='confirmation':
        old.verify_development(args.gate_development,current)
        f=json.loads(args.freeze.read_text()) if args.freeze else {}
        if f.get('hashes')!=current or f.get('settings')!=SETTINGS or f.get('cohort')!=json.loads(old.MANIFEST.read_text()):
            raise ValueError('CONFIRMATION_REQUIRES_FROZEN_SOURCE_AND_SETTINGS')
    args.output.mkdir(parents=True,exist_ok=False)
    old.write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,settings=SETTINGS,cohort=args.cohort,stage='a',
        cohort_sha256=hashlib.sha256(old.MANIFEST.read_bytes()).hexdigest(),physics=0,model_calls=0,
        source_adapter='nav2_bringup_resolution_005_v5'))
    old.PublicActor=actor_factory
    old.static_inputs=lambda world:authored_inputs(world.static,world.start)
    old.SETTINGS=SETTINGS
    write=old.write
    def record(path,value):
        write(path,serialized_grid(value) if path.name=='own_grid.json' else value)
    old.write=record
    results=[]
    for i,start,seed in old.cohort(args.cohort):
        name=f's{i}-{start}-{seed}-static_map'
        r=old.episode(i,start,seed,args.cohort,'static_map','oracle',args.output/name)
        results.append(r)
        write(args.output/'results.json',results)
        print(name,r['status'],'contacts',r['collisions'],'time',r['time_s'],flush=True)
    passed=(old.development_pass(results) if args.cohort=='diagnostic' else len(results)==32
            and sum(r['status']=='B_confirmed' for r in results)>=30
            and not any(r['status']=='B_false_confirmed' for r in results))
    write(args.output/'gate.json',dict(passed=passed,next_stages='allowed' if passed else 'BLOCKED_DO_NOT_RUN'))
    assert 'mujoco' not in sys.modules
    print('GATE',passed,flush=True)


if __name__=='__main__':main()
