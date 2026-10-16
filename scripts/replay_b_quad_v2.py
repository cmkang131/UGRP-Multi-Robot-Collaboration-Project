"""Offline replay of the B quad stage: off vs contrast_v1 vs contrast_v2.

Reads saved JPEGs only (no simulation). Detection sees own RGB + commanded servo
+ own pose. Labels (is B / are B corners in view) come from the e2e11 replay
rows (scripts/replay_b_marker_detect.py output) and are written to the
evaluation record only. Frames without labels are reported separately.
"""
import argparse, glob, hashlib, json, subprocess, sys
from collections import Counter
from pathlib import Path
import cv2, numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.e2e_rgb_gate import boundary

OPTIONS = ('off', 'contrast_v1', 'contrast_v2')


def zjson(path):
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if str(path).endswith('.zst') else Path(path).read_bytes()
    return [json.loads(l) for l in raw.splitlines() if l.strip()]


def detect(rgb, servo, pose):
    out = {}
    for o in OPTIONS:
        d = {}
        got = boundary(rgb, servo, pose, diagnostics=d, marker_detect=o)
        reasons = Counter(c['reason'] for c in d['contours'] if c['area_px2'] >= 100)
        out[o] = dict(accepted=got is not None, reasons=dict(reasons))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--e2e11-outputs', type=Path, required=True)   # outputs dir with selected-frames + azure-runs
    ap.add_argument('--e2e14-frames', type=Path, required=True)    # scratchpad e2e14seq dir (unlabeled)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    rows = []
    root = a.e2e11_outputs/'e2e11-stall-odometry/selected-frames'
    for run in sorted(root.iterdir()):
        raw = a.e2e11_outputs/'azure-runs'/run.name/'raw'
        for rid in ('r1', 'r2'):
            frames = zjson(raw/f'robots/{rid}/frames.jsonl.zst') if (raw/f'robots/{rid}/frames.jsonl.zst').exists() else zjson(raw/f'robots/{rid}/frames.jsonl')
            own = {r['frame_id']: r for r in zjson(raw/f'robots/{rid}/ownmap.jsonl.zst' if (raw/f'robots/{rid}/ownmap.jsonl.zst').exists() else raw/f'robots/{rid}/ownmap.jsonl')}
            for f in frames:
                p = run/'raw'/f['path']
                if not p.exists(): continue
                data = p.read_bytes()
                assert hashlib.sha256(data).hexdigest() == f['sha256']
                rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), 1), cv2.COLOR_BGR2RGB)
                servo = {int(k): v for k, v in f['commanded_servo'].items()}
                rows.append(dict(set='e2e11', run=run.name, robot=rid, frame_id=f['frame_id'],
                                 detect=detect(rgb, servo, own[f['frame_id']]['pose_own_m'])))
    for d in sorted(a.e2e14_frames.glob('e2e14-*')):
        for rdir in sorted((d/'raw/robots').iterdir()):
            frames = zjson(rdir/'frames.jsonl.zst'); own = {r['frame_id']: r for r in zjson(rdir/'ownmap.jsonl.zst')}
            for f in frames:
                p = rdir.parents[1]/f['path']
                if not p.exists() or f['frame_id'] not in own: continue
                data = p.read_bytes(); assert hashlib.sha256(data).hexdigest() == f['sha256']
                rgb = cv2.cvtColor(cv2.imdecode(np.frombuffer(data, np.uint8), 1), cv2.COLOR_BGR2RGB)
                servo = {int(k): v for k, v in f['commanded_servo'].items()}
                rows.append(dict(set='e2e14', run=d.name, robot=rdir.name, frame_id=f['frame_id'],
                                 detect=detect(rgb, servo, own[f['frame_id']]['pose_own_m'])))
    a.out.write_text(json.dumps(rows, sort_keys=True))
    for s in ('e2e11', 'e2e14'):
        sub = [r for r in rows if r['set'] == s]
        print(s, len(sub), {o: sum(r['detect'][o]['accepted'] for r in sub) for o in OPTIONS})
        for o in OPTIONS:
            c = Counter()
            for r in sub: c.update(r['detect'][o]['reasons'])
            print(' ', o, dict(c))

if __name__ == '__main__': main()
