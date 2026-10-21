#!/usr/bin/env python3
"""pairact P5: student/teacher run dirs -> episode rows JSONL for report_tables.py pairact-eval.

Eval-only; reads the --student-eval run (scripts/run_warp_flow_teacher.py, P5_STUDENT_EVAL.md)
and the teacher run on the same cases, writes one new rows file.  Format (dsh/report-auto
scripts/report_tables.py pairact-eval):

  {"type":"header","prereg_sha256","excluded_seeds":[...],"static_check_sha256","cases_sha256",
   "runs":{arm:[{"attempt","dir","summary_sha256"}]},"schema":"ugrp.pairact.p5_rows.v1"}
  {"type":"episode","arm":"student"|"teacher","seed","attempt":1|2,"status":"complete"|"HOST_ERROR",
   "success","funnel":{stage: true|false|null},"termination","student_gt_corrections",
   "teacher_commands_issued_to_student","world","dir"}

Per world (summary.json worlds[k], k -> case index via world_indices):
  status      HOST_ERROR when the index has no world row or raw/result.json status is HOST_ERROR
  success     worlds[k].success is True and worlds[k].carry_success is True (grasp hold gate AND the
              GT pair_carry_eval success = prereg success definition), both arms
  funnel      student: summary student_funnel.reached (harness/pairact_student_eval.StudentFunnel);
              teacher: approach/alignment/READY/grasp null (not recorded by the teacher runner),
              hold_3s = worlds[k].success, carry_1m/door from raw result.json carry_eval.funnel
              (carried_1m without drop_events, door_passed), place = success
  student_gt_corrections            raw result.json student_eval.gt_inputs_to_student (null if absent)
  teacher_commands_issued_to_student summary teacher_steps (null if absent)
  termination 'success' | 'HOST_ERROR' | 'cap_end' | carry_failure | 'failure'

Arm 'hybrid_n' (--hybrid-n, arm N '학습 근거리 + 코드 운반(hybrid)', run with --hybrid-carry): same as
'student' plus carry_mode, gt_inputs_to_code, code_segment_s, student_commands_executed_ratio and
hybrid_outcome from summary worlds[k].hybrid (raw result.json hybrid). A world without the hybrid
block is an error (the run was not a hybrid run). Never merged with 'student'.

Prereg exclusions.host_error (P5 only): one rerun of the same seed.  --student-rerun/--teacher-rerun
give attempt 2 rows, accepted only for seeds that were HOST_ERROR in attempt 1.
Rule A static exclusion: --static-check (static_stance_check.py output on the same cases);
flagged['overlap'] case indices become excluded_seeds and must not have been run.

Usage:
  python scripts/pairact_p5_rows.py --prereg PAIRACT_R1_EVAL_PREREG.json --cases p5-heldout-cases.json \
    --student RUN/p5-student --teacher RUN/p5-teacher [--static-check static.json] \
    [--student-rerun RUN/p5-student-rerun] [--teacher-rerun ...] --out RUN/report/p5-rows.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SCHEMA = 'ugrp.pairact.p5_rows.v1'
STUDENT_ARMS = ('student', 'hybrid_n')
FUNNEL = ('approach', 'alignment', 'READY', 'grasp', 'hold_3s', 'carry_1m', 'door', 'place')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    path = Path(path)
    if path.is_file():
        return json.loads(path.read_text())
    zst = path.with_name(path.name + '.zst')
    if zst.is_file():
        return json.loads(subprocess.check_output(['zstd', '-dc', str(zst)]))
    return None


def load_cases(path):
    cases = json.loads(Path(path).read_text())
    cases = cases['cases'] if isinstance(cases, dict) else cases
    return [int(c['plan']['seed']) for c in cases]


def teacher_funnel(world, raw):
    ce = (raw or {}).get('carry_eval')
    hold = world.get('success') is True
    if ce is None:
        carry = door = None if raw is None else False
    else:
        f = ce.get('funnel') or {}
        carry = bool(hold and f.get('carried_1m') and not ce.get('drop_events'))
        door = bool(carry and f.get('door_passed'))
    return dict(approach=None, alignment=None, READY=None, grasp=None, hold_3s=hold, carry_1m=carry, door=door)


def arm_rows(arm, run_dir, *, attempt, seeds, only=None):
    """Episode rows of one run dir.  only: case indices allowed (rerun)."""
    run_dir = Path(run_dir)
    summary = read_json(run_dir / 'summary.json')
    if summary is None:
        raise ValueError(f'{run_dir}/summary.json missing: a started run without summary must be '
                         'reported by hand as HOST_ERROR for its indices')
    idx = [int(i) for i in summary.get('world_indices') or range(len(seeds))]
    if only is not None and set(idx) - set(only):
        raise ValueError(f'{arm} attempt {attempt}: rerun indices {sorted(set(idx) - set(only))} '
                         'were not HOST_ERROR in attempt 1 (only one HOST_ERROR rerun is allowed)')
    worlds = {idx[int(w['world'])]: w for w in summary.get('worlds') or ()}
    rows = []
    for k, i in enumerate(idx):
        base = dict(type='episode', arm=arm, seed=seeds[i], attempt=attempt, world=i, dir=str(run_dir))
        w = worlds.get(i)
        raw = read_json(run_dir / f'world-{k:03d}' / 'raw' / 'result.json') if w is not None else None
        if w is not None and w.get('seed') is not None and int(w['seed']) != seeds[i]:
            raise ValueError(f'{arm} world {i}: seed {w["seed"]} != cases seed {seeds[i]}')
        if w is None or (raw or {}).get('status') == 'HOST_ERROR':
            rows.append(dict(base, status='HOST_ERROR', success=False, funnel={s: None for s in FUNNEL},
                             termination='HOST_ERROR', student_gt_corrections=None,
                             teacher_commands_issued_to_student=None,
                             **({'carry_mode': None, 'gt_inputs_to_code': None} if arm == 'hybrid_n' else {})))
            continue
        success = w.get('success') is True and w.get('carry_success') is True
        extra = {}
        if arm == 'hybrid_n':
            hy = w.get('hybrid')
            if not isinstance(hy, dict):
                raise ValueError(f'hybrid_n world {i}: no hybrid block (run was not --hybrid-carry)')
            extra = dict(carry_mode=hy.get('carry_mode'), gt_inputs_to_code=hy.get('gt_inputs_to_code'),
                         code_segment_s=hy.get('code_segment_s'), hybrid_outcome=hy.get('outcome'),
                         student_commands_executed_ratio=hy.get('student_commands_executed_ratio'))
        if arm in STUDENT_ARMS:
            reached = (w.get('student_funnel') or {}).get('reached') or {}
            funnel = {s: reached.get(s) for s in FUNNEL}
            gt = ((raw or {}).get('student_eval') or {}).get('gt_inputs_to_student')
            teacher_steps = w.get('teacher_steps')
        else:
            funnel = teacher_funnel(w, raw)
            funnel['place'] = success
            gt = teacher_steps = None
        term = ('success' if success else 'cap_end' if w.get('cap_end') or (raw or {}).get('cap_end')
                else w.get('carry_failure') or 'failure')
        rows.append(dict(base, status='complete', success=success, funnel=funnel, termination=term,
                         student_gt_corrections=gt, teacher_commands_issued_to_student=teacher_steps, **extra))
    return rows


def build(a):
    seeds = load_cases(a.cases)
    excluded, static_sha = [], None
    if a.static_check:
        static = json.loads(Path(a.static_check).read_text())
        excluded = sorted(seeds[int(i)] for i in static['flagged']['overlap'])
        static_sha = sha256(a.static_check)
    head = dict(type='header', schema=SCHEMA, prereg_sha256=sha256(a.prereg), excluded_seeds=excluded,
                static_check_sha256=static_sha, cases_sha256=sha256(a.cases), runs={},
                host_error_rule='prereg exclusions.host_error: one rerun of the same seed; second HOST_ERROR is a failure')
    rows = [head]
    arms = [('student', a.student, a.student_rerun), ('teacher', a.teacher, a.teacher_rerun)]
    if getattr(a, 'hybrid_n', None):
        arms.insert(1, ('hybrid_n', a.hybrid_n, getattr(a, 'hybrid_n_rerun', None)))
    for arm, first, rerun in arms:
        head['runs'][arm] = []
        r1 = arm_rows(arm, first, attempt=1, seeds=seeds)
        head['runs'][arm].append(dict(attempt=1, dir=str(first), summary_sha256=sha256(Path(first) / 'summary.json')))
        rows += r1
        if rerun:
            host = [r['world'] for r in r1 if r['status'] == 'HOST_ERROR']
            rows += arm_rows(arm, rerun, attempt=2, seeds=seeds, only=host)
            head['runs'][arm].append(dict(attempt=2, dir=str(rerun), summary_sha256=sha256(Path(rerun) / 'summary.json')))
    ran = {r['seed'] for r in rows[1:]}
    if set(excluded) & ran:
        raise ValueError(f'rule-A excluded seeds were run: {sorted(set(excluded) & ran)}')
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--student', type=Path, required=True)
    p.add_argument('--teacher', type=Path, required=True)
    p.add_argument('--student-rerun', type=Path)
    p.add_argument('--teacher-rerun', type=Path)
    p.add_argument('--hybrid-n', type=Path, help="arm N hybrid run dir (--hybrid-carry); P5 arm 'hybrid_n'")
    p.add_argument('--hybrid-n-rerun', type=Path)
    p.add_argument('--static-check', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    if a.out.exists():
        p.error(f'{a.out} exists; write a new rows file')
    rows = build(a)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    print(f'{a.out}: {len(rows) - 1} episode rows')
    return 0


if __name__ == '__main__':
    sys.exit(main())
