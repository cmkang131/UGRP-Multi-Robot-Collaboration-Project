"""egomap44 prediction only: immutable own contacts/poses, no GT inputs."""
from pathlib import Path
import argparse
import copy
import importlib.util
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/camera-map-integration-v1')
CACHE = Path('/Users/changmin/projects/ugrp/outputs/own-map-causal-landmarks-v1')
EP = Path('/Users/changmin/projects/ugrp/outputs/wall-segment-dev-v1/new-seed')
sys.path.insert(0, str(ROOT))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


old = module('egomap42_camera_adapter', ROOT/'experiments/2026-10-08-own-map-causal-landmarks/code/replay.py')
load, rows, sha, head, dump = old.load, old.rows, old.sha, old.head, old.dump
from harness.self_camera_grid import CameraGrid, OPTION
from harness.self_map_causal import before


def source_files():
    return list(dict.fromkeys([*old.source_files(), Path(__file__),
        ROOT/'harness/self_camera_grid.py', ROOT/'harness/self_odom_grid.py',
        ROOT/'harness/wall_confidence.py', ROOT/'harness/self_wall_memory_robust.py']))


def prepare():
    if (RAW/'prepared.json').exists():
        raise ValueError('PREPARATION_ALREADY_SEALED')
    expected = load(EP/'artifacts.sha256.json')
    names = ['own-contacts.jsonl', 'frontend-covariances.jsonl', 'decisions.json',
             'frontend-ledger.json', 'grid.json', 'graph.json']
    for n in names:
        assert sha(EP/n) == expected[n], n
    previous = load(CACHE/'prepared.json')
    assert sha(CACHE/'own-inputs.json') == previous['own_inputs_sha256']
    for cut in previous['cuts']:
        for c in ('own', 'static'):
            assert sha(CACHE/f'maps/{c}-{cut["trial"]}.json') == cut['maps'][c]
            assert sha(CACHE/f'maps/{c}-{cut["trial"]}-landmarks.json') == cut['landmarks'][c]
    contacts = rows(EP/'own-contacts.jsonl')
    poses = {r['frame_id']: r for r in rows(EP/'frontend-covariances.jsonl')}
    decisions = {r['frame_id']: r for r in load(EP/'decisions.json')}
    admitted = {r['frame_id'] for r in load(EP/'frontend-ledger.json')}
    dense, sparse = CameraGrid('r3'), CameraGrid('r3')
    cuts = copy.deepcopy(previous['cuts'])
    snapshots = {}
    for r in contacts:
        for cut in cuts:
            i = cut['trial']
            if i not in snapshots and not before(r['t'], cut['cut_t']):
                snapshots[i] = dense.export()
                cut.update(snapshot_t=dense.odom.t, snapshot_frame_id=dense.ledger[-1]['frame_id'],
                           scans=len(dense.ledger), last_scan_t=dense.ledger[-1]['t'])
                assert all(before(s['t'], cut['cut_t']) for s in dense.ledger)
                dump(RAW/f'maps/own-{i}-ledger.json', dense.ledger)
        p = poses[r['frame_id']]
        assert abs(p['t']-r['t']) < 1e-8
        d = decisions.get(r['frame_id'], {})
        evidence = d.get('wall_confidence')
        packet = dict(t=r['t'], frame_id=r['frame_id'], robot_id='r3', segments=r['segments'],
            camera_xy=r['camera'], features=r['features'], pose=p['pose'], covariance=p['covariance'],
            settled=d.get('reason') != 'unsettled',
            weights=None if evidence is None else [v['weight'] for v in evidence])
        dense.integrate(**packet)
        if r['frame_id'] in admitted:
            sparse.integrate(**packet)
    assert len(snapshots) == 3
    # Off artifacts remain exact copies, not regenerated dictionaries.
    for src, dest in [(EP/'grid.json', RAW/'off-grid.json'),
                      (CACHE/'own-inputs.json', RAW/'own-inputs.json')]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        assert sha(src) == sha(dest)
    dump(RAW/'on-grid.json', dense.export())
    dump(RAW/'on-ledger.json', dense.ledger)
    dump(RAW/'on-events.json', dense.events)
    dump(RAW/'sparse-online-grid.json', sparse.export())
    for cut in cuts:
        i = cut['trial']
        dump(RAW/f'maps/own-{i}.json', snapshots[i])
        for filename in (f'static-{i}.json', f'own-{i}-landmarks.json', f'static-{i}-landmarks.json'):
            shutil.copyfile(CACHE/'maps'/filename, RAW/'maps'/filename)
        cut['maps'] = {c: sha(RAW/f'maps/{c}-{i}.json') for c in ('own', 'static')}
    prepared = dict(previous, source_sha=head(), preregistration='60decda7', cuts=cuts,
        source_code_hashes={str(f.relative_to(ROOT)): sha(f) for f in source_files()},
        input_hashes={str(EP/n): sha(EP/n) for n in names},
        egomap42_prepared_sha256=sha(CACHE/'prepared.json'), map_update=OPTION,
        pose_estimator='sealed original contemporary poses; no re-estimation or feedback',
        likelihood_tempering='off', scans_before=len(admitted), scans_after=dense.frames,
        input_frames=len(contacts), physics=0, model_calls=0, gt_inputs=False)
    dump(RAW/'prepared.json', prepared)
    for n in names:
        assert sha(EP/n) == expected[n], n
    assert 'mujoco' not in sys.modules
    print('SEALED MAPS', len(admitted), '->', dense.frames, 'prefix scans', [c['scans'] for c in cuts], flush=True)


def configure_old():
    # Reuse the entire pinned predictor and scorer, including seeds and gates.
    old.RAW, old.EXP = RAW, EXP
    # old.source_files remains its original function; our hashes add new modules.
    return old


def predict(condition, trial):
    configure_old().predict(condition, 'on', trial)
    assert 'mujoco' not in sys.modules


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['prepare', 'predict'])
    p.add_argument('--condition', choices=['own', 'static'])
    p.add_argument('--trial', type=int, choices=range(3))
    a = p.parse_args()
    if a.stage == 'prepare': prepare()
    else: predict(a.condition, a.trial)
