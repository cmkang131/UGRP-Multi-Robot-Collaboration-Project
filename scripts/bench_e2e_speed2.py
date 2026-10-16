"""Function-level micro-benchmark for the round-2 exact toggles (Mac, no sim).

Inputs are captured from the fixed saved-frame receive replay with the toggles
off (v200 base), then each function is re-run on deep copies with the toggle
off and on. Outputs (return value plus every mutated container, pickled so
set/dict iteration order is compared) must be byte-identical. Timing is the
minimum of ``--repeat`` runs per input, summed over inputs.
"""
import argparse
import copy
import json
import pickle
import time
from pathlib import Path

import numpy as np

from scripts.replay_e2e_receive_speed import V200, load_frames, replay


def captured(frames, limit):
    import harness.public_navigation_raytrace as pr
    import harness.public_navigation_unknown as pu
    import harness.e2e_own_inputs as own
    import harness.active_wall_vision as awv
    store = dict(rays=[], costmap=[], scan=[], wall=[])
    original = dict(rays=pr.receive_rays, costmap=pu.from_observed_grid, scan=own.scan, observe=awv.observe)

    def keep(name, value):
        if len(store[name]) < limit:
            store[name].append(copy.deepcopy(value))

    def receive_rays(grid, latest, static_hits, observation, pose):
        keep('rays', (grid, latest, static_hits, observation, pose))
        return original['rays'](grid, latest, static_hits, observation, pose)

    def from_observed_grid(grid, pose, latest, static_hits):
        keep('costmap', (grid, pose, latest, static_hits))
        return original['costmap'](grid, pose, latest, static_hits)

    def scan(value, path='input'):
        if path == 'input':
            keep('scan', value)
        return original['scan'](value, path)

    def observe(rgb, servo, **kwargs):
        keep('wall', (rgb, dict(servo), kwargs))
        return original['observe'](rgb, servo, **kwargs)

    patched = [(pr, 'receive_rays', receive_rays), (pu, 'from_observed_grid', from_observed_grid),
               (own, 'scan', scan), (awv, 'observe', observe)]
    import harness.active_wall_mapping as awm
    import harness.self_map_closed_loop as smcl
    import harness.e2e_live_mapping as elm
    for module in (awm, smcl):
        if getattr(module, 'receive_rays', None) is original['rays']:
            patched.append((module, 'receive_rays', receive_rays))
    if getattr(elm, 'observe', None) is original['observe']:
        patched.append((elm, 'observe', observe))
    for module in list(__import__('sys').modules.values()):
        if module is None or not getattr(module, '__name__', '').startswith('harness.'):
            continue
        for name, fn in (('receive_rays', receive_rays), ('from_observed_grid', from_observed_grid)):
            if getattr(module, name, None) is original['rays' if name == 'receive_rays' else 'costmap']:
                patched.append((module, name, fn))
    saved = [(m, n, getattr(m, n)) for m, n, _ in patched]
    try:
        for m, n, fn in patched:
            setattr(m, n, fn)
        replay(frames, dict(V200))
    finally:
        for m, n, fn in saved:
            setattr(m, n, fn)
    return store


def timed(fn, inputs, options, repeat):
    from harness.e2e_exact_speedups import Options, using
    total, outputs = 0., []
    for item in inputs:
        best = None
        for _ in range(repeat):
            args = copy.deepcopy(item)
            with using(Options(**options)):
                start = time.perf_counter()
                result = fn(args)
                elapsed = time.perf_counter()-start
            best = elapsed if best is None else min(best, elapsed)
        total += best
        outputs.append(pickle.dumps(result, protocol=5))
    return total, outputs


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--frames', action='append', required=True)
    p.add_argument('--limit', type=int, default=60)
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--output', required=True)
    a = p.parse_args(argv)
    import os
    os.environ.setdefault('UGRP_CONTROLLER_VISIBILITY_SPEEDUPS', 'shared-v1')
    frames = load_frames(a.frames)
    store = captured(frames, a.limit)
    from harness.public_navigation_raytrace import receive_rays
    from harness.public_navigation_unknown import from_observed_grid
    from harness.e2e_own_inputs import scan
    from harness.active_wall_vision import observe
    from harness.self_wall_segment_points import contact_points
    import harness.e2e_exact_speedups2 as s2

    def rays(args):
        grid, latest, static_hits, observation, pose = args
        out = receive_rays(grid, latest, static_hits, observation, pose)
        return out, grid.__dict__, latest

    def costmap(args):
        c = from_observed_grid(*args)
        return c.costs, c.__dict__

    def scanned(args):
        return scan(args)

    def wall_pair(args):
        rgb, servo, kwargs = args
        s2._FRONTEND.clear()  # only the same-frame pair may share work
        return observe(rgb, servo, **kwargs), contact_points(rgb, servo)

    cases = dict(rays=(rays, 'vector_rays'), costmap=(costmap, 'vector_costmap_writes'),
                 scan=(scanned, 'lazy_scan_path'), wall=(wall_pair, 'shared_wall_frontend'))
    result = {}
    # floor_goal_v3 track cells: the v200 replay profile has 47 updates of ~72k
    # cells (3,384,082 genexpr calls); same-size synthetic integer cells.
    rng = np.random.default_rng(7)
    track_inputs = [np.floor(rng.normal(scale=40., size=(72000, 2))).astype(int) for _ in range(5)]
    import harness.floor_goal_v3 as v3

    def track(cells):
        target = set()
        if v3.track_cells_enabled() and cells.ndim == 2 and cells.shape[1] == 2:
            target.update(zip(cells[:, 0], cells[:, 1]))
        else:
            target.update(tuple(x) for x in cells)
        return [tuple(map(type, c)) + c for c in target]
    store['track'] = track_inputs
    cases['track'] = (track, 'track_cell_tuples')
    for name, (fn, toggle) in cases.items():
        inputs = store[name]
        off_s, off = timed(fn, inputs, dict(V200), a.repeat)
        on_s, on = timed(fn, inputs, {**V200, toggle: True}, a.repeat)
        result[name] = dict(toggle=toggle, inputs=len(inputs), identical=sum(x == y for x, y in zip(off, on)),
                            off_s=off_s, on_s=on_s, off_ms_per_call=1e3*off_s/max(len(inputs), 1),
                            on_ms_per_call=1e3*on_s/max(len(inputs), 1),
                            saved_ms_per_call=1e3*(off_s-on_s)/max(len(inputs), 1),
                            reduction_pct=100*(1-on_s/off_s) if off_s else None)
        print(name, json.dumps(result[name]))
    Path(a.output).write_text(json.dumps(dict(schema='ugrp.e2e_speed2_bench.v1', limit=a.limit,
                                              repeat=a.repeat, cases=result), indent=1))


if __name__ == '__main__':
    main()
