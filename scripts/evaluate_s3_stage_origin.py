"""Raw-only evaluation; fixed authored route and unchanged 20mm threshold."""
import argparse
import json
import platform
from pathlib import Path
from scripts.evaluate_s3_integer_carry import evaluate as previous
from scripts.evaluate_s3_synchronized_carry import read
from sim.s3_stage_origin import OPTION


def evaluate(raw):
    r = previous(raw)
    r['stage_origin_option'] = read(raw/'bundle.json')['stage_origin']['option']
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Oracle evaluation only')
    cc = read(a.cohort/'cohort.json')
    assert len(cc) == 20
    results = [dict(name=x['name'], **evaluate(a.cohort/x['name']/'raw')) for x in cc]
    by = {}
    for option in ('off', OPTION):
        runs = [r for r in results if r['stage_origin_option'] == option]
        pair = [r for r in runs if r['case'] == 'pair']
        cyan = [r for r in runs if r['case'] == 'cyan']
        by[option] = dict(n=len(runs), pair_n=len(pair), cyan_n=len(cyan),
            counts={k: sum(r['joint'][k] for r in runs) for k in ('alignment', 'grasp', 'lift', 'carry')},
            pulse_count_correct=sum(r['pulse_count_correct'] for r in pair),
            endpoint_reached=sum(r['endpoint_reached'] for r in pair),
            setdown=sum(r['setdown'] for r in pair),
            drop_aborts=sum(r['drop_aborts'] for r in runs),
            tilt_aborts=sum(r['tilt_aborts'] for r in runs),
            host_errors=sum(r['status'] == 'HOST_ERROR' for r in runs),
            cyan_regression_carry=sum(r['joint']['carry'] for r in cyan))
    gate = by[OPTION]
    passed = all(gate[k] == 6 for k in ('pulse_count_correct', 'endpoint_reached', 'setdown')) and gate['cyan_regression_carry'] == 4 and gate['drop_aborts'] == gate['tilt_aborts'] == gate['host_errors'] == 0
    summary = dict(host='oracle-x86', n=20, runs=results, by_option=by,
        second_stage_gate_passed=passed, initial_checks_healthy=sum(r['initial_check']['healthy'] for r in results))
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'runs'}))


if __name__ == '__main__':
    raise SystemExit(main())
