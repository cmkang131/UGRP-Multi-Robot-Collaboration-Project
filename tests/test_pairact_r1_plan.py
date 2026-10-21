"""pairact-r1 train-ready plan: tiers, P5 cap, P5 counting, hybrid switch, checkpoint freeze (CPU only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

from harness import pairact_collect as pc  # noqa: E402
from harness import pairact_r1_plan as plan  # noqa: E402
import pairact_r1_freeze_checkpoint as fz  # noqa: E402
import pairact_r1_p5_decide as dec  # noqa: E402

EXP = ROOT / 'experiments/2026-10-21-pairact-r1'
SEEDS = list(range(8342000, 8342020))


# ------------------------------------------------------------------ tiers

def test_tiers_cover_collect_decisions_and_never_change_hyperparameters():
    assert set(plan.TRAINABLE) == set(pc.TRAINABLE)
    tp = json.loads((EXP / 'TRAIN_PLAN.json').read_text())
    for d in plan.TRAINABLE:
        p = plan.train_plan(d)
        assert p['train'] and p['p5'] and p['config_deltas'] == {} and p['steps'] == 20000
        assert tp['tiers'][d]['config_deltas'] == {}
    assert plan.train_plan('TRAIN_SMALL_DATA')['claim'] == 'funnel_primary'
    assert plan.train_plan('TRAIN_DATA_RANGE_LIMITED', limited_bins=[{'bin': 'B5'}])['limited_bins'] == ['B5']
    for d in plan.NO_TRAIN:
        p = plan.train_plan(d)
        assert not p['train'] and not p['p5']
    with pytest.raises(ValueError):
        plan.train_plan('COLLECTING')


def test_train_plan_config_matches_registered_config():
    from harness import pairact_r1
    cfg = pairact_r1.load_config(EXP / 'PAIRACT_R1_TRAIN_CONFIG_DRAFT.json')
    fixed = json.loads((EXP / 'TRAIN_PLAN.json').read_text())['config']['fixed']
    for k in ('steps', 'checkpoint_every', 'seed', 'batch_size', 'chunk', 'base_arm', 'issued_clock_deadband',
              'done_recovery', 'place_sync'):
        assert cfg[k] == fixed[k], k
    assert cfg['selection']['split'] == 'validation'


# ------------------------------------------------------------------ cap

def test_episode_cap_rule():
    c = plan.episode_cap_s([40.0, 52.3, 47.0])
    assert c['carry_budget_s'] == 80 + 4.5 and c['cap_s'] == 60 + 84.5     # ceil10(78.45)=80
    assert plan.episode_cap_s([90.0])['carry_budget_s'] == 120               # 140+4.5 capped
    assert plan.episode_cap_s([], any_timeout=True)['carry_budget_s'] == 120
    assert plan.episode_cap_s([]) is None
    with pytest.raises(ValueError):
        plan.episode_cap_s([0.0])


# ------------------------------------------------------------------ counting + hybrid

def reach(last):
    i = plan.FUNNEL.index(last) if last else -1
    return {s: k <= i for k, s in enumerate(plan.FUNNEL)}


def ep(arm, seed, last, *, status='complete', attempt=1, corr=0):
    f = reach(last)
    r = dict(type='episode', arm=arm, seed=seed, attempt=attempt, status=status, success=last == 'place',
             funnel=f if status == 'complete' else {s: None for s in plan.FUNNEL})
    if arm == 'teacher':
        r['funnel'].update(approach=None, alignment=None, READY=None, grasp=None)
        r.update(student_gt_corrections=None, teacher_commands_issued_to_student=None)
    else:
        r.update(student_gt_corrections=corr, teacher_commands_issued_to_student=corr)
    return r


def counts(student_last, teacher_last, header=None):
    h = header or dict(type='header', schema=plan.ROWS_SCHEMA, excluded_seeds=[])
    eps = [ep('student', s, x) for s, x in zip(SEEDS, student_last)]
    eps += [ep('teacher', s, x) for s, x in zip(SEEDS, teacher_last)]
    return plan.p5_counts(h, eps, seeds=SEEDS, arms=['student', 'teacher'])


T_GOOD = ['place'] * 16 + ['hold_3s'] * 4


def test_hybrid_carry_when_hold_reached_but_carry_lost():
    c = counts(['hold_3s'] * 4 + ['carry_1m'] * 2 + ['door'] + ['alignment'] * 13, T_GOOD)
    d = plan.hybrid_decision(c)
    assert (d['H'], d['D'], d['P'], d['k']) == (7, 1, 0, 3) and d['decision'] == 'HYBRID_CARRY'


def test_grasp_first_when_hold_below_k():
    c = counts(['hold_3s'] * 2 + ['READY'] * 18, T_GOOD)
    assert plan.hybrid_decision(c)['decision'] == 'GRASP_FIRST'


def test_p2_path_first_when_teacher_door_weak():
    c = counts(['hold_3s'] * 6 + ['grasp'] * 14, ['door'] * 9 + ['hold_3s'] * 11)
    assert plan.hybrid_decision(c)['decision'] == 'P2_PATH_FIRST'


def test_place_first_and_pure_continue():
    c = counts(['door'] * 6 + ['place'] * 1 + ['grasp'] * 13, T_GOOD)
    assert plan.hybrid_decision(c)['decision'] == 'PLACE_FIRST'
    c = counts(['place'] * 4 + ['door'] * 2 + ['grasp'] * 14, T_GOOD)
    d = plan.hybrid_decision(c)
    assert d['decision'] == 'PURE_CONTINUE' and d['pure_minimum_met']


def test_corrections_invalidate_or_unverify():
    eps = [ep('student', s, 'place', corr=1 if s == SEEDS[0] else 0) for s in SEEDS]
    eps += [ep('teacher', s, 'place') for s in SEEDS]
    h = dict(type='header', schema=plan.ROWS_SCHEMA, excluded_seeds=[])
    c = plan.p5_counts(h, eps, seeds=SEEDS, arms=['student', 'teacher'])
    assert c['arms']['student']['success'] == 19 and c['arms']['student']['funnel']['place'] == 19
    assert plan.hybrid_decision(c)['decision'] == 'INVALID_STUDENT_CORRECTED'
    eps[1]['student_gt_corrections'] = None
    eps[0]['student_gt_corrections'] = eps[0]['teacher_commands_issued_to_student'] = 0
    c = plan.p5_counts(h, eps, seeds=SEEDS, arms=['student', 'teacher'])
    assert plan.hybrid_decision(c)['decision'] == 'UNVERIFIED_CORRECTIONS'


def test_rule_a_n_eff_rerun_and_rejections():
    h = dict(type='header', schema=plan.ROWS_SCHEMA, excluded_seeds=[SEEDS[-1]], static_check_sha256='x')
    eps = [ep('student', s, 'hold_3s') for s in SEEDS[:-1]] + [ep('teacher', s, 'place') for s in SEEDS[:-1]]
    eps[0] = ep('student', SEEDS[0], None, status='HOST_ERROR')
    eps.append(ep('student', SEEDS[0], 'place', attempt=2))
    c = plan.p5_counts(h, eps, seeds=SEEDS, arms=['student', 'teacher'])
    assert c['n_eff'] == 19 and c['arms']['student']['success'] == 1 and c['arms']['teacher']['success'] == 19
    assert c['arms']['teacher']['unrecorded'] == ['approach', 'alignment', 'READY', 'grasp']
    with pytest.raises(ValueError, match='excluded seed'):
        plan.p5_counts(h, eps + [ep('student', SEEDS[-1], 'place')], seeds=SEEDS, arms=['student', 'teacher'])
    with pytest.raises(ValueError, match='duplicate'):
        plan.p5_counts(h, eps + [ep('student', SEEDS[1], 'place', attempt=2)], seeds=SEEDS, arms=['student', 'teacher'])
    with pytest.raises(ValueError, match='static_check'):
        plan.p5_counts(dict(h, static_check_sha256=None), eps, seeds=SEEDS, arms=['student', 'teacher'])


def test_decide_cli_binds_prereg_sha(tmp_path):
    prereg = EXP / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json'
    sha = hashlib.sha256(prereg.read_bytes()).hexdigest()
    rows = tmp_path / 'rows.jsonl'
    eps = [ep('student', s, 'hold_3s' if i < 5 else 'grasp') for i, s in enumerate(SEEDS)]
    eps += [ep('teacher', s, 'place') for s in SEEDS]
    head = dict(type='header', schema=plan.ROWS_SCHEMA, prereg_sha256=sha, excluded_seeds=[])
    rows.write_text('\n'.join(json.dumps(r) for r in [head] + eps) + '\n')
    out = dec.decide(prereg, rows)
    assert out['hybrid']['decision'] == 'HYBRID_CARRY' and out['text']['student'] == 'student 0/20'
    assert out['label'].startswith('DRAFT')
    rows.write_text('\n'.join(json.dumps(r) for r in [dict(head, prereg_sha256='0')] + eps) + '\n')
    with pytest.raises(ValueError, match='prereg_sha256'):
        dec.decide(prereg, rows)


def test_eval_prereg_v2_keeps_v1_rules_and_adds_v2_fields():
    e = json.loads((EXP / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json').read_text())
    assert e['revision'].startswith('v2') and e['hybrid_switch']['rule_id'] == plan.HYBRID_RULE_ID
    assert '60' in e['episode_cap_sim_s']['rule'] and e['episode_cap_sim_s']['same_for_both_arms'] is True
    assert 'n/N_eff' in e['teacher_same_seed']['rule'] and 'nonzero' in e['student_correction_audit']
    assert tuple(e['funnel']['order']) == plan.FUNNEL
    assert (e['seeds']['first'], e['seeds']['last'], e['seeds']['n']) == (8342000, 8342019, 20)


# ------------------------------------------------------------------ freeze

def make_run(tmp_path, *, verdict='SELECTED', step=7000, passed=True):
    ds, st, cfg = tmp_path / 'ds', tmp_path / 'st.json', tmp_path / 'cfg.json'
    ds.mkdir()
    (ds / 'manifest.json').write_text('{"complete": true}')
    st.write_text('{}')
    cfg.write_text('{}')
    actor = tmp_path / 'main' / f'step-{step}' / 'actor'
    actor.mkdir(parents=True)
    (actor / 'SHA256.json').write_text('{"model.safetensors": "aa"}')
    off = tmp_path / 'offline'
    off.mkdir()
    (off / 'selection.json').write_text(json.dumps(dict(
        split='validation', verdict=verdict, selected_step=step if verdict == 'SELECTED' else None,
        dataset_manifest_sha256=fz.sha256(ds / 'manifest.json'), stage_targets_sha256=fz.sha256(st))))
    (off / 'checkpoints.jsonl').write_text(json.dumps(dict(step=step, passed=passed,
                                                           actor_sha256={'model.safetensors': 'aa'})) + '\n')
    return off, tmp_path / 'main', ds, st, cfg


def test_freeze_checkpoint(tmp_path):
    off, run, ds, st, cfg = make_run(tmp_path)
    rep = tmp_path / 'report.json'
    rep.write_text(json.dumps({'decision': {'decision': 'TRAIN_SMALL_DATA', 'labels': ['소량'],
                                            'limited_bins': [{'bin': 'B5'}]}}))
    rec = fz.freeze(off, run, ds, st, cfg, rep)
    assert rec['selected_step'] == 7000 and rec['collect_decision'] == 'TRAIN_SMALL_DATA'
    assert rec['limited_bins'] == ['B5']
    rep.write_text(json.dumps({'decision': {'decision': 'NO_TRAIN_BELOW_FLOOR'}}))
    with pytest.raises(ValueError, match='not trainable'):
        fz.freeze(off, run, ds, st, cfg, rep)
    (run / 'step-7000/actor/SHA256.json').write_text('{"model.safetensors": "bb"}')
    with pytest.raises(ValueError, match='differs from the gated'):
        fz.freeze(off, run, ds, st, cfg)


def test_freeze_refuses_no_selection(tmp_path):
    off, run, ds, st, cfg = make_run(tmp_path, verdict='NOT_READY_NO_CHECKPOINT_PASSES')
    with pytest.raises(ValueError, match='no checkpoint'):
        fz.freeze(off, run, ds, st, cfg)


# ------------------------------------------------------------------ arm N (v2.1)

def hyb(seed, last, *, mode='nav', code=0, corr=0, status='complete'):
    r = ep('hybrid_n', seed, last, corr=corr, status=status)
    r.update(carry_mode=mode, gt_inputs_to_code=code)
    return r


def test_train_plan_lists_both_arms_with_labels_and_vms():
    tp = json.loads((EXP / 'TRAIN_PLAN.json').read_text())
    assert tp['arms']['F']['vm'] == 'gcp2' and tp['arms']['N']['vm'] == 'gcp6'
    assert tp['arms']['F']['budget_gpu_h'] == tp['arms']['N']['budget_gpu_h'] == 4.6
    for a in ('F', 'N'):
        assert (EXP / Path(tp['arms'][a]['config']).name).exists()
        assert tp['arms'][a]['label'] == plan.ARM_LABELS[tp['arms'][a]['p5_arm']]
    arms = plan.train_plan('TRAIN')['arms']
    assert arms['N'] == dict(config='PAIRACT_R1_TRAIN_CONFIG_ARM_N.json', p5_arm='hybrid_n',
                             label='학습 근거리 + 코드 운반(hybrid)')
    assert arms['F']['label'] == '학습 전 구간'


def test_prereg_v21_registers_arm_n_hybrid_only_and_no_pooling():
    e = json.loads((EXP / 'PAIRACT_R1_EVAL_PREREG_DRAFT.json').read_text())
    ids = [a['id'] for a in e['arms']]
    assert ids == ['student', 'hybrid_n', 'teacher']
    a = {x['id']: x for x in e['arms']}
    assert a['student']['label'] == plan.ARM_LABELS['student'] and a['hybrid_n']['label'] == plan.ARM_LABELS['hybrid_n']
    assert a['hybrid_n']['training_arm'] == 'N' and 'never run as a pure student' in a['hybrid_n']['forbidden']
    assert "'nav'" in a['hybrid_n']['carry_mode_rule'] and '창민' in a['hybrid_n']['carry_mode_rule']
    r = e['arm_rules']
    assert 'never added' in r['no_pooling'] and 'same N_eff' in r['same_seeds']
    assert 'arm F' in r['hybrid_switch_relation'] and 'not an input' in r['hybrid_switch_relation']
    assert e['revision'].startswith('v2') and 'v2.1' in e['revision']


def test_hybrid_arm_counts_need_code_audit_and_nav_mode():
    h = dict(type='header', schema=plan.ROWS_SCHEMA, excluded_seeds=[])
    eps = [ep('student', s, 'hold_3s') for s in SEEDS] + [ep('teacher', s, 'place') for s in SEEDS]
    eps += [hyb(s, 'place') for s in SEEDS[:5]] + [hyb(s, 'hold_3s') for s in SEEDS[5:]]
    arms = ['student', 'hybrid_n', 'teacher']
    c = plan.p5_counts(h, eps, seeds=SEEDS, arms=arms)
    assert c['arms']['hybrid_n']['success'] == 5 and c['arms']['student']['success'] == 0
    table = {r['arm']: r['text'] for r in plan.arm_table(c)}
    assert table == {'student': '학습 전 구간 0/20', 'hybrid_n': '학습 근거리 + 코드 운반(hybrid) 5/20',
                     'teacher': 'teacher = GT 기준(학습 결과 아님) 20/20'}
    # the switch rule reads arm F only; arm N success does not change it
    assert plan.hybrid_decision(c)['decision'] == 'HYBRID_CARRY'
    with pytest.raises(ValueError, match='arm F student only'):
        plan.hybrid_decision(c, student='hybrid_n')
    eps2 = list(eps); eps2[-1] = hyb(SEEDS[-1], 'place', code=1)
    eps2[-2] = hyb(SEEDS[-2], 'place', code=None)
    c2 = plan.p5_counts(h, eps2, seeds=SEEDS, arms=arms)['arms']['hybrid_n']
    assert c2['corrections_nonzero'] == [SEEDS[-1]] and c2['corrections_unknown'] == [SEEDS[-2]]
    eps3 = list(eps); eps3[-1] = hyb(SEEDS[-1], 'place', mode='map')
    with pytest.raises(ValueError, match='not approved'):
        plan.p5_counts(h, eps3, seeds=SEEDS, arms=arms)
    assert plan.p5_counts(h, eps3, seeds=SEEDS, arms=arms, hybrid_modes=('nav', 'map'))['arms']['hybrid_n']['success'] == 6


def test_freeze_records_arm_and_checks_scope(tmp_path):
    off, run, ds, st, cfg = make_run(tmp_path)
    cfg.write_text(json.dumps({'arm': 'N', 'segment_scope': 'near_only_v1'}))
    sel = json.loads((off / 'selection.json').read_text())
    (off / 'selection.json').write_text(json.dumps(dict(sel, segment_scope='near_only_v1')))
    rec = fz.freeze(off, run, ds, st, cfg)
    assert (rec['arm'], rec['segment_scope']) == ('N', 'near_only_v1')
    (off / 'selection.json').write_text(json.dumps(dict(sel, segment_scope='full_v1')))
    with pytest.raises(ValueError, match='segment scope'):
        fz.freeze(off, run, ds, st, cfg)


def test_pairact_l4_host_profile_admits_gcp2_and_gcp6_only():
    from scripts.beamact1_runtime import host_profile_check
    assert host_profile_check('ugrp-sim-b-1014', 'ugrp-act-l4-gcp2', 'g2-standard-8')['vm'] == 'gcp2'
    assert host_profile_check('ugrp-sim-f-1016', 'ugrp-act-l4-gcp6', 'g2-standard-8')['vm'] == 'gcp6'
    for bad in (('ugrp-sim-b-1014', 'ugrp-sim-gcp2', 'n4-highcpu-64'), ('ugrp-sim-f-1016', 'ugrp-act-l4-gcp2', 'g2-standard-8')):
        with pytest.raises(ValueError):
            host_profile_check(*bad)
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / 'scripts/train_grasp_act.py'), '--dataset', str(tmp_path_dummy()),
                        '--output', '/nonexistent/out', '--stage', 'smoke', '--steps', '300',
                        '--execution-host-profile', 'pairact_r1_l4'],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 2 and 'pairact-r1 training only' in r.stderr


def tmp_path_dummy():
    return ROOT / 'experiments'
