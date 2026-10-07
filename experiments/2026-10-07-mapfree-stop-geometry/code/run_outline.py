"""One frozen candidate, unchanged diagnostic gate before unopened oracle32."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
EXP=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'experiments/2026-10-07-mapfree-navigation-persistence/code')]
import run_persistent as old
from harness.public_navigation_outline import OutlineActor

SETTINGS={**old.SETTINGS,'navigation':'public_ros_v4','footprint_check':'nav2_edge_v1'}


def hashes():
    h=old.hashes()
    for p in [Path(__file__),ROOT/'harness/public_navigation_outline.py']:
        h[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    return h


def actor_factory(condition,static_grid=None,static_goal=None,*,navigation):
    # Runner-only dependency adapter: preserved episode calls its v3 factory;
    # explicit v4 runner substitutes the v4 actor, never admits v4 by default.
    if navigation!='public_ros_v3':raise ValueError('LEGACY_FACTORY_CONTRACT')
    return OutlineActor(condition,static_grid,static_goal,navigation='public_ros_v4')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--navigation',default='off',choices=['off','public_ros_v4'])
    p.add_argument('--cohort',choices=['diagnostic','confirmation'],required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--gate-development',type=Path)
    p.add_argument('--freeze',type=Path)
    args=p.parse_args()
    if args.navigation=='off':p.error('Default off: explicitly select public_ros_v4')
    current=hashes()
    if args.cohort=='confirmation':
        old.verify_development(args.gate_development,current)
        freeze=json.loads(args.freeze.read_text()) if args.freeze else {}
        if freeze.get('hashes')!=current or freeze.get('settings')!=SETTINGS or freeze.get('cohort')!=json.loads(old.MANIFEST.read_text()):
            raise ValueError('CONFIRMATION_REQUIRES_FROZEN_SOURCE_AND_SETTINGS')
    args.output.mkdir(parents=True,exist_ok=False)
    old.write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,settings=SETTINGS,cohort=args.cohort,stage='a',source_adapter='outline_only_v4',
        cohort_sha256=hashlib.sha256(old.MANIFEST.read_bytes()).hexdigest(),physics=0,model_calls=0))
    old.PublicActor=actor_factory
    old.SETTINGS=SETTINGS
    results=[]
    for i,s,seed in old.cohort(args.cohort):
        name=f's{i}-{s}-{seed}-static_map'
        row=old.episode(i,s,seed,args.cohort,'static_map','oracle',args.output/name)
        results.append(row);old.write(args.output/'results.json',results)
        print(name,row['status'],row['collisions'],row['navigation_events'],flush=True)
    if args.cohort=='diagnostic':
        passed=old.development_pass(results)
    else:
        passed=len(results)==32 and sum(r['status']=='B_confirmed' for r in results)>=30 and not any(r['status']=='B_false_confirmed' for r in results)
    old.write(args.output/'gate.json',dict(passed=passed,next_stages='allowed' if passed else 'BLOCKED_DO_NOT_RUN'))
    print('GATE',passed,flush=True)


if __name__=='__main__':main()
