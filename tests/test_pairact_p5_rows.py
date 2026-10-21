"""pairact P5 rows writer on fake run dirs (no physics)."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pairact_p5_rows as pr  # noqa: E402

SEEDS = list(range(8342000, 8342020))
STUDENT_REACHED = dict(approach=True, alignment=True, READY=True, grasp=True, hold_3s=False,
                       carry_1m=False, door=False, place=False)


def setup(tmp_path):
    pre = tmp_path / 'prereg.json'
    pre.write_text(json.dumps(dict(status='FROZEN')))
    cases = tmp_path / 'cases.json'
    cases.write_text(json.dumps([dict(plan=dict(seed=s)) for s in SEEDS]))
    return pre, cases


def run_dir(path, arm, indices, *, missing=(), host=(), win=()):
    worlds = []
    for k, i in enumerate(indices):
        if i in missing:
            continue
        ok = i in win
        w = dict(world=k, seed=SEEDS[i], success=ok or arm == 'teacher', carry_success=ok, cap_end=False,
                 carry_failure=None if ok else 'carry_total_timeout')
        raw = dict(status='HOST_ERROR' if i in host else 'complete')
        if arm in ('student', 'hybrid_n'):
            if arm == 'hybrid_n':
                w['hybrid'] = dict(carry_mode='nav', gt_inputs_to_code=0, code_segment_s=40., outcome='handed_back',
                                   student_commands_executed_ratio=.5)
            w.update(student_funnel=dict(reached=dict(STUDENT_REACHED, **({s: True for s in pr.FUNNEL} if ok else {}))),
                     teacher_steps=0)
            raw['student_eval'] = dict(gt_inputs_to_student=0, teacher_steps=0)
        else:
            raw['carry_eval'] = dict(success=ok, drop_events=[], funnel=dict(carried_1m=True, door_passed=ok))
        worlds.append(w)
        (path / f'world-{k:03d}' / 'raw').mkdir(parents=True)
        (path / f'world-{k:03d}' / 'raw' / 'result.json').write_text(json.dumps(raw))
    path.mkdir(parents=True, exist_ok=True)
    (path / 'summary.json').write_text(json.dumps(dict(world_indices=list(indices), worlds=worlds)))
    return path


def args(pre, cases, student, teacher, out, **kw):
    a = ['--prereg', str(pre), '--cases', str(cases), '--student', str(student), '--teacher', str(teacher),
         '--out', str(out)]
    for k, v in kw.items():
        a += ['--' + k.replace('_', '-'), str(v)]
    return a


def test_rows_header_funnel_and_rerun(tmp_path):
    pre, cases = setup(tmp_path)
    idx = [i for i in range(20) if i != 7]                  # case 7 excluded by rule A
    st = run_dir(tmp_path / 'student', 'student', idx, missing=(3,), host=(4,), win=(0,))
    te = run_dir(tmp_path / 'teacher', 'teacher', idx, win=(0, 1, 2))
    rr = run_dir(tmp_path / 'student-rerun', 'student', [3, 4])
    static = tmp_path / 'static.json'
    static.write_text(json.dumps(dict(flagged=dict(overlap=[7], admission=[], floor=[]))))
    out = tmp_path / 'report' / 'p5-rows.jsonl'
    assert pr.main(args(pre, cases, st, te, out, static_check=static, student_rerun=rr)) == 0
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    head, ep = rows[0], rows[1:]
    assert head['excluded_seeds'] == [SEEDS[7]] and head['static_check_sha256'] == pr.sha256(static)
    assert head['prereg_sha256'] == pr.sha256(pre) and [r['attempt'] for r in head['runs']['student']] == [1, 2]
    s = {(r['seed'], r['attempt']): r for r in ep if r['arm'] == 'student'}
    t = {r['seed']: r for r in ep if r['arm'] == 'teacher'}
    assert len(t) == 19 and SEEDS[7] not in t
    assert s[(SEEDS[0], 1)]['success'] and s[(SEEDS[0], 1)]['funnel']['place'] is True
    assert s[(SEEDS[0], 1)]['student_gt_corrections'] == 0 and s[(SEEDS[0], 1)]['teacher_commands_issued_to_student'] == 0
    assert s[(SEEDS[1], 1)]['funnel']['READY'] is True and s[(SEEDS[1], 1)]['funnel']['hold_3s'] is False
    assert s[(SEEDS[3], 1)]['status'] == 'HOST_ERROR' and s[(SEEDS[4], 1)]['status'] == 'HOST_ERROR'
    assert s[(SEEDS[3], 2)]['status'] == 'complete' and s[(SEEDS[4], 2)]['attempt'] == 2
    assert t[SEEDS[2]]['success'] and t[SEEDS[2]]['funnel']['door'] is True and t[SEEDS[2]]['funnel']['READY'] is None
    assert t[SEEDS[5]]['funnel']['hold_3s'] is True and t[SEEDS[5]]['funnel']['carry_1m'] is True
    assert t[SEEDS[5]]['funnel']['door'] is False and t[SEEDS[5]]['termination'] == 'carry_total_timeout'
    with pytest.raises(SystemExit):
        pr.main(args(pre, cases, st, te, out))


def test_rerun_of_non_host_error_seed_refused(tmp_path):
    pre, cases = setup(tmp_path)
    st = run_dir(tmp_path / 'student', 'student', list(range(20)))
    te = run_dir(tmp_path / 'teacher', 'teacher', list(range(20)))
    rr = run_dir(tmp_path / 'rerun', 'student', [5])
    with pytest.raises(ValueError, match='only one HOST_ERROR rerun'):
        pr.main(args(pre, cases, st, te, tmp_path / 'o.jsonl', student_rerun=rr))


def test_excluded_seed_that_ran_is_refused(tmp_path):
    pre, cases = setup(tmp_path)
    st = run_dir(tmp_path / 'student', 'student', list(range(20)))
    te = run_dir(tmp_path / 'teacher', 'teacher', list(range(20)))
    static = tmp_path / 'static.json'
    static.write_text(json.dumps(dict(flagged=dict(overlap=[2]))))
    with pytest.raises(ValueError, match='excluded seeds were run'):
        pr.main(args(pre, cases, st, te, tmp_path / 'o.jsonl', static_check=static))


def test_missing_gt_record_is_null_not_zero(tmp_path):
    pre, cases = setup(tmp_path)
    st = run_dir(tmp_path / 'student', 'student', [0], win=(0,))
    raw = st / 'world-000' / 'raw' / 'result.json'
    raw.write_text(json.dumps(dict(status='complete')))
    s = json.loads((st / 'summary.json').read_text()); s['worlds'][0].pop('teacher_steps')
    (st / 'summary.json').write_text(json.dumps(s))
    te = run_dir(tmp_path / 'teacher', 'teacher', [0])
    rows = pr.build(pr.argparse.Namespace(prereg=pre, cases=cases, student=st, teacher=te, student_rerun=None,
                                          teacher_rerun=None, static_check=None))
    r = next(x for x in rows if x.get('arm') == 'student')
    assert r['student_gt_corrections'] is None and r['teacher_commands_issued_to_student'] is None


def test_hybrid_n_arm_rows_are_separate_and_carry_the_code_audit(tmp_path):
    pre, cases = setup(tmp_path)
    idx = list(range(20))
    st = run_dir(tmp_path / 'student', 'student', idx)
    hy = run_dir(tmp_path / 'hybrid', 'hybrid_n', idx, win=(0, 1))
    te = run_dir(tmp_path / 'teacher', 'teacher', idx, win=(0, 1, 2))
    out = tmp_path / 'rows.jsonl'
    assert pr.main(args(pre, cases, st, te, out, hybrid_n=hy)) == 0
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert set(rows[0]['runs']) == {'student', 'hybrid_n', 'teacher'}
    h = [r for r in rows[1:] if r['arm'] == 'hybrid_n']
    assert len(h) == 20 and sum(r['success'] for r in h) == 2
    assert all(r['carry_mode'] == 'nav' and r['gt_inputs_to_code'] == 0 for r in h)
    assert sum(r['success'] for r in rows[1:] if r['arm'] == 'student') == 0
    # a plain student run cannot pose as hybrid_n
    with pytest.raises(ValueError, match='no hybrid block'):
        pr.main(args(pre, cases, st, te, tmp_path / 'o2.jsonl', hybrid_n=st))
