"""Separate GPU diagnostic: select only the first sealed pair cases; retain guards.

Never edits the original stack. The original infrastructure check and future
driver main (including all Guard callbacks/finalization) run unchanged. A small
batch can fail the original speed gate; C with one completion cannot pass its
four-completion pilot. Neither condition is waived by this diagnostic.
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


def subset_plan(plan, indices):
    """Only change sealed case selection and explicitly assert the GPU backend."""
    if indices not in ('0', '0,1'):
        raise ValueError('only first one or two sealed cases authorized')
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
    parser.add_argument('--indices', choices=('0', '0,1'), required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.arm == 'arm_c' and args.indices != '0':
        parser.error('C authorized for one episode only')
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
    if selected != [8342000, 8342001][:len(selected)]:
        raise ValueError('unexpected sealed seeds')
    record = dict(arm=args.arm, seeds=selected, host_zone_restore=identity,
                  administrative_source_sha256={str(p): h for p, h in PINS.items()},
                  changed=['indices', 'explicit existing mjwarp_batch_v1 default'],
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
    driver.main()


if __name__ == '__main__':
    main()
