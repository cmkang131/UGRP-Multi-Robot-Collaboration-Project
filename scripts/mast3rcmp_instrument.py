"""Generate a new audited headless entry point from pinned upstream main.py.

MASt3R-SLAM e6f4e3d (Murai, Dexheimer, Davison), CC BY-NC-SA 4.0.
Algorithms/thresholds stay upstream; only observation logging and output change.
Never modifies the upstream source. Run the generated file from its repo root.
"""
import argparse
import hashlib
from pathlib import Path

UPSTREAM_SHA = 'e6f4e3d474fad0e11f561482012be864ba8c3f17'
MAIN_SHA256 = '354cc6930f23daa2c7761bc1fc75f29b8c63d13acb78e2b8b7432b674012ba79'


def instrument(src, output):
    text = Path(src).read_text()
    if hashlib.sha256(Path(src).read_bytes()).hexdigest() != MAIN_SHA256:
        raise ValueError('upstream_main_sha256_mismatch')
    changes = [
        ('from mast3r_slam.visualization import WindowMsg, run_visualization',
         'from mast3rcmp_probe import WindowMsg, Probe\n'
         'def run_visualization(*args):\n    raise RuntimeError("headless_only")'),
        ('    keyframes = SharedKeyframes(manager, h, w)',
         '    probe = Probe()\n    keyframes = SharedKeyframes(manager, h, w)'),
        ('        timestamp, img = dataset[i]',
         '        timestamp, img = dataset[i]\n        probe.begin(i, timestamp)'),
        ('            states.set_frame(frame)\n            i += 1',
         '            states.set_frame(frame)\n            probe.end(frame, "initialized", keyframes, K)\n            i += 1'),
        ('            add_new_kf, match_info, try_reloc = tracker.track(frame)',
         '            add_new_kf, match_info, try_reloc = tracker.track(frame)\n'
         '            probe.end(frame, "tracking_failed" if try_reloc else "tracked", keyframes, K)'),
        ('        elif mode == Mode.RELOC:',
         '        elif mode == Mode.RELOC:\n            add_new_kf = False'),
        ('        else:\n            raise Exception("Invalid mode")',
         '            probe.end(states.get_frame(), "relocalized" if states.get_mode() == Mode.TRACKING else "relocalization_failed", keyframes, K)\n'
         '        else:\n            raise Exception("Invalid mode")'),
        ('    if dataset.save_results:\n        save_dir, seq_name = eval.prepare_savedir(args, dataset)\n        eval.save_traj',
         '    probe.finish(keyframes)\n    if False:  # dense output is in the probe; no GUI/reconstruction exports\n        save_dir, seq_name = eval.prepare_savedir(args, dataset)\n        eval.save_traj'),
    ]
    for old, new in changes:
        if text.count(old) != 1:
            raise ValueError(f'upstream_anchor_count:{old!r}:{text.count(old)}')
        text = text.replace(old, new)
    output = Path(output)
    with output.open('x') as handle:
        handle.write(text)
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source')
    p.add_argument('output')
    a=p.parse_args()
    print(instrument(a.source,a.output))
