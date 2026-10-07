"""Identical saved K/L observations/candidate targets; no old mission reruns."""
from collections import Counter
import subprocess
import numpy as np
from scipy.ndimage import label
from unknown_common import *
from harness.public_navigation.costmap import from_grid
from harness.public_navigation_outline import OutlineCostmap


def prepare(actor, record):
    pose = np.asarray(record['pose_odom'])
    actor.odom.correct(pose,np.zeros((3,3)))
    actor.t = record['t']
    actor.receive(record['observation'],[])
    if isinstance(actor,UnknownActor):cm = actor.make_costmap()
    else:
        base = from_grid(actor.grid,pose,actor.latest,actor.static_hits)
        cm = OutlineCostmap(base.raw,base.origin,base.resolution)
    return cm,pose


def diagnose(actor, cm, pose, candidates):
    labels,n = label(cm.costs < 253)
    start = cm.world_to_map(pose[:2])
    component = labels[start[1],start[0]]
    connected = (labels == component) if component else np.zeros_like(labels,dtype=bool)
    counts = Counter(candidates=0,connected_candidates=0,valid=0,native_empty=0,connector_rejected=0)
    for point in candidates:
        goal = cm.world_to_map(point)
        counts['candidates'] += 1
        counts['connected_candidates'] += int(connected[goal[1],goal[0]])
        route = actor.navigator.core.plan(cm.costs,start,goal)
        if not len(route):counts['native_empty'] += 1
        elif not cm.sweep_clear(pose,[*cm.map_to_world(route)[0],pose[2]]):counts['connector_rejected'] += 1
        else:counts['valid'] += 1
    return dict(robot_component_cells=int(connected.sum()),navigable_components=int(n),
                free_cells=int((cm.raw==0).sum()),**counts)


def main():
    out = RAW/'development'
    current = hashes()
    out.mkdir(parents=True,exist_ok=False)
    write(out/'source.json',dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        hashes=current,physics=0,model_calls=0,load_average=__import__('os').getloadavg()))
    manifest = read(v6.prior.EXP/'cohort.json')
    expected = read(v6.EXP/'results/development.json')
    results = []
    for row,old in zip(manifest['rows'],expected):
        name = f"s{row['scenario']}-{row['start']}-{row['seed']}-own_frontier"
        assert old['case'] == name
        record = lines(v6.PRIOR_RAW/name/'actor.jsonl')[0]
        world = v6.RayOracleWorld(row['scenario'],row['pose'],row['seed'],'confirmation')
        world.advance(dict(t=0.,kind='stop'),2.)
        observation,patches,truth = world.observe(0)
        assert {k:v for k,v in observation.items() if not k.endswith('_origins_xy')} == record['observation']
        assert not patches and not record['patches']
        record = {**record,'observation':observation}
        before_actor = v6.RaytraceActor('own_frontier',navigation='public_ros_v6')
        before_cm,pose = prepare(before_actor,record)
        yy,xx = np.nonzero(before_cm.costs<253)
        points = before_cm.map_to_world(np.column_stack([xx,yy]))
        frontiers = before_actor.navigator.core.frontiers(before_cm.raw,before_cm.origin,before_cm.resolution,pose[:2])
        candidates = [p for f in frontiers for p in points[np.linalg.norm(points-f[:2],axis=1)<=.5]]
        before = diagnose(before_actor,before_cm,pose,candidates)
        for key,value in before.items():assert value == old['after'][key], (name,key,value,old['after'][key])
        after_actor = UnknownActor('own_frontier',navigation='public_ros_v7')
        after_cm,pose = prepare(after_actor,record)
        after = diagnose(after_actor,after_cm,pose,candidates)
        plan = after_actor.plan()
        command = after_actor.command(plan)
        results.append(dict(case=name,before=before,after=after,endpoint_bytes_equal=True,
            identical_candidate_targets=True,selected_plan=plan,first_command=command,
            footprint_support_cells=len(after_actor.footprint_support),events=after_actor.navigator.events))
        write(out/'results.json',results)
        print(name,'valid',before['valid'],'->',after['valid'],'component',after['robot_component_cells'],flush=True)
    gate = dict(n=len(results),passed=len(results)==32 and all(r['after']['robot_component_cells']>36 and r['after']['valid']>=1 for r in results))
    write(out/'gate.json',gate)
    assert hashes()==current and 'mujoco' not in sys.modules
    print(json.dumps(gate),flush=True)


if __name__=='__main__':main()
