"""Opt-in setup-only v2 gate: keep the authored v7 certified-stance support."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from scripts.prepare_beampair1 import prepare
from scripts.run_beampair1 import dependency_modules

MODE='beampair_gate_valid_v2'
ROOT=Path(__file__).resolve().parents[1]
EXP=ROOT/'experiments/2026-10-16-beampair6'


def distribution_k(report):
    if report['branch']!='A' or report['v7_unique_beams']!=7:
        raise ValueError('complete v7 branch A census required')
    values=[v['free_goal_N'] for row in report['rows'] if row['population']=='v7'
            for v in row['ends'].values()]
    if not values or min(values)<=0:raise ValueError('v7 contains an infeasible end')
    # k=91 is the observed minimum (percentile 0), not a tuned success target.
    # All 7 authored beams x 2 ends x 3 seeds have 91, and s2's fixed-event
    # phase has the same counts. See beampair6/placement-validity.{json,csv}.
    return min(values)


def validity_checker(family,body_clearance,margin,k):
    """Authored setup geometry only. Never called by any teacher/control path."""
    import math
    def check(pose,static):
        rects=[(o['id'],(*o['center_m'],*o['half_extents_m'],o.get('yaw_rad',0.))) for o in static['obstacles']]
        ends={}
        for end,d in (('teal',-.27),('blue',.27)):
            x,y=pose[0]+d*math.cos(pose[2]),pose[1]+d*math.sin(pose[2]);free=0;blocks=[]
            for offset,distance,_,certificate in family:
                yaw=pose[2]+(math.pi if end=='blue' else 0.)+offset
                goal=(x-distance*math.cos(yaw),y-distance*math.sin(yaw),yaw)
                gaps=[(name,body_clearance(goal,[],[rect])) for name,rect in rects]
                name,gap=min(gaps,key=lambda v:v[1])
                if gap>=margin:free+=1
                else:blocks.append((name,gap))
            names=Counter(name for name,gap in blocks)
            ends[end]=dict(certified_N=len(family),free_goal_N=free,
                blocked_object=names.most_common(1)[0][0] if names else 'none:all_certified_stances_clear',
                min_gap_m=min((gap for name,gap in blocks),default=None),
                blocker_occurrences=dict(names))
        return dict(k=k,accepted=all(v['free_goal_N']>=k for v in ends.values()),ends=ends)
    return check


def generate(seed,output,dependency,mode):
    output.mkdir(parents=True,exist_ok=True)
    if any((output/n).exists() for n in ('gate-plan.json','setup-funnel.json')):
        raise ValueError('new output directory required; previous evidence is immutable')
    if mode=='off':
        return prepare(seed,output=output)
    if mode!=MODE:raise ValueError('unknown setup validity mode')
    report_path=EXP/'placement-validity.json';report=json.loads(report_path.read_bytes());k=distribution_k(report)
    with dependency_modules(dependency):
        from sim.grasp_act_search24 import reachability_map
        from sim.grasp_act_search18 import body_clearance
        from sim.grasp_act_search21 import FRESH_MARGIN_M
        from sim.zone_cargo import kind
        family=reachability_map(kind('long_beam').grasps[0].grip_xyz[2])
        check=validity_checker(family,body_clearance,FRESH_MARGIN_M,k)
    prepare(seed,output=output,validity=check,version='beampair6')
    for name in ('gate-plan.json','setup-funnel.json'):
        path=output/name;value=json.loads(path.read_bytes())
        value.update(setup_validity=MODE,default='off',k=k,k_basis='v7 initial and authored fixed-event end count minimum',
            census_sha256=hashlib.sha256(report_path.read_bytes()).hexdigest(),dependency_sha=report['dependency_sha'],
            reproduce=f'python -m scripts.prepare_beampair6 --seed {seed} --output {output} --dependency-root {dependency} --setup-validity {MODE}',
            scope='setup-only; positions excluded from all action selection; not physical success')
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,default=8318700)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--dependency-root',type=Path,required=True)
    p.add_argument('--setup-validity',choices=['off',MODE],default='off')
    a=p.parse_args();generate(a.seed,a.output,a.dependency_root,a.setup_validity)
