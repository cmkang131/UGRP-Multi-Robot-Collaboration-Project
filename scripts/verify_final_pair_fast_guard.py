"""Offline v88 raw replay / CPU microbenchmark of v91's guard, never renders.

No collection is started. Full recorded qpos/qvel rows are installed into the
same non-rendering v88 model and mj_kinematics refreshes geometry. Sampling is
50 ms, not a reconstruction of the intervening 0.25 ms physics substeps.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import time
from types import SimpleNamespace

import numpy as np

from sim.final_pair_v3 import PhysicsBackend as Old, make_scene
from sim.final_pair_fast import PhysicsBackend as New

RAW_ROOT = Path('/Users/changmin/projects/ugrp/outputs')
RAW_CASES = (
    RAW_ROOT / 'final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded/zone_wide_two_doors_final_v3',
    RAW_ROOT / 'final-pair-v88-cal-747d2b9f-20261001-r6/calibration-fine/zone_wide_two_doors_final_v3',
)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def observer(cls, bundle, scene, world):
    obj = cls.__new__(cls)
    obj.bundle, obj.scene, obj.world = bundle, scene, world
    obj._last_guard_xy, obj.saved, obj.held = {}, [], []
    obj.ports = {rid: SimpleNamespace(hold=lambda t, rid=rid: obj.held.append((rid, t)))
                 for rid in ('r1', 'r2', 'r3')}
    obj._append = lambda path, row: obj.saved.append((path, row))
    return obj


def outcome(obj):
    obj.saved.clear()
    obj.held.clear()
    reason = None
    try:
        obj.collection_guard()
    except Exception as exc:
        reason = (type(exc).__name__, str(exc))
    minimum = getattr(obj, '_clearance_min', None)
    return {'exception': reason, 'minimum_hex': None if minimum is None else float(minimum).hex(),
            'abort_records': obj.saved.copy(), 'holds': obj.held.copy(),
            'previous_xy_hex': {k: v.tobytes().hex() for k, v in obj._last_guard_xy.items()}}


def benchmark(old, new, *, repeats=7, calls=300):
    """Process CPU time excludes descheduling by the ongoing r8 collection."""
    old.collection_guard()
    new.collection_guard()
    times = {'old': [], 'new': []}
    for repeat in range(repeats):
        for key, obj in ([('old', old), ('new', new)] if repeat % 2 == 0 else
                         [('new', new), ('old', old)]):
            start = time.process_time_ns()
            for _ in range(calls):
                obj.collection_guard()
            times[key].append((time.process_time_ns()-start)/calls)
    medians = {k: statistics.median(v) for k, v in times.items()}
    return {'clock': 'process_time_ns', 'calls_per_repeat': calls, 'repeats': repeats,
            'ns_per_call': times, 'median_ns_per_call': medians,
            'speedup': medians['old']/medians['new'],
            'qualification': 'offline CPU microbenchmark; no exclusive wall-time or collection throughput claim'}


def replay(case, *, measure=False):
    import mujoco
    from sim.zone_final_v3_scene import build_world
    case = Path(case)
    trajectory = case / 'eval_only/trajectory.jsonl'
    bundle = json.loads((case/'bundle.json').read_text())
    assert json.loads((case/'result.json').read_text())['protocol_complete']
    scene = make_scene(bundle, seed=911)
    load_start = list(os.getloadavg())
    world = build_world(scene, bundle['contact_profile'], seed=911, render=False,
        warehouse_layout=scene.engine_layout, warehouse_cargo_ids=None)
    old, new = [observer(cls, bundle, scene, world) for cls in (Old, New)]
    sequential = [observer(cls, bundle, scene, world) for cls in (Old, New)]
    count, aborts, sequential_aborts, first = 0, {}, {}, None
    minima = hashlib.sha256()
    try:
        assert world.renderer is None
        with trajectory.open() as stream:
            for line in stream:
                row = json.loads(line)
                assert len(row['qpos']) == world.model.nq and len(row['qvel']) == world.model.nv
                world.data.qpos[:] = row['qpos']
                world.data.qvel[:] = row['qvel']
                world.data.time = row['t']
                mujoco.mj_kinematics(world.model, world.data)
                # There is no previous 0.25 ms substep in this 50 ms log. Clear
                # only displacement history to compare each row's full wall /
                # envelope / recorded-minimum output, not stale minima after
                # the first downsample-induced displacement trip.
                old._last_guard_xy.clear()
                new._last_guard_xy.clear()
                a, b = outcome(old), outcome(new)
                assert a == b, (count, a, b)
                minima.update((str(a['minimum_hex'])+'\n').encode())
                if a['exception']:
                    reason = a['exception'][1]
                    aborts[reason] = aborts.get(reason, 0)+1
                sa, sb = [outcome(obj) for obj in sequential]
                assert sa == sb, (count, sa, sb)
                if sa['exception']:
                    reason = sa['exception'][1]
                    sequential_aborts[reason] = sequential_aborts.get(reason, 0)+1
                first = first or row
                count += 1
        assert count > 0
        result = {'case': str(case), 'check': bundle['check'], 'rows': count,
                  'nq': world.model.nq, 'nv': world.model.nv, 'ngeom': world.model.ngeom,
                  'exact_guard_matches': count, 'mismatches': 0, 'abort_counts': aborts,
                  'clearance_min_series_sha256': minima.hexdigest(),
                  'sequential_guard_matches': count, 'sequential_abort_counts': sequential_aborts,
                  'trajectory_sha256': digest(trajectory), 'bundle_sha256': digest(case/'bundle.json'),
                  'result_sha256': digest(case/'result.json'),
                  'render': False, 'loadavg_start': load_start,
                  'scope': 'each full row independently, plus separate sequential state; no intermediate substep reconstruction',
                  'sequential_caveat': '50 ms samples can exceed 0.25 ms displacement bound; post-abort history stays frozen, so trips cascade. These are synthetic comparisons, not collection failures.'}
        if measure:
            world.data.qpos[:] = first['qpos']
            world.data.qvel[:] = first['qvel']
            world.data.time = first['t']
            mujoco.mj_kinematics(world.model, world.data)
            old._last_guard_xy.clear()
            new._last_guard_xy.clear()
            result['benchmark'] = benchmark(old, new)
        result['loadavg_end'] = list(os.getloadavg())
        return result
    finally:
        world.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args(argv)
    import mujoco
    report = {'python': platform.python_version(), 'platform': platform.platform(),
              'numpy': np.__version__, 'mujoco': mujoco.__version__, 'cases': []}
    for case in RAW_CASES:
        report['cases'].append(replay(case, measure=args.benchmark))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
