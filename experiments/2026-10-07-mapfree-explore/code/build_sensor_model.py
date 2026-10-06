"""Extract measured error tables only; no detector rerun, MuJoCo or model calls."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EXP = Path(__file__).resolve().parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/ego-wall-map-probe/wall-bias-fix/options')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build():
    metadata = {'wall': {}, 'B': {}, 'sources': {}, 'scope': 'legacy wall statistics, camera-v3 static B, v7 prior noise'}
    arrays = {}
    for split, names in [('development', ['main-D-step3-sag']),
                         ('confirmation', ['s912-D-step3-sag', 's913-D-step3-sag'])]:
        tables = []
        for name in names:
            p = RAW/name/'columns.npz'
            metadata['sources'][str(p)] = sha(p)
            a = np.load(p)['mask_on']
            # Each cell retains the joint detection/miss, row correctness and signed residual.
            visible = np.isfinite(a[:, 2]) & np.isfinite(a[:, 3]) & (a[:, 3] <= 4.) & (a[:, 3] > 0)
            detected = np.isfinite(a[:, 0]) & np.isfinite(a[:, 1])
            correct = np.abs(a[:, 0]-a[:, 2]) <= 3.
            for f in range(len(a)):
                ids = np.flatnonzero(visible[f])
                if len(ids) < 8:
                    continue
                # 96 normalized columns, frame-correlated spatial resampling.
                index = ids[np.minimum((np.arange(96)*len(ids)/96).astype(int), len(ids)-1)]
                tables.append(np.stack([detected[f,index], correct[f,index],
                                         a[f,1,index]-a[f,3,index], a[f,3,index]], axis=1))
        table = np.asarray(tables, dtype=np.float32)
        arrays['wall_'+split] = table
        hit = table[:,:,0] == 1
        residual = table[:,:,2][hit]
        metadata['wall'][split] = {'source_frames': len(table), 'normalized_columns': int(hit.size),
            'recall': float(hit.mean()), 'precision_row_3px': float(table[:,:,1][hit].mean()),
            'range_residual_quantiles_m': dict(zip(['p05','p50','p95'],np.quantile(residual,[.05,.5,.95]).tolist())),
            'abs_residual_median_m': float(np.median(np.abs(residual))),
            'note': '>=8 visible positive-range <=4m columns; per-frame 96-column normalization; no positive-depth rerun'}
        p = ROOT/f'outputs/mapfree-goal-floor-v3/{split}-v3/results.json'
        metadata['sources'][str(p)] = sha(p)
        b = json.loads(p.read_text())
        positive = [f for f in b['frames'] if f['positive']]
        errors = [x for f in positive for x in f['errors_m']]
        arrays['B_errors_'+split] = np.array(errors, dtype=np.float32)
        metadata['B'][split] = {'recall': sum(f['tp'] for f in positive)/len(positive),
            'positive_frames': len(positive), 'precision': b['summary']['frame_precision'],
            'negative_recorded_fp_components': 14, 'negative_recorded_frames': 527,
            'fp_rate': 14/527, 'note': 'recorded v3 negatives are previously seen; FP stream separate from static P=1'}
    fp = []
    for case in ('s1042','s1043','s1044','s1045'):
        p = ROOT/f'outputs/mapfree-goal-floor-v3/recorded-v3/{case}/predictions.jsonl'
        metadata['sources'][str(p)] = sha(p)
        for line in p.read_text().splitlines():
            for patch in json.loads(line)['patches']:
                fp.append({k:patch[k] for k in ('center_body_m','hull_body_m','confidence','pixels')})
    metadata['B_false_patches'] = fp
    np.savez_compressed(EXP/'sensor-errors.npz', **arrays)
    metadata['sensor_errors_sha256'] = sha(EXP/'sensor-errors.npz')
    for p in ['harness/self_map_prob.py','harness/self_odom_grid.py','harness/floor_goal.py',
              'sim/masterpi_camera_profile.py','experiments/2026-10-07-mapfree-goal-floor/v3-selection.json',
              'experiments/2026-10-07-mapfree-goal-floor/v3-results.json']:
        metadata['sources'][p] = sha(ROOT/p)
    (EXP/'sensor-model.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps({'wall': metadata['wall'], 'B': metadata['B']}, indent=2))

if __name__ == '__main__':
    build()
