"""Convert admitted v6 episodes locally on the GCP training disk; no upload."""
import argparse
import json
from pathlib import Path

import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.grasp_act_data import convert


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs-root', type=Path, required=True)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--audit-seeds', type=int, nargs='+', help='partial output cannot train')
    a = p.parse_args()
    report = convert(a.runs_root, json.loads(a.protocol.read_text()), a.output, seeds=a.audit_seeds)
    print(json.dumps({'status': report['status'], 'episodes': len(report['episodes']),
                      'rows': sum(e['rows_selected'] for e in report['episodes'])}))


if __name__ == '__main__':
    main()
