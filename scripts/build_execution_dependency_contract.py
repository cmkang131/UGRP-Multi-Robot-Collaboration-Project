"""Build/verify v2 dependencies for NEW registrations; never run or approve them.

python -m scripts.build_execution_dependency_contract build --spec candidate.json
python -m scripts.build_execution_dependency_contract verify --contract receipt.json --expected-sha256 <approved-digest>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.execution_dependency_contract import ROOT, build_contract, read_json, verify_contract


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--spec', type=Path, required=True)
    build.add_argument('--output', type=Path, help='new file only; omit to print a preview')
    verify = sub.add_parser('verify')
    verify.add_argument('--contract', type=Path, required=True)
    verify.add_argument('--expected-sha256', required=True)
    args = parser.parse_args(argv)
    if args.command == 'build':
        result = build_contract(read_json(args.spec), root=args.root)
        text = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        if args.output:
            with args.output.open('x') as stream:
                stream.write(text)
        else:
            print(text, end='')
    else:
        result = verify_contract(read_json(args.contract), expected_sha256=args.expected_sha256, root=args.root)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
