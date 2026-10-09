"""Managed S3 DEV runner. Default is a no-physics plan; no model path exists."""
from __future__ import annotations

import argparse
import errno
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from harness import zone_s3_contract as contract
from harness.zone_s3_host import Runtime, IntegratedTrial, ROBOTS
from scripts.run_final_environment_checks import check_source, write


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seed', type=int, choices=contract.SEEDS, default=contract.SEEDS[0])
    p.add_argument('--speedups', choices=('none', 'v98-exact-v6'), default='v98-exact-v6')
    p.add_argument('--door-yield', choices=('off', 's3-door-yield-v1'), default='off')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--release-s3-simulation', action='store_true',
                   help='coordinator explicitly releases S3 after the S2 reservation; lock vacancy alone is not release')
    return p


def environment_record():
    # Import names are not distribution names (cv2 can be opencv-python-headless).
    mapping = importlib.metadata.packages_distributions()
    return {'python': sys.version, 'platform': platform.platform(), 'packages': {
        module: {dist: importlib.metadata.version(dist) for dist in mapping.get(module, ())}
        for module in ('numpy', 'mujoco', 'cv2', 'PIL')}}


def artifact_manifest(out):
    write(out/'artifacts.sha256.json', {str(p.relative_to(out)): contract.hp.base.sha(p)
        for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts.sha256.json'})


def run(bundle, out, *, runtime_factory=Runtime, backend_factory=None):
    selected = contract
    if bundle.get('door_yield', 'off') != 'off':
        from harness import zone_s3_door_contract as selected
        from harness.zone_s3_door_yield import Runtime as DoorRuntime
        if runtime_factory is Runtime:
            runtime_factory = DoorRuntime
    selected.verify(bundle)
    scenario, map_bundle, sheet = contract.inputs()
    static = contract.hp.resolve(bundle['map_id'])[0]
    if backend_factory is None:
        from sim.zone_s3_host import PhysicsBackend
        backend_factory = PhysicsBackend
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    write(out/'bundle.json', bundle)
    started = time.monotonic()
    result = {'execution_bundle_id': selected.BUNDLE_ID, 'source_sha': bundle['source_sha'],
        'seed': bundle['seed'], 'status': 'HOST_ERROR', 'cohort_role': 'FUNCTIONAL_DEV',
        'research_result': False, 'physical_success': None, 'model_calls': 0, 'http_attempts': 0,
        'model_response_time_s': 0., 'tokens': 0, 'commands_issued': {r: 0 for r in ROBOTS},
        'loadavg_start': list(os.getloadavg()), 'in_run_drop_tilt_contact_detection': False,
        'dev_light': True, 'evaluation': None}
    backend = runtime = trial = None
    try:
        write(out/'environment.json', environment_record())
        backend = backend_factory(bundle, out, seed=bundle['seed'])
        reset = backend.reset(bundle['reset_cap_s'])
        if not 0 <= reset <= bundle['reset_cap_s']+1e-8:
            raise RuntimeError('RESET_SIM_CAP_EXCEEDED')
        start = backend.now
        backend.set_deadline(start+bundle['case_cap_s'])
        runtime = runtime_factory(static, sheet['orders'], contract.ROOT/bundle['calibration'],
                                  bundle['calibration_sha256'], seed=bundle['seed'])
        runtime.initial_commands(start, backend.commands)
        trial = IntegratedTrial(scenario, seed=bundle['seed'], links=runtime.links, map_bundle=map_bundle,
            horizon_s=start+bundle['case_cap_s'], code_sha=bundle['source_sha'],
            pair_records=runtime.pair.team.records)
        runtime.trial = trial
        if selected is not contract:
            result['door_yield'] = bundle['door_yield']
        trial.begin(start)
        ended = None
        steps = round(bundle['case_cap_s']/bundle['tick_s'])
        for i in range(steps+1):
            backend.eval_sample()  # return ignored; no truth or referee input to runtime
            if i == steps:
                break
            if ended is None:
                runtime.on_frames(backend.now, backend.capture())
                commands = runtime.step(backend.now)
                if runtime.terminal:
                    ended = backend.now
                    commands = [(r, {'kind': 'hold'}) for r in ROBOTS]
                for rid, action in commands:
                    backend.issue(rid, action)
                    runtime.on_command(rid, backend.now, action)
                    result['commands_issued'][rid] += 1
            if ended is not None and backend.now-ended >= bundle['settle_s']-1e-8:
                break
            backend.advance_to(start+(i+1)*bundle['tick_s'])
        # Cancel outstanding drive leases at the bounded end, including a horizon.
        for rid in ROBOTS:
            backend.issue(rid, {'kind': 'hold'})
            runtime.on_command(rid, backend.now, {'kind': 'hold'})
            result['commands_issued'][rid] += 1
        failures = runtime.failures
        result.update(reset_sim_s=reset, check_sim_s=backend.now-start, controller_failures=failures,
                      commands_complete=bool(runtime.terminal and not failures),
                      end_reason='controller_failure' if failures else 'commands_ended' if ended is not None else 'sim_horizon')
        # The actual delivery verdict is computed only here, after all control.
        result['evaluation'] = backend.evaluate(sheet['orders'], static)
        result['status'] = ('DEV_DELIVERED' if result['commands_complete']
                            and result['evaluation']['orders_complete'] else 'DEV_NOT_DELIVERED')
    except Exception as exc:
        result.update(status='HOST_ERROR', failure={'type': type(exc).__name__, 'message': str(exc),
            'class': 'ENOSPC' if getattr(exc, 'errno', None) == errno.ENOSPC else 'HOST_ERROR'})
    finally:
        for name, record in (('student_record.json', runtime.record if runtime is not None else None),
                             ('trial.json', (lambda: trial.finish(backend.now)) if trial is not None else None)):
            if record is not None:
                try:
                    value = record()
                    if name == 'trial.json' and selected is not contract:
                        value['inter_robot_channels'].append(bundle['door_yield'])
                        value['door_protocol'] = bundle['door_protocol']
                    write(out/name, value)
                except Exception as exc:
                    result.update(status='HOST_ERROR', record_error=str(exc))
        for owner in (runtime, backend):
            if owner is not None:
                try:
                    owner.close()
                except Exception as exc:
                    result.update(status='HOST_ERROR', cleanup_error=str(exc))
        result.update(loadavg_end=list(os.getloadavg()), wall_s=time.monotonic()-started)
        write(out/'result.json', result)
        artifact_manifest(out)
    return result


def require_execution(args):
    if not args.release_s3_simulation:
        raise ValueError('S3_SIM_RESERVED_FOR_PR393: explicit coordinator release required even when lock is vacant')
    check_source(args.expected_source_sha)
    primary = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        cwd=contract.ROOT, text=True).strip()).parent
    if not args.output.is_absolute() or not args.output.resolve().is_relative_to((primary/'outputs').resolve()):
        raise ValueError('S3 raw must be an absolute path under primary outputs')
    if args.output.exists():
        raise FileExistsError(args.output)
    if shutil.disk_usage(primary).free < 10*1024**3:
        raise OSError(errno.ENOSPC, 'less than 10 GiB free')
    if int(subprocess.check_output(['ps', '-o', 'nice=', '-p', str(os.getpid())], text=True).strip()) != 0:
        raise ValueError('S3 requires nice 0')
    from scripts.agent_lock import DEFAULT_ROOT, status
    from scripts.agent_sim_slots import sim_holders
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=contract.ROOT, text=True).strip()
    held = status(DEFAULT_ROOT)
    expected_branch = ('codex/s3-door-yield' if args.door_yield != 'off' else 'codex/s3-three-robot-host')
    if (branch != expected_branch or not held or not held['pid_alive']
            or held['owner'] != 'codex' or held['branch'] != branch or sim_holders(DEFAULT_ROOT)):
        raise ValueError('S3 requires its own live exclusive SIM lock; no slots or foreign lock')


def main(argv=None):
    args = parser().parse_args(argv)
    if args.execute:
        require_execution(args)  # before physics, provider or speedup construction
    selected = contract
    if args.door_yield != 'off':
        from harness import zone_s3_door_contract as selected
    bundle = selected.bundle(args.expected_source_sha, seed=args.seed, speedups=args.speedups)
    if not args.execute:
        print(json.dumps({'execution_started': False, 'execution_bundle_id': selected.BUNDLE_ID,
            'bundle_sha256': contract.hp.base.digest(bundle), 'seed': args.seed,
            'source_sha': args.expected_source_sha, 'model_calls': 0,
            'simulation_release_required': True, 'physical_success': None}, indent=2))
        return 0
    from harness.zone_pair_highpose_exact_speedups import RunSpeedups
    speed = RunSpeedups(args.speedups, args.output)
    rc = 1
    try:
        speed.start()
        result = run(bundle, args.output)
        rc = 0 if result['status'] == 'DEV_DELIVERED' else 1
        return rc
    finally:
        speed.finish(rc)
        if args.output.is_dir():
            artifact_manifest(args.output)  # include the late speedups.json sidecar


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
