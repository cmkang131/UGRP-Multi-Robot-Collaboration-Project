"""Same-input frontend replay; all predictions sealed before separate GT scoring."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import numpy as np
ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.self_wall_memory_robust import SelfWallMemory
from harness.active_wall_mapping import OPTIONS
from harness.rbpf_motion_gate import install as motion_install, OPTION as MOTION
from harness.rbpf_insertion import install, OPTION
from harness.self_odom_grid import transform
RAW = Path('/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/baseline')
OUT = Path('/Users/changmin/projects/ugrp/outputs/rbpf-insertion-v1')


def load(p): return json.loads(p.read_text())
def dump(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
    with p.open() as f:
        for line in f:
            yield json.loads(line)


def predict(mode):
    for name, digest in load(RAW/'artifacts.sha256.json').items():
        assert sha(RAW/name) == digest, name
    out = OUT/mode
    out.mkdir(exist_ok=False)
    commands = sorted(rows(RAW/'robots/r3/commands.jsonl'), key=lambda r:r['t'])
    memory = SelfWallMemory('r3', **OPTIONS, self_map_options={'start_time': commands[0]['t']})
    g = install(motion_install(memory.self_map, rbpf_update=MOTION), rbpf_insertion='off' if mode == 'off' else OPTION)
    cursor, poses = 0, []
    for row in rows(RAW/'own-contacts.jsonl'):
        t = row['t']
        while cursor < len(commands) and commands[cursor]['t'] < t-1e-8:
            memory.command(commands[cursor])
            cursor += 1
        g.odom.advance(t)
        if row['segments']:
            g.observe_contacts_confident(t=t, frame_id=row['frame_id'], robot_id='r3', segments=row['segments'],
                                         features=row['features'], camera_xy=row['camera'])
        poses.append(dict(robot_id='r3', t=t, pose=list(g.odom.pose), covariance=g.odom.covariance.tolist()))
        if len(poses) % 200 == 0:
            print(mode, len(poses), 'frames', g.resamples, 'resamples', flush=True)
    prediction = dict(grid=g.export(), poses=poses, decisions=g.decisions, ledger=g.ledger)
    dump(out/'prediction.json', prediction)
    receipt = dict(sha256=sha(out/'prediction.json'), gt_read=False,
        source_sha=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        inputs={name:sha(RAW/name) for name in ('own-contacts.jsonl','robots/r3/commands.jsonl','artifacts.sha256.json')})
    dump(out/'seal.json', receipt)
    if mode == 'off':
        verify_off()
    assert 'mujoco' not in sys.modules
    print(mode, 'sealed', receipt['sha256'], flush=True)


def verify_off():
    # Compare the public JSON bytes, not internal tuples against parsed lists.
    p = load(OUT/'off/prediction.json')
    values = {'poses':[{k:r[k] for k in ('robot_id','t','pose')} for r in p['poses']],
              'grid':p['grid'], 'decisions':p['decisions'], 'ledger':p['ledger']}
    originals = {'poses':'frontend-poses.json', 'grid':'frontend-grid.json',
                 'decisions':'decisions.json', 'ledger':'frontend-ledger.json'}
    checks = {k:(json.dumps(v,indent=2)+'\n').encode() == (RAW/originals[k]).read_bytes()
              for k,v in values.items()}
    dump(OUT/'off/byte-verification.json', dict(equal=checks, prediction_sha256=sha(OUT/'off/prediction.json')))
    assert all(checks.values()), checks
    print('off legacy JSON bytes', checks, flush=True)


def score():
    verify_off()
    predictions = {}
    for mode in ('off','on'):
        assert sha(OUT/mode/'prediction.json') == load(OUT/mode/'seal.json')['sha256']
        predictions[mode] = load(OUT/mode/'prediction.json')
    # Evaluation boundary: both own-only predictions above already exist.
    spec = importlib.util.spec_from_file_location('old_score', ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    sys.path.insert(0, str(ROOT/'experiments/2026-10-05-ego-wall-map-probe/code'))
    import odom_grid_replay as metrics
    truth = {round(r['t'],6):r for r in rows(RAW/'eval_only/trajectory.jsonl')}
    start = truth[min(truth)]
    origin = [*start['robot_xyz_m'][:2], start['robot_yaw_rad']]
    static = load(RAW/'inputs/static_map.json')
    rects = np.array([w['center_m']+w['half_extents_m'] for w in static['obstacles'] if w.get('kind') == 'wall'])
    samples = metrics.wall_samples(rects)
    cameras = list(rows(RAW/'eval_only/camera.jsonl'))
    visible = old.in_view(samples, cameras, rects)
    acquisition = load(ROOT/'experiments/2026-10-07-rbpf-motion-gate/results/baseline.json')
    result = dict(qualification='same-input frontend; graph covariance not invented; physical path unchanged',
                  legacy_byte_verification=load(OUT/'off/byte-verification.json'),
                  source_frames=acquisition['coverage']['frames'],
                  acquisition_coverage=acquisition['coverage'], b=acquisition['b'],
                  wall_contacts=acquisition['wall_contacts'], modes={})
    for mode, p in predictions.items():
        poses, g, decisions = p['poses'], p['grid'], p['decisions']
        xy = transform([r['pose'][:2] for r in poses], origin)
        actual = np.array([truth[round(r['t'],6)]['robot_xyz_m'][:2] for r in poses])
        errors = np.linalg.norm(xy-actual, axis=1)
        sigma = np.array([np.sqrt(np.linalg.eigvalsh(np.array(r['covariance'])[:2,:2]).max()) for r in poses])
        cells = np.array([c for c in g['cells'] if c[2]>0]).reshape(-1,3)
        occupied = transform((cells[:,:2]+.5)*.1, origin)
        quality, cover = metrics.quality(occupied, rects, samples)
        region = old.in_view(occupied, cameras, rects)
        correct = metrics.boundary_dist(occupied, rects) <= .15
        ancestry = np.arange(100)
        for d in decisions:
            if d.get('resampled'):
                ancestry = ancestry[d['parent_indices']]
        from collections import Counter
        rejected = [d for d in decisions if d['status']=='rejected']
        r = dict(endpoint_error_m=float(errors[-1]), sigma_xy_m=float(sigma[-1]), error_sigma_ratio=float(errors[-1]/sigma[-1]),
                 error_2sigma_ratio=float(errors[-1]/(2*sigma[-1])), path_rmse_m=float(np.sqrt(np.mean(errors**2))),
                 over_2sigma=int((errors>2*sigma).sum()), pose_n=len(poses), resamples=g['resamples'], ancestors=len(set(ancestry)),
                 rejected_resamples=sum(d.get('resampled',False) for d in rejected),
                 sensor_updates=sum(any(e['reason'] in ('improved_proposal','low_overlap','search_boundary','high_residual')
                                        for e in d.get('particle_events',[])) for d in decisions),
                 reasons=dict(Counter(d['reason'] for d in decisions)),
                 occupied_cells=len(cells), inserted_frames=len(p['ledger']), full_map=quality,
                 observed_region=dict(precision_correct=int(correct[region].sum()), precision_cells=int(region.sum()),
                    precision=float(correct[region].mean()) if region.any() else None,
                    recalled_samples=int(cover[visible].sum()), visible_samples=int(visible.sum()), total_samples=len(samples),
                    recall=float(cover[visible].mean()), visible_wall_fraction=float(visible.mean())),
                 seal=load(OUT/mode/'seal.json'))
        result['modes'][mode] = r
    off, on = result['modes']['off'], result['modes']['on']
    result['gate'] = dict(off_bytes=all(result['legacy_byte_verification']['equal'].values()),
        admitted_55=all(p['grid']['motion_gate']['processed']==55 for p in predictions.values()),
        deferred_836=all(p['grid']['motion_gate']['skipped']==836 for p in predictions.values()),
        on_inserted_55=on['inserted_frames']==55,
        on_late_inserted_47=sum(d['inserted'] for d in predictions['on']['decisions'] if d['t']>36.1+1e-8)==47)
    result['software_gate_passed'] = all(result['gate'].values())
    result['physical_admitted'] = False
    result['qualification'] += '; lifecycle conformance gate, not a map accuracy gate; physical zero'
    for mode,p in predictions.items():
        ds={r['frame_id']:r for r in p['decisions']}
        counts=[dict(segments=0,inserted_segments=0) for _ in range(5)]
        for row in rows(RAW/'own-contacts.jsonl'):
            for distance in np.linalg.norm(np.asarray(row['segments'])-row['camera'],axis=2).max(1):
                bucket=counts[min(4,int(distance))]
                bucket['segments']+=1
                bucket['inserted_segments']+=int(ds[row['frame_id']]['inserted'])
        result['modes'][mode]['range_segments']=counts
        result['modes'][mode]['inserted_times']=[r['t'] for r in p['ledger']]
    dump(EXP/'results/comparison.json', result)
    print(json.dumps(result, indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['off','on','score','verify-off'])
    args=parser.parse_args()
    if args.mode=='score': score()
    elif args.mode=='verify-off': verify_off()
    else: predict(args.mode)
