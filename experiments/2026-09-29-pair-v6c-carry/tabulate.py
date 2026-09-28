"""Pass-rate tables for the carry / set-down stage probes (reads only the raw ``cases.jsonl`` + ``result.json``).

Usage: python experiments/2026-09-29-pair-v6c-carry/tabulate.py <raw dir> [<raw dir> ...] [--json out.json]

Definitions (the same ones the README uses):
  cases            every planned case
  staging_infeasible  the teacher could not stage the case (HOST_ERROR whose message is the calibrated
                   14.5..18.0 cm grasp-envelope ValueError of ``solve_grip_ik``). The controller never ran, so the
                   case is not a pass or a fail of the stage under test and is left out of the denominator.
  staged           cases - staging_infeasible
  passed           row['passed']
Timing: ``stage_sim_s`` (stage entry to controller exit / failure, SIM seconds); ``base_motion_commands`` (mecanum
commands the two robots issued after the submit); wall time and load averages are reported for context only.
"""
from __future__ import annotations

import collections
import json
import re
import statistics
import sys
from pathlib import Path

ENVELOPE_TEXT = 'outside the calibrated 14.5..18.0 cm grasp envelope'


def case_dir(raw: Path, case_id: str) -> Path:
    return raw / 'cases' / re.sub(r'[^A-Za-z0-9_.+-]+', '_', case_id)   # scripts/run_pair_stage_probes.py naming


def host_error_message(raw: Path, row: dict) -> str:
    if row.get('category') != 'HOST_ERROR':
        return ''
    try:
        return str(json.loads((case_dir(raw, row['case_id']) / 'result.json').read_text())['host_error']['message'])
    except (OSError, KeyError, ValueError, TypeError):
        return ''


def load(raw: Path) -> list[dict]:
    rows = [json.loads(line) for line in (raw / 'cases.jsonl').read_text().splitlines() if line.strip()]
    for row in rows:
        msg = host_error_message(raw, row)
        row['host_error_message'] = msg
        row['staging_infeasible'] = ENVELOPE_TEXT in msg
        row['cause_final'] = 'STAGING_IK_ENVELOPE' if row['staging_infeasible'] else row['cause']
        try:
            res = json.loads((case_dir(raw, row['case_id']) / 'result.json').read_text())
        except (OSError, ValueError):
            res = {}
        term, submit = (res.get('termination') or {}), res.get('submit_t')
        # SIM seconds the run consumed after the submit, and the first in-stage failure relative to the submit
        row['run_sim_s'] = None if term.get('sim_s') is None or submit is None else round(term['sim_s'] - submit, 2)
        ff = (row.get('first_failure') or {}).get('sim_s')
        row['fail_after_submit_s'] = None if ff is None or submit is None else round(ff - submit, 2)
        row['termination_outcome'] = term.get('outcome')
    return rows


def med(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 2) if values else None


def group(rows):
    staged = [r for r in rows if not r['staging_infeasible']]
    fail = [r for r in staged if not r['passed']]
    sims = [r['stage_sim_s'] for r in staged]
    runs = [r['run_sim_s'] for r in staged]
    cmd_base = [sum((r.get('base_motion_commands') or {}).values()) for r in staged]
    cmd_all = [sum((r.get('command_total') or {}).values()) for r in staged]
    return {'cases': len(rows), 'staging_infeasible': len(rows) - len(staged), 'staged': len(staged),
            'passed': sum(r['passed'] for r in staged),
            'causes': dict(collections.Counter(r['cause_final'] for r in fail)),
            'sub': dict(collections.Counter(f"{r['cause_final']}/{r.get('cause_sub')}" for r in fail if r.get('cause_sub'))),
            'first_failure_robot': dict(collections.Counter(str((r.get('first_failure') or {}).get('robot_id')) for r in fail)),
            'first_failure_reason': dict(collections.Counter(str((r.get('first_failure') or {}).get('reason')) for r in fail)),
            'stage_sim_s': {'min': min((s for s in sims if s is not None), default=None),
                            'median': med(sims), 'max': max((s for s in sims if s is not None), default=None)},
            'run_sim_s_after_submit': {'min': min((s for s in runs if s is not None), default=None),
                                       'median': med(runs), 'max': max((s for s in runs if s is not None), default=None)},
            'fail_after_submit_s_median': med([r['fail_after_submit_s'] for r in fail]),
            'base_motion_commands_median': med(cmd_base), 'commands_total_median': med(cmd_all),
            'termination': dict(collections.Counter(r['termination_outcome'] for r in staged)),
            'wall_s_median': med([r.get('wall_s') for r in staged])}


def main(argv):
    out_json = None
    if '--json' in argv:
        i = argv.index('--json')
        out_json = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    result = {}
    for arg in argv:
        raw = Path(arg)
        rows = load(raw)
        manifest = json.loads((raw / 'manifest.json').read_text())
        legs = collections.defaultdict(list)
        for r in rows:
            legs[r.get('leg')].append(r)
        entry = {'source_sha': manifest['source']['source_sha'][:8], 'probe_version': manifest['probe_version'],
                 'state': manifest['state'], 'source_changed': manifest['source_changed'],
                 'wall_s': manifest.get('wall_s'), 'all': group(rows),
                 'by_leg': {str(k): group(v) for k, v in sorted(legs.items(), key=lambda kv: (kv[0] is None, kv[0]))},
                 'diag_patch': sorted({r.get('diag_patch') for r in rows}, key=str)}
        result[raw.name] = entry
        print(f"== {raw.name}  sha {entry['source_sha']}  probe {entry['probe_version']}  state {entry['state']}  "
              f"source_changed {entry['source_changed']}  wall {entry['wall_s']} s  diag {entry['diag_patch']}")
        for name, g in [('all', entry['all'])] + list(entry['by_leg'].items()):
            print(f"  {name:>4}: {g['passed']}/{g['staged']} staged pass ({g['cases']} planned, {g['staging_infeasible']} infeasible)  "
                  f"causes {g['causes']} sub {g['sub']}  reasons {g['first_failure_reason']}  first-fail robot {g['first_failure_robot']}  "
                  f"stage SIM s {g['stage_sim_s']}  run SIM s after submit {g['run_sim_s_after_submit']}  "
                  f"fail after submit (median) {g['fail_after_submit_s_median']} s  base cmds med {g['base_motion_commands_median']}  "
                  f"all cmds med {g['commands_total_median']}  ends {g['termination']}  wall med {g['wall_s_median']} s")
    if out_json:
        Path(out_json).write_text(json.dumps(result, indent=1, default=str))


if __name__ == '__main__':
    main(sys.argv[1:])
