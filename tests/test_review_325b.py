"""PR #325 fix verification and new counterexamples; offline only.

Imported from independent review 6f87c959. All counterexamples are mandatory.
Defaults to the current checkout, including in CI; REVIEW_325B_TREE may select
an isolated candidate. No production source is edited by this file.
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
    return ((Path(tree) if tree else ROOT) / path).read_bytes()


@pytest.mark.parametrize('path', PINNED)
def test_g3251_restored_bytes_equal_main_and_original_pin(path):
    original = blob(BASE, REGISTRATION)
    assert candidate_bytes(REGISTRATION) == original
    data = candidate_bytes(path)
    assert data == blob(BASE, path)
    assert hashlib.sha256(data).hexdigest() == json.loads(original)['v6_contract']['source_sha256'][path]


@pytest.mark.parametrize('contract', ('v6_contract', 'scene_contract'))
def test_historical_registration_and_successor_pins_preserved(contract):
    from tests.v6h_successor_pins import SEAL, successor_pins
    original = blob(BASE, REGISTRATION)
    assert candidate_bytes(REGISTRATION) == original
    for path, expected in successor_pins(contract).items():
        data = candidate_bytes(path)
        assert data == blob(SEAL, path), path
        assert hashlib.sha256(data).hexdigest() == expected, path


@pytest.fixture
def color_api(monkeypatch):
    tree_name = os.environ.get('REVIEW_325B_TREE')
    tree = Path(tree_name).resolve() if tree_name else ROOT
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


@pytest.fixture
def aligner(monkeypatch):
    from harness import m1_color_perception as perception
    # Isolate evidence lifetime from image fitting; real JPEG loss sequences above
    # cover the full detector -> target -> alignment caller path for every kind.
    monkeypatch.setattr(perception.edge, 'decode_jpeg_b64', lambda _: object())
    monkeypatch.setattr(perception, 'top_edge_yaw', lambda *a, **kw:
                        {'ok': True, 'yaw_mod90_rad': 0.})
    result = perception.KindEdgeYawAligner('red')
    result.frame = {'image': 'fake', 'actuator_state': {'servo_pulses': {}}}
    return result


def establish_vote(aligner):
    for _ in range(3):
        result = aligner.observe({'visible': True, 'kind': 'red'}, (.32, 0.))
    assert result['ready'] and aligner.last_ready is not None
    assert aligner._previous_normal is not None


def require_fresh_votes(aligner):
    assert not aligner._fits
    assert aligner.last_ready is None and aligner._previous_normal is None
    for index in range(3):
        result = aligner.observe({'visible': True, 'kind': 'red'}, (.32, 0.))
        assert result['ready'] is (index == 2)
        if index < 2:
            assert aligner.last_ready is None


@pytest.mark.parametrize('target', (None, (), (.32,), (.32, 0., 0.),
                                   ('bad', 0.), (float('nan'), 0.),
                                   (.32, float('inf')), (0., 0.), (10**400, 0.)),
                         ids=('none', 'empty', 'short', 'long', 'nonnumeric',
                              'nan', 'inf', 'zero', 'overflow'))
def test_invalid_target_ends_all_alignment_evidence(aligner, target):
    establish_vote(aligner)
    result = aligner.observe({'visible': True, 'kind': 'red'}, target)
    assert not result['ready'] and result['reason'] == 'INVALID_TARGET_XY'
    require_fresh_votes(aligner)


@pytest.mark.parametrize('loss', ('no_frame', 'no_image', 'no_pwm', 'wrong_kind', 'invisible'))
def test_current_evidence_loss_ends_ready_window(aligner, loss):
    establish_vote(aligner)
    frame = aligner.frame
    box = {'visible': True, 'kind': 'red'}
    if loss == 'no_frame':
        aligner.frame = None
    elif loss == 'no_image':
        aligner.frame = {'actuator_state': {'servo_pulses': {}}}
    elif loss == 'no_pwm':
        aligner.frame = {'image': 'fake'}
    elif loss == 'wrong_kind':
        box['kind'] = 'green'
    else:
        box['visible'] = False
    for _ in range(8):  # Longer than the six-fit window; old readiness never revives.
        assert not aligner.observe(box, (.32, 0.))['ready']
        assert aligner.last_ready is None
    aligner.frame = frame
    require_fresh_votes(aligner)


def test_base_motion_reset_ends_alignment_evidence(aligner):
    establish_vote(aligner)
    aligner.reset_window()
    require_fresh_votes(aligner)


def test_ready_result_expires_when_votes_no_longer_agree(aligner, monkeypatch):
    from harness import m1_color_perception as perception
    establish_vote(aligner)
    for yaw in (.2, .4, .6, .8, 1.0, 1.2):
        monkeypatch.setattr(perception, 'top_edge_yaw', lambda *a, **kw:
                            {'ok': True, 'yaw_mod90_rad': yaw})
        result = aligner.observe({'visible': True, 'kind': 'red'}, (.32, 0.))
    assert not result['ready'] and aligner.last_ready is None


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('bad', ('missing_image', 'bad_hash'))
def test_rejected_own_frame_invalidates_prior_votes(color_api, kind, bad):
    wrist, _, observation, order, _ = color_api
    skill = wrist.WristColorBoxDelivery(order(kind)).box
    for fid in (1, 2):
        skill.decide(observation(kind + '_floor', fid))
    frame = observation(kind + '_floor', 3)
    if bad == 'missing_image':
        del frame['image']
    else:
        frame['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        skill.decide(frame)
    assert not skill.last_face_alignment['ready'] and skill.last_target is None
    assert not skill._face_aligner._fits and skill._face_aligner.last_ready is None
    skill.decide(observation(kind + '_floor', 4))
    assert not skill.last_face_alignment['ready']
    assert len(skill._face_aligner._fits) == 1


@pytest.mark.parametrize('kind', KINDS)
def test_default_skill_and_placement_require_m1_pose(color_api, kind):
    wrist, legacy, observation, order, _ = color_api
    skill = wrist.WristColorBoxDelivery(order(kind))
    assert skill.mode == 'm1'
    gt = legacy.PoseEstimate(0., 0., 0., 'gt_stub_eval_only')
    frame = observation(kind + '_floor')
    with pytest.raises(ValueError, match='pose source'):
        skill.decide(frame, gt)
    with pytest.raises(ValueError, match='pose source'):
        skill.confirm_placement(frame, gt)


@pytest.mark.parametrize('kind', KINDS)
def test_diagnostic_skill_requires_explicit_opt_in(color_api, kind):
    wrist, legacy, observation, order, _ = color_api
    skill = wrist.WristColorBoxDelivery(order(kind), mode='diagnostic')
    gt = legacy.PoseEstimate(0., 0., 0., 'gt_stub_eval_only')
    frame = observation(kind + '_floor')
    assert skill.decide(frame, gt)['kind'] == 'mecanum'
    placement = skill.confirm_placement(frame, gt)
    assert placement['mode'] == 'diagnostic' and not placement['counts_as_m1_input']


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('bad_mode', ('diagnostic', None, 'unknown'))
def test_m1_executor_rejects_factory_mode_mismatch(color_api, kind, bad_mode):
    wrist, _, _, order, make_executor = color_api
    executor = make_executor(kind)
    assert executor.deliver('o', 'B')['accepted']
    def factory(order, **kwargs):
        result = wrist.WristColorBoxDelivery(order, **kwargs)
        result.mode = bad_mode
        return result
    executor.skill_factory = factory
    from harness.zone_own_contract import ExecutorContractError
    rejected = False
    try:
        executor._skill_for(executor.job)(order(kind))
    except ExecutorContractError as exc:
        if 'different mode' not in str(exc):
            raise
        rejected = True
    assert rejected, f'M1 executor accepted factory mode {bad_mode!r}'


@pytest.mark.parametrize('kind', KINDS)
def test_explicit_diagnostic_executor_factory_is_allowed(color_api, kind):
    wrist, _, _, order, make_executor = color_api
    executor = make_executor(kind)
    assert executor.deliver('o', 'B')['accepted']
    executor.mode = 'diagnostic'
    executor.skill_factory = lambda order, **kwargs: wrist.WristColorBoxDelivery(
        order, mode='diagnostic', **kwargs)
    assert executor._skill_for(executor.job)(order(kind)).mode == 'diagnostic'
