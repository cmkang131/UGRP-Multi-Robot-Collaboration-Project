"""GCP5 original-recording replay: allowed-input extraction -> sealed memory -> evaluation.

No physics/render. Score alone opens eval-only.json and static-map.json.
The latter is only an evaluator's landmark label catalogue, never memory input.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import numpy as np


def read(p):
    p = Path(p)
    return json.loads(p.read_text() if p.exists() else subprocess.check_output(['zstd', '-dc', str(p)+'.zst']))


def digest(p):
    p = Path(p)
    if not p.exists(): p = Path(str(p)+'.zst')
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(p, v):
    with Path(p).open('x') as f: json.dump(v, f, indent=2, allow_nan=False, ensure_ascii=False)


def extract(a):
    import cv2
    from harness.egomem_vision import EgocentricDetector
    a.output.mkdir(parents=True, exist_ok=False)
    own = read(a.input/'own.json')['frames']; online = read(a.input/'online-trajectory.json'); scans = read(a.input/'scans.json')
    if not len(own) == len(online) == len(scans): raise ValueError('FRAME_JOIN_REQUIRED')
    detector = EgocentricDetector(); rows = []; counts = Counter(); reasons = Counter(); next_sensor = 0.
    cv2.setNumThreads(1)
    for f, r, s in zip(own, online, scans):
        if not f['t'] == r['t'] == s['t']: raise ValueError('TIME_JOIN_REQUIRED')
        if digest(a.input/f['rgb']) != f['sha256']: raise ValueError('RGB_CHANGED')
        # Explicit allowlist: corrected_pose/map_event/AMCL output are NEVER
        # forwarded. LK is the same own-image increment before static correction.
        flow = r['lk']; measured = flow['status'] == 'measured'
        delta = flow['delta'] if measured else f['command_delta']
        cov = flow['covariance'] if measured else f['command_covariance']
        points = []; diagnostic = None
        if f['t']+1e-8 >= next_sensor:
            next_sensor = f['t']+1.  # existing mapbuild scan update cadence, unchanged.
            counts['sampled'] += 1
            if any(x in flow['status'] for x in ('camera_unsettled', 'servo_change', 'bootstrap')):
                reasons['camera_unsettled'] += 1
            else:
                rgb = cv2.cvtColor(cv2.imread(str(a.input/f['rgb'])), cv2.COLOR_BGR2RGB)
                points, diagnostic = detector.observe(rgb, f['servo'], s)
                counts['settled'] += 1
                counts['features'] += len(diagnostic['features']); counts['point_frames'] += bool(points)
                counts['points'] += len(points); reasons.update(diagnostic['rejected_corner_reasons'])
                if not points: reasons['no_supported_point_landmark'] += 1
        rows.append(dict(t=f['t'], frame_id=f['frame_id'], motion_delta=delta, motion_covariance=cov,
                         motion_source='own_lk' if measured else 'own_command_unqualified_native',
                         observations=points, detector=diagnostic))
    dump(a.output/'allowed.json', rows)
    inputs = {str(a.input/n): digest(a.input/n) for n in ('own.json', 'online-trajectory.json', 'scans.json')}
    dump(a.output/'extraction-seal.json', dict(inputs=inputs, allowed_sha256=digest(a.output/'allowed.json'),
         controller_fields=['motion_delta', 'motion_covariance', 'observations', 't', 'frame_id'],
         excluded=['corrected_pose', 'map_event', 'static-map', 'public-start-zone', 'eval-only', 'spawn', 'top_rgb'],
         truth_inputs=0, static_map_inputs=0, rgb_verified=len(rows), counts=dict(counts), rejection_distribution=dict(reasons)))
    funnel = []; left = len(rows)
    for name, passed in [('sensor_sampled', counts['sampled']), ('camera_settled', counts['settled']), ('point_detected', counts['point_frames'])]:
        funnel.append(dict(stage=name, input_n=left, cumulative_pass_n=passed, rejected_n=left-passed)); left = passed
    dump(a.output/'rejection_table.json', dict(unit='frames', funnel=funnel, reasons=dict(reasons), raw=str(a.input), reproduction=sys.argv,
         blocked_object='not_observed', minimum_gap_m=None, gap_status='not_measured'))
    print(json.dumps(dict(stage='extracted', counts=dict(counts), reasons=dict(reasons))), flush=True)


def predict(a):
    from harness.egocentric_landmark_memory import LandmarkMemory, OPTION, language_context
    seal = read(a.output/'extraction-seal.json')
    if digest(a.output/'allowed.json') != seal['allowed_sha256']: raise ValueError('ALLOWED_INPUT_CHANGED')
    mem = LandmarkMemory(option=OPTION); rows = []; events = Counter()
    for row in read(a.output/'allowed.json'):
        result = mem.step(row['t'], row['motion_delta'], row['motion_covariance'], row['observations'])
        events.update(e['reason'] for e in result['events'])
        rows.append(dict(t=row['t'], frame_id=row['frame_id'], **result))
    dump(a.output/'predictions.json', rows)
    dump(a.output/'llm-input-example.json', language_context(rows[-1]['memories']))
    sources = {str(Path(p).resolve()): digest(p) for p in ('harness/egocentric_landmark_memory.py', 'harness/egomem_vision.py', __file__)}
    dump(a.output/'prediction-seal.json', dict(prediction_sha256=digest(a.output/'predictions.json'),
         allowed_sha256=seal['allowed_sha256'], extraction_seal_sha256=digest(a.output/'extraction-seal.json'), sources=sources,
         truth_inputs=0, static_map_inputs=0, global_pose_state=False, full_cross_covariance=True, events=dict(events), reproduction=sys.argv))
    print(json.dumps(dict(stage='predictions_sealed', frames=len(rows), events=dict(events))), flush=True)


def score(a):
    from harness.egomem_vision import lm
    from harness.egocentric_landmark_memory import relative
    seal = read(a.output/'prediction-seal.json')
    if digest(a.output/'predictions.json') != seal['prediction_sha256']: raise ValueError('PREDICTIONS_CHANGED')
    if digest(a.output/'allowed.json') != seal['allowed_sha256']: raise ValueError('ALLOWED_INPUT_CHANGED')
    pred = read(a.output/'predictions.json'); allowed = read(a.output/'allowed.json')
    truth = read(a.input/'eval-only.json')['frames']; static = read(a.input/'static-map.json')
    if not len(pred) == len(truth) == len(allowed): raise ValueError('EVAL_JOIN_REQUIRED')
    labels = []
    for name, zone in static['regions'].items():
        rgba = np.fromstring(zone['rgba'], sep=' ') if isinstance(zone['rgba'], str) else np.asarray(zone['rgba'])
        h = lm.hue(rgba[:3]); bucket = int(round(h/(2*lm.PARAMS['hue_tolerance']))) % math.ceil(180/(2*lm.PARAMS['hue_tolerance']))
        xy = np.asarray(zone['center_m']); size = np.asarray(zone['half_extents_m'])
        for j, sign in enumerate(([-1,-1],[-1,1],[1,-1],[1,1])):
            labels.append(dict(id=f'{name}-corner{j}', kind='zone_corner', signature=f'floor_hue_{bucket}', xy=(xy+size*sign).tolist()))
    for i, door in enumerate(static.get('passages', [])):
        if door.get('kind') == 'door': labels.append(dict(id=f'door{i}', kind='door', signature='observed_door', xy=door['center_m']))
    associations = {}; errors = []; updates = []; path = 0.; previous = None; seen = {}; assignment_errors = []
    for row, f, g in zip(pred, allowed, truth):
        if not row['t'] == f['t'] == g['t']: raise ValueError('EVAL_TIME_JOIN_REQUIRED')
        pose = np.asarray(g['pose'])
        if previous is not None: path += float(np.linalg.norm(pose[:2]-previous[:2]))
        previous = pose
        observations = {o['id']: o for o in f['observations']}
        for e in row['events']:
            if e['reason'] == 'created':
                o = observations[e['observation']]
                candidates = [p for p in labels if p['kind'] == o['kind'] and p['signature'] == o['signature']]
                if candidates:
                    nearest = min(candidates, key=lambda p: np.linalg.norm(relative(p['xy'],pose)-o['relative_xy_m']))
                    associations[e['memory_id']] = nearest
                    assignment_errors.append(float(np.linalg.norm(relative(nearest['xy'],pose)-o['relative_xy_m'])))
            if e['reason'] in ('created', 'reobserved'):
                if e['reason'] == 'reobserved' and e['memory_id'] in associations:
                    target = relative(associations[e['memory_id']]['xy'], pose)
                    updates.append(dict(t=row['t'], gap_s=e['gap_s'], memory_id=e['memory_id'], target=associations[e['memory_id']]['id'],
                        before_m=float(np.linalg.norm(target-e['predicted_xy_m'])), after_m=float(np.linalg.norm(target-e['updated_xy_m']))))
                seen[e['memory_id']] = path
        for m in row['memories']:
            if m['id'] not in associations: continue
            target = relative(associations[m['id']]['xy'], pose)
            xy = np.asarray(m['relative_xy_m']); error = float(np.linalg.norm(xy-target))
            # Hypothetical yaw-only look toward stored bearing. This is NOT
            # actual navigation/reacquisition; actual return is the next stage.
            da = math.atan2(target[1],target[0])-m['bearing_rad']; da = math.atan2(math.sin(da),math.cos(da))
            errors.append(dict(t=row['t'], path_m=path, since_seen_path_m=path-seen[m['id']], age_s=m['age_s'],
                memory_id=m['id'], target=associations[m['id']]['id'], kind=m['kind'], error_m=error,
                radius95_m=m['radius95_m'], bearing_error_deg=abs(math.degrees(da)), observed_now=m['last_seen_s']==row['t']))
    def stats(values):
        return dict(n=len(values), median=float(np.median(values)), p95=float(np.percentile(values,95)), maximum=float(max(values))) if values else dict(n=0,median=None,p95=None,maximum=None)
    summary = dict(status='OFFLINE_ONLY', frames=len(pred), actual_path_m=path, memories_created=seal['events'].get('created',0),
        last_memory_count=len(pred[-1]['memories']), evaluated_memories=len(associations), memory_error_m=stats([r['error_m'] for r in errors]),
        initial_label_distance_m=stats(assignment_errors), reobservations=len(updates),
        reobservations_error_reduced=sum(u['after_m']<u['before_m'] for u in updates),
        before_m=stats([u['before_m'] for u in updates]), after_m=stats([u['after_m'] for u in updates]),
        actual_return_reacquisition_rate=None, actual_return_trials=0, physical_success=False, student_success=False, llm_success=False,
        evaluation_catalogue='nearest same-appearance exact scene corner/door, evaluation only; wrong RGB detections may be mislabeled',
        raw=str(a.input), truth_sha256=digest(a.input/'eval-only.json'), evaluation_catalogue_sha256=digest(a.input/'static-map.json'),
        prediction_sha256=seal['prediction_sha256'], rejection_table=str((a.output/'rejection_table.json').resolve()))
    dump(a.output/'frame-errors.json', errors); dump(a.output/'reobservations.json', updates); dump(a.output/'summary.json', summary)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1,3,figsize=(13,3.5))
    for ax,key,label in zip(axes,['path_m','since_seen_path_m','age_s'],['Travel (m)','Travel since seen (m)','Time since seen (SIM s)']):
        if errors: ax.scatter([r[key] for r in errors],[r['error_m'] for r in errors],s=1,alpha=.2)
        ax.set(xlabel=label,ylabel='Relative landmark error (m)'); ax.grid()
    fig.tight_layout(); fig.savefig(a.output/'memory-error-curves.png',dpi=150); plt.close(fig)
    fig,ax=plt.subplots(figsize=(5,4))
    if updates: ax.scatter([u['before_m'] for u in updates],[u['after_m'] for u in updates],s=10)
    ax.set(xlabel='Before reobservation error (m)',ylabel='After reobservation error (m)');ax.grid();fig.tight_layout();fig.savefig(a.output/'reobservation.png',dpi=150)
    print(json.dumps(summary),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['extract','predict','score']);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not platform.node().startswith('ugrp-act-l4-gcp5'): raise ValueError('GCP5_ORIGINAL_CPU_ONLY')
    if not Path('/home/ugrp/ugrp-sim/leases/egomem1.json').is_file(): raise ValueError('OWN_LEASE_REQUIRED')
    globals()[a.stage](a)


if __name__=='__main__':main()
