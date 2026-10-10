"""Three preregistered saved-input arms; no renderer or evaluation imports."""
import argparse
import copy
import importlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import time

from harness import pf_sensor_proposal as proposal
from harness.zone_final_pair_binding import bind

HERE = Path(__file__).parent
ARMS = ('n100', 'n500', 'sensor100')


def load(path):
    spec = importlib.util.spec_from_file_location('saved_'+path.stem, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def replay(kind, raw, out, adapter, arm):
    count = 500 if arm == 'n500' else 100
    option = proposal.OPTION if arm == 'sensor100' else 'off'
    before, utc, cpu, loadavg = time.monotonic(), time.time(), time.process_time(), os.getloadavg()
    audit = {}
    try:
        if kind == 'ownmap':
            previous = load(HERE.parent/'s3fix6/replay_ownmap.py')
            population = load(HERE.parent/'s3fix8/particle_count.py')
            for name in ('harness', 'scripts', 'sim'):
                importlib.import_module(name).__path__ = [str(adapter/name)]
            module = importlib.import_module('harness.self_map_rbpf')
            population.install_population(module, count)
            def attach(grid, **kw):
                assert len(grid.poses) == count
                proposal.attach_ownmap(grid, sensor_proposal=option)
                rows = []
                old = grid.resample_if_needed
                def resample():
                    import numpy as np
                    ess = float(1/(grid.weights@grid.weights))
                    value = old()
                    rows.append(dict(t=float(grid.odom.t), n=len(grid.poses),
                        unique=len(np.unique(grid.poses, axis=0)), ess_before=ess))
                    return value
                grid.resample_if_needed = resample
                audit.update(population=rows, proposal=getattr(grid, 'sensor_proposal_audit', None))
                if option != 'off': grid.observation_consistency_audit = grid.sensor_proposal_audit
                return grid
            bind(previous.replay, attach_ownmap=attach)(raw, out, adapter, 'off' if arm == 'n100' else arm)
        else:
            previous = load(HERE.parent/'s3fix6/replay_s3.py')
            def runtime(static, *args, config, **kwargs):
                plain = copy.deepcopy(config)
                plain['options']['observation_consistency'] = 'off'
                rt = previous.Runtime(static, *args, config=plain, **kwargs)
                for rid, own in rt.localizers.items():
                    proposal.attach_s3(own, sensor_proposal=option, tracking_particles=count, static=static)
                    audit[rid] = own.sensor_proposal_audit
                return rt
            bind(previous.replay, Runtime=runtime)(raw, out, 'off')
    finally:
        if out.exists():
            wall = time.monotonic()-before
            elapsed_utc = time.time()-utc
            result = dict(arm=arm, persistent_tracking_particles=count, sensor_proposal=option,
                wall_s=wall, utc_elapsed_s=elapsed_utc, clock_gap_s=elapsed_utc-wall, cpu_s=time.process_time()-cpu,
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                loadavg_start=loadavg, loadavg_end=os.getloadavg(), physics_runs=0,
                gt_inputs=False, audit=audit)
            (out/'proposal-cost.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--kind', choices=['ownmap', 's3'], required=True)
    p.add_argument('--raw', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--adapter', type=Path); p.add_argument('--arm', choices=ARMS, required=True)
    a = p.parse_args(); replay(a.kind, a.raw, a.output, a.adapter, a.arm)
