"""Saved input corruption, withheld truth and approval tests; no simulator."""
from copy import deepcopy
import hashlib
import json
import math

import cv2
import numpy as np
import pytest

from harness.grasp_act_contract import SERVOS, SCHEMA, validate_observation
from harness.grasp_act_solo_recording import SoloRecorder, camera_config, validate_recording, validate_approval
from scripts.check_solo_recording import check
from tests.test_grasp_act_solo_run_path import backend  # fake world fixture; no physics/render backend


def issued(now=0.):
    return {'t': now, 'wheels': [0.]*4, 'duration_s': [0.]*4, 'pwm': {str(s): 1500 for s in SERVOS}}


def plan():
    return {'episode_id': 'train-86000', 'robot_id': 'r1', 'kind': 'cyan', 'role': 'west',
            'seed': 86000, 'split': 'train', 'negative_probe': False}


def camera_runtime(root):
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
    c = camera_config()
    (root/'evaluation').mkdir(exist_ok=True)
    (root/'evaluation/camera-runtime.json').write_text(json.dumps({'pos': c['position_m'],
        'quat': c['quat_wxyz'], 'resolution': [c['width'], c['height']],
        'intrinsic': mujoco_pixel_intrinsic(c['width'], c['height']).tolist()}))


def recorded(root, n=4):
    r = SoloRecorder(root, plan(), issued(), handoff=lambda *args: .4)
    previous = issued()
    for i in range(n):
        now = round(i*.1, 8)
        frame = np.full((480, 640, 3), 90+i, np.uint8)
        jpeg = cv2.imencode('.jpg', frame)[1].tobytes()
        skill = 'release' if i >= 2 else 'grasp'
        r.observe(now, jpeg, frame, skill=skill, phase='lower' if i >= 2 else 'approach', previous=previous)
        value = issued(now)
        value['pwm']['6'] += i*10
        r.target(value, skill_after='release' if i >= 1 else 'grasp',
                 phase_after='complete' if i == n-1 else 'lower', complete=i == n-1)
        previous = value
    r.close()
    camera_runtime(root)
    return r


def test_native_bytes_histories_targets_and_pickup_token_are_student_valid(tmp_path):
    r = recorded(tmp_path)
    proof = check(tmp_path, seconds=.3)
    assert proof['passed'] and proof['frames'] == proof['observations'] == 4
    assert proof['resolution'] == [640, 480]
    assert proof['period_min_s'] == pytest.approx(.1)
    rows = [json.loads(x) for x in (tmp_path/'student-r1.jsonl').read_text().splitlines()]
    labels = [json.loads(x) for x in (tmp_path/'teacher-r1.jsonl').read_text().splitlines()]
    assert [x['done'] for x in labels] == [False, True, False, True]
    assert rows[2]['destination_zone'] == 'pickup_site'
    assert all('visible_target' not in x and 'physical_success' not in x for x in rows)
    assert r.record()['local_handoff_seen']
    corrupted = {**rows[-1], 'contact': [1, 1]}
    with pytest.raises(ValueError, match='whitelist'):
        validate_observation(corrupted)


@pytest.mark.parametrize('damage', ['history', 'target', 'jpeg', 'fov'])
def test_first_interval_rejects_shifted_action_tampered_image_and_camera(tmp_path, damage):
    recorded(tmp_path)
    if damage in ('history', 'target'):
        p = tmp_path/('student-r1.jsonl' if damage == 'history' else 'teacher-r1.jsonl')
        rows = [json.loads(x) for x in p.read_text().splitlines()]
        if damage == 'history':
            rows[1]['issued'][-1]['pwm']['6'] += 1
        else:
            rows[1]['clean_teacher_command']['t'] += .1
        p.write_text(''.join(json.dumps(x)+'\n' for x in rows))
    elif damage == 'jpeg':
        (tmp_path/'rgb/r1/000001.jpg').write_bytes(b'broken')
    else:
        p = tmp_path/'evaluation/camera-runtime.json'
        v = json.loads(p.read_text()); v['intrinsic'][0] *= 1.1; p.write_text(json.dumps(v))
    with pytest.raises(ValueError):
        check(tmp_path, seconds=.3)


def test_truth_free_scan_cannot_accept_a_pose_and_ignores_map_gt():
    from sim.grasp_act_solo_teacher import primitives
    from sim.grasp_act_solo_lookaround import SoloLookaround
    p = primitives()
    a = SoloLookaround({'bounds_m': [-2, 2, -2, 2]}, ops=p, truth_free_v1=True)
    b = SoloLookaround({'bounds_m': [-999, 999, -999, 999]}, ops=p, truth_free_v1=True)
    with pytest.raises(ValueError, match='no pose'):
        a.arm([4., 2., math.pi])
    a.arm(); b.arm()
    a.start(0., 1500); b.start(0., 500)
    pwm = dict(p.folded)
    frame = lambda: np.zeros((480, 640, 3), np.uint8)
    done = False
    for i in range(150):
        ca, done = a.step(i*.1, pwm, frame)
        cb, db = b.step(i*.1, pwm, frame)
        assert ca == cb and done == db
        pwm.update({int(k): v for k, v in ca['pwm'].items()})
        if done:
            break
    assert done and a.loc is None
    assert len([e for e in a.events if e['event'] == 'view']) == 6
    assert a.record()['self_pose_source'] == 'none'


@pytest.mark.parametrize('change', [dict(truth_free_v1=False), dict(negative=True), dict(lift='off'),
                                  dict(margin=False), dict(stability='off')])
def test_recording_refuses_leaking_or_diagnostic_profiles(change):
    kw = dict(training_rgb=True, truth_free_v1=True, negative=False,
              stability='align_relook_v1', reach='pad_window_v2', lift='solo_lift_lookback_v1', margin=True)
    validate_recording(plan(), **kw)
    with pytest.raises(ValueError):
        validate_recording(plan(), **{**kw, **change})


def test_gate_seeds_and_uncorrected_gate_cannot_be_training_or_batch(tmp_path):
    with pytest.raises(ValueError, match='registered train'):
        validate_recording({**plan(), 'seed': 79700}, training_rgb=True, truth_free_v1=True,
            negative=False, stability='align_relook_v1', reach='pad_window_v2', lift='solo_lift_lookback_v1', margin=True)
    assert validate_approval(None, stage='pilot', sha='a'*40, host={}) is None
    with pytest.raises(ValueError, match='coordinator'):
        validate_approval(None, stage='batch', sha='a'*40, host={})
    p = tmp_path/'approval.json'
    p.write_text(json.dumps({'approved': True, 'source_sha': 'a'*40,
        'corrected_teacher_gate': {'source_sha': 'c35e2ff2', 'N': 40, 'n': 40}}))
    with pytest.raises(ValueError, match='uncorrected gate'):
        validate_approval(p, stage='batch', sha='a'*40, host={})


def test_plan_has_balanced_bulk_fresh_seeds_and_no_gate_or_holdout_samples():
    from scripts.make_solo_record_plan import prepare, make_queue
    from collections import Counter
    from harness.grasp_act_seed_splits import split_of
    p = prepare()
    assert len(p['episodes']) == 50
    assert Counter(e['kind'] for e in p['episodes'][2:]) == dict.fromkeys(('cyan', 'red', 'green', 'yellow'), 12)
    assert all(split_of(e['seed']) == 'train' and not e['scenario_id'].startswith('s4') for e in p['episodes'])
    assert p['gate_promotion_authorized_if_all_conditions_pass'] is False
    q = make_queue(p, 'a'*40)
    assert q['stage_counts'] == {'pilot': 2, 'batch': 48} and not q['runs_enabled']
    assert all(not r['enabled'] for r in q['runs'])
    assert all('--training-rgb' in r['command'] and '--solo-truth-free-lookaround-v1' in r['command'] for r in q['runs'])
    assert all(r['requires_coordinator_approval'] and len(r['depends_on']) == 2 for r in q['runs'][2:])
    assert q['storage_budget_mib']['reserved_total'] == 50*1024


def test_real_runner_writes_separate_failure_inputs_with_fake_backend(backend):
    from tests.test_grasp_act_solo_run_path import plan as runtime_plan
    from sim.masterpi_camera_profile import mujoco_pixel_intrinsic
    runner, world, runs = backend
    c = camera_config()
    world.model.cam_pos = np.array([c['position_m']])
    world.model.cam_quat = np.array([c['quat_wxyz']])
    world.model.cam_resolution = np.array([[640, 480]])
    world.model.cam_intrinsic = np.array([mujoco_pixel_intrinsic(640, 480)])
    p = {**runtime_plan(), 'split': 'train', 'seed': 86000}
    out = runs/'record'
    result = runner.run(p, out, execution_host='gcp1', profile='solo_visible_only_v1', hidden=True,
        look=True, cap_s=.4, teacher_stability='align_relook_v1', reach_mode='pad_window_v2',
        rgb_lift_mode='solo_lift_lookback_v1', solo_lift_lookback_margin_v1=True,
        training_rgb=True, solo_truth_free_lookaround_v1=True)
    assert result['status'] == 'complete' and result['recording']['frames'] == 4
    assert result['training_include'] is result['training_candidate'] is result['physical_success'] is False
    assert (out/'teacher-raw/commands.jsonl').exists() and (out/'evaluation/eval-only.jsonl').exists()
    assert not (out/'teacher-commands.jsonl').exists() and not (out/'eval-only.jsonl').exists()
    assert check(out, seconds=.3)['passed']
