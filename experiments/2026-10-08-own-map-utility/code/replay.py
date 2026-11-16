"""egomap41 sealed prediction, then separate GT scoring; no physics or models."""
from pathlib import Path
import argparse, hashlib, json, math, subprocess, sys
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
EXP = Path(__file__).resolve().parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/own-map-utility-v1')
EP = Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
POINTS = Path('/Users/changmin/projects/ugrp/outputs/wall-contact-types-v1/32002/off/points.jsonl')
from harness.self_pose_graph import between
from harness.self_odom_grid import transform
from harness.self_pulse_rotation import RotationPulseOdometry
from harness.self_wall_export import export_walls, memory_text
from harness.self_map_relocalize import Relocalizer, plan_to_remembered_goal


def load(p): return json.loads(Path(p).read_text())
def rows(p): return [json.loads(l) for l in Path(p).read_text().splitlines()]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def head(): return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
def dump(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, allow_nan=False, default=lambda x: x.tolist())+'\n')


def remembered_goal(controller, frames):
    """Same B detector/memory as egomap34; no map or GT target coordinates."""
    for row in controller:
        goal = row['goal']
        assert goal['robot_id'] == 'r3' and goal['coordinate_frame'] == 'r3/own_odom'
        confirmed = [c for c in goal['candidates'] if c['state'] == 'locally_confirmed_region']
        if not confirmed: continue
        c = min(confirmed, key=lambda c: (c['confirmed_t'], c['id']))
        f = frames[row['frame_id']]
        return dict(entity=dict(kind='floor_zone', id='B'), center_m=c['center_m'],
            source='own', detector='floor_color_v3', candidate_id=c['id'],
            obs_id=f"r3-obs-{row['frame_id']:06d}", t_sim=row['t'], frame_sha256=f['sha256'],
            observations=c['observations'], first_t=c['first_t'],
            bounds_m=c['bounds_m'], confidence=c['confidence'], partial_extent=True)
    return None


def static_grid(static):
    """Authored static baseline only. Closed-cell intersection retains thin walls."""
    resolution = .1
    x0, x1, y0, y1 = static['bounds_m']
    cells = []
    for y in range(math.floor(y0/resolution), math.ceil(y1/resolution)):
        for x in range(math.floor(x0/resolution), math.ceil(x1/resolution)):
            center = (np.array([x, y])+.5)*resolution
            hit = not (x0 <= center[0] <= x1 and y0 <= center[1] <= y1)
            for o in static['obstacles']:
                if o.get('traversable', False): continue
                assert not o.get('yaw_rad', 0)
                if np.all(abs(center-o['center_m']) <= np.array(o['half_extents_m'])+resolution/2+1e-12):
                    hit = True; break
            cells.append([x, y, 1. if hit else -1.])
    return dict(robot_id='r3', frame='authored_static_world', resolution_m=resolution, cells=cells)


def prepare():
    target = RAW/'prepared.json'
    if target.exists(): raise ValueError('PREPARATION_ALREADY_SEALED')
    expected = load(EP/'artifacts.sha256.json')
    names = ['grid.json', 'graph.json', 'frontend-covariances.jsonl', 'own-controller.jsonl',
        'robots/r3/frames.jsonl', 'robots/r3/commands.jsonl', 'inputs/static_map.json']
    for n in names: assert sha(EP/n) == expected[n], n
    frames = {f['frame_id']: {k: f[k] for k in ('frame_id', 'sim_time', 'sha256', 'path', 'commanded_servo')}
              for f in rows(EP/'robots/r3/frames.jsonl')}
    for f in frames.values(): assert sha(EP/f['path']) == f['sha256']
    covs = {r['frame_id']: r['covariance'] for r in rows(EP/'frontend-covariances.jsonl')}
    graph, grid = load(EP/'graph.json'), load(EP/'grid.json')
    ledger = [dict(r, robot_id='r3') for r in graph['ledger']]
    observations = {i: dict(robot_id='r3', obs_id=f'r3-obs-{i:06d}',
        frame_sha256=f['sha256'], pose_covariance=covs.get(i)) for i, f in frames.items()}
    export = export_walls(grid, ledger, robot_id='r3', wall_export='segments_confidence_v1',
        observations=observations, pose_covariance=covs[max(covs)], now=max(f['sim_time'] for f in frames.values()))
    dump(RAW/'wall-memory.json', export)
    (RAW/'wall-memory.txt').write_text(memory_text(export)+'\n')
    goal = remembered_goal(rows(EP/'own-controller.jsonl'), frames)
    commands = rows(EP/'robots/r3/commands.jsonl')
    points = rows(POINTS)
    odom = RotationPulseOdometry(commands[0]['t'])
    ci = 0; before = np.zeros(3); sequence = []
    for point in points:
        t = point['t']
        while ci < len(commands) and commands[ci]['t'] <= t+1e-8:
            odom.command(commands[ci]); ci += 1
        now = np.array(odom.advance(t))
        delta = between(before, now); before = now
        sequence.append(dict(t=t, frame_id=point['frame_id'], points=point['points'], delta=delta.tolist(),
            servo=frames[point['frame_id']]['commanded_servo']))
    dump(RAW/'own-inputs.json', sequence)
    dump(RAW/'maps/own.json', grid)
    static = load(EP/'inputs/static_map.json')
    dump(RAW/'maps/static.json', static_grid(static))
    dump(target, dict(source_sha=head(), preregistration=['4df2e085','3c3b72cb'],
        input_hashes={str(EP/n): sha(EP/n) for n in names} | {str(POINTS): sha(POINTS)},
        own_inputs_sha256=sha(RAW/'own-inputs.json'), own_goal=goal,
        static_goal=dict(entity=dict(kind='floor_zone', id='B'),
                         center_m=static['regions']['zone_B']['center_m'], source='authored_static_map'),
        maps={c: sha(RAW/f'maps/{c}.json') for c in ('own','static')},
        start_t=min(f['sim_time'] for f in frames.values()), final_t=sequence[-1]['t'],
        raw_physics=0, model_calls=0, prediction_gt_inputs=False))
    print('Prepared frozen grid export, observed B entity, own endpoints and command deltas', flush=True)


def predict(condition, trial):
    out = RAW/f'{condition}-{trial}.json'
    if out.exists(): raise ValueError('TRIAL_ALREADY_SEALED')
    p = load(RAW/'prepared.json')
    assert sha(RAW/'own-inputs.json') == p['own_inputs_sha256']
    assert sha(RAW/f'maps/{condition}.json') == p['maps'][condition]
    seq = [r for r in load(RAW/'own-inputs.json') if r['t'] >= p['start_t']+[60.,90.,120.][trial]-1e-8]
    grid = load(RAW/f'maps/{condition}.json')
    goal = p['own_goal'] if condition == 'own' else p['static_goal']
    pf = Relocalizer(grid, seed=41001+trial)
    output = []; streak = 0; plan = None
    for i, r in enumerate(seq):
        result = pf.step(t=r['t'], points=r['points'], delta=r['delta'] if i else [0.,0.,0.],
                         servo={int(k): v for k,v in r['servo'].items()})
        streak = streak+1 if result['resolved'] else 0
        result.update(frame_id=r['frame_id'], stable_resolved=streak>=5,
            declared_goal=bool(streak>=5 and goal and np.linalg.norm(np.array(result['pose'][:2])-goal['center_m'])<=.20))
        if streak>=5 and plan is None:
            plan = dict(t=r['t'], pose=result['pose'],
                **plan_to_remembered_goal(grid, result['pose'], None if goal is None else goal['center_m']))
        output.append(result)
        if i%100==0: print(condition, trial, i, '/', len(seq), 'particles', pf.n, flush=True)
    dump(out, dict(source_sha=head(), condition=condition, trial=trial, seed=41001+trial,
        prepared_sha256=sha(RAW/'prepared.json'), input_frames=len(seq), points=sum(len(r['points']) for r in seq),
        start_t=seq[0]['t'], goal=goal, plan=plan, rows=output, gt_inputs=False,
        source_code_hashes={str(f.relative_to(ROOT)): sha(f) for f in source_files()}))
    print('SEALED', condition, trial, sha(out), flush=True)


def source_files():
    return [Path(__file__),ROOT/'harness/self_map_relocalize.py',ROOT/'harness/self_wall_export.py',
        ROOT/'harness/self_pulse_rotation.py',ROOT/'harness/self_pulse_odom.py',ROOT/'harness/rbpf_rejection.py',
        *sorted((ROOT/'harness/own_map_amcl_vendor').glob('*.py'))]


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('stage', choices=['prepare','predict'])
    parser.add_argument('--condition', choices=['own','static']); parser.add_argument('--trial', type=int, choices=range(3))
    a = parser.parse_args()
    if a.stage == 'prepare': prepare()
    else: predict(a.condition, a.trial)
    assert 'mujoco' not in sys.modules


if __name__ == '__main__': main()
