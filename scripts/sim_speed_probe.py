"""Measurement-only wrapper around the grasp teacher run (no behaviour change).

Counts mj_step / mj_forward / mj_render calls, per-step contacts, constraint rows and
solver iterations, and dumps MuJoCo's own mjData timers at the end. `--cprofile`
additionally writes a pstats file and the top functions. The teacher run itself is
unmodified; this only wraps mujoco entry points.
"""
from __future__ import annotations
import argparse, cProfile, io, json, pstats, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--episode', type=int, default=0)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cap-s', type=float, default=30.)
    p.add_argument('--finish-on-done', action='store_true', help='not a fixed-length probe: stop when the teacher completes (success measurement)')
    p.add_argument('--cprofile', action='store_true')
    p.add_argument('--instrument', action='store_true', help='wrap mj_step to record ncon/nefc/niter (small overhead)')
    p.add_argument('--speed-options', default='', help='forwarded to run() when supported')
    a = p.parse_args()
    import mujoco, numpy as np
    stats = {'calls': {}, 'wall_s': {}}
    last = {}
    series = {'ncon': [], 'nefc': [], 'niter': [], 'nisland': []}

    def wrap(name, record=False):
        original = getattr(mujoco, name)

        def inner(*args, **kwargs):
            at = time.perf_counter()
            result = original(*args, **kwargs)
            stats['wall_s'][name] = stats['wall_s'].get(name, 0.) + time.perf_counter() - at
            stats['calls'][name] = stats['calls'].get(name, 0) + 1
            if record and len(args) >= 2:
                m, d = args[0], args[1]
                last['model'], last['data'] = m, d
                if a.instrument:
                    series['ncon'].append(int(d.ncon))
                    series['nefc'].append(int(d.nefc))
                    series['niter'].append(int(d.solver_niter[0]))
                    series['nisland'].append(int(d.nisland))
            return result
        setattr(mujoco, name, inner)
    wrap('mj_step', True)
    for name in ('mj_forward', 'mj_kinematics', 'mj_camlight', 'mj_comPos', 'mj_render'):
        if hasattr(mujoco, name):
            wrap(name)
    from scripts.run_grasp_act_teacher import run
    plan = json.loads(a.plan.read_text())['episodes'][a.episode]
    import inspect
    kwargs = dict(cap_s=a.cap_s, probe=not a.finish_on_done, teacher_profile='visible_only')
    if 'execution_host' in inspect.signature(run).parameters:
        kwargs['execution_host'] = None
    if a.speed_options:
        kwargs['speed_options'] = a.speed_options
    profiler = cProfile.Profile() if a.cprofile else None
    at = time.perf_counter()
    if profiler:
        profiler.enable()
    try:
        report = run(plan, a.out, **kwargs)
    finally:
        if profiler:
            profiler.disable()
    wall = time.perf_counter() - at
    summary = {'wall_total_s': wall, 'sim_s': report.get('sim_s'), 'wall_per_sim': report.get('wall_per_sim'),
               'physical_success': report.get('physical_success'), 'timings_s': report.get('timings_s'),
               'mujoco_calls': stats['calls'], 'mujoco_wall_s': stats['wall_s']}
    m, d = last.get('model'), last.get('data')
    if m is not None:
        names = [n for n in dir(mujoco.mjtTimer) if n.startswith('mjTIMER_') and n != 'mjTIMER_NUM']
        timers = {}
        for n in names:
            idx = int(getattr(mujoco.mjtTimer, n))
            t = d.timer[idx]
            timers[n] = {'duration_s': float(t.duration), 'number': int(t.number)}
        summary['mjdata_timers'] = timers
        summary['model'] = {'timestep': float(m.opt.timestep), 'integrator': int(m.opt.integrator),
                            'solver': int(m.opt.solver), 'iterations': int(m.opt.iterations), 'tolerance': float(m.opt.tolerance),
                            'noslip_iterations': int(m.opt.noslip_iterations), 'cone': int(m.opt.cone), 'impratio': float(m.opt.impratio),
                            'nbody': int(m.nbody), 'ngeom': int(m.ngeom), 'njnt': int(m.njnt), 'nv': int(m.nv), 'nu': int(m.nu),
                            'nmesh': int(m.nmesh), 'npair': int(m.npair), 'nexclude': int(m.nexclude), 'nu_': int(m.nu),
                            'opt_flags_disable': int(m.opt.disableflags), 'opt_flags_enable': int(m.opt.enableflags),
                            'ccd_iterations': int(m.opt.ccd_iterations), 'ccd_tolerance': float(m.opt.ccd_tolerance),
                            'sleep_enabled': bool(m.opt.enableflags & (1 << 5)) if False else None}
    if series['ncon']:
        def q(x):
            arr = np.asarray(x)
            return {'mean': float(arr.mean()), 'p50': float(np.percentile(arr, 50)), 'p95': float(np.percentile(arr, 95)), 'max': float(arr.max())}
        summary['per_step'] = {k: q(v) for k, v in series.items()}
        summary['steps_recorded'] = len(series['ncon'])
    if profiler:
        s = io.StringIO()
        ps = pstats.Stats(profiler, stream=s).sort_stats('tottime')
        ps.print_stats(30)
        summary['cprofile_tottime_top30'] = s.getvalue()
        s = io.StringIO()
        pstats.Stats(profiler, stream=s).sort_stats('cumulative').print_stats(35)
        summary['cprofile_cumulative_top35'] = s.getvalue()
    (a.out.parent / (a.out.name + '-probe.json')).write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps({k: summary[k] for k in ('wall_total_s', 'sim_s', 'wall_per_sim', 'physical_success', 'timings_s')}, default=str))


if __name__ == '__main__':
    main()
