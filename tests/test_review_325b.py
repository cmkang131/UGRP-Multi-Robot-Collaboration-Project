"""PR #325 fix verification and new counterexamples; offline only.

Use REVIEW_325B_TREE=<archive of 9db1bbb6> and the candidate's offline_guard.
Without a candidate tree only the git-blob preservation tests run. Behavioral
tests deliberately skip on the review branch, which has no T03 implementation.
Strict xfail applies only to assertion failures, never import/setup errors.
Use --runxfail after fixing. No production source is edited by this file.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = '394f9cda5d67a9d1b94ad1688f39f5616fc00e7b'
CANDIDATE = '9db1bbb6c035be711037bcea28eb984471dc300b'
REGISTRATION = 'experiments/2026-09-29-pair-v6e-carry/prereg_v6e.json'
PINNED = (
    'harness/owncam_delivery_shared.py', 'harness/zone_own_deliver.py',
    'harness/zone_own_executor.py', 'harness/zone_own_status.py',
    'harness/zone_own_team_host.py',
)
KINDS = ('cyan', 'red', 'green')


def blob(ref, path):
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT)


def candidate_bytes(path):
    # The override reintroduces actual pre-fix bytes for negative controls.
    ref = os.environ.get('REVIEW_325B_PIN_REF')
    if ref:
        return blob(ref, path)
    tree = os.environ.get('REVIEW_325B_TREE')
    return (Path(tree) / path).read_bytes() if tree else blob(CANDIDATE, path)


@pytest.mark.parametrize('path', PINNED)
def test_g3251_restored_bytes_equal_main_and_original_pin(path):
    original = blob(BASE, REGISTRATION)
    assert candidate_bytes(REGISTRATION) == original
    data = candidate_bytes(path)
    assert data == blob(BASE, path)
    assert hashlib.sha256(data).hexdigest() == json.loads(original)['v6_contract']['source_sha256'][path]


@pytest.mark.parametrize('contract', ('v6_contract', 'scene_contract'))
def test_all_current_registration_pins_preserved(contract):
    original = blob(BASE, REGISTRATION)
    assert candidate_bytes(REGISTRATION) == original
    for path, expected in json.loads(original)[contract]['source_sha256'].items():
        data = candidate_bytes(path)
        assert data == blob(BASE, path), path
        assert hashlib.sha256(data).hexdigest() == expected, path


@pytest.fixture
def color_api(monkeypatch):
    tree_name = os.environ.get('REVIEW_325B_TREE')
    if tree_name is None:
        pytest.skip('Set REVIEW_325B_TREE to the extracted candidate; main has no color modules')
    tree = Path(tree_name).resolve()
    monkeypatch.syspath_prepend(str(tree))
    modules = [importlib.import_module(name) for name in (
        'harness.wrist_color_boxes', 'harness.m1_color_contract',
        'harness.zone_color_box_executor', 'harness.wrist_zone_skill',
    )]
    for module in modules:
        if not Path(module.__file__).resolve().is_relative_to(tree):
            raise RuntimeError(f'Wrong source loaded: {module.__file__}')
    wrist, contract, executor, legacy = modules
    fixtures = tree / 'tests/fixtures/m1_color_boxes_v1'
    labels = json.loads((fixtures / 'labels.json').read_text())
    transport = json.loads((fixtures / 'transport.json').read_text())
    for row in transport['frames']:
        if hashlib.sha256((fixtures / row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise RuntimeError('Candidate RGB fixture bytes changed')

    def observation(name, fid=1):
        row = next(r for r in labels['frames'] if r['file'] == name + '.png')
        data = (fixtures / (name + '.jpg')).read_bytes()
        return {'robot_id': 'r1', 'camera': 'robot_cam', 'frame_id': fid,
                'sim_time': float(fid), 'image': base64.b64encode(data).decode(),
                'sha256': hashlib.sha256(data).hexdigest(),
                'actuator_state': {'servo_pulses': dict(row['own_servo_pwm'])}}

    def order(kind):
        return contract.ColorBoxOrder(kind, 'bay', (.4, 0.), (.25, .25), 'B1', (.32, 0.))

    def make_executor(kind):
        static_map = json.loads((tree / 'maps/zones/zone_wide_door_tags_v2.json').read_text())
        calibration = json.loads((tree / 'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json').read_text())
        sheet = {'orders': [{'order_id': 'o', 'kind': kind, 'count': 1, 'required_robots': 1,
                            'destination_zone': 'B',
                            'initial_location': {'pickup_bay': 'P1', 'slot': 'P1-1'}}]}
        return executor.ZoneColorBoxExecutor(
            'r1', static_map, calibration['params'], sheet,
            skill_factory=wrist.WristColorBoxDelivery, pose_estimate_cls=legacy.PoseEstimate,
            search_rows_y=(-2.45, -1.65, -.85, -.05, .75), judgments=False)

    return wrist, legacy, observation, order, make_executor


@pytest.mark.parametrize('kind', KINDS)
def test_three_uninterrupted_own_frames_can_establish_face_vote(color_api, kind):
    wrist, _, observation, order, _ = color_api
    skill = wrist.WristColorBoxDelivery(order(kind), mode='m1').box
    for fid in range(1, 4):
        skill.decide(observation(kind + '_floor', fid))
        assert skill.last_face_alignment['ready'] is (fid == 3)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('loss', ('black', 'wrong_kind', 'occluded'))
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason='R325B-1: real no-target path returns before clearing edge votes')
def test_real_kind_loss_requires_fresh_face_votes(color_api, kind, loss):
    wrist, _, observation, order, _ = color_api
    skill = wrist.WristColorBoxDelivery(order(kind), mode='m1').box
    for fid in (1, 2):
        skill.decide(observation(kind + '_floor', fid))
    assert len(skill._face_aligner._fits) == 2
    other = next(k for k in KINDS if k != kind)
    name = {'black': 'black', 'wrong_kind': other + '_floor',
            'occluded': kind + '_occluded'}[loss]
    skill.decide(observation(name, 3))
    assert skill.last_target is None and not skill.last_face_alignment['ready']
    remaining_after_loss = len(skill._face_aligner._fits)
    skill.decide(observation(kind + '_floor', 4))
    # On the candidate this is already ready, using two pre-loss votes.
    assert not skill.last_face_alignment['ready'], skill.last_face_alignment
    assert remaining_after_loss == 0
    assert len(skill._face_aligner._fits) == 1


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason='R325B-2: documented direct factory silently creates diagnostic skill')
def test_documented_executor_factory_keeps_m1_pose_boundary(color_api, kind):
    _, legacy, observation, order, make_executor = color_api
    executor = make_executor(kind)
    assert executor.mode == 'm1' and executor.deliver('o', 'B')['accepted']
    skill = executor._skill_for(executor.job)(order(kind))
    rejected = False
    try:
        skill.decide(observation(kind + '_floor'), legacy.PoseEstimate(0., 0., 0., 'gt_stub_eval_only'))
    except ValueError as exc:
        if 'pose source' not in str(exc):
            raise
        rejected = True
    assert rejected, f'executor={executor.mode}, skill={skill.mode}: GT-labelled pose emitted an action'
    assert skill.mode == executor.mode


@pytest.mark.parametrize('kind', KINDS)
def test_explicit_m1_skill_refuses_gt_pose(color_api, kind):
    wrist, legacy, observation, order, _ = color_api
    skill = wrist.WristColorBoxDelivery(order(kind), mode='m1')
    with pytest.raises(ValueError, match='pose source'):
        skill.decide(observation(kind + '_floor'), legacy.PoseEstimate(0., 0., 0., 'gt_stub_eval_only'))
