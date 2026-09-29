"""Frames -> VIS3 column observations (torch env, `.venv-reference-act`).

Robot-side path: raw fisheye JPEG -> `seg_model.Segmenter` (checkpoint seg-v2, frozen) -> `vision_loc.column_observations`
(frozen config). Writes `obs_vision.json` (student observations). If the render has eval-only labels it also writes
`obs_oracle.json` (observations from the teacher segmentation render: perception-ceiling diagnostic, NEVER a student)
and per-frame class agreement between the network and the labels (`seg_agreement.json`).

usage: python segment_frames.py <render_dir> [--device mps|cpu]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('render_dir')
    ap.add_argument('--device', default=None)
    a = ap.parse_args(argv)
    import seg_model
    ctx = common.Context()
    vl = ctx.vl
    if common.sha_file(common.CHECKPOINT) != common.CHECKPOINT_SHA256:
        raise SystemExit('segmentation checkpoint hash differs from the registered seg-v2')
    seg = seg_model.Segmenter(common.CHECKPOINT, a.device, ctx.infer_size)
    d = Path(a.render_dir)
    man = json.loads((d / 'render_manifest.json').read_text())
    obs_v, obs_o, agree = {}, {}, {}
    t0 = time.time()
    for row in man['rows']:
        bgr = cv2.imread(str(d / row['file']), cv2.IMREAD_COLOR)
        probs = seg.probs(bgr)
        und = vl.mp.undistort(bgr) if ctx.obs_params.get('refine_px') else None
        obs_v[row['name']] = vl.column_observations(probs, ctx.columns, ctx.obs_params, und).as_dict()
        lab_path = row['eval_only'].get('label')
        if lab_path:
            lab = cv2.imread(str(d / lab_path), cv2.IMREAD_UNCHANGED)
            obs_o[row['name']] = vl.column_observations(vl.one_hot(lab), ctx.columns, ctx.obs_params).as_dict()
            pred = probs.argmax(2)
            valid = vl.VALID & (lab != vl.IGNORE)
            per = {}
            for c, name in ((vl.FLOOR, 'floor'), (vl.WALL, 'wall')):
                inter = float(((pred == c) & (lab == c) & valid).sum())
                union = float((((pred == c) | (lab == c)) & valid).sum())
                per[name] = {'iou': None if union == 0 else round(inter / union, 4), 'label_px': int(((lab == c) & valid).sum())}
            per['pixel_acc'] = round(float(((pred == lab) & valid).sum() / max(valid.sum(), 1)), 4)
            agree[row['name']] = per
    meta = {'frames': len(obs_v), 'wall_s': round(time.time() - t0, 1), 'device': str(seg.dev), 'infer_size': list(ctx.infer_size),
            'provenance': ctx.provenance()}
    (d / 'obs_vision.json').write_text(json.dumps({'meta': meta, 'obs': obs_v}))
    if obs_o:
        (d / 'obs_oracle.json').write_text(json.dumps({'meta': {**meta, 'kind': 'oracle (eval-only teacher labels)'}, 'obs': obs_o}))
        (d / 'seg_agreement.json').write_text(json.dumps(agree, indent=1))
    print(json.dumps({k: meta[k] for k in ('frames', 'wall_s', 'device')}))


if __name__ == '__main__':
    main()
