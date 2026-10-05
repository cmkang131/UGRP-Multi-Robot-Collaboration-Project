"""Read-only v88 training diagnosis. No renderer, stepping, or held-out input.

Run from the repo root with the existing simulation Python. The output must
be a new directory. PR #358 IO/camera modules are loaded from a pinned Git
object in memory; the worktree, raw, fitter, and frozen criteria stay intact.
"""
from __future__ import annotations

import collections
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path('/Users/changmin/projects/ugrp/outputs')
ASSEMBLER = subprocess.check_output(['git', 'rev-parse', 'd00208ba'], cwd=ROOT, text=True).strip()
RAW = {
    'unloaded': OUT/'final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded',
    'fine': OUT/'final-pair-v88-cal-747d2b9f-20261001-r6/calibration-fine',
    'loaded': OUT/'final-pair-v88-cal-747d2b9f-20261001-r8/calibration-loaded',
}


def pinned_module(name):
    path = name.replace('.', '/') + '.py'
    blob = subprocess.check_output(['git', 'show', f'{ASSEMBLER}:{path}'], cwd=ROOT)
    spec = importlib.util.spec_from_loader(name, loader=None, origin=f'{ASSEMBLER}:{path}')
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(ROOT/path)
    sys.modules[name] = module
    exec(compile(blob, str(ROOT/path), 'exec'), module.__dict__)
    return module


def native(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value))


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=native)+'\n')


def intervals(mask, t):
    indices = np.flatnonzero(mask)
    return [[float(t[x[0]]), float(t[x[-1]]), len(x)] for x in
            np.split(indices, np.flatnonzero(np.diff(indices) != 1)+1) if len(x)]


def main(dest):
    dest.mkdir(parents=True, exist_ok=False)
    ci = pinned_module('scripts.final_pair_calibration_io')
    cam = pinned_module('scripts.final_pair_calibration_camera')
    from scripts import final_pair_calibration_motion as motion
    from harness.own_beam_edge import edge_line
    from harness.vision_pose_source_final import camera_key
    prime = json.loads((ROOT/'experiments/2026-10-01-v88-measured-calibration/criterion_B_prime.json').read_text())
    gate = prime['parent_text']
    inputs = ci.Inputs()
    data = {}
    for profile, path in RAW.items():
        print('audit', profile, flush=True)
        data[profile] = ci.load_collection(path, profile, inputs)
    loaded = data['loaded']
    valid, reasons = ci.loaded_mask(loaded, inputs, prime['loaded_selection'])
    t = loaded['robots']['r1']['t']
    start = t[0]
    result = {'assembler_sha': ASSEMBLER, 'analysis_base_sha': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'raw': {k: {'root': v, 'source_sha': data[k]['bundle']['source_sha'],
                    'artifacts_sha256': ci.file_sha(data[k]['folder']/'artifacts.sha256.json')}
                for k, v in RAW.items()},
        'load_selection': reasons, 'valid_intervals_relative_s': intervals(valid, t-start)}
    support, response = [], []
    for rid, robot in loaded['robots'].items():
        before = motion.deadband_support(robot, gate)
        robot['segments'] = ci.selected_segments(loaded['segments'], valid)
        after = motion.deadband_support(robot, gate)
        for axis in before:
            for x, y in zip(before[axis], after[axis]):
                support.append({'robot': rid, 'axis': axis, **x, 'before': x['windows'], 'after': y['windows']})
        for axis, name in enumerate(motion.b.AXES):
            for a,z in loaded['segments'][name]['steps']:
                plateau_end = a+200
                target = motion.b.c.endpoint_targets(robot['pose'], np.array([a]), 200)[0]
                tail = motion.b.c.endpoint_targets(robot['pose'], np.array([a+100]), 100)[0]
                command = float(robot['u'][a, axis])
                response.append({'robot': rid, 'axis': name, 'command': command,
                    'relative_start_s': float(t[a]-start), 'valid_samples': int(valid[a:z+1].sum()),
                    'samples': z-a+1, 'travel_10s': target, 'tail_velocity_5s': tail/5.,
                    'tail_driven_gain': float(tail[axis]/5./command)})
    result['support'] = support
    result['step_response'] = response
    original = motion.least_squares
    def logged_fit(*args, **kwargs):
        opt = original(*args, **kwargs)
        lo, hi = (np.asarray(x) for x in kwargs['bounds'])
        result['optimizer'] = {'theta': opt.x, 'values': np.r_[np.exp(opt.x[:7]), opt.x[7:]],
            'lower_values': np.r_[np.exp(lo[:7]), lo[7:]], 'upper_values': np.r_[np.exp(hi[:7]), hi[7:]],
            'active_mask': opt.active_mask, 'success': opt.success, 'message': opt.message,
            'nfev': opt.nfev, 'rank': np.linalg.matrix_rank(opt.jac),
            'singular_values': np.linalg.svd(opt.jac, compute_uv=False),
            'rmse': np.sqrt(np.mean(opt.fun**2))}
        return opt
    motion.least_squares = logged_fit
    print('fit with unchanged bounds', flush=True)
    try:
        motion.fit_shared(list(loaded['robots'].values()), gate, deadband=True)
    except ValueError as exc:
        result['fit_rejection'] = str(exc)
    finally:
        motion.least_squares = original
    save(dest/'motion.json', result)
    print('camera stationary groups', flush=True)
    camera_records = []
    for profile, collection in data.items():
        v = valid if profile == 'loaded' else np.ones(7401, bool)
        for rid, robot in collection['robots'].items():
            groups = collections.defaultdict(list)
            for frame, label in zip(robot['frames'], robot['labels']):
                i = round((frame['sim_time']-robot['t'][0])/.05)
                lo = max(0,i-20)
                still = not np.any(robot['u'][lo:i]) and frame['_still_s'] >= 1.-1e-7
                key = camera_key({int(k): x for k,x in frame['commanded_servo'].items()})
                groups[key].append((frame,label,still,bool(np.all(v[lo:i+1]))))
            for key, rows in groups.items():
                accepted = [label for _,label,still,load in rows if still and load]
                item = {'profile': profile, 'robot': rid, 'pose': key, 'frames': len(rows),
                    'times_relative_s': [rows[0][0]['sim_time']-robot['t'][0], rows[-1][0]['sim_time']-robot['t'][0]],
                    'stationary_settled': sum(s for _,_,s,_ in rows), 'stationary_loaded': len(accepted),
                    'selected_frame_ids': [f['frame_id'] for f,_,s,l in rows if s and l]}
                if accepted:
                    item['optical'] = cam.camera_summary([cam.rigid(l) for l in accepted])
                    item['floor'] = cam.camera_summary([cam.rigid(l['chassis_to_floor']) for l in accepted])
                camera_records.append(item)
    save(dest/'camera.json', camera_records)
    print('recorded images', flush=True)
    samples = []
    for profile, collection in data.items():
        for rid, robot in collection['robots'].items():
            by_pose = collections.defaultdict(list)
            for f in robot['frames']:
                key = camera_key({int(k): x for k,x in f['commanded_servo'].items()})
                by_pose[key].append(f)
            for key, frames in by_pose.items():
                # The two required loaded poses, all loaded pan views, and the
                # stationary r2 baseline when a same-pose sample does not exist.
                if not key.startswith(('807,1897,2187,','1269,2052,2494,')) and not (rid=='r2' and profile!='loaded'):
                    continue
                for j in sorted(set(np.linspace(0,len(frames)-1,3,dtype=int))):
                    f = frames[j]
                    blob = inputs.read(collection['folder']/f['path'])
                    im = Image.open(io.BytesIO(blob)).convert('RGB')
                    rgb = np.asarray(im)
                    hsv = np.asarray(im.convert('HSV')).astype(int)
                    h,s,v = hsv.transpose(2,0,1)
                    mask = (h>25)&(h<90)&(s>100)&(v>60)
                    roi = rgb[40:300,140:500]
                    samples.append({'profile': profile, 'robot': rid, 'pose': key,
                        'frame_id': f['frame_id'], 'relative_s': f['sim_time']-robot['t'][0],
                        'path': collection['folder']/f['path'], 'sha256': hashlib.sha256(blob).hexdigest(),
                        'mask_pixels': int(mask.sum()), 'roi_mask_pixels': int(mask[40:300,140:500].sum()),
                        'roi_mean_rgb': roi.mean(axis=(0,1)), 'roi_std_rgb': roi.std(axis=(0,1)),
                        'edge': edge_line(im)})
    save(dest/'images.json', samples)
    # Shape-only pair diagnostic as in #358; fine mean never becomes a loaded
    # candidate. No pair fit or acceptance is performed with this placeholder.
    report = json.loads((OUT/'final-pair-v88-measured-dryrun-20261003-035426/fit_report.json').read_text())
    rows, excluded = cam.pair_rows(loaded, report['fine']['motion']['candidate'], valid, inputs, prime['pair_model'])
    save(dest/'pair.json', {'mean_scope': 'fine placeholder for edge-path diagnosis only', 'rows': rows, 'excluded': excluded})
    print('verify all audited inputs unchanged', flush=True)
    inputs.verify()
    save(dest/'verification.json', {'input_files_verified': len(inputs.files), 'raw_unchanged': True,
        'no_rendering': True, 'no_physics_stepping': True, 'no_heldout_reads': True,
        'numpy': np.__version__, 'source_sha': ASSEMBLER})
    print('done', dest, flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
