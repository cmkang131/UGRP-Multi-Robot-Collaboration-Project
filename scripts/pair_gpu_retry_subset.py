"""Run the sealed pair diagnostic with CPU init allowed and GPU-only rollout.

Original infrastructure/future drivers and all guard callbacks stay unchanged.
CPU-init authorization: user decision 2026-10-27 20:02 KST. N=20 per arm is
separate from the existing cohort; speed/pilot gates are never waived.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

INFRA = Path('/home/ugrp/ugrp-sim/baseline-resume-ops-20261027/infrastructure_driver.py')
FUTURE = Path('/home/ugrp/ugrp-sim/baseline-treatment/future_driver.py')
PINS = {
    INFRA: 'c00a564a01d11699f8bfbf73d808b57955589bbda7f64fb4c1f2711c53b790cf',
    FUTURE: '91d9704966f96c07241ae0eb6a38febcbc030ca11114ed7e14bfa2ec3b8b9aa0',
}


SEALED_INDICES = ','.join(map(str, range(20)))


def subset_plan(plan, indices):
    """Only change sealed case selection and explicitly assert the GPU backend."""
    if indices not in ('0', '0,1', SEALED_INDICES):
        raise ValueError('only first one/two or full sealed N=20 authorized')
    argv = list(plan['argv'])
    pos = argv.index('--indices') + 1
    if argv[pos] != ','.join(map(str, range(20))):
        raise ValueError('unexpected sealed case selection')
    if '--physics-backend' in argv:
        raise ValueError('unexpected explicit backend in sealed plan')
    argv[pos] = indices
    argv += ['--physics-backend', 'mjwarp_batch_v1']
    return dict(plan, argv=argv)


def load(path, name):
    if hashlib.sha256(path.read_bytes()).hexdigest() != PINS[path]:
        raise ValueError('pinned administrative source mismatch: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm', choices=('arm_s', 'arm_c'), required=True)
    parser.add_argument('--indices', choices=('0', '0,1', SEALED_INDICES), default=SEALED_INDICES)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.out.exists():
        raise ValueError('new output path required')
    infra = load(INFRA, 'retry_original_infra')
    # Original --check validates exact VM id, original guard bytes and host,
    # then installs its approved restoration module for the original runner.
    sys.argv = [str(INFRA), '--check']
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        infra.main()
    identity = json.loads(captured.getvalue())
    sys.path.insert(0, str(FUTURE.parent))
    driver = load(FUTURE, 'retry_original_future')
    original_plan = driver.make_plan
    driver.make_plan = lambda arm, out: subset_plan(original_plan(arm, out), args.indices)
    cases_path = Path('/home/ugrp/ugrp-sim/runs/pairact-p5-eval-20261025/p5-heldout-cases.json')
    cases = json.loads(cases_path.read_text())
    selected = [cases[int(i)]['plan']['seed'] for i in args.indices.split(',')]
    if selected != list(range(8342000, 8342000 + len(selected))):
        raise ValueError('unexpected sealed seeds')
    record = dict(arm=args.arm, seeds=selected, host_zone_restore=identity,
                  administrative_source_sha256={str(p): h for p, h in PINS.items()},
                  changed=['authorized sealed indices', 'explicit existing mjwarp_batch_v1 default',
                           'administrative scoped CPU-init guard'],
                  cpu_init_authorization='user 2026-10-27 20:02 KST',
                  guards_unchanged=True, separate_diagnostic_cohort=True,
                  rejection_table=str(FUTURE.parent / 'prior-funnel.json'))
    if args.execute:
        with args.out.with_suffix('.subset.json').open('x') as stream:
            json.dump(record, stream, indent=2)
    else:
        print(json.dumps(record, indent=2))
    sys.argv = [str(FUTURE), '--arm', args.arm, '--out', str(args.out)]
    if args.execute:
        sys.argv.append('--execute')
    if not args.execute:
        driver.main()
        return
    # Verify original files BEFORE preloading the unchanged modules for wrapping.
    # The original driver repeats verification and all original execution gates.
    from verify_baseline import verify
    reference = json.loads((FUTURE.parent / 'baseline-reference.json').read_text())
    checked = verify(reference)
    if not checked['all_match']:
        raise ValueError('frozen artifact/hash mismatch before guard installation')
    root = original_plan(args.arm, str(args.out))['cwd']
    sys.path[:0] = [str(Path(root) / 'scripts'), root]
    import mujoco
    import warp_flow_episode
    import warp_act_backend
    from pair_gpu_cpu_guard import CPUInitGuard
    guard = CPUInitGuard(args.out.with_suffix('.cpu-init.json'), args.arm, selected)
    with guard.installed(mujoco, warp_flow_episode, warp_act_backend):
        driver.main()


if __name__ == '__main__':
    main()
