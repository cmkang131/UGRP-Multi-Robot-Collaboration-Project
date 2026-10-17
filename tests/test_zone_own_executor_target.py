"""T13 target wiring: synthetic evidence, real saved JPEG perception, no World."""
import base64
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness.zone_identity_jobs import TARGET_API, TargetJob
from harness.zone_study_contract import ContractViolation
from harness.zone_target_identity import (BOX_SIZE, CueDetection, CueFrame, PublicVisualCatalogue,
                                          TargetRecoveryJobs)
from harness.zone_target_rgb import OwnRGBRecognizer, TargetView, attention_image
from harness.zone_target_executor import TargetOwnExecutor, TargetSkill
from tests.test_zone_identity_jobs import FakeTargetExecutor, order

ROOT = Path(__file__).resolve().parents[1]


def catalogue(*items):
    return {'schema': 'ugrp.public_visual_catalogue.v1', 'complete': True,
            'objects': [{'item_id': item, 'kind': kind, 'shape': 'box', 'color': kind,
                         'dimensions_m': list(BOX_SIZE)} for item, kind in (items or [('cyan_1', 'cyan')])]}


def specific():
    return order('order-cyan', 1, identity='specific_item', item_ids=['cyan_1'])


def detection(name='a', previous=(), kind='cyan', **kwargs):
    return CueDetection(name, kind, (.2, .2, .4, .4), previous, shape='box', dimensions_m=BOX_SIZE, **kwargs)


class Fixture:
    def __init__(self, orders=None, catalog=None, backend=None):
        self.backend = backend or FakeTargetExecutor()
        self.jobs = TargetRecoveryJobs('r1', orders or [specific()], self.backend,
                                        visual_catalogue=catalog or catalogue())
        self.seq, self.last = 0, None

    def frame(self, *ds, ambiguous=()):
        self.seq += 1
        sha = hashlib.sha256(str(self.seq).encode()).hexdigest()
        frame = CueFrame('r1', self.seq, float(self.seq), sha, self.last, tuple(ds), ambiguous)
        self.jobs.observe(frame)
        self.last = sha
        return frame

    def submit(self, name='a', oid='order-cyan', item='cyan_1'):
        return self.jobs.submit(oid, name, item_id=item, now_sim_s=float(self.seq))


def test_specific_public_descriptor_reaches_backend_with_distinct_order_and_item():
    f = Fixture()
    f.frame(detection())
    result = f.submit()
    assert result['state'] == 'running'
    assert result['resolved_item_id'] == 'cyan_1'
    job, = f.backend.submitted
    assert job['order_id'] == 'order-cyan' and job['requested_item_id'] == 'cyan_1'
    assert job['detection_id'] == 'a' and job['rgb_sha256'] == f.last


@pytest.mark.parametrize('fault,reason', [
    ('public_duplicate', 'PUBLIC_CUE_AMBIGUOUS'), ('visible_duplicate', 'OWN_CUE_NOT_UNIQUE'),
    ('partial', 'OWN_CUE_AMBIGUOUS'), ('shape', 'OWN_SHAPE_SIZE_UNGROUNDED'),
    ('size', 'OWN_SHAPE_SIZE_UNGROUNDED'), ('name_only', 'OWN_CUE_NOT_UNIQUE')])
def test_ambiguity_never_submits_even_when_the_detection_is_named_like_the_item(fault, reason):
    cat = catalogue(('cyan_1', 'cyan'), ('unrequested', 'cyan')) if fault == 'public_duplicate' else catalogue()
    f = Fixture(catalog=cat)
    d = detection('cyan_1')
    if fault == 'shape': d = replace(d, shape='unknown')
    if fault == 'size': d = replace(d, dimensions_m=(.08, .08, .08))
    if fault == 'name_only': d = replace(d, kind='red')
    ds = [d, replace(d, detection_id='b', bbox=(.6, .2, .8, .4))] if fault == 'visible_duplicate' else [d]
    f.frame(*ds, ambiguous=('cyan',) if fault == 'partial' else ())
    assert f.submit('cyan_1')['reason'] == reason
    assert f.backend.submitted == []


def test_loss_cancels_then_specific_reidentifies_without_changing_token_or_count():
    f = Fixture()
    f.frame(detection())
    job = f.submit()['job']
    f.frame()
    assert f.backend.cancelled == [(job['job_id'], 'TRACK_LOST_OR_AMBIGUOUS')]
    f.frame(detection('new'))
    retried = f.submit('new')
    assert retried['state'] == 'running'
    assert retried['job']['local_token'] == job['local_token']
    assert retried['job']['job_id'] != job['job_id']
    assert f.jobs.claim('order-cyan')['observed_count'] == 0


def test_red_drop_cancels_before_refresh_and_requires_new_frame():
    f = Fixture([order('red-order', 2, kind='red', zone='B')], catalogue(('r-a', 'red'), ('r-b', 'red')))
    f.frame(detection(kind='red'))
    job = f.submit(oid='red-order', item=None)['job']
    f.frame(detection(kind='red', previous=('a',), holding='yes'))
    n = len(f.backend.refreshed)
    f.frame(detection(kind='red', previous=('a',), holding='no', resting='yes'))
    assert len(f.backend.refreshed) == n
    assert f.backend.cancelled[-1] == (job['job_id'], 'OWN_RGB_DROP_OBSERVED')
    assert f.submit(oid='red-order', item=None)['reason'] == 'RECOVERY_REOBSERVE_REQUIRED'
    f.frame(detection(kind='red', previous=('a',), holding='no', resting='yes'))
    assert f.submit(oid='red-order', item=None)['state'] == 'running'


def test_count_requires_held_own_open_and_two_destination_frames():
    f = Fixture()
    f.frame(detection())
    job = f.submit()['job']['job_id']
    f.jobs.terminal(job)
    assert f.jobs.claim('order-cyan')['observed_count'] == 0
    f.frame(detection(previous=('a',), holding='yes'))
    f.jobs.issued_open(job, command_id='open', issued_at_sim_s=f.seq)
    f.frame(detection(previous=('a',), holding='no', resting='yes', zone='A'))
    assert f.jobs.claim('order-cyan')['observed_count'] == 0
    f.frame(detection(previous=('a',), holding='no', resting='yes', zone='A'))
    assert f.jobs.claim('order-cyan')['observed_count'] == 1
    assert f.submit()['reason'] == 'TARGET_ALREADY_COUNTED_OR_ASSIGNED'


def test_catalogue_rejects_private_runtime_fields():
    cat = catalogue()
    cat['objects'][0]['position'] = [1, 2, 3]
    with pytest.raises(ContractViolation): PublicVisualCatalogue(cat)


def test_attention_excludes_other_objects_and_preserves_selected_pixel_geometry():
    bgr = np.zeros((480, 640, 3), np.uint8)
    bgr[30:80, 40:90] = (0, 0, 230)
    bgr[200:350, 250:400] = (200, 180, 20)
    contour = np.array([[[40, 30]], [[89, 30]], [[89, 79]], [[40, 79]]])
    result = cv2.imdecode(np.frombuffer(attention_image(bgr, contour), np.uint8), cv2.IMREAD_COLOR)
    assert result.shape == bgr.shape
    assert not result[200:350, 250:400].any()
    hsv = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)
    assert hsv[50, 60, 0] == 92 and hsv[50, 60, 2] == 230


def saved_observation():
    path = ROOT/'tests/fixtures/wrist_zone_skill_v6'
    row = next(r for r in json.loads((path/'frames.json').read_text())['frames'] if r['file'] == 'yawp00.0_v1.jpg')
    data = (path/row['file']).read_bytes()
    # Deliberately load only public camera pixels and own issued PWM, never labels.
    return {'robot_id': 'r1', 'frame_id': 1, 'sim_time': 1., 'camera': 'robot_cam',
            'image': base64.b64encode(data).decode(), 'sha256': hashlib.sha256(data).hexdigest(),
            'actuator_state': {'servo_pulses': row['own_servo_pwm'], 'motor_commands': [0.]*4}}


def test_real_saved_rgb_recognizer_produces_specific_grounding_without_labels():
    from harness.zone_color_boxes import BOX_DIMS_M
    assert BOX_SIZE == BOX_DIMS_M
    static = json.loads((ROOT/'maps/zones/zone_wide_door_geometry_v2.json').read_text())
    recognizer = OwnRGBRecognizer('r1', static)
    report = SimpleNamespace(initialized=False)
    frame = recognizer.observe(1., saved_observation(), report)
    cyan = [d for d in frame.detections if d.kind == 'cyan']
    assert len(cyan) == 1
    assert PublicVisualCatalogue(catalogue()).resolve('cyan_1', frame, cyan[0].detection_id) is None
    assert recognizer.candidates[cyan[0].detection_id]['map_xy'] is None


def test_black_rgb_does_not_create_grounding():
    obs = saved_observation()
    ok, data = cv2.imencode('.jpg', np.zeros((480, 640, 3), np.uint8))
    assert ok
    obs.update(image=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())
    r = OwnRGBRecognizer('r1', {'zone_slots': {}})
    frame = r.observe(1., obs, SimpleNamespace(initialized=False))
    assert not frame.detections and 'cyan' in frame.ambiguous_kinds


@pytest.mark.parametrize('field,value', [('robot_id', 'r2'), ('camera', 'top'), ('sim_time', 2.), ('sha256', '0'*64)])
def test_rgb_boundary_rejects_foreign_stale_or_forged_input(field, value):
    obs = saved_observation()
    obs[field] = value
    with pytest.raises((ValueError, RuntimeError)):
        OwnRGBRecognizer('r1', {}).observe(1., obs, SimpleNamespace(initialized=False))


class FakeDelivery:
    def __init__(self, executor, job, target, view, point):
        self.target, self.views, self.skill = target, [view], None
    def bind(self, view): self.views.append(view)


def backend_fixture():
    from tests.test_zone_own_executor import make, MAP
    ex = make()
    ex.orders = {'order-cyan': specific()}
    ex.now = 1.
    ex.last_report = SimpleNamespace(initialized=True)
    ex.servo = {1: 2000}
    events = []
    rec = SimpleNamespace(frame=None, candidates={})
    def view(job, frame, did):
        return TargetView(job.job_id, job.local_token, did, frame.rgb_sha256, {'frame_id': frame.sequence, 'sha256': 'b'*64})
    rec.target_view = view
    wrapper = TargetOwnExecutor(ex, visual_catalogue=catalogue(), cancel_scheduled=lambda t, why: events.append((t, why)),
                                recognizer=rec, delivery_factory=FakeDelivery)
    frame = CueFrame('r1', 1, 1., 'a'*64, None, (detection(),))
    rec.frame, rec.candidates = frame, {'a': {'map_xy': [.3, -.8]}}
    wrapper.jobs.observe(frame)
    return wrapper, events


def test_backend_passes_exact_target_to_delivery_and_cancel_drops_scheduled_commands():
    ex, cancels = backend_fixture()
    result = ex.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)
    assert result['state'] == 'running'
    assert as_job(ex.job.ctl.target) == result['job']
    # Avoid the legacy summary reading the fake ctl; cancellation callback is
    # nevertheless the real target adapter path under test.
    ex.inner.cancel = lambda now, why: setattr(ex.inner, 'job', None)
    ex.jobs._stop('TRACK_LOST_OR_AMBIGUOUS')
    assert cancels == [(1., 'TRACK_LOST_OR_AMBIGUOUS')]
    assert ex.target is None and ex.inner.job is None


def as_job(job):
    from dataclasses import asdict
    return asdict(job)


def test_native_deliver_has_no_targetless_fallback():
    ex, _ = backend_fixture()
    with pytest.raises(TypeError): ex.deliver('order-cyan', 'A')


def test_skill_requires_bound_target_before_any_action():
    from harness.wrist_zone_skill_v5 import CoarseOrderSheet
    job = TargetJob(TARGET_API, 'j', 'r1', 'order-cyan', 'cyan_1', 'specific_item', 'cyan', 'A', 't', 'a', 1, 'a'*64)
    sk = TargetSkill(CoarseOrderSheet('cyan', 'own_rgb', (.3, 0.), (.25, .25), 'A1', (4., 0.)), target=job, mode='m1')
    with pytest.raises(ContractViolation): sk.decide(saved_observation(), None)
    with pytest.raises(ContractViolation): sk.bind(TargetView('wrong', 't', 'a', 'a'*64, {}))


def test_ambiguity_during_delivery_cancels_before_refresh_without_backend_fault():
    f = Fixture()
    f.frame(detection())
    job = f.submit()['job']
    n = len(f.backend.refreshed)
    f.frame(detection(previous=('a',)), ambiguous=('cyan',))
    assert f.backend.cancelled[-1] == (job['job_id'], 'OWN_CUE_AMBIGUOUS')
    assert len(f.backend.refreshed) == n and not f.jobs._backend_fault
    f.frame(detection('b'))
    assert f.submit('b')['state'] == 'running'


def test_refused_submission_does_not_poison_backend():
    ex, _ = backend_fixture()
    ex.inner.last_report.initialized = False
    assert ex.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)['reason'] == 'TARGET_SUBMIT_REFUSED'
    assert not ex.jobs._backend_fault
    ex.inner.last_report.initialized = True
    assert ex.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)['state'] == 'running'


def test_real_delivery_creates_bound_target_skill_and_own_only_planner(monkeypatch):
    from harness.zone_target_executor import TargetDelivery
    ex, _ = backend_fixture()
    ex.delivery_factory = TargetDelivery
    # Fake only the locomotion driver: run the real delivery/skill constructors.
    monkeypatch.setattr(TargetDelivery, '_start_leg', lambda self, goal, **kw: setattr(self, 'leg_goal', goal))
    result = ex.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)
    assert result['state'] == 'running'
    ctl = ex.job.ctl
    skill = ctl.skill_factory(ctl._make_order())
    assert isinstance(skill, TargetSkill) and as_job(skill.target) == result['job']
    assert skill.target_view is ctl.target_view and callable(skill.planner)
    with pytest.raises(ContractViolation): ctl._search_detect(None, None)


def test_cancel_uses_actual_host_queue_drop_and_does_not_touch_peer():
    from harness.zone_own_team_host import OwnCamTeamHost
    ex, _ = backend_fixture()
    holds = []
    slot = SimpleNamespace(timeline=[(2., [{'kind': 'arm', 'pulse': 1400}])], capture_after=True,
                           next_decide=2., cancellations=[])
    peer = SimpleNamespace(timeline=[(2., [{'kind': 'arm', 'pulse': 1300}])])
    host = SimpleNamespace(robots={'r1': slot, 'r2': peer}, _hold=lambda rid, now: holds.append((rid, now)))
    ex.cancel_scheduled = lambda now, why: OwnCamTeamHost._drop_scheduled(host, 'r1', now, why)
    assert ex.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)['state'] == 'running'
    ex.inner.cancel = lambda now, why: setattr(ex.inner, 'job', None)
    ex.jobs._stop('OWN_RGB_DROP_OBSERVED')
    assert slot.timeline == [] and slot.capture_after is False
    assert slot.cancellations[0]['dropped_macro_commands'] == 1 and holds == [('r1', 1.)]
    assert peer.timeline == [(2., [{'kind': 'arm', 'pulse': 1300}])]


def test_freshness_timeout_stops_before_lower_step():
    ex, cancels = backend_fixture()
    ex.jobs.submit('order-cyan', 'a', item_id='cyan_1', now_sim_s=1.)
    ex.inner.cancel = lambda now, why: setattr(ex.inner, 'job', None)
    ex.inner.step = lambda now: pytest.fail('stale target reached the lower controller')
    assert ex.step(1.251)['commands'] == [{'kind': 'hold'}]
    assert cancels == [(1.251, 'TARGET_FRAME_EXPIRED')]


def test_invalid_active_frame_stops_and_requires_valid_evidence():
    f = Fixture()
    frame = f.frame(detection())
    job = f.submit()['job']
    with pytest.raises(ContractViolation): f.jobs.observe(replace(frame, robot_id='r2'))
    assert f.backend.cancelled[-1] == (job['job_id'], 'INVALID_OWN_RECOVERY_FRAME')
    assert f.jobs._evidence_invalid


def test_real_skill_consumes_bound_saved_rgb_with_original_pixel_coordinates():
    from harness.wrist_zone_skill import PoseEstimate
    from harness.wrist_zone_skill_v5 import CoarseOrderSheet
    r = OwnRGBRecognizer('r1', {'zone_slots': {}})
    frame = r.observe(1., saved_observation(), SimpleNamespace(initialized=False))
    d, = frame.detections
    job = TargetJob(TARGET_API, 'j', 'r1', 'order-cyan', 'cyan_1', 'specific_item', 'cyan', 'A', 't',
                    d.detection_id, 1, frame.rgb_sha256)
    view = r.target_view(job, frame, d.detection_id)
    skill = TargetSkill(CoarseOrderSheet('cyan', 'own_rgb', (.3, 0.), (.25, .25), 'A1', (4., 0.)),
                        target=job, mode='m1')
    skill.bind(view)
    result = skill.decide(view.observation, PoseEstimate(0., 0., 0., 'owncam_pf'))
    assert result['kind'] in {'pose', 'mecanum', 'drive', 'wait'}
    assert skill._validated['sha256'] == view.observation['sha256']
    assert skill._validated['sha256'] != frame.rgb_sha256
    assert skill._validated['robot_id'] == 'r1'
