"""Torch-free stand-in of ``scripts/vision_loc_worker.py`` for the subprocess tests (not a test module).

Speaks the real protocol (``harness.vision_loc_protocol``) with a fixed observation, so the real
``VisionWorkerClient`` pipes, timeouts, kill and EOF paths run in CI. ``--mode``:
ok | die_after:N | hang_after:N | garbage_after:N | error_after:N | wrong_seq | reject | no_ready | bad_ready
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from harness import vision_loc_protocol as vp  # noqa: E402


def ready(cfg, **over):
    row = {'schema': vp.SCHEMA, 'ready': True, 'runtime_inputs': ['own_bgr'],
           'checkpoint_sha256': cfg['model']['sha256'], 'config_sha256': vp.prereg_student()['config']['sha256'],
           'obs_params': vp.obs_params(), 'columns': [int(c) for c in vp.columns()], 'device': 'cpu',
           'torch_threads': 1, 'deterministic': True, 'versions': {'fake': True}}
    row.update(over)
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', default='ok')
    p.add_argument('--pid-file')
    args = p.parse_args()
    if args.pid_file:
        Path(args.pid_file).write_text(str(os.getpid()))
    cfg = vp.load_config()
    mode, _, n = args.mode.partition(':')
    n = int(n or 0)
    if mode == 'no_ready':
        time.sleep(60)
        return 0
    print(json.dumps(ready(cfg, checkpoint_sha256='0' * 64) if mode == 'bad_ready' else ready(cfg)), flush=True)
    cols = len(vp.columns())
    obs = {'b_kind': [1] * cols, 'b_lo': [300.] * cols, 'b_hi': [300.] * cols,
           't_kind': [0] * cols, 't_lo': [None] * cols, 't_hi': [None] * cols}
    for k, line in enumerate(sys.stdin):
        seq, _, digest = vp.decode_request(json.loads(line))
        if k >= n and mode == 'die_after':
            os._exit(3)
        if k >= n and mode == 'hang_after':
            time.sleep(60)
        if k >= n and mode == 'garbage_after':
            print('not json', flush=True)
            continue
        if k >= n and mode == 'error_after':
            print(json.dumps({'schema': vp.SCHEMA, 'error': 'fixture error'}), flush=True)
            continue
        if mode == 'reject':
            print(json.dumps({'schema': vp.SCHEMA, 'seq': seq, 'bgr_sha256': digest, 'rejected': 'fixture'}), flush=True)
            continue
        print(json.dumps(vp.obs_reply(seq + 1 if mode == 'wrong_seq' else seq, digest, obs, 1.)), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
