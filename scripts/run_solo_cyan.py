"""Managed S2 solo cyan DEV adapter. No physics is imported before --execute admission."""
from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from harness import zone_solo_cyan_contract_v106 as contract
from harness.zone_solo_cyan_v106 import Runtime
from scripts.run_final_environment_checks import check_source, write


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--admission', choices=('dev-pilot',), default='dev-pilot')
    p.add_argument('--seed', type=int, choices=contract.DEV_SEEDS, default=911)
    p.add_argument('--robot-id', choices=('r1', 'r2', 'r3'), default='r3')
    p.add_argument('--pickup-slot', default='P1-2')
    p.add_argument('--destination', choices=('A', 'B', 'C'), default='B')
    p.add_argument('--passage-id', default='door_1')
    p.add_argument('--stage-probe', choices=('pick', 'door', 'place'), default='place')
    p.add_argument('--speedups', choices=('none', 'v98-exact-v6'), default='v98-exact-v6')
    p.add_argument('--lock-owner', choices=('codex', 'claude', 'kiro'), default='claude')
    p.add_argument('--sim-slot')
    return p


def stage_reached(runtime, stage):
    if stage == 'pick':
        return any(e['event'] == 'high_carry_pose' for e in runtime.events)
    if stage == 'door':
        # A fresh relook can advance route_i before the floor-resting box is
        # regrasped. Wait for the existing HIGH sequence to finish; own command
        # state only, with actual lifting still checked by the post-run judge.
        return (runtime.route_i >= 2 and runtime.state == 'carry'
                and not runtime.regrasp and runtime.beam_grasp_confirmed)
    return runtime.state == 'done'


def run(bundle, out, *, stage='place', runtime_factory=Runtime, backend_factory=None):
    """Finite loop; only own frames and issued commands enter runtime_factory."""
    if backend_factory is None:
        from sim.solo_cyan_v106 import PhysicsBackend
        backend_factory = PhysicsBackend
    from sim.solo_cyan_v106 import evaluate
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'bundle.json', bundle)
    result = {'execution_bundle_id': contract.BUNDLE_ID, 'source_sha': bundle['source_sha'],
        'status': 'HOST_ERROR', 'cohort_role': 'FUNCTIONAL_DEV', 'stage_probe': stage,
        'research_result': False, 'physical_success': None, 'loadavg_start': list(os.getloadavg()),
        'model_calls': 0, 'commands_issued': 0, 'in_run_drop_tilt_contact_detection': False}
    backend = runtime = None
    try:
        backend = backend_factory(bundle, out, seed=bundle['task']['seed'])
        reset = backend.reset(5.)
        if not 0 <= reset <= 5.+1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start+bundle['case_cap_s'])
        static = contract.hp.resolve(contract.MAP_ID)[0]
        runtime = runtime_factory(static, contract.ROOT/contract.CALIBRATION, contract.CALIBRATION_SHA,
                                  **bundle['task'])
        rid = bundle['task']['robot_id']
        runtime.initial_commands(start, {rid: backend.commands[rid]})
        end_at = None
        for i in range(round(bundle['case_cap_s']/bundle['tick_s'])+1):
            backend.eval_sample()  # write-only judge inputs
            if end_at is None:
                runtime.on_frames(backend.now, backend.capture())
                for rid, action in runtime.step(backend.now):
                    backend.issue(rid, action)
                    runtime.on_command(rid, backend.now, action)
                    result['commands_issued'] += 1
                if runtime.terminal or stage_reached(runtime, stage):
                    end_at = backend.now
                    # A stage stop cancels pending drive expiry without opening the grip.
                    backend.issue(runtime.robot_id, {'kind': 'hold'})
                    runtime.on_command(runtime.robot_id, backend.now, {'kind': 'hold'})
                    result['commands_issued'] += 1
            if end_at is not None and backend.now-end_at >= 3.-1e-8:
                break
            if i == round(bundle['case_cap_s']/bundle['tick_s']):
                break
            backend.advance_to(start+(i+1)*bundle['tick_s'])
        reached = stage_reached(runtime, stage) and not runtime.failure
        result.update(status='STAGE_REACHED_UNQUALIFIED' if reached else 'STAGE_FAILED',
            stage_reached=reached, failure=runtime.failure, controller_state=runtime.state,
            reset_sim_s=reset, check_sim_s=backend.now-start,
            evaluation=evaluate(backend.eval_rows, static, bundle['task']['destination']))
    except Exception as exc:
        result.update(status='HOST_ERROR', failure={'type': type(exc).__name__, 'message': str(exc),
            'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
    finally:
        if runtime is not None:
            try:
                write(out/'student_record.json', runtime.record())
            except Exception as exc:
                result.update(status='HOST_ERROR', record_error=str(exc))
        for obj in (runtime, backend):
            if obj is not None:
                try:
                    obj.close()
                except Exception as exc:
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result['loadavg_end'] = list(os.getloadavg())
        write(out/'result.json', result)
        write(out/'artifacts.sha256.json', {str(p.relative_to(out)): contract.hp.base.sha(p)
            for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    task = {k: getattr(args, k) for k in ('seed', 'robot_id', 'pickup_slot', 'destination', 'passage_id')}
    bundle = contract.bundle(args.expected_source_sha, **task,
                             stage_probe=args.stage_probe, speedups=args.speedups)
    if not args.execute:
        print(json.dumps({'execution_started': False, 'execution_bundle_id': contract.BUNDLE_ID,
            'source_sha': args.expected_source_sha, 'bundle_sha256': contract.hp.base.digest(bundle),
            'task': task, 'stage_probe': args.stage_probe, 'speedups': args.speedups,
            'runnable_mode': 'DEV_PILOT', 'physical_success': None}, indent=2))
        return 0
    check_source(args.expected_source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        cwd=contract.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary/'outputs').resolve()):
        raise ValueError('raw output must be absolute under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    from scripts.agent_lock import DEFAULT_ROOT, status
    from scripts.agent_sim_slots import require_sim_slot, sim_holders
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    if args.sim_slot:
        require_sim_slot(DEFAULT_ROOT, slot=args.sim_slot, owner=args.lock_owner, branch=branch)
    else:
        held = status(DEFAULT_ROOT)
        if (not held or not held['pid_alive'] or held['owner'] != args.lock_owner or held['branch'] != branch
                or sim_holders(DEFAULT_ROOT)):
            raise ValueError('live owned SIM lock for this branch required')
    from harness.zone_pair_highpose_exact_speedups import RunSpeedups
    speed = RunSpeedups(args.speedups, args.output)
    rc = 1
    try:
        speed.start()
        result = run(bundle, args.output, stage=args.stage_probe)
        rc = 0 if result['status'] == 'STAGE_REACHED_UNQUALIFIED' else 1
        return rc
    finally:
        speed.finish(rc)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
