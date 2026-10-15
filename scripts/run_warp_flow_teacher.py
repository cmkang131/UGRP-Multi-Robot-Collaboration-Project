"""Default-off, finite gcp2 beampair6 client of the shared warp1 backend."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--physics-backend', choices=['off', 'mjwarp_batch_v1', 'c_pilot_v1'], default='off')
    p.add_argument('--adapter-source', type=Path, required=True)
    p.add_argument('--teacher-source', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--episode', type=int, default=0)
    p.add_argument('--nworld', type=int, choices=[1, 16, 64, 256], default=1)
    p.add_argument('--cap-s', type=float, default=60.)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--compiled-reference-v1', type=Path)
    p.add_argument('--compiled-geometry-312-v1', type=Path)
    p.add_argument('--export-compiled-only', action='store_true')
    p.add_argument('--vm-hourly-usd', type=float, required=True)
    return p


def require_source(path, expected):
    if subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip() != expected:
        raise ValueError('exact frozen source required: '+expected)
    if subprocess.check_output(['git', '-C', str(path), 'status', '--porcelain', '--untracked-files=no']):
        raise ValueError('clean frozen source required')


def main():
    p = parser(); a = p.parse_args()
    if a.physics_backend == 'off' or platform.system() != 'Linux':
        p.error('explicit Linux gcp2 backend opt-in required; Mac physics/render forbidden')
    if not 0 < a.cap_s <= 60 or not 0 < a.vm_hourly_usd < float('inf'):
        p.error('finite existing 60 SIM second cap and explicit positive price required')
    from simalt_host import gcp2_identity
    host = gcp2_identity()
    if a.physics_backend == 'mjwarp_batch_v1' and host['instance'] != 'ugrp-act-l4-gcp2':
        p.error('existing gcp2 L4 required')
    if a.physics_backend == 'c_pilot_v1' and a.nworld != 1:
        p.error('CPU concurrency uses separate N1 processes')
    from warp_flow_episode import ADAPTER_SHA, TEACHER_SHA, make_lane
    require_source(a.adapter_source, ADAPTER_SHA)
    require_source(a.teacher_source, TEACHER_SHA)
    source = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    require_source(ROOT, source)
    plans = json.loads(a.plan.read_text())
    plan = plans['episodes'][a.episode]
    if plan['seed'] not in (8318726, 8318620, 8318600, 8318604, 8318611, 8318631):
        p.error('known beampair6 development six only; gate queue is HOLD_SCENE')
    import numpy as np
    import mujoco
    from warp_act_backend import CTransport, WarpTransport
    a.out.mkdir(parents=True, exist_ok=False)
    report = dict(schema='ugrp.warp2.batch.v1', status='running', source_sha=source,
        adapter_sha=ADAPTER_SHA, teacher_sha=TEACHER_SHA, physics_backend=a.physics_backend,
        host=host, nworld=a.nworld, seed=plan['seed'], cap_s=a.cap_s,
        plan_sha256=hashlib.sha256(a.plan.read_bytes()).hexdigest(), mujoco=mujoco.__version__,
        gate_eligible=False, scene_status='HOLD_SCENE', training_rgb=False, student_execution=False,
        model_calls=0, backend_results_pooled=False, hourly_usd=a.vm_hourly_usd,
        price_basis='explicit VM hourly estimate; billing and independent cost attribution unverified',
        reproduce=sys.argv, counts=dict(planned=a.nworld, started=0, completed=0, physical_success=0,
            cap_end=0, HOST_ERROR=0, unstarted=a.nworld))
    write(a.out/'summary.json', report)
    hooks = (WarpTransport if a.physics_backend == 'mjwarp_batch_v1' else CTransport)(host, source, a.physics_backend, a.out)
    lanes, bridges, contexts, results = [], [], [], {}
    active = np.ones(a.nworld, dtype=bool)
    ticks = np.zeros(a.nworld, dtype=int)
    start = time.perf_counter(); loop_start = None
    try:
        for i in range(a.nworld):
            lane, bridge = make_lane(a.adapter_source, a.teacher_source, plan, a.out/f'world-{i:03d}', hooks, i, a.cap_s)
            lanes.append(lane); bridges.append(bridge)
            setup = next(lane)
            if setup['kind'] != 'setup':
                raise RuntimeError('initial setup barrier required')
            contexts.append(setup)
            report['counts']['started'] += 1
        if a.export_compiled_only:
            from simalt_compiled_compat import export_reference, export_geometry
            if mujoco.__version__ != '3.12.0':
                raise ValueError('reference export requires existing C3.12 environment')
            xml = a.out/'runtime-scene.xml'; xml.write_text(contexts[0]['world'].scene_xml)
            export_reference(contexts[0]['world'].model, xml, mujoco.__version__, a.out/'compiled-312.json')
            export_geometry(contexts[0]['world'].model, xml, mujoco.__version__, a.out/'compiled-geometry312.npz')
            report.update(status='compiled_export_only', physics_steps=0)
            return
        if a.physics_backend == 'mjwarp_batch_v1':
            hooks.initialize(contexts, compiled_reference=a.compiled_reference_v1,
                compiled_geometry=a.compiled_geometry_312_v1)
            report.update(camera=hooks.camera, compatibility=hooks.compat, capacities=hooks.capacities)
        report['setup_compile_s'] = time.perf_counter()-start
        loop_start = time.perf_counter()
        while active.any():
            at = time.perf_counter()
            for i in np.flatnonzero(active):
                try:
                    row = next(lanes[i])
                    if row['kind'] != 'step':
                        raise RuntimeError('physics barrier required')
                    ticks[i] += 1
                except StopIteration as done:
                    results[int(i)] = done.value
                    active[i] = False
            hooks.seconds['teacher_visibility_eval_recording'] += time.perf_counter()-at
            if active.any():
                hooks.step(contexts, active)
            write(a.out/'progress.json', dict(ticks=ticks.tolist(), active=int(active.sum()),
                loop_wall_s=time.perf_counter()-loop_start, timing=dict(hooks.seconds)))
        report['status'] = 'complete'
    except BaseException as error:
        report.update(status='HOST_ERROR', error_type=type(error).__name__, error=str(error),
            traceback=traceback.format_exc())
        raise
    finally:
        close_errors = []
        for lane in lanes:
            try:
                lane.close()
            except BaseException as error:
                close_errors.append(dict(type=type(error).__name__, error=str(error)))
        hooks.save_states()
        wall = time.perf_counter()-start
        loop = time.perf_counter()-loop_start if loop_start is not None else None
        worlds = []
        for i, result in sorted(results.items()):
            cap = not result['physical_success'] and result['sim_s'] >= a.cap_s-1e-8  # frozen runner grid epsilon
            worlds.append(dict(world=i, physical_success=result['physical_success'], cap_end=bool(cap),
                sim_s=result['sim_s'], joint_held=result['joint_held'], input_audit=result['input_audit']))
        sim = sum(r['sim_s'] for r in worlds)
        report['counts'].update(completed=len(worlds), physical_success=sum(r['physical_success'] for r in worlds),
            cap_end=sum(r['cap_end'] for r in worlds), HOST_ERROR=int(report['status'] == 'HOST_ERROR'),
            unstarted=a.nworld-report['counts']['started'])
        report.update(worlds=worlds, wall_s=wall, loop_wall_s=loop,
            aggregate_completed_sim_s=sim, timing=dict(hooks.seconds), close_errors=close_errors,
            transforms=[b.transforms for b in bridges],
            vm_cost_estimate_usd=wall*a.vm_hourly_usd/3600,
            sim_s_per_wall_s=sim/loop if loop else None, end_to_end_sim_s_per_wall_s=sim/wall,
            sim_s_per_usd=sim/(wall*a.vm_hourly_usd/3600))
        rejections = Counter('cap_end' if r['cap_end'] else 'teacher_failure'
                             for r in worlds if not r['physical_success'])
        if report['status'] == 'HOST_ERROR':
            rejections[report.get('error_type', 'HOST_ERROR')] += 1
        table = dict(population='worlds_one_replicated_development_seed', raw=str(a.out), reproduce=sys.argv,
            funnel=[dict(stage='requested', passed_cumulative_N=a.nworld, rejected_N=0),
                    dict(stage='setup', passed_cumulative_N=len(contexts), rejected_N=a.nworld-len(contexts)),
                    dict(stage='returned', passed_cumulative_N=len(worlds), rejected_N=len(contexts)-len(worlds)),
                    dict(stage='physical_success', passed_cumulative_N=report['counts']['physical_success'],
                         rejected_N=len(worlds)-report['counts']['physical_success'])],
            rejections=[dict(reason_category=k, blocked_object='software:'+k if report['status']=='HOST_ERROR' else 'none:unattributed',
                min_gap_m=None, gap_scope='no geometric cause attributed; inspect frozen candidate ledger', count=v)
                for k, v in rejections.items()])
        write(a.out/'rejection_table.json', table)
        report['rejection_table'] = str(a.out/'rejection_table.json')
        report['sha256'] = {str(f.relative_to(a.out)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in a.out.rglob('*') if f.is_file() and f.name != 'summary.json'}
        write(a.out/'summary.json', report)
    print(json.dumps({k: report[k] for k in ('status', 'seed', 'nworld', 'counts', 'wall_s', 'sim_s_per_wall_s', 'sim_s_per_usd')}))


if __name__ == '__main__':
    main()
