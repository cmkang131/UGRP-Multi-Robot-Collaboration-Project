"""Report the actual submitted wave's first30 median; no simulation imports."""
import argparse
import json
from pathlib import Path

from scripts.record_map_amcl import speed_summary


def check_wave(runs, source_sha):
    receipts, failed = [], []
    for run in runs:
        raw = Path(run)/'raw'
        try:
            result = json.loads((raw/'result.json').read_text())
            receipt = json.loads((raw/'first30.json').read_text())
            if result['source_sha'] != source_sha or (
                    result.get('finalization_complete') and result['status'] != 'RECORDED'):
                raise ValueError('SOURCE_OR_COMPLETION_MISMATCH')
            if receipt['frames_per_robot'] != 301 or receipt['observation_period_s'] != .1:
                raise ValueError('FIRST30_INCOMPLETE')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            receipt = None
            failed.append(dict(run=str(run), error=str(exc)))
        receipts.append(receipt)
    return dict(speed_summary(receipts), runs=[str(r) for r in runs], failed=failed,
                scope='Every run in the submitted wave, including unfinished first30 and HOST_ERROR')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-source-sha', required=True)
    parser.add_argument('runs', nargs='+', type=Path)
    args = parser.parse_args(argv)
    result = check_wave(args.runs, args.expected_source_sha)
    print(json.dumps(result))
    return 2 if result['blocked'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
