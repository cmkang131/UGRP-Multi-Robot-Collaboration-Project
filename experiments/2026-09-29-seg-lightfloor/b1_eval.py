"""B1 protocol with a chosen segmentation checkpoint on an existing B1 render (torch env).

Frames, truth poses, start-error draws, seeds, prior, filter, calibration, map: exactly those of
`experiments/2026-09-29-carry-relocalization-b1` (its relocalize_grid.py runs unchanged, as a subprocess).  Only the
segmentation network that produces the student's column observations differs.

usage: b1_eval.py <name> --ckpt <seg ckpt> --render <b1 render dir> [--pre rgb|perimg|gray_perimg] [--xf none|gain0.4|...]
                  [--looks p20 search] [--cells S Y] [--n S=40,Y=8] [--checkpoints ...] [--robots ...] [--skip-runs]
Output: $OUT/b1/<name>/<render dir name>/{render_manifest.json, frames -> B1 frames, obs_vision.json, seg_agreement.json, runs.jsonl, summary.json}
"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
B1 = HERE.parents[1] / 'experiments' / '2026-09-29-carry-relocalization-b1'
sys.path[:0] = [str(HERE), str(B1)]
import common  # noqa: E402  (B1)
import cv2, numpy as np  # noqa: E402
import seg_ft  # noqa: E402

OUT = Path('/Users/changmin/projects/ugrp/outputs/seg-lightfloor-20260929')


def make_obs(ckpt, pre, xf, src: Path, dst: Path, infer_size=None):
    ctx = common.Context()
    vl = ctx.vl
    seg = seg_ft.Seg(Path(ckpt), pre, infer_size or ctx.infer_size, xf=seg_ft.XFS[xf])
    man = json.loads((src / 'render_manifest.json').read_text())
    obs_v, agree = {}, {}
    t0 = time.time()
    for row in man['rows']:
        bgr = cv2.imread(str(src / row['file']), cv2.IMREAD_COLOR)
        probs = seg.probs(bgr)
        und = vl.mp.undistort(bgr) if ctx.obs_params.get('refine_px') else None
        obs_v[row['name']] = vl.column_observations(probs, ctx.columns, ctx.obs_params, und).as_dict()
        lab_path = row['eval_only'].get('label')
        if lab_path:
            lab = cv2.imread(str(src / lab_path), cv2.IMREAD_UNCHANGED)
            pred = probs.argmax(2)
            valid = vl.VALID & (lab != vl.IGNORE)
            per = {}
            for c, name in ((vl.FLOOR, 'floor'), (vl.WALL, 'wall')):
                inter = float(((pred == c) & (lab == c) & valid).sum())
                union = float((((pred == c) | (lab == c)) & valid).sum())
                per[name] = {'iou': None if union == 0 else round(inter / union, 4), 'label_px': int(((lab == c) & valid).sum())}
            per['pixel_acc'] = round(float(((pred == lab) & valid).sum() / max(valid.sum(), 1)), 4)
            agree[row['name']] = per
    meta = {'frames': len(obs_v), 'wall_s': round(time.time() - t0, 1), 'device': str(seg.dev), 'infer_size': list(infer_size or ctx.infer_size),
            'checkpoint_sha256': seg.sha256, 'pre': pre, 'xf': xf}
    (dst / 'obs_vision.json').write_text(json.dumps({'meta': meta, 'obs': obs_v}))
    (dst / 'seg_agreement.json').write_text(json.dumps(agree, indent=1))
    return meta, agree


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('name'); ap.add_argument('--ckpt', required=True); ap.add_argument('--render', required=True)
    ap.add_argument('--pre', default='rgb'); ap.add_argument('--xf', default='none')
    ap.add_argument('--looks', nargs='*', default=['p20']); ap.add_argument('--cells', nargs='+', default=['S', 'Y'])
    ap.add_argument('--n', default='S=40,Y=8'); ap.add_argument('--checkpoints', type=int, nargs='*'); ap.add_argument('--robots', nargs='*')
    ap.add_argument('--infer-size', type=int, nargs=2); ap.add_argument('--skip-runs', action='store_true'); ap.add_argument('--tag', default='')
    a = ap.parse_args()
    src = Path(a.render)
    dst = OUT / 'b1' / a.name / src.name
    dst.mkdir(parents=True, exist_ok=True)
    if not (dst / 'frames').exists():
        os.symlink(src / 'frames', dst / 'frames')
    if not (dst / 'eval_only').exists() and (src / 'eval_only').exists():
        os.symlink(src / 'eval_only', dst / 'eval_only')
    (dst / 'render_manifest.json').write_bytes((src / 'render_manifest.json').read_bytes())
    if not (dst / 'obs_vision.json').exists():
        meta, agree = make_obs(a.ckpt, a.pre, a.xf, src, dst, a.infer_size)
        w = [v['wall']['iou'] for v in agree.values() if v['wall']['iou'] is not None]
        print('obs', json.dumps(meta), 'wall IoU median', round(float(np.median(w)), 3), 'p10', round(float(np.percentile(w, 10)), 3), flush=True)
    if a.skip_runs:
        return
    runs = dst / f'runs{a.tag}.jsonl'
    if runs.exists():
        runs.unlink()
    cmd = [sys.executable, str(B1 / 'relocalize_grid.py'), str(dst), str(runs), '--obs', 'vision', '--prior', 'wide', '--cells', *a.cells, '--n', a.n, '--looks', *a.looks]
    if a.checkpoints is not None:
        cmd += ['--checkpoints', *map(str, a.checkpoints)]
    if a.robots:
        cmd += ['--robots', *a.robots]
    env = {**os.environ, 'OMP_NUM_THREADS': '1'}
    t0 = time.time()
    print(subprocess.run(cmd, env=env, capture_output=True, text=True).stdout.strip(), round(time.time() - t0), 's', flush=True)


if __name__ == '__main__':
    main()
