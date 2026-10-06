"""Versioned evaluator/algorithm ablations and preregistered fresh cohorts."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import run_grid as old
from grid_world_v2 import RectangleWorld, RectangleOracleWorld

NEW_STARTS = {'E':[-.55,-1.65,math.pi/4], 'F':[1.35,-.65,-math.pi/2]}
COHORTS = {'seen':(['B','D'],[2701,2702],'confirmation'),
           'development':(['A','C'],[1701],'development'),
           'confirmation':(['E','F'],[3701,3702],'confirmation')}


def hashes():
    h = old.source_hashes()
    for p in sorted((old.ROOT/'harness').glob('own_map_navigation*.py')):
        h[str(p.relative_to(old.ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return h


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cohort',choices=COHORTS,required=True)
    parser.add_argument('--sensing',choices=['noisy','oracle'],required=True)
    parser.add_argument('--algorithm',choices=['v1','v2'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--freeze',type=Path)
    args = parser.parse_args()
    if args.cohort=='confirmation':
        frozen = json.loads(args.freeze.read_text()) if args.freeze else {}
        if frozen.get('hashes')!=hashes() or frozen.get('starts')!=NEW_STARTS:
            raise ValueError('FRESH_CONFIRMATION_REQUIRES_FROZEN_SOURCE')
    args.output.mkdir(parents=True,exist_ok=False)
    old.write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=hashes(),cohort=args.cohort,sensing=args.sensing,algorithm=args.algorithm,
        environment='rect_footprint_v2',starts=NEW_STARTS,cohorts=COHORTS))
    old.GridWorld = RectangleWorld if args.sensing=='noisy' else RectangleOracleWorld
    if args.algorithm=='v2':
        from navigation_actor_v2 import ActorV2
        old.Actor = ActorV2
    old.STARTS.update(NEW_STARTS)
    starts,seeds,split = COHORTS[args.cohort]
    results = []
    for i in range(1,9):
        for start in starts:
            for seed in seeds:
                for mode in ('static_map','own_frontier'):
                    name = f's{i}-{start}-{seed}-{mode}'
                    result = old.episode(i,start,seed,split,mode,args.output/name)
                    result.update(cohort=args.cohort,sensing=args.sensing,algorithm=args.algorithm,environment='rect_footprint_v2')
                    old.write(args.output/name/'result.json',result)
                    results.append(result)
                    print(name,result['status'],round(result['coverage'],3),flush=True)
    old.write(args.output/'results.json',results)


if __name__=='__main__':
    main()
