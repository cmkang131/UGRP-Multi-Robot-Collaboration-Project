"""Evaluation-only GT-pose bridge around the frozen v5 paired 2D runner.

No navigator, environment, sensor or recovery implementation changes. Oracle
pose is intentionally privileged, explicitly requested, and not a real actor.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

EXP=Path(__file__).resolve().parents[1]
ROOT=EXP.parents[1]
sys.path[:0]=[str(ROOT),str(Path(__file__).parent),str(ROOT/'experiments/2026-10-07-mapfree-s4-final/code')]
import run_resolution as v5
import register_cohort as registration
from harness.public_navigation_resolution import ResolutionActor,authored_inputs
from harness.self_odom_grid import transform
from grid_world import inverse

PRIOR=Path('/Users/changmin/projects/ugrp/outputs/mapfree-s4-final-v1/confirmation-v5')
SETTINGS=v5.SETTINGS
CRITERIA=dict(total_pairs=32,B_fraction=.8,false_B=0,distance_ratio=2.,time_ratio=2.,
              coverage_median=.4,collisions=0,wrong_doors=0,false_passage=0,min_door_attempts=1)


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):v5.old.write(p,value)


def verify_frozen():
    frozen=read(v5.EXP/'freeze.json')
    current=v5.hashes()
    if frozen['hashes']!=current or frozen['settings']!=SETTINGS:
        raise ValueError('V5_FROZEN_SOURCE_OR_SETTINGS_CHANGED')
    return current


def hashes():
    out=verify_frozen()
    for p in [EXP/'README.md',EXP/'cohort.json',Path(__file__),Path(registration.__file__)]:
        out[str(p.relative_to(ROOT))]=sha(p)
    return out


def verify_prior():
    # Checks all original 32 episode result.json against the aggregate, not just pass=true.
    v5.old.verify_gate(PRIOR,'a',verify_frozen())
    return dict(path=str(PRIOR),source_sha256=sha(PRIOR/'source.json'),results_sha256=sha(PRIOR/'results.json'),
                true_B=sum(r['status']=='B_confirmed' for r in read(PRIOR/'results.json')))


class OraclePoseBridge:
    """Only an explicit local pose sample may enter; no geometry/goal fields."""
    def __init__(self,odometry,pose_reader):
        self.odometry,self.pose_reader=odometry,pose_reader
        self.sync()

    def sync(self):
        pose=np.asarray(self.pose_reader(),float)
        if pose.shape!=(3,) or not np.isfinite(pose).all():
            raise ValueError('ORACLE_POSE_ONLY_3_FINITE_VALUES')
        self.odometry.correct(pose,np.zeros((3,3)))

    def command(self,row):
        self.odometry.command(row)
        self.sync()

    def advance(self,t):
        self.odometry.advance(t)
        self.sync()
        return self.pose

    def __getattr__(self,key):return getattr(self.odometry,key)


def summary(rows,boundary):
    expected={(f's{i}',s,seed) for i in range(1,9) for s in ('K','L') for seed in (6701,6702)}
    groups={c:[r for r in rows if r['condition']==c] for c in ('static_map','own_frontier')}
    complete=all(len(g)==32 and {(r['scenario'],r['start'],r['seed']) for r in g}==expected for g in groups.values())
    aggregates={}
    for condition,g in groups.items():
        success=[r for r in g if r['status']=='B_confirmed']
        med=lambda values:float(np.median(values)) if values else None
        aggregates[condition]=dict(n=len(g),true_B=len(success),false_B=sum(r['status']=='B_false_confirmed' for r in g),
            coverage_median=med([r['coverage'] for r in g]),first_B_time_s=med([r['first_B']['time_s'] for r in success]),
            first_B_distance_m=med([r['first_B']['distance_m'] for r in success]),
            end_time_s=med([r['time_s'] for r in g]),end_distance_m=med([r['distance_m'] for r in g]),
            collisions=sum(r['collisions'] for r in g),wrong_doors=sum(r['wrong_door_attempts'] for r in g),
            false_passage=sum(r['false_candidate_passage_attempts'] for r in g),door_attempts=sum(r['door_attempts'] for r in g),
            statuses=dict(Counter(r['status'] for r in g)),
            max_end_pose_error_m=max((r['end_position_error_m'] for r in g),default=None))
    pairs={}
    for r in rows:pairs.setdefault((r['scenario'],r['start'],r['seed']),{})[r['condition']]=r
    d,t=[],[]
    for pair in pairs.values():
        if len(pair)==2 and all(r['status']=='B_confirmed' for r in pair.values()):
            a,b=pair['own_frontier']['first_B'],pair['static_map']['first_B']
            d.append(a['distance_m']/max(1e-9,b['distance_m']))
            t.append(a['time_s']/b['time_s'])
    paired=dict(common_successes=len(d),distance_ratio=float(np.median(d)) if d else None,
                time_ratio=float(np.median(t)) if t else None)
    own=aggregates['own_frontier']
    checks=dict(boundary=bool(boundary and complete),B_confirmation=own['true_B']/32>=.8 and own['false_B']==0,
        efficiency=bool(d and paired['distance_ratio']<=2 and paired['time_ratio']<=2),
        coverage=own['coverage_median'] is not None and own['coverage_median']>=.4,
        safety=own['collisions']==0 and own['wrong_doors']==0 and own['false_passage']==0 and own['door_attempts']>=1)
    return dict(conditions=aggregates,paired=paired,checks=checks,criteria_passed=sum(checks.values()),
                passed=all(checks.values()),criteria=CRITERIA,complete=complete,
                pose_condition='oracle_gt_pose_v1',noisy_runs=0,physics=0,model_calls=0)


def configure(manifest):
    old=v5.old
    OriginalWorld=old.RectangleOracleWorld
    active=[]
    class World(OriginalWorld):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            active[:]=[self]
    def actor_factory(condition,static_grid=None,static_goal=None,*,navigation):
        assert navigation=='public_ros_v3'
        if condition=='own_frontier':
            assert static_grid is None and static_goal is None
        actor=ResolutionActor(condition,static_grid,static_goal,navigation='public_ros_v5')
        world=active[0]
        # The reader returns ONLY start-relative pose. No hidden map/goal/labels.
        def sample():
            xy=inverse([world.pose[:2]],world.start)[0]
            return [*xy,world.pose[2]-world.start[2]]
        actor.odom=OraclePoseBridge(actor.odom,sample)
        if condition=='own_frontier':
            assert not actor.grid.odds and not actor.static_hits and actor.static_goal is None
        return actor
    old.RectangleOracleWorld=World
    old.PublicActor=actor_factory
    starts={(r['scenario'],r['start'],r['seed']):r['pose'] for r in manifest['rows']}
    old.start_pose=lambda i,start,seed:starts[(i,start,seed)]
    old.static_inputs=lambda world:authored_inputs(world.static,world.start)
    old.SETTINGS=SETTINGS
    original_write=old.write
    def record(path,value):
        original_write(path,v5.serialized_grid(value) if path.name=='own_grid.json' else value)
    old.write=record
    return old


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--navigation',choices=['off','public_ros_v5'],default='off')
    args=p.parse_args()
    if args.navigation=='off':p.error('Explicit frozen public_ros_v5 required')
    current=hashes()
    frozen=read(EXP/'freeze.json')
    if frozen['hashes']!=current or frozen['settings']!=SETTINGS or frozen['criteria']!=CRITERIA:
        raise ValueError('EXACT_PREREGISTERED_FREEZE_REQUIRED')
    prior=verify_prior()
    manifest=read(EXP/'cohort.json')
    assert manifest==registration.generate()
    args.output.mkdir(parents=True,exist_ok=False)
    native=v5.old.build()
    write(args.output/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,settings=SETTINGS,criteria=CRITERIA,prior_gate=prior,cohort_sha256=sha(EXP/'cohort.json'),
        pose_condition='oracle_gt_pose_v1',stage='b',cohort='confirmation',physics=0,model_calls=0,
        native_sha256=sha(native),python=sys.version))
    runner=configure(manifest)
    rows=[]
    for entry in manifest['rows']:
        for mode in ('static_map','own_frontier'):
            i,start,seed=(entry[k] for k in ('scenario','start','seed'))
            name=f's{i}-{start}-{seed}-{mode}'
            row=runner.episode(i,start,seed,'confirmation',mode,'oracle',args.output/name)
            rows.append(row)
            write(args.output/'results.json',rows)
            print(name,row['status'],'coverage',round(row['coverage'],4),'contacts',row['collisions'],
                  'time',round(row['time_s'],1),flush=True)
    assert hashes()==current and 'mujoco' not in sys.modules
    result=summary(rows,boundary=True)
    write(args.output/'gate.json',result)
    print('FRONTIER_GATE',result['passed'],result['criteria_passed'],'of 5',flush=True)


if __name__=='__main__':main()
