"""Explicit offline Python audit trace/run prototype for NEW v2 registrations."""
import argparse
import json
from pathlib import Path

from harness.execution_dependency_contract import ROOT, read_json
from harness.runtime_provenance import TraceFailure, run_sealed, trace_contract


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    trace = sub.add_parser('trace')
    trace.add_argument('--static-contract', type=Path, required=True)
    trace.add_argument('--expected-static-sha256', required=True)
    trace.add_argument('--cases', type=Path, required=True, help='JSON list of {entry, args}')
    trace.add_argument('--env', action='append', default=[], help='non-secret environment name to inherit')
    trace.add_argument('--policy', type=Path, help='sealed environment/identity abort or warn policy')
    trace.add_argument('--output', type=Path, required=True)
    run = sub.add_parser('run')
    run.add_argument('--seal', type=Path, required=True)
    run.add_argument('--expected-sha256', required=True)
    run.add_argument('--case-index', type=int, default=0)
    for command in (trace, run):
        command.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args(argv)
    if args.command == 'trace':
        # Check before executing a canonical case; exclusive write checks again.
        if args.output.exists():
            parser.error('output already exists; old seals are never overwritten')
        try:
            value = trace_contract(read_json(args.static_contract),
                                   expected_static_sha256=args.expected_static_sha256,
                                   cases=read_json(args.cases), root=args.root, env_names=args.env,
                                   policy=read_json(args.policy) if args.policy else None, timeout=args.timeout)
        except TraceFailure as exc:
            failure = args.output.with_name(args.output.name + '.failed.json')
            with failure.open('x') as stream:
                json.dump(exc.report, stream, indent=2)
                stream.write('\n')
            print(json.dumps({'status': 'HOST_ERROR', 'report': str(failure)}))
            return 86
        with args.output.open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
        print(json.dumps({'sha256': value['sha256'], 'files': len(value['files'])}))
        return 0
    value = run_sealed(read_json(args.seal), expected_sha256=args.expected_sha256,
                       root=args.root, case_index=args.case_index, timeout=args.timeout)
    print(json.dumps(value))
    return 0 if value['status'] == 'OK' else 86


if __name__ == '__main__':
    raise SystemExit(main())
