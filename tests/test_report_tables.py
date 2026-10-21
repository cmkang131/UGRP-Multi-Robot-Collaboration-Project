"""scripts/report_tables.py on fake inputs (no physics, no run roots)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import report_tables as rt

FIX = Path(__file__).parent / 'fixtures' / 'report_auto'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return path


def frozen_copy(src, dst, status='FROZEN'):
    d = json.loads(Path(src).read_text())
    d['status'] = status
    dst.write_text(json.dumps(d))
    return dst


# ------------------------------------------------------------------ basics

def test_wilson_known_values():
    lo, hi = rt.wilson(0, 20)
    assert lo == 0.0 and abs(hi - 0.1611) < 1e-3
    lo, hi = rt.wilson(10, 20)
    assert abs(lo - 0.2993) < 1e-3 and abs(hi - 0.7007) < 1e-3
    assert rt.wilson(0, 0) == (None, None)
    with pytest.raises(ValueError):
        rt.wilson(3, 2)


def test_nn_format():
    assert rt.nn(6, 6).startswith('6/6 (100%, CI 61–100%)')
    assert rt.nn(0, 0) == '0/0'


def test_draft_prereg_refused_without_flag(tmp_path):
    inputs = rt.Inputs()
    with pytest.raises(rt.ReportError, match='allow-draft'):
        rt.check_prereg(inputs, FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json')
    pre = rt.check_prereg(inputs, FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', allow_draft=True)
    assert pre['final'] is False and pre['status'] == 'DRAFT_NOT_REGISTERED'


def test_prereg_sha_mismatch_refused(tmp_path):
    inputs = rt.Inputs()
    with pytest.raises(rt.ReportError, match='recorded prereg sha256'):
        rt.check_prereg(inputs, FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', recorded_sha={'x': '0' * 64},
                        allow_draft=True)
    with pytest.raises(rt.ReportError, match='expect-prereg-sha'):
        rt.check_prereg(inputs, FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', expect_sha='1' * 64, allow_draft=True)


def test_frozen_status_is_final(tmp_path):
    p = frozen_copy(FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', tmp_path / 'p.json')
    assert rt.check_prereg(rt.Inputs(), p)['final'] is True
    p2 = frozen_copy(FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', tmp_path / 'p2.json', 'READY_FOR_REVIEW')
    assert rt.check_prereg(rt.Inputs(), p2, allow_draft=True)['final'] is False


# ------------------------------------------------------------------ (a) tournament

def tournament_rows(prereg_path, *, base_ok=6, cand_ok=None, drop_arm_runs=0, g_fail=None):
    pre = json.loads(Path(prereg_path).read_text())
    cand_ok = cand_ok or {'A-c1': 10, 'A-c2': 7, 'A-c3': 9}
    g_fail = g_fail or {}
    rows = [dict(type='header', prereg_sha256=sha(prereg_path))]
    seeds = [(c, s) for c in ('HO4', 'TRAIN4') for s in pre['seeds'][c]]
    for arm in pre['arms']:
        k = base_ok if arm == 'A-base' else cand_ok[arm]
        i = 0
        for rep in (1, 2, 3):
            for c, s in seeds:
                i += 1
                if arm == 'A-c3' and i <= drop_arm_runs:
                    continue
                rows.append(dict(type='world_run', arm=arm, rep=rep, cohort=c, seed=s, status='complete',
                                 release_success=i <= k, physical_success=i <= k, drop_detected=False,
                                 G=i > g_fail.get(arm, 2), early_open_grasp=False, open_issued=i <= k + 1,
                                 release_done=i <= k, cap_end=i > k))
    return rows


def run(argv):
    return rt.main([str(a) for a in argv])


def test_tournament_winner_and_safety(tmp_path):
    p = frozen_copy(FIX / 'CARRY_TOURNAMENT_A_PREREG_DRAFT.json', tmp_path / 'prereg.json')
    led = write_jsonl(tmp_path / 'ledger.jsonl', tournament_rows(p, g_fail={'A-c1': 5}))
    out = tmp_path / 'out'
    assert run(['tournament', '--prereg', p, '--ledger', led, '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())
    v = doc['data']['verdicts']
    assert v['A-c1'].startswith('탈락(안전: G -3/24)')   # +4 primary but G 19 vs 22
    assert v['A-c3'] == '승자'                             # +3 meets the minimum
    assert v['A-c2'].startswith('최소 개선폭 미달')
    assert doc['data']['winner'] == 'A-c3'
    md = (out / 'report.md').read_text()
    assert '9/24' in md and str(sha(led)) in md and sha(p) in md
    assert doc['inputs_sha256'][str(led)] == sha(led)


def test_tournament_incomplete_is_pending_and_draft_labelled(tmp_path):
    p = FIX / 'CARRY_TOURNAMENT_A_PREREG_DRAFT.json'
    led = write_jsonl(tmp_path / 'ledger.jsonl', tournament_rows(p, drop_arm_runs=2))
    out = tmp_path / 'out'
    assert run(['tournament', '--prereg', p, '--ledger', led, '--out', out]) == 2       # draft refused
    assert run(['tournament', '--prereg', p, '--ledger', led, '--out', out, '--allow-draft']) == 0
    doc = json.loads((out / 'report.json').read_text())
    assert doc['verdict_allowed'] is False and doc['data']['winner'] is None
    assert len(doc['data']['missing']) == 2 and doc['data']['arms']['A-c3']['missing'] == 2
    assert '초안 기준, 판정 아님' in (out / 'report.md').read_text()


def test_tournament_rejects_unregistered_seed_and_sha(tmp_path):
    p = frozen_copy(FIX / 'CARRY_TOURNAMENT_A_PREREG_DRAFT.json', tmp_path / 'prereg.json')
    rows = tournament_rows(p)
    rows[1]['seed'] = 99999
    led = write_jsonl(tmp_path / 'l.jsonl', rows)
    assert run(['tournament', '--prereg', p, '--ledger', led, '--out', tmp_path / 'o']) == 2
    rows = tournament_rows(p)
    rows[0]['prereg_sha256'] = 'f' * 64
    led = write_jsonl(tmp_path / 'l2.jsonl', rows)
    assert run(['tournament', '--prereg', p, '--ledger', led, '--out', tmp_path / 'o2']) == 2


def test_tournament_host_error_rule_from_prereg(tmp_path):
    p = frozen_copy(FIX / 'CARRY_TOURNAMENT_A_PREREG_DRAFT.json', tmp_path / 'prereg.json')
    rows = tournament_rows(p)
    target = next(r for r in rows if r.get('arm') == 'A-c3' and r.get('release_success'))
    for k in ('release_success', 'physical_success', 'G'):
        target.pop(k)
    target['status'] = 'HOST_ERROR'
    out = tmp_path / 'out'
    assert run(['tournament', '--prereg', p, '--ledger', write_jsonl(tmp_path / 'l.jsonl', rows), '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())
    assert doc['data']['arms']['A-c3']['host_error'] == 1 and doc['data']['arms']['A-c3']['primary'] == 8
    md = (out / 'report.md').read_text()
    assert '재실행하지 않고 분모에 남겨 실패' in md
    rows[1]['status'] = 'retry'
    assert run(['tournament', '--prereg', p, '--ledger', write_jsonl(tmp_path / 'l2.jsonl', rows),
                '--out', tmp_path / 'o2']) == 2


# ------------------------------------------------------------------ (a') pairact P1

def p1_prereg(tmp_path, excluded=(37,), status='FROZEN'):
    d = json.loads((FIX / 'PAIRACT_P1_PREREG_DRAFT.json').read_text())
    d['status'] = status
    d['static_exclusion']['tournament']['excluded_worlds'] = list(excluded)
    d['static_exclusion']['confirmation']['excluded_worlds'] = []
    p = tmp_path / 'P1.json'
    p.write_text(json.dumps(d))
    return p


def p1_rows(p, stage, passes, *, excluded=(37,), host=None, arms=None):
    """passes: arm -> set of passing world indices; host: arm -> set of HOST_ERROR indices."""
    not_exec = [15] if stage == 'tournament' else []
    excluded = list(excluded) if stage == 'tournament' else []
    arms = arms or list(passes)
    rows = [dict(type='header', prereg_sha256=sha(p), stage=stage, excluded_worlds=excluded, not_executed=not_exec,
                 arms=arms)]
    for a in passes:
        for w in range(40):
            st = ('excluded' if w in excluded else 'not_executed' if w in not_exec
                  else 'HOST_ERROR' if w in (host or {}).get(a, ()) else 'complete')
            rows.append(dict(type='world_run', arm=a, rep=1, cohort=stage, world=w, seed=8420000 + w, status=st,
                             success=st == 'complete' and w in passes[a], cap_end=False))
    return rows


def test_pairact_p1_tournament_winner_tie_and_host_error(tmp_path):
    p = p1_prereg(tmp_path)
    allw = set(range(40)) - {15, 37}                                   # 38 executable, N_eff 39, need 38
    passes = {'r13': allw - {27}, 'c1': set(allw), 'c2b': set(allw), 'c3': allw - {27, 3}}
    out = tmp_path / 'out'
    led = write_jsonl(tmp_path / 'l.jsonl', p1_rows(p, 'tournament', passes, host={'c3': {5}}))
    assert run(['pairact-p1', '--prereg', p, '--ledger', led, '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())['data']
    assert (doc['N_eff'], doc['need']) == (39, 38)
    assert doc['arms']['r13']['n'] == 37 and doc['arms']['c1']['n'] == 38 and doc['arms']['c3']['host_error'] == 1
    assert doc['winner'] == 'c1'                                       # tie c1/c2b, both pass 27 -> c3, c1, c2b order
    assert doc['verdicts']['c2b'] == '채택 기준 통과(패)' and doc['verdicts']['c3'] == '채택 기준 미달'
    assert doc['arms']['c3']['new_failures_vs_r13'] == [3, 5]
    md = (out / 'report.md').read_text()
    assert '38/39' in md and '37/40' in md and '재실행하지 않고' in md


def test_pairact_p1_confirmation_d5_and_refusals(tmp_path):
    p = p1_prereg(tmp_path)
    allw = set(range(40))
    led = write_jsonl(tmp_path / 'c.jsonl', p1_rows(p, 'confirmation', {'r13': set(allw), 'c1': allw - {1}}))
    out = tmp_path / 'out'
    assert run(['pairact-p1', '--prereg', p, '--ledger', led, '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())['data']
    assert doc['winner'] is None and doc['verdicts']['c1'].startswith('불채택(r13보다 적음')
    # missing arm -> held; duplicate row, wrong exclusion and sha mismatch -> refused
    rows = p1_rows(p, 'tournament', {'r13': set(range(40)) - {15, 37}}, arms=['r13', 'c1', 'c2b', 'c3'])
    assert run(['pairact-p1', '--prereg', p, '--ledger', write_jsonl(tmp_path / 'm.jsonl', rows),
                '--out', tmp_path / 'om']) == 0
    assert json.loads((tmp_path / 'om' / 'report.json').read_text())['data']['missing'] == ['c1', 'c2b', 'c3']
    bad = rows + [rows[1]]
    assert run(['pairact-p1', '--prereg', p, '--ledger', write_jsonl(tmp_path / 'd.jsonl', bad), '--out', tmp_path / 'o']) == 2
    bad = [dict(r) for r in rows]
    bad[0]['excluded_worlds'] = []
    assert run(['pairact-p1', '--prereg', p, '--ledger', write_jsonl(tmp_path / 'e.jsonl', bad), '--out', tmp_path / 'o']) == 2
    bad = [dict(rows[0], prereg_sha256='0' * 64)] + rows[1:]
    assert run(['pairact-p1', '--prereg', p, '--ledger', write_jsonl(tmp_path / 's.jsonl', bad), '--out', tmp_path / 'o']) == 2
    (tmp_path / 'draft').mkdir()
    d = p1_prereg(tmp_path / 'draft', status='READY_FOR_REVIEW')                   # not FROZEN -> refused
    rows = p1_rows(d, 'tournament', {'r13': set(range(40))}, arms=['r13', 'c1', 'c2b', 'c3'])
    assert run(['pairact-p1', '--prereg', d, '--ledger', write_jsonl(tmp_path / 'r.jsonl', rows), '--out', tmp_path / 'o']) == 2


# ------------------------------------------------------------------ (b1) pairact collect

def collect_report(prereg_sha, mode='training'):
    def t(s, a, n, e=0):
        return dict(attempts=n, successes=s, admitted=a, env_failures=e, env_by_kind={}, record_errors=0)
    bins = [dict(bin=f'B{i}', distance_m=[0.3 + 0.3 * (i // 2), 0.6 + 0.3 * (i // 2)],
                 yaw='facing' if i % 2 == 0 else 'away', **t(20 - i, 18 - i, 40), success_rate=None,
                 admitted_rate=None, need=max(0, 20 - (18 - i)), bin_limited=i == 5, setup_rejections=i,
                 failure_subreasons={'approach:cap_end:none': 2}) for i in range(6)]
    rep = dict(schema='ugrp.pairact_r1.collect_report.v2', prereg_sha256=prereg_sha, mode=mode, noise='on',
               run_state='STOPPED', not_pooled_with=['B teacher gate n/40', 'C student n/20'])
    if mode == 'measurement':
        rep['pilot'] = dict(text='pilot', **t(20, 15, 40, 2), bins=bins)
        return rep
    rep['A'] = dict(text='교사 시연 수집 ...', **t(105, 93, 240, 3), bins=bins,
                    by_seed_phase={'primary': dict(**t(80, 70, 200), bins=bins), 'extension': dict(**t(25, 23, 40), bins=bins)},
                    bin_limited=[])
    rep['validation'] = dict(text='validation: 물리 성공 12 / 20, 채택 11 / 20 (환경 실패 0 별도)', **t(12, 11, 20))
    rep['decision'] = dict(decision='TRAIN_SMALL_DATA', train_stop='STOP_CAP', validation='pending',
                           labels=['소량 데이터(A<150): 결과 해석은 단계 퍼널 중심으로 제한'], limited_bins=[])
    return rep


@pytest.mark.parametrize('mode', ['training', 'measurement'])
def test_pairact_collect(tmp_path, mode):
    p = tmp_path / 'COLLECT_PREREG.json'
    p.write_text(json.dumps(dict(status='FROZEN', schema='ugrp.pairact_r1.collect_prereg.v2')))
    r = tmp_path / 'report.json'
    r.write_text(json.dumps(collect_report(sha(p), mode)))
    out = tmp_path / 'out'
    assert run(['pairact-collect', '--prereg', p, '--report', r, '--out', out]) == 0
    md = (out / 'report.md').read_text()
    if mode == 'training':
        assert '표기 A' in md and '105/240' in md and '93/240' in md and '분모가 아닙니다' in md
        assert 'TRAIN_SMALL_DATA' in md
    else:
        assert 'pilot(수율 측정, 시연 아님)' in md and '20/40' in md
    assert '| B5 |' in md


def test_pairact_collect_sha_mismatch(tmp_path):
    p = tmp_path / 'COLLECT_PREREG.json'
    p.write_text(json.dumps(dict(status='FROZEN')))
    r = tmp_path / 'report.json'
    r.write_text(json.dumps(collect_report('0' * 64)))
    assert run(['pairact-collect', '--prereg', p, '--report', r, '--out', tmp_path / 'o']) == 2


# ------------------------------------------------------------------ (b2) pairact P5 eval

FUNNEL = ['approach', 'alignment', 'READY', 'grasp', 'hold_3s', 'carry_1m', 'door', 'place']


def episode(arm, seed, reach, **kw):
    f = {st: i < reach for i, st in enumerate(FUNNEL)}
    row = dict(type='episode', arm=arm, seed=seed, attempt=1, status='complete', success=reach == len(FUNNEL),
               funnel=f, termination='success' if reach == len(FUNNEL) else 'cap_end',
               student_gt_corrections=0, teacher_commands_issued_to_student=0)
    row.update(kw)
    return row


def test_pairact_eval_funnel_and_exclusions(tmp_path):
    p = frozen_copy(FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', tmp_path / 'p.json')
    seeds = list(range(8342000, 8342020))
    rows = [dict(type='header', prereg_sha256=sha(p), excluded_seeds=[8342019], static_check_sha256='a' * 64)]
    for i, s in enumerate(seeds[:-1]):
        rows.append(episode('teacher', s, 8 if i < 15 else 5))
        if s == 8342003:
            rows.append(episode('student', s, 0, status='HOST_ERROR', termination='HOST_ERROR'))
            rows.append(episode('student', s, 0, status='HOST_ERROR', attempt=2, termination='HOST_ERROR'))
        elif s == 8342004:
            rows.append(episode('student', s, 8, student_gt_corrections=1))
        else:
            rows.append(episode('student', s, 8 if i == 0 else i % 5))
    led = write_jsonl(tmp_path / 'rows.jsonl', rows)
    out = tmp_path / 'out'
    assert run(['pairact-eval', '--prereg', p, '--rows', led, '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())
    a = doc['data']['arms']
    assert doc['data']['N_eff'] == 19
    assert a['teacher']['n'] == 15 and a['student']['n'] == 1                 # corrected seed is not a success
    assert a['student']['host_error_twice'] == [8342003]
    assert a['teacher']['funnel']['approach'] == 19
    md = (out / 'report.md').read_text()
    assert '표기 C' in md and '1/19' in md and '15/19' in md and '8342004' in md


def test_pairact_eval_unrecorded_teacher_stages_and_null_counters(tmp_path):
    p = frozen_copy(FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', tmp_path / 'p.json')
    rows = [dict(type='header', prereg_sha256=sha(p))]
    for s in range(8342000, 8342020):
        t = episode('teacher', s, 8 if s < 8342010 else 6, student_gt_corrections=None,
                    teacher_commands_issued_to_student=None)
        for st in ('approach', 'alignment', 'READY', 'grasp'):
            t['funnel'][st] = None                                  # pairact_p5_rows: teacher runner does not record
        rows.append(t)
        rows.append(episode('student', s, 8 if s == 8342000 else 3,
                            **({'student_gt_corrections': None} if s == 8342000 else {})))
    out = tmp_path / 'out'
    assert run(['pairact-eval', '--prereg', p, '--rows', write_jsonl(tmp_path / 'r.jsonl', rows), '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())['data']['arms']
    assert doc['teacher']['n'] == 10 and doc['student']['n'] == 0      # null GT counter is not a success
    assert doc['teacher']['unrecorded'] == ['approach', 'alignment', 'READY', 'grasp']
    assert not doc['teacher'].get('funnel_non_monotone')
    md = (out / 'report.md').read_text()
    assert '미기록' in md and '8342000' in md and 'door에서 멈춤' in md


def test_pairact_eval_refusals(tmp_path):
    p = frozen_copy(FIX / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json', tmp_path / 'p.json')
    head = dict(type='header', prereg_sha256=sha(p))
    for bad in ([episode('student', 8341000, 1)],                                     # not heldout
                [episode('student', 8342000, 1), episode('student', 8342000, 2)],     # double count
                [episode('student', 8342000, 7, success=True)],                       # success without place
                [episode('oracle', 8342000, 1)]):                                     # unknown arm
        led = write_jsonl(tmp_path / 'r.jsonl', [head] + bad)
        assert run(['pairact-eval', '--prereg', p, '--rows', led, '--out', tmp_path / 'o']) == 2
    led = write_jsonl(tmp_path / 'r.jsonl', [dict(head, excluded_seeds=[8342001])])   # exclusion without hash
    assert run(['pairact-eval', '--prereg', p, '--rows', led, '--out', tmp_path / 'o']) == 2


# ------------------------------------------------------------------ (c) L1-lite

def l1_analysis(prereg_sha, wins=None, host=(), not_run=(), dev=False):
    """Shape of scripts/analyze_l1lite.py analyze() output (dsh/l1lite-alloc f6e812bc6)."""
    wins = wins or {'no_comm': 2, 'structured': 5, 'peer_en': 6, 'leader_en': 4}
    cells, table = [], {}
    for c in rt.L1_CONDITIONS:
        mine = []
        for i, s in enumerate(rt.L1_TEST_SEEDS + ((701,) if dev and c == 'peer_en' else ())):
            ok = i < wins[c] and (c, s) not in host and (c, s) not in not_run
            reasons = ([] if ok else ['HOST_ERROR'] if (c, s) in host else ['NOT_RUN'] if (c, s) in not_run
                       else ['L1LITE_DUPLICATE_SLOT', 'SLOTS_NOT_DISTINCT'] if c == 'no_comm' else ['CLAIM_INCOMPLETE'])
            mine.append(dict(condition=c, seed=s, success=ok, reasons=reasons, attempts=1,
                             primary_reason=reasons[0] if reasons else None))
        cells += mine
        prim = {}
        for x in mine:
            if x['primary_reason']:
                prim[x['primary_reason']] = prim.get(x['primary_reason'], 0) + 1
        table[c] = dict(n_success=sum(x['success'] for x in mine), n_total=len(mine), primary_failure_reasons=prim,
                        host_error=prim.get('HOST_ERROR', 0), not_run=prim.get('NOT_RUN', 0),
                        aux=dict(completion_sim_s_success_median=40.1, min_body_gap_m_min=.1, min_body_gap_m_median=.2,
                                 utterances_per_run_mean=2.0, deadlock_runs=0, hallucination_total=0,
                                 hallucination_runs=0, llm_calls_total=12, llm_tokens_total=12000,
                                 llm_cost_usd_total=0.0012))
    return dict(schema='ugrp.e2ewarp.l1lite_analysis.v1', frozen_source_sha='f' * 40, prereg_sha256=prereg_sha,
                table=table, cells=cells, excluded=[dict(order=25, condition='peer_en', seed=701, kind='dev',
                                                        reason='dev_seed')], protocol_deviations=[],
                ledger=dict(path='ledger.json', sha256=None))


def frozen_md(src, dst):
    dst.write_text(Path(src).read_text().replace('**READY_FOR_REVIEW**', '**FROZEN**', 1))
    return dst


def test_l1lite_condition_table_from_analysis(tmp_path):
    p = frozen_md(FIX / 'PREREG_L1LITE.md', tmp_path / 'PREREG_L1LITE.md')
    led = tmp_path / 'ledger.json'
    led.write_text('{"schema": "ugrp.e2ewarp.l1lite_ledger.v1"}')
    an = l1_analysis(sha(p), host={('leader_en', 606)})
    an['ledger']['sha256'] = sha(led)
    a = tmp_path / 'analysis.json'
    a.write_text(json.dumps(an))
    out = tmp_path / 'out'
    assert run(['l1lite', '--prereg', p, '--analysis', a, '--ledger', led, '--out', out]) == 0
    doc = json.loads((out / 'report.json').read_text())
    st = doc['data']['conditions']
    assert [st[c]['n'] for c in rt.L1_CONDITIONS] == [2, 5, 6, 4] and st['leader_en']['host_error'] == 1
    assert st['no_comm']['component_failures']['서로 다른 슬롯'] == 4
    assert doc['verdict_allowed'] is True and doc['data']['incomplete'] is False
    md = (out / 'report.md').read_text()
    assert '6/6' in md and 'dev_seed' in md and '[확인 필요]' not in md


def test_l1lite_markdown_status_and_refusals(tmp_path):
    p = FIX / 'PREREG_L1LITE.md'                                       # READY_FOR_REVIEW -> draft
    a = tmp_path / 'a.json'
    a.write_text(json.dumps(l1_analysis(sha(p))))
    assert rt.prereg_status(p.read_bytes()) == 'READY_FOR_REVIEW'
    assert run(['l1lite', '--prereg', p, '--analysis', a, '--out', tmp_path / 'o']) == 2
    assert run(['l1lite', '--prereg', p, '--analysis', a, '--out', tmp_path / 'o', '--allow-draft']) == 0
    for bad in (l1_analysis('0' * 64), l1_analysis(sha(p), dev=True), dict(l1_analysis(sha(p)), schema='x')):
        a.write_text(json.dumps(bad))
        assert run(['l1lite', '--prereg', p, '--analysis', a, '--out', tmp_path / 'o', '--allow-draft']) == 2
    led = tmp_path / 'ledger.json'
    led.write_text('{}')
    a.write_text(json.dumps(l1_analysis(sha(p))))                      # ledger hash not in analysis
    assert run(['l1lite', '--prereg', p, '--analysis', a, '--ledger', led, '--out', tmp_path / 'o',
                '--allow-draft']) == 2


def test_l1lite_incomplete_run_label(tmp_path):
    p = frozen_md(FIX / 'PREREG_L1LITE.md', tmp_path / 'P.md')
    a = tmp_path / 'a.json'
    a.write_text(json.dumps(l1_analysis(sha(p), not_run={('structured', s) for s in rt.L1_TEST_SEEDS[:5]})))
    out = tmp_path / 'out'
    assert run(['l1lite', '--prereg', p, '--analysis', a, '--out', out]) == 0
    assert json.loads((out / 'report.json').read_text())['data']['incomplete'] is True
    assert '실행 불완전' in (out / 'report.md').read_text()


# ------------------------------------------------------------------ (d) E2E

def e2e_report(level, success, reach_to='done', fail_code=None, subs_ok=True):
    stages = list(rt.E2E_STAGES)
    k = stages.index(reach_to) + 1
    rb = dict(reached={s: i < k for i, s in enumerate(stages)}, sim_s={}, final_phase='DONE', fail_code=fail_code)
    subs = [{'stage': 'release', 'by': 'rule_script:release_open_v1'}] if level == 'E2E-1p' else []
    return dict(schema='ugrp.e2e_min.evaluation.v1', level=level, success=success,
                success_components=dict(drops_zero=True), e2e_substitutions=subs,
                substitutions_match_level=subs_ok, aux=dict(stage_reach={'r1': rb, 'r2': rb}))


def test_e2e_levels_not_pooled_with_substitution(tmp_path):
    p = tmp_path / 'PREREG.md'
    p.write_text('# 최소 E2E 사전 등록 초안 (상태: DRAFT)\n')
    rows = [dict(type='header', prereg_sha256=sha(p)),
            dict(type='run', level='E2E-1p', seed=601, smoke=True, report=e2e_report('E2E-1p', False, 'carry', 'E2E_NAV_TIMEOUT')),
            dict(type='run', level='E2E-1p', seed=601, report=e2e_report('E2E-1p', True)),
            dict(type='run', level='E2E-1p', seed=601, report=e2e_report('E2E-1p', False, 'release', 'E2E_RELEASE_TIMEOUT')),
            dict(type='run', level='E2E-2', seed=601, report=e2e_report('E2E-2', False, 'grasp', 'E2E_GRASP_TIMEOUT'))]
    led = write_jsonl(tmp_path / 'rows.jsonl', rows)
    out = tmp_path / 'out'
    assert run(['e2e', '--prereg', p, '--rows', led, '--out', out]) == 2                # .md status unknown -> draft
    assert run(['e2e', '--prereg', p, '--rows', led, '--out', out, '--allow-draft']) == 0
    doc = json.loads((out / 'report.json').read_text())
    lv = doc['data']['levels']
    assert (lv['E2E-1p']['n'], lv['E2E-1p']['N'], lv['E2E-1p']['ran']) == (1, 3, 2)   # smoke excluded
    assert (lv['E2E-2']['n'], lv['E2E-2']['N']) == (0, 6)
    assert lv['E2E-1p']['reach']['release'] == 4 and lv['E2E-1p']['robot_N'] == 6
    md = (out / 'report.md').read_text()
    assert 'release←rule_script:release_open_v1' in md and 'smoke 1회' in md and '초안 기준' in md


def test_e2e_refuses_substitution_mismatch_and_overflow(tmp_path):
    p = tmp_path / 'PREREG.json'
    p.write_text(json.dumps(dict(status='FROZEN')))
    head = dict(type='header', prereg_sha256=sha(p))
    led = write_jsonl(tmp_path / 'r.jsonl', [head, dict(type='run', level='E2E-2', seed=601,
                                                         report=e2e_report('E2E-2', True, subs_ok=False))])
    assert run(['e2e', '--prereg', p, '--rows', led, '--out', tmp_path / 'o']) == 2
    led = write_jsonl(tmp_path / 'r.jsonl', [head] + [dict(type='run', level='E2E-1p', seed=601,
                                                            report=e2e_report('E2E-1p', True))] * 4)
    assert run(['e2e', '--prereg', p, '--rows', led, '--out', tmp_path / 'o']) == 2   # 4 > registered 3
    with pytest.raises(SystemExit):                                                  # N is fixed, no override
        run(['e2e', '--prereg', p, '--rows', led, '--out', tmp_path / 'o', '--planned', 'E2E-1p=4'])


def test_e2e_fixed_n_matches_prereg_and_host_error_row(tmp_path):
    doc = (FIX / 'E2E_PREREG_DRAFT.md').read_text()
    assert "E2E-1' 3, E2E-2 6" in doc and rt.E2E_PLANNED == {'E2E-1p': 3, 'E2E-2': 6}
    assert rt.prereg_status((FIX / 'E2E_PREREG_DRAFT.md').read_bytes()) == 'DRAFT'
    p = tmp_path / 'PREREG.md'
    p.write_text('# 최소 E2E 사전 등록 (상태: FROZEN)\n')
    rows = [dict(type='header', prereg_sha256=sha(p)),
            dict(type='run', level='E2E-1p', seed=601, status='HOST_ERROR'),
            dict(type='run', level='E2E-1p', seed=601, report=e2e_report('E2E-1p', True))]
    out = tmp_path / 'out'
    assert run(['e2e', '--prereg', p, '--rows', write_jsonl(tmp_path / 'r.jsonl', rows), '--out', out]) == 0
    lv = json.loads((out / 'report.json').read_text())['data']['levels']['E2E-1p']
    assert (lv['n'], lv['N'], lv['ran'], lv['host_error'], lv['reach']['done']) == (1, 3, 2, 1, 2)
    assert '[확인 필요]' not in (out / 'report.md').read_text()


# ------------------------------------------------------------------ figures

def test_figure_written_when_matplotlib_present(tmp_path):
    pytest.importorskip('matplotlib')
    f = rt.bar_figure(tmp_path / 'f.png', 't', ['a', 'b'], [('x', [(1, 6), (0, 0)]), ('y', [(6, 6), (3, 6)])])
    assert f and Path(f).stat().st_size > 1000
