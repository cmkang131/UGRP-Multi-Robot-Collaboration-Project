#!/usr/bin/env python3
"""Tournament A run root -> world-run ledger JSONL for scripts/report_tables.py tournament.

Eval-only, reads files under one tournament run root and writes one new ledger file
(never into a run directory).  Pre-registration: CARRY_TOURNAMENT_A_PREREG_DRAFT.json
("ledger" and "host_error" keys).

Run root layout (same as the C2c driver, scripts/act18_c2c_stage.py):

    <run_root>/<arm>-<ho4|train4>-rep<k>/R8-<diag|train>/group-NNN/plans.json
    <run_root>/<arm>-<ho4|train4>-rep<k>/R8-<diag|train>/group-NNN/evaluation/
        summary.json  initial-plans.json  actor-actions.jsonl  owner/evaluation-only.jsonl

Ledger (JSONL)::

    {"type":"header","prereg_sha256":...,"run_root":...,"schema":"ugrp.act18.tournament_ledger.v1"}
    {"type":"world_run","arm":"A-c1","rep":1,"cohort":"HO4","seed":88668,"status":"complete",
     "release_success":..,"physical_success":..,"drop_detected":..,"G":..,"early_open_grasp":..,
     "open_issued":..,"release_done":..,"cap_end":..,"run":"A-c1-ho4-rep1","group":0,"world":0}

Rules (prereg "host_error"): a group whose summary.json is missing, unreadable, has
status HOST_ERROR or lacks student_scores gives status HOST_ERROR for every seed in
its plans.json.  HOST_ERROR rows stay in the denominator as failures and are never
re-run.  A run directory that does not exist gives no rows (the report lists it as
not executed and holds the verdict).

Per world-run keys:
  release_success, physical_success, drop_detected, cap_end
      summary.json student_scores (harness/grasp_act_rollout.SoloScore.record, evaluate_act16w)
  G   grasp done issued and a 3 s stable lift completed at or before it
      (scripts/act18_c2c_analyze.py group_rows definition, owner/evaluation-only.jsonl)
  early_open_grasp
      in the grasp skill, an issued gripper pwm['1'] >= 1900 after the first issued
      pwm['1'] < 1900 (re-open after closing; actor-actions.jsonl)
  open_issued   an issued pwm['1'] >= 1900 in the release skill
  release_done  issued_done_times['release'] present

Usage:
  python scripts/act18_tournament_ledger.py --prereg P --run-root R --out R-report/tournament-ledger.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act18_c2c_analyze import stable_lift_complete  # noqa: E402

SCHEMA = 'ugrp.act18.tournament_ledger.v1'
GRIPPER_OPEN_PWM = 1900          # scripts/act18_gripper_state.py: closed is pwm['1'] < 1900
RUN_NAME = re.compile(r'^(?P<arm>.+)-(?P<cohort>ho4|train4)-rep(?P<rep>\d+)$')
COHORT = {'ho4': 'HO4', 'train4': 'TRAIN4'}
STAGE = {'ho4': 'diag', 'train4': 'train'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def gripper_flags(actions_path, n_worlds):
    """Per world: (early_open_grasp, open_issued) from actor-actions.jsonl rows."""
    closed = [False] * n_worlds
    early = [False] * n_worlds
    opened = [False] * n_worlds
    path = Path(actions_path)
    if not path.exists():
        return [None] * n_worlds, [None] * n_worlds
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for w, (action, skill) in enumerate(zip(row['actions'], row['skills'])):
            if w >= n_worlds:
                break
            pwm = int(action['command']['pwm']['1'])
            if skill == 'grasp':
                if pwm < GRIPPER_OPEN_PWM:
                    closed[w] = True
                elif closed[w]:
                    early[w] = True
            elif skill == 'release' and pwm >= GRIPPER_OPEN_PWM:
                opened[w] = True
    return early, opened


def group_world_runs(group_dir, *, arm, rep, cohort, run):
    """World-run rows of one group directory (HOST_ERROR rows when the group did not finish)."""
    group_dir = Path(group_dir)
    group = int(group_dir.name.split('-')[1])
    plans = (_json(group_dir / 'plans.json') or {}).get('episodes')
    if not plans:
        raise ValueError(f'{group_dir}/plans.json missing or empty: seeds of the group unknown')
    ev = group_dir / 'evaluation'
    summary = _json(ev / 'summary.json')
    base = dict(type='world_run', arm=arm, rep=rep, cohort=cohort, run=run, group=group)
    scores = (summary or {}).get('student_scores') or []
    if summary is None or summary.get('status') == 'HOST_ERROR' or len(scores) != len(plans):
        reason = ('no summary.json' if summary is None else
                  f'summary status {summary.get("status")}' if summary.get('status') == 'HOST_ERROR' else
                  f'student_scores {len(scores)} != plans {len(plans)}')
        return [dict(base, world=w, seed=int(p['seed']), status='HOST_ERROR', host_error_reason=reason)
                for w, p in enumerate(plans)]
    by_seed = {int(s['seed']): s for s in scores}
    lift_t = stable_lift_complete(ev / 'owner/evaluation-only.jsonl')
    early, opened = gripper_flags(ev / 'actor-actions.jsonl', len(plans))
    rows = []
    for w, plan in enumerate(plans):
        s = by_seed[int(plan['seed'])]
        done = (s.get('issued_done_times') or {}).get('grasp')
        complete = lift_t.get(w)
        rows.append(dict(base, world=w, seed=int(plan['seed']), status='complete',
                         release_success=s.get('release_success') is True,
                         physical_success=s.get('physical_success') is True,
                         drop_detected=s.get('drop_detected') is True,
                         G=bool(done is not None and complete is not None and complete <= done + 1e-8),
                         early_open_grasp=early[w], open_issued=opened[w],
                         release_done=(s.get('issued_done_times') or {}).get('release') is not None,
                         cap_end=bool(s.get('cap_end') or s.get('resource_cap_end')),
                         failure_reason=s.get('failure_reason')))
    return rows


def ledger_rows(prereg_path, run_root):
    prereg = json.loads(Path(prereg_path).read_text())
    arms = set(prereg['arms'])
    rows = [dict(type='header', schema=SCHEMA, prereg_sha256=sha256(prereg_path), run_root=str(run_root),
                 host_error_rule='HOST_ERROR stays in the denominator as a failure; never re-run')]
    for run_dir in sorted(Path(run_root).iterdir()):
        m = RUN_NAME.match(run_dir.name)
        if not run_dir.is_dir() or not m:
            continue
        arm, cohort, rep = m['arm'], m['cohort'], int(m['rep'])
        if arm not in arms:
            raise ValueError(f'{run_dir.name}: arm {arm!r} not in prereg arms {sorted(arms)}')
        groups = sorted((run_dir / f'R8-{STAGE[cohort]}').glob('group-*'))
        if not groups:
            raise ValueError(f'{run_dir}: no group directories (run started but layout unknown)')
        for g in groups:
            rows += group_world_runs(g, arm=arm, rep=rep, cohort=COHORT[cohort], run=run_dir.name)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='new ledger JSONL (outside the run directories)')
    a = p.parse_args(argv)
    if a.out.exists():
        p.error(f'{a.out} exists; write a new ledger file')
    rows = ledger_rows(a.prereg, a.run_root)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    world = [r for r in rows if r['type'] == 'world_run']
    print(f'{a.out}: {len(world)} world-runs, HOST_ERROR {sum(r["status"] == "HOST_ERROR" for r in world)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
