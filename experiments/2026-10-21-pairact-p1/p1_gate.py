"""pairact P1: pre-registered index set and adoption verdict (pure; used by run_p1.sh).

Decisions D2/D3 (owner, 2026-10-20):
* static exclusion = rule A only (``flagged['overlap']`` of static_stance_check.py:
  every certified pose of one beam end overlaps a box).  Rule B (11.07 mm floor) unused.
* excluded worlds leave the denominator: N_eff = N_nominal - len(excluded);
  adopt iff success >= ceil(0.95 * N_eff).  The nominal n/N_nominal is reported too.
* world 15 (r3 deviation, log flood) is NOT an exclusion: it is not executed and
  counts as a failure inside N_eff, as in r13.

Usage:
  python p1_gate.py indices PREREG.json tournament|confirmation   -> comma list for --indices
  python p1_gate.py verdict PREREG.json tournament|confirmation OUT_ROOT ARM...
"""
import hashlib
import json
import math
import sys
from pathlib import Path

ADOPT_FRACTION = .95


def check_frozen(prereg, stage):
    if prereg.get('status') != 'FROZEN':
        raise SystemExit(f"prereg status {prereg.get('status')!r}: run needs FROZEN")
    excl = prereg['static_exclusion'][stage]['excluded_worlds']
    if not isinstance(excl, list):
        raise SystemExit(f'{stage}: excluded_worlds not recorded (static check must run first)')
    return excl


def indices(n_nominal, not_executed, excluded):
    skip = set(not_executed) | set(excluded)
    if not skip <= set(range(n_nominal)):
        raise ValueError('index out of range')
    return [i for i in range(n_nominal) if i not in skip]


def threshold(n_nominal, excluded):
    n_eff = n_nominal - len(set(excluded))
    return n_eff, math.ceil(round(ADOPT_FRACTION * n_eff, 9))


def verdict(rows, n_nominal, excluded):
    """rows: [{'arm', 'success_n' or None, ...}].  Missing/None success counts as 0."""
    n_eff, need = threshold(n_nominal, excluded)
    out = []
    for r in rows:
        s = r.get('success_n')
        s = s if isinstance(s, int) else 0
        out.append({**r, 'success_counted': s, 'nominal': f'{s}/{n_nominal}', 'effective': f'{s}/{n_eff}',
                    'need': need, 'adopt': s >= need})
    return {'N_nominal': n_nominal, 'excluded': sorted(set(excluded)), 'N_eff': n_eff, 'need': need, 'arms': out}


def _rows(root, arms):
    rows = []
    for arm in arms:
        s = Path(root)/arm/'summary.json'
        if not s.exists():
            rows.append({'arm': arm, 'status': 'NO_SUMMARY', 'success_n': None}); continue
        d = json.loads(s.read_text())
        rows.append({'arm': arm, 'success_n': d.get('success_n'), 'completed_N': d.get('completed_N'),
                     'planned_N': d.get('planned_N'), 'cap_end': d.get('cap_end'), 'HOST_ERROR': d.get('HOST_ERROR'),
                     'summary_sha256': hashlib.sha256(s.read_bytes()).hexdigest()})
    return rows


def main(argv):
    cmd, prereg_path, stage = argv[:3]
    prereg = json.loads(Path(prereg_path).read_text())
    ws = prereg['world_set'][stage]
    excl = check_frozen(prereg, stage)
    if cmd == 'indices':
        print(','.join(map(str, indices(ws['nominal_denominator'], ws.get('not_executed', []), excl))))
    elif cmd == 'verdict':
        root, arms = argv[3], argv[4:]
        v = verdict(_rows(root, arms), ws['nominal_denominator'], excl)
        v['prereg_sha256'] = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()
        (Path(root)/'tournament-raw.json').write_text(json.dumps(v, indent=1))
        print(json.dumps(v, indent=1))
    else:
        raise SystemExit('cmd: indices | verdict')


if __name__ == '__main__':
    main(sys.argv[1:])
