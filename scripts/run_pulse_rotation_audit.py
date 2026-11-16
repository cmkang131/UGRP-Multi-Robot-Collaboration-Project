"""Preregistered egomap32 clock-only bilateral pulse measurements; no GT feedback."""
import argparse
import json
import os
from pathlib import Path
from time import monotonic
from scripts.run_active_wall_nav2 import frozen_bundle, verify_source, dump
from scripts.run_wall_servo_stiffness import arm
from scripts.run_wall_parallax_strafe import sha

ROOT = Path(__file__).resolve().parents[1]
RAW = Path('/Users/changmin/projects/ugrp/outputs/pulse-rotation-audit-v1')


def schedule():
    """Integer 20Hz ticks, fixed beforehand; 5 repetitions per direction/mode."""
    tick = 40
    blocks, commands = [], {}
    for rep in range(1, 6):
        cells = [('single', 1, 1), ('single', -1, 1),
                 ('continuous', 1, 10), ('continuous', -1, 10)]
        if rep % 2 == 0:
            cells.reverse()
        for mode, sign, pulses in cells:
            blocks.append(dict(repeat=rep, mode=mode, sign=sign, pulses=pulses,
                               start_tick=tick, end_tick=tick + 4*pulses,
                               split='fit' if rep <= 3 else 'check'))
            for j in range(pulses):
                commands[tick + 4*j] = dict(kind='mecanum', forward=0., left=0.,
                                             turn=sign*.35, duration_s=.10)
            tick += 4*pulses + 36  # 1.8 seconds after the final full .20s cycle
    return blocks, commands, tick


def acquire(out, source, backend_factory):
    blocks, commands, ticks = schedule()
    bundle = frozen_bundle('rotation-audit', source)
    bundle.update(execution_bundle_id='egomap32-rotation-audit-v1', check='pulse-rotation-audit',
                  case='rotation-audit', case_cap_s=ticks/20, capture_s=1.)
    bundle['task']['seed'] = 32001
    bundle['acquisition'] = 'clock-only rotation diagnostic; no exploration policy'
    out.mkdir(parents=True, exist_ok=False)
    dump(out/'bundle.json', bundle)
    dump(out/'schedule.json', dict(blocks=blocks, commands=commands, ticks=ticks))
    result = dict(status='HOST_ERROR', source_sha=source, model_calls=0, freeze=False,
                  loadavg_start=list(os.getloadavg()), seed=32001)
    started = monotonic()
    backend = None
    try:
        backend = backend_factory(bundle, out, seed=32001)
        backend.reset(5.)
        start = backend.now
        result['start_sim_s'] = start
        backend.set_deadline(round(start + ticks/20, 9))
        for a in arm(bundle['initial_servo']):
            backend.issue('r3', a)
        for tick in range(ticks + 1):
            if tick in commands:
                backend.issue('r3', commands[tick])
            if tick % 20 == 0:
                backend.capture()
            backend.eval_sample()  # ignored return; safety may only abort
            if tick % 100 == 0:
                print('rotation SIM', tick/20, flush=True)
                dump(out/'progress.json', dict(sim_s=tick/20))
            if monotonic() - started > 900:
                raise TimeoutError('HOST_BUDGET_15_MINUTES')
            if tick < ticks:
                backend.advance_to(round(start + (tick + 1)/20, 9))
        result.update(status='RECORDED', total_sim_s=backend.now,
                      samples=ticks + 1, frames=ticks//20 + 1, blocks=len(blocks), pulses=len(commands))
    except Exception as e:
        result.update(status='PHYSICAL_FAILURE' if type(e).__name__ == 'PhysicalStop' else 'HOST_ERROR',
                      failure=dict(type=type(e).__name__, message=str(e)), enospc=getattr(e,'errno',None)==28)
        import traceback
        traceback.print_exc()
    finally:
        if backend is not None:
            backend.close()
        result.update(wall_s=monotonic()-started, loadavg_end=list(os.getloadavg()))
        dump(out/'result.json', result)
        dump(out/'artifacts.sha256.json', {str(p.relative_to(out)):sha(p)
             for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--execute',action='store_true')
    args=p.parse_args()
    receipt=verify_source(args.expected_source_sha)
    assert args.output.resolve()==RAW/'measurement' and not args.output.exists()
    if not args.execute:
        return 0
    from scripts.agent_lock import DEFAULT_ROOT,status,acquire as take,release
    assert status(DEFAULT_ROOT) is None,'physics lock occupied'
    lock=take(DEFAULT_ROOT,owner='codex',branch='claude/ego-wall-map',
              purpose='egomap32 bilateral v122 rotation measurement',pid=os.getpid(),expected_minutes=15)
    try:
        import signal
        def timeout(*_):
            raise TimeoutError('HOST_BUDGET_15_MINUTES')
        signal.signal(signal.SIGALRM,timeout)
        signal.setitimer(signal.ITIMER_REAL,900)
        from sim.pulse_rotation_audit import PhysicsBackend
        result=acquire(args.output,args.expected_source_sha,PhysicsBackend)
        dump(args.output/'source-admission.json',receipt)
        dump(args.output/'lock.json',lock)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        release(DEFAULT_ROOT,owner='codex')
    print(json.dumps(result),flush=True)
    return 0 if result['status']=='RECORDED' else 1


if __name__=='__main__':
    raise SystemExit(main())
