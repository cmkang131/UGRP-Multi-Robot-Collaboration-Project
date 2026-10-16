#!/usr/bin/env python3
"""Tag-free vision localization worker (``vision_zero_tag_v1``): own BGR frame -> column observations.

Runs in the existing ACT environment (torch; ``configs/vision_loc_worker.json`` ``python``), never in
the MuJoCo environment. Same JSON-lines pattern as ``scripts/reference_act_worker.py`` /
``scripts/carry_input_worker.py``: one startup line, then one reply line per request line.

Per request (``harness.vision_loc_protocol``): exactly one own 640x480 BGR frame -> PR #233's
``seg_model.Segmenter.probs`` (checkpoint sha256-checked) -> ``vision_loc.column_observations`` with
the registered VIS3 obs config. CPU, one thread, deterministic algorithms: the same frame always gives
the same reply bytes (SYNC SIM determinism). The worker exits on stdin EOF (parent gone: no orphan),
on a malformed request (protocol error line, exit 2) and on SIGTERM.
"""
from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import vision_loc_protocol as vp  # noqa: E402


def _rows(a):
    return [None if not math.isfinite(float(x)) else float(x) for x in a]


def observe(seg, vl, bgr, cols, obs_params):
    """(obs dict at full precision, infer ms) of one own frame."""
    t0 = time.perf_counter()
    probs = seg.probs(bgr)
    und = vl.mp.undistort(bgr) if obs_params.get('refine_px') else None
    obs = vl.column_observations(probs, cols, obs_params, und)
    ms = 1000. * (time.perf_counter() - t0)
    return {'b_kind': [int(k) for k in obs.b_kind], 'b_lo': _rows(obs.b_lo), 'b_hi': _rows(obs.b_hi),
            't_kind': [int(k) for k in obs.t_kind], 't_lo': _rows(obs.t_lo), 't_hi': _rows(obs.t_hi)}, ms


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('--config', type=Path, default=vp.CONFIG_FILE)
    p.add_argument('--checkpoint', type=Path, help='override the configured checkpoint path (hash still checked)')
    args = p.parse_args(argv)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    cfg = vp.load_config(args.config)
    ckpt = Path(args.checkpoint or cfg['model']['checkpoint']).expanduser()
    if vp.file_sha256(ckpt) != cfg['model']['sha256']:
        raise SystemExit(f'{ckpt}: sha256 differs from {cfg["model"]["sha256"]}')
    import cv2
    import numpy as np
    import torch
    torch.set_num_threads(int(cfg['torch_threads']))
    torch.use_deterministic_algorithms(True)
    cv2.setNumThreads(1)
    vl, _ = vp.load_vis3()
    import seg_model                                     # PR #233, hash-checked by load_vis3 (VIS3_DIR on sys.path)
    seg = seg_model.Segmenter(ckpt, cfg['device'], tuple(vp.selected_config()['infer_size']))
    obs_params = vp.obs_params()
    cols = vp.columns()
    ready = {'schema': vp.SCHEMA, 'ready': True, 'runtime_inputs': ['own_bgr'], 'checkpoint_sha256': seg.sha256,
             'config_sha256': vp.file_sha256(vp.VIS3_DIR / 'selected_config_v3.json'), 'obs_params': obs_params,
             'columns': [int(c) for c in cols], 'device': str(seg.dev), 'torch_threads': torch.get_num_threads(),
             'deterministic': bool(torch.are_deterministic_algorithms_enabled()),
             'versions': {'torch': torch.__version__, 'opencv': cv2.__version__, 'numpy': np.__version__,
                          'python': sys.version.split()[0]}}
    print(json.dumps(ready), flush=True)
    for line in sys.stdin:
        try:
            seq, bgr, digest = vp.decode_request(json.loads(line))
        except (ValueError, KeyError, TypeError) as exc:        # malformed request: protocol error, stop
            print(json.dumps({'schema': vp.SCHEMA, 'error': f'{type(exc).__name__}: {exc}'[:500]}), flush=True)
            return 2
        if not np.isfinite(bgr).all() or int(bgr.max()) == int(bgr.min()):
            reply = {'schema': vp.SCHEMA, 'seq': seq, 'bgr_sha256': digest, 'rejected': 'uniform_or_corrupt_frame'}
        else:
            obs, ms = observe(seg, vl, bgr, cols, obs_params)
            reply = vp.obs_reply(seq, digest, obs, ms)
        print(json.dumps(reply, allow_nan=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
