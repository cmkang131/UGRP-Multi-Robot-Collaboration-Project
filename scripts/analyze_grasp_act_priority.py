"""Saved RGB-measurement geometry only; no World, renderer, or remote calls."""
import argparse
import json
import math
from copy import deepcopy
from pathlib import Path
from sim.grasp_act_priority import (PARK_Y, beam_xy, world_xy, checked_path,
                                    reserved_constraints)
from sim.grasp_act_goal_set import geometry
from sim.grasp_act_visible_route import constraints


def segment_distance(point, a, b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0.,min(1.,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/max(1e-20,dx*dx+dy*dy)))
    return math.dist(point,(a[0]+t*dx,a[1]+t*dy))


def path_clearance(path, point):
    return min(segment_distance(point,a,b) for a,b in zip(path,path[1:]))


def witness(case):
    """Existence of a serial path at one frozen visible snapshot, not rollout.

    Hypothetical parking/final poses are used ONLY by this static evaluator.
    The runtime never receives the partner's route or these synthetic poses.
    """
    w=deepcopy(case['world']);bounds=(-20,20,-20,20)
    teal=next(r for r,e in case['roles'].items() if e=='teal')
    blue=next(r for r,e in case['roles'].items() if e=='blue')
    starts={r:list(w['robots'][r]['pose'][:2]) for r in (teal,blue)}
    park=world_xy(w,(beam_xy(w,starts[blue])[0],PARK_Y))
    goals={r:geometry(w,r,case['roles'][r],(0.,.203))[3] for r in (teal,blue)}
    original={r:checked_path(starts[r],goals[r],bounds,constraints(w,r,True)) for r in (teal,blue)}
    parking=checked_path(starts[blue],park,bounds,constraints(w,blue,True))
    w['robots'][blue]['pose'][:2]=park
    first=checked_path(starts[teal],goals[teal],bounds,reserved_constraints(w,teal,'teal',True))
    w['robots'][teal]['pose'][:2]=goals[teal]
    second=checked_path(park,goals[blue],bounds,reserved_constraints(w,blue,'blue',True))
    paths={'blue_parks':parking,'teal_approaches':first,'blue_approaches':second}
    clearances=({ 'parking_to_stationary_teal':path_clearance(parking,starts[teal]),
                  'teal_to_parked_blue':path_clearance(first,park),
                  'blue_to_ready_teal':path_clearance(second,goals[teal]),
                  'teal_to_reserved_blue_goal':path_clearance(first,goals[blue])}
                if all(len(p)>=2 for p in paths.values()) else {})
    return {'episode':case['episode'],'snapshot_elapsed_s':case['elapsed_s'],
            'input_observer':case['rid'],'starts':starts,'goals':goals,'parking_point':park,
            'paths':paths,'original_paths':original,
            'clearance_m':clearances,'required_peer_clearance_m':.34,
            'exists':bool(clearances) and min(clearances.values())>=.34,
            'scope':'frozen observed geometry, ideal positions at stage boundaries; not new viewpoints, odometry or physical success'}


def main():
    import hashlib
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path,default=Path('tests/fixtures/grasp_act_search10_peer.json'))
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    data=json.loads(a.fixture.read_text());proof=[witness(c) for c in data['cases']]
    for row in proof:row['baseline_gate_index']={11:8,12:14,14:32}[row['episode']]
    result={'schema':'ugrp.grasp_act.search11_geometry.v1','fixture':str(a.fixture),
        'fixture_sha256':hashlib.sha256(a.fixture.read_bytes()).hexdigest(),'fixture_source_sha':data['source_sha'],
        'witnesses':proof,'witness_pass_n':sum(w['exists'] for w in proof),'witness_N':len(proof),
        'scope':'three saved visible snapshots from 793865d2 reproductions; ideal frozen geometry and sequential stationary-peer clearance only; no claim of new views, observed runtime clearance, or physical grasp',
        'additional_rejections_of_original_gate40':{'n':0,'N':40,'rate':0.,
            'reason':'no proof any of the six starts is unreachable; no additional sampler exclusion'},
        'failure_decisions':[
            {'index':3,'candidate':'reproduce; not proven graspable','exclude':False,'reason':'cargo blocks nominal stance in saved view; prior axial IK/path witness disproves blanket geometric impossibility, but that recovery is OFF here'},
            {'index':7,'candidate':'reproduce; search remains baseline','exclude':False,'reason':'lost view is not geometric infeasibility; waiting changes timing/views, unmeasured'},
            {'index':8,'candidate':'serial route witness; physical unverified','exclude':False,'reason':'peer occupancy, movable obstacle; witness uses reproduction11'},
            {'index':14,'candidate':'serial route witness; physical unverified','exclude':False,'reason':'peer occupancy, movable obstacle; witness uses reproduction12'},
            {'index':17,'candidate':'reproduce; not proven graspable','exclude':False,'reason':'observed wall blocks nominal stance; prior198mm IK/path witness exists, baseline nominal handoff retained; peer interaction also visible'},
            {'index':32,'candidate':'serial route witness; physical unverified','exclude':False,'reason':'peer occupancy, movable obstacle; witness uses reproduction14'}]}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{k:w[k] for k in ('baseline_gate_index','exists','clearance_m')} for w in proof]))


if __name__=='__main__':main()
