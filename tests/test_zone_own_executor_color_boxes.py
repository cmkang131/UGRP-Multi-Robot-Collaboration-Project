"""T03: saved, independently constructed RGB labels + fake M1/host contracts.

No World, renderer, provider worker, network or physics steps are used.
"""
import base64
import copy
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import m1_color_perception as p
from harness import zone_color_box_executor as zox
from harness.m1_color_contract import BOX_KINDS, ColorBoxOrder
from harness.m1_owncam_delivery import M1OwnCamDelivery
from harness.m1_color_delivery import ColorSharedPoseDelivery
from harness.wrist_color_boxes import KindBoxSkill, WristColorBoxDelivery
from harness.wrist_zone_skill import PoseEstimate
from harness.zone_color_box_delivery import bottom_clipped_box_px
from tests.test_zone_own_executor import MAP, CALIB, ROWS_Y, SEARCH_POSE

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / 'tests/fixtures/m1_color_boxes_v1'
MANIFEST = json.loads((FIX / 'labels.json').read_text())
FRAMES = MANIFEST['frames']


def image(name):
    return base64.b64encode((FIX / name).with_suffix('.jpg').read_bytes()).decode()


def observation(name, fid=1, pose=None):
    raw = (FIX / name).with_suffix('.jpg').read_bytes()
    return {'robot_id': 'r1', 'frame_id': fid, 'sim_time': float(fid), 'camera': 'robot_cam',
            'image': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'actuator_state': {'servo_pulses': {str(k): v for k, v in (pose or SEARCH_POSE).items()}}}


def order(kind):
    return ColorBoxOrder(kind, 'bay', (.4, 0.), (.25, .25), 'B1', (.32, 0.))


def executor(kind='red', factory=WristColorBoxDelivery):
    sheet = {'orders': [{'order_id': 'o', 'kind': kind, 'count': 1, 'required_robots': 1,
                        'destination_zone': 'B', 'initial_location': {'pickup_bay': 'P1', 'slot': 'P1-1'}}]}
    return zox.ZoneColorBoxExecutor('r1', MAP, CALIB['params'], sheet, skill_factory=factory,
                              pose_estimate_cls=PoseEstimate, search_rows_y=ROWS_Y, judgments=False)


def test_fixed_synthetic_fixture_hashes_and_labels():
    assert hashlib.sha256((FIX/'labels.json').read_bytes()).hexdigest() == \
        '99f74aa7ce7c8565697da8a3d6f621c98677eed542054ddaed72e0bf59e03ff4'
    assert len(FRAMES) == 25
    for row in FRAMES:
        assert hashlib.sha256((FIX/row['file']).read_bytes()).hexdigest() == row['sha256']
    for row in json.loads((FIX/'transport.json').read_text())['frames']:
        assert hashlib.sha256((FIX/row['file']).read_bytes()).hexdigest() == row['sha256']
        assert hashlib.sha256((FIX/row['source']).read_bytes()).hexdigest() == row['source_sha256']
    assert 'no detector outputs' in MANIFEST['label_source']


@pytest.mark.parametrize('kind', BOX_KINDS)
@pytest.mark.parametrize('row', FRAMES, ids=lambda r: r['file'])
def test_rgb_confusion_and_refusal_matrix(row, kind):
    data = image(row['file'])
    floor = p.observe_ground_box(data, row['own_servo_pwm'], kind)
    assert floor['visible'] is (row['kind'] == kind and row['floor_visible'])
    held = p.compare_box_comotion(data, data, kind=kind)
    assert held['attached'] is (row['kind'] == kind and row['attachment_visible'])
    if row['kind'] != kind:
        assert not p.observe_known_box_top(data, row['own_servo_pwm'], kind)['visible']


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_same_policy_and_box_geometry_for_three_kinds(kind):
    skill = WristColorBoxDelivery(order(kind), mode='m1')
    assert type(skill.box) is KindBoxSkill
    assert skill.box.box_kind == kind and skill.box.perception_mode == 'markerless'
    action = skill.box.decide(observation(f'{kind}_floor.png'))
    assert skill.box.last_box['kind'] == kind and skill.box.last_target is not None
    # Identical geometry and brightness: the color must not change commands.
    reference = WristColorBoxDelivery(order('cyan'), mode='m1').box
    assert action == reference.decide(observation('cyan_floor.png'))
    assert p.compare_box_comotion(image(f'{kind}_held.png'), image(f'{kind}_held.png'), kind=kind)['thresholds'] == \
        p.compare_box_comotion(image('cyan_held.png'), image('cyan_held.png'), kind='cyan')['thresholds']


@pytest.mark.parametrize('kind', BOX_KINDS)
@pytest.mark.parametrize('shown', BOX_KINDS)
def test_wrist_holding_and_release_never_accept_other_kind(kind, shown):
    skill = WristColorBoxDelivery(order(kind), mode='m1').box
    skill.phase = 'verify_lift'
    skill.decide(observation(f'{shown}_held.png'))
    assert not skill.held  # Even the right color still needs the complete own-pan probe.
    if shown != kind:
        assert skill.reason == 'VISUAL_LIFT_UNCONFIRMED'
    skill = WristColorBoxDelivery(order(kind), mode='m1').box
    skill.phase = 'verify_release'
    skill._inspection_pose = dict(SEARCH_POSE)
    skill._grasp = dict(SEARCH_POSE)
    skill.decide(observation(f'{shown}_floor.png'))
    if shown != kind:
        assert skill.reason != 'VISUAL_RELEASE_CONFIRMED' and skill.last_target is None


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_full_fake_attachment_probe_then_other_color_loss(kind):
    skill = WristColorBoxDelivery(order(kind), mode='m1').box
    skill.phase = 'verify_lift'
    for fid, pan in enumerate((1500, 1560, 1440, 1500), 1):
        skill.decide(observation(f'{kind}_held.png', fid, {**SEARCH_POSE, 6: pan}))
    assert skill.phase == 'carry' and skill.held
    assert skill.last_attachment['kind'] == kind
    wrong = next(k for k in BOX_KINDS if k != kind)
    action = skill.decide(observation(f'{wrong}_held.png', 5))
    assert action == {'kind': 'finish', 'reason': 'VISUAL_LOAD_DROPPED_OR_OCCLUDED'}
    assert not skill.last_attachment['attached']


@pytest.mark.parametrize('kind', BOX_KINDS)
@pytest.mark.parametrize('shown', BOX_KINDS)
def test_placement_needs_expected_kind_and_validated_original_frame(kind, shown):
    skill = WristColorBoxDelivery(order(kind), mode='m1')
    frame = observation(f'{shown}_floor.png')
    skill._gate._validate_observation(frame)
    skill._validated = {k: frame[k] for k in ('frame_id', 'sha256', 'camera', 'robot_id')}
    estimate = PoseEstimate(0., 0., 0., 'own_rgb_apriltag_ekf')
    result = skill.confirm_placement(frame, estimate)
    assert result['in_slot'] is (shown == kind)
    assert result['kind'] == kind
    with pytest.raises(ValueError, match='last strictly validated'):
        skill.confirm_placement({**frame, 'sha256': '0'*64}, estimate)
    with pytest.raises(ValueError, match='pose source'):
        skill.confirm_placement(frame, PoseEstimate(0., 0., 0., 'gt_stub_eval_only'))


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_edge_vote_clears_after_current_color_is_lost(kind):
    aligner = p.KindEdgeYawAligner(kind)
    valid = observation(f'{kind}_floor.png')
    fit = p.observe_ground_box(valid['image'], SEARCH_POSE, kind)
    for _ in range(3):
        aligner.frame = valid
        result = aligner.observe(fit, (.32, 0.))
    assert result['ready']
    aligner.frame = observation('black.png')
    assert not aligner.observe({'visible': False}, (.32, 0.))['ready']
    assert not aligner._fits


@pytest.mark.parametrize('kind', BOX_KINDS)
@pytest.mark.parametrize('shown', BOX_KINDS)
def test_bottom_clip_uses_ordered_kind(kind, shown):
    count = bottom_clipped_box_px(image(f'{shown}_clipped.png'), kind, profile=p.PROFILE)
    assert (count >= 40) is (kind == shown)


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_m1_search_and_coarse_order_keep_kind(kind):
    ctl = ColorSharedPoseDelivery(MAP, CALIB['params'], box_kind=kind, box_profile=p.PROFILE, slot_id='B1', slot_xy=(.32, 0.),
              skill_factory=lambda o: None, pose_estimate_cls=PoseEstimate, search_rows_y=ROWS_Y)
    report = SimpleNamespace(initialized=True, yaw_rad=0., x_m=0., y_m=0., t_est=1., std_xy_m=.01)
    wrong = next(k for k in BOX_KINDS if k != kind)
    ctl._search_detect(observation(f'{wrong}_floor.png'), report)
    assert not ctl.target_detections
    ctl._search_detect(observation(f'{kind}_floor.png'), report)
    assert len(ctl.target_detections) == 1
    ctl.target_xy = (.32, 0.)
    assert ctl._make_order().kind == kind


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_executor_passes_kind_into_controller_and_skill(kind, monkeypatch):
    ex = executor(kind)
    assert ex.deliver('o', 'B')['accepted']
    assert ex.job.args['box_kind'] == ex._held_kind() == kind
    # Finish only the initial own look; no provider/world runs in this test.
    ex.job.phase = 'look'
    ex.job.sweep = {}
    monkeypatch.setattr(ex, '_tick_sweep', lambda *a: None)
    captured = {}
    def controller(*a, **kw):
        captured.update(kw)
        return SimpleNamespace(decide=lambda now: {'mode': 'tick', 'commands': [{'kind': 'hold'}]})
    monkeypatch.setattr(zox, 'ColorDeliverController', controller)
    ex._step_deliver(1., ex.job)
    assert captured['box_kind'] == kind and captured['box_profile'] == p.PROFILE
    made = captured['skill_factory'](order(kind))
    assert type(made) is WristColorBoxDelivery and made.box.box_kind == kind


@pytest.mark.parametrize('bad', ('yellow', 'can', 'tile', 'heavy_crate', 'long_beam', 'unknown', '', None))
def test_unsupported_kind_fails_before_motion(bad):
    with pytest.raises(ValueError):
        ColorBoxOrder(bad, 'bay', (.4, 0.), (.25, .25), 'B1', (4.6, -2.1))
    ex = executor(bad)
    assert not ex.deliver('o', 'B')['accepted']
    assert ex.job is None
    with pytest.raises(ValueError):
        p.compare_box_comotion(image('red_held.png'), image('red_held.png'), kind=bad)


def test_legacy_cyan_is_still_default_and_old_skill_cannot_admit_red():
    from harness.wrist_zone_skill_v9 import WristZoneDeliveryV9
    assert executor('cyan', WristZoneDeliveryV9).deliver('o', 'B')['accepted']
    ex = executor('red', WristZoneDeliveryV9)
    assert ex.deliver('o', 'B')['rejected_reason'] == 'KIND_NOT_SUPPORTED_BY_M1_SKILL'
    assert ex.job is None


@pytest.mark.parametrize('condition', ('no_comm', 'peer_ko', 'leader_ko', 'structured'))
def test_conditions_and_private_changes_do_not_change_local_actions(condition):
    # Public local action enters the same real executor API in all four conditions.
    # Private setup is deliberately never an argument to controller/skill.
    from harness.zone_study_contract import CONDITIONS
    from harness.zone_study_scenarios import public_part
    assert condition in CONDITIONS
    private = {'placements': [{'kind': 'red', 'pose_m': [1., -2.45, 0.]}], 'events': [{'at_sim_s': 62.5}]}
    reference = None
    for counterfactual in (private, {'placements': [], 'events': [{'at_sim_s': -999.}], 'judge': 'success'}):
        before = copy.deepcopy(counterfactual)
        scenario = {'scenario_id': 't03-dev', 'orders': list(executor().orders.values()), 'eval': counterfactual}
        public = public_part(scenario)
        ex = zox.ZoneColorBoxExecutor('r1', MAP, CALIB['params'], public, skill_factory=WristColorBoxDelivery,
                                 pose_estimate_cls=PoseEstimate, search_rows_y=ROWS_Y, judgments=False)
        accepted = ex.deliver('o', 'B')
        skill = ex._skill_for(ex.job)(order('red'))
        result = (accepted, skill.box.decide(observation('red_floor.png')), ex.events,
                  ex.box_profile, type(skill).__name__, skill.box.attachment_home_reference)
        if reference is None:
            reference = result
        assert result == reference and before == counterfactual
    for cls in (M1OwnCamDelivery, ColorSharedPoseDelivery, WristColorBoxDelivery, KindBoxSkill):
        assert 'condition' not in inspect.signature(cls).parameters


def test_runtime_source_closure_includes_selected_color_skill():
    from harness.python_source_closure import source_closure
    closure = source_closure(ROOT, ('harness/zone_color_box_executor.py',), modules=('harness.wrist_color_boxes',))
    assert {'harness/wrist_color_boxes.py', 'harness/m1_color_perception.py',
            'harness/m1_color_contract.py', 'harness/zone_own_deliver.py'} <= set(closure)


def test_factory_cannot_claim_color_support_and_return_a_cyan_box():
    def bad_factory(order, robot_id):
        return WristColorBoxDelivery(globals()['order']('cyan'), robot_id=robot_id, mode='m1')
    bad_factory.box_perception_profile = p.PROFILE
    ex = executor(factory=bad_factory)
    assert ex.deliver('o', 'B')['accepted']
    with pytest.raises(zox.ExecutorContractError, match='different profile or kind'):
        ex._skill_for(ex.job)(order('red'))


def test_kind_survives_job_end_and_wrong_kind_held_flag_is_not_yes():
    ex = executor('green')
    assert ex.deliver('o', 'B')['accepted']
    ex.job.ctl = SimpleNamespace(skill=SimpleNamespace(phase='nav_preplace',
                                box=SimpleNamespace(held=True, box_kind='red')))
    assert ex.holding()['answer'] != 'yes'
    # Later own holding judgments must still ask about green after an aborted job.
    ex.job = None
    assert ex._held_kind() == 'green'


def test_wrong_kind_placement_cannot_increment_delivered_count(monkeypatch):
    ex = executor('green')
    assert ex.deliver('o', 'B')['accepted']
    ex.job.ctl = SimpleNamespace(
        decide=lambda now: {'mode': 'done', 'outcome': 'SKILL_OWN_RGB_PLACEMENT_IN_SLOT'},
        skill=SimpleNamespace(placement={'kind': 'red', 'reason': 'IN_SLOT'}), lookback_gates=[])
    failures = []
    finished = []
    monkeypatch.setattr(ex, '_fail', lambda now, reason, **kw: failures.append(reason))
    monkeypatch.setattr(ex, '_finish', lambda *a, **kw: finished.append((a, kw)))
    ex._step_deliver(1., ex.job)
    assert failures == ['PLACEMENT_KIND_MISMATCH'] and not ex._delivered_per_zone
    assert finished == []


@pytest.mark.parametrize('bad', ('%%%', '', base64.b64encode(b'not an image').decode()))
def test_malformed_rgb_never_emits_motion_or_claims_success(bad):
    sk = WristColorBoxDelivery(order('green'), mode='m1')
    frame = observation('green_floor.png')
    frame['image'] = bad
    with pytest.raises(ValueError):
        sk.box.decide(frame)
    assert not sk.box.held and sk.box.reason != 'VISUAL_RELEASE_CONFIRMED'


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_uniform_color_is_not_attachment_evidence(kind):
    frame = cv2.imdecode(np.frombuffer((FIX/f'{kind}_held.png').read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    frame[:] = frame[300, 300]
    data = base64.b64encode(cv2.imencode('.jpg', frame)[1].tobytes()).decode()
    assert not p.compare_box_comotion(data, data, kind=kind)['attached']


def test_unvalidated_final_v3_geometry_is_still_refused_before_physics():
    from harness.zone_robot_model_runtime import require_v3_consumers
    with pytest.raises(ValueError, match='explicit v3 skill'):
        require_v3_consumers({'skill_module': 'harness.wrist_color_boxes'}, lambda *a: None)


@pytest.mark.parametrize('kind', BOX_KINDS)
def test_expected_kind_placement_increments_count_and_finishes(kind, monkeypatch):
    ex = executor(kind)
    assert ex.deliver('o', 'B')['accepted']
    ex.job.ctl = SimpleNamespace(
        decide=lambda now: {'mode': 'done', 'outcome': 'SKILL_OWN_RGB_PLACEMENT_IN_SLOT'},
        skill=SimpleNamespace(placement={'kind': kind, 'reason': 'IN_SLOT'}), lookback_gates=[])
    finished, failures = [], []
    monkeypatch.setattr(ex, '_fail', lambda *a, **kw: failures.append((a, kw)))
    monkeypatch.setattr(ex, '_finish', lambda *a, **kw: finished.append((a, kw)))
    ex._step_deliver(1., ex.job)
    assert ex._delivered_per_zone == {'B': 1} and failures == []
    assert len(finished) == 1
    assert finished[0][0] == (1., 'own_camera_confirmed', 'SKILL_OWN_RGB_PLACEMENT_IN_SLOT')
