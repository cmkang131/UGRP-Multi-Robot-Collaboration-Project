"""Copy a minimal excerpt of saved own frames for the review-3 shape regressions.

Raw roots are read only. The JPEG bytes and own input records are copied
unchanged. The ground-truth grip in `eval_only` is computed from each run's
eval_only/trace.jsonl for test assertions ONLY; it never reaches a controller.
"""
import bisect, hashlib, json, math, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'tests/fixtures/zone_pair_v6_review3'
RAW = Path('/Users/changmin/projects/ugrp/outputs')
V5H = RAW/'zone-pair-dev-v5h-f87921dc52f7a3f12d41b4bc6ab5c30227890e8e'
V5B = RAW/'zone-pair-dev-v5b-3ea2edc08e5addafaf3cedc934c463ad8e1635c8'
GRIP_INSET_M = .03
FRAMES = [  # (raw root, run, robot, input index), chosen by offline survey distance
    (V5H, 'dev13', 'r1', 1343), (V5H, 'dev13', 'r1', 592), (V5H, 'dev14', 'r1', 1256),
    (V5H, 'dev14', 'r1', 1238), (V5B, 'dev09', 'r2', None),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def gt_grip(run_dir, rid, t):
    rows = [json.loads(l) for l in (run_dir/'eval_only/trace.jsonl').open()]
    ts = [r['t'] for r in rows]
    i = min(bisect.bisect_left(ts, t), len(ts)-1)
    g = rows[i]; rx, ry, ryaw = g['robots'][rid]
    c = g['beam_corners']
    ends = [[(c[0][k]+c[2][k])/2 for k in (0, 1)], [(c[4][k]+c[6][k])/2 for k in (0, 1)]]
    def base(p):
        dx, dy = p[0]-rx, p[1]-ry
        return [math.cos(ryaw)*dx+math.sin(ryaw)*dy, -math.sin(ryaw)*dx+math.cos(ryaw)*dy]
    near, far = sorted((base(e) for e in ends), key=lambda p: math.hypot(*p))
    L = math.dist(near, far)
    grip = [near[k]+GRIP_INSET_M*(far[k]-near[k])/L for k in (0, 1)]
    return {'grip_base_m': [round(v, 5) for v in grip], 'trace_t': ts[i], 'dt_s': round(ts[i]-t, 4),
            'trace_sha256': sha((run_dir/'eval_only/trace.jsonl').read_bytes())}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for root, run, rid, index in FRAMES:
        run_dir = root/run
        # index None: the existing v5c fixture frame dev09_r2_1491 (input 01490).
        source = run_dir/'inputs'/rid/f'{1490 if index is None else index:05d}.json'
        obs = json.loads(source.read_text())
        image = run_dir/obs['image_file']
        data = image.read_bytes()
        assert sha(data) == obs['sha256'], image
        name = f"{root.name.split('-')[3]}_{run}_{rid}_{obs['frame_id']:05d}.jpg"
        shutil.copyfile(image, OUT/name)
        rows.append({'file': name, 'observation': obs, 'source_image': str(image), 'source_input': str(source),
                     'source_input_sha256': sha(source.read_bytes()),
                     'eval_only': gt_grip(run_dir, rid, obs['sim_time'])})
    (OUT/'manifest.json').write_text(json.dumps({
        'scope': 'own JPEG + own input record (unchanged bytes); eval_only ground truth for assertions only',
        'builder': 'experiments/2026-09-28-zone-pair-v6/review3-fixes/build_fixtures.py',
        'frames': rows}, indent=1)+'\n')


if __name__ == '__main__':
    main()
