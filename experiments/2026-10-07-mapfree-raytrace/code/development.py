"""Compare saved first observations only, without replaying any old mission."""
from collections import Counter
import subprocess
import numpy as np
from scipy.ndimage import label
from common import *
from harness.public_navigation_resolution import ResolutionActor
from harness.public_navigation.costmap import from_grid
from harness.public_navigation_outline import OutlineCostmap


def diagnose(actor, record):
    pose = np.asarray(record['pose_odom'])
    actor.odom.correct(pose, np.zeros((3,3)))
    actor.t = record['t']
    actor.receive(record['observation'], [])
    original = from_grid(actor.grid, pose, actor.latest, actor.static_hits)
    cm = OutlineCostmap(original.raw, original.origin, original.resolution)
    labels, n = label(cm.costs < 253)
    start = cm.world_to_map(pose[:2])
    connected = labels == labels[start[1], start[0]]
    yy, xx = np.nonzero(cm.costs < 253)
    cells = np.column_stack([xx, yy])
    points = cm.map_to_world(cells)
    frontiers = actor.navigator.core.frontiers(cm.raw, cm.origin, cm.resolution, pose[:2])
    counts = Counter(candidates=0, connected_candidates=0, valid=0, native_empty=0, connector_rejected=0)
    for f in frontiers:
        for x,y in cells[np.linalg.norm(points-f[:2],axis=1)<=.5]:
            counts['candidates'] += 1
            counts['connected_candidates'] += int(connected[y,x])
            route = actor.navigator.core.plan(cm.costs, start, (int(x),int(y)))
            if not len(route): counts['native_empty'] += 1
            elif not cm.sweep_clear(pose, [*cm.map_to_world(route)[0],pose[2]]): counts['connector_rejected'] += 1
            else: counts['valid'] += 1
    return dict(robot_component_cells=int(connected.sum()), navigable_components=int(n),
                free_cells=int((cm.raw==0).sum()), frontiers=len(frontiers), **counts), (cm,connected,pose,frontiers)


def main():
    out = RAW/'development'
    current = hashes()
    out.mkdir(parents=True, exist_ok=False)
    write(out/'source.json', dict(sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(), hashes=current))
    manifest = read(prior.EXP/'cohort.json')
    expected = read(prior.EXP/'results/diagnosis.json')
    results = []
    for row, old in zip(manifest['rows'], expected):
        name = f"s{row['scenario']}-{row['start']}-{row['seed']}-own_frontier"
        # Old report order is lexicographic, manifest order identical for K/L/6701/2.
        assert old['case']==name
        path = PRIOR_RAW/name
        record = lines(path/'actor.jsonl')[0]
        world = RayOracleWorld(row['scenario'],row['pose'],row['seed'],'confirmation')
        world.advance(dict(t=0.,kind='stop'),2.)
        observation,patches,truth = world.observe(0)
        base = {k:v for k,v in observation.items() if not k.endswith('_origins_xy')}
        assert base == record['observation'] and not patches and not record['patches']
        before,_ = diagnose(ResolutionActor('own_frontier',navigation='public_ros_v5'), record)
        for key in ('robot_component_cells','navigable_components'):
            assert before[key] == old[key]
        actor = RaytraceActor('own_frontier',navigation='public_ros_v6')
        after,data = diagnose(actor, {**record,'observation':observation})
        results.append(dict(case=name,before=before,after=after,endpoint_bytes_equal=True,
                            ray_update=actor.ray_updates[-1]))
        write(out/'results.json',results)
    gate = dict(n=len(results),passed=len(results)==32 and all(r['after']['robot_component_cells']>36 and r['after']['valid']>=1 for r in results))
    write(out/'gate.json',gate)
    assert hashes()==current and 'mujoco' not in sys.modules
    print(json.dumps(gate),flush=True)


if __name__=='__main__': main()
