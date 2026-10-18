"""Non-physical tests for the default-off contract-v1 self-centric binding.

No simulator, no GPU, no mujoco.  The tests drive the loaded-FK navigation
composition and the release adapter with synthetic own frames and a stub
navigator report whose shape is the canonical ``ugrp.e2ewarp.selfnav.v1``
registration produced by ``harness.e2ewarp_selfnav`` (also exercised directly
here).  They assert the default-off fail-closed contract, the absence of any
static map/hash/global pose, and the memory-hash/revision binding.
"""
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness import e2e_warp_components as components
from harness import e2e_warp_release as release
from harness import e2ewarp_mapcorr as mc
from harness import e2ewarp_selfnav as sn
from harness.e2e_warp_runtime import OwnFrame
from harness.grasp_act_contract import command as issued_command

ROOT = Path(__file__).resolve().parents[1]
SEARCH_PWM = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}
LANDMARKS = [dict(kind='zone_B', range_m=0.2, bearing_deg=0.0, last_seen_s=1.0,
                  uncertainty_m=0.4, range_measured=True)]


def registration(*, ready=True, registered=True, destination_registered=True,
                 revision=7, destination_kind='zone_B', landmarks=None):
    landmarks = list(LANDMARKS if landmarks is None else landmarks)
    landmark = next((dict(item) for item in landmarks if item['kind'] == destination_kind), None)
    return dict(schema=sn.SCHEMA, owner=sn.OWNER, ready=ready,
                registered=registered, destination_registered=destination_registered,
                evidence_revision=int(revision),
                memory_sha256=sn.memory_sha256(landmarks, revision),
                landmarks=len(landmarks), destination_kind=destination_kind,
                destination_landmark=landmark,
                pose_estimate=dict(frame='self_centric', position_xy=[0.0, 0.0]),
                static_map_used=False, truth_inputs=0, held_world_reads=0,
                source='own_rgb_and_own_issued_commands')


def own_jpeg(seed=0):
    rng = np.random.RandomState(seed)
    rgb = rng.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    ok, raw = cv2.imencode('.jpg', cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return raw.tobytes()


def own_frame(robot='r1', sim=0.0, tick=0, grip=2000):
    pwm = {str(k): int(v) for k, v in SEARCH_PWM.items()}
    pwm['1'] = grip
    return OwnFrame(robot, 0, tick, sim, own_jpeg(tick),
                    (dict(t=sim, wheels=[0.] * 4, duration_s=[0.] * 4, pwm=pwm),))


class MemoryOwner:
    """Stub navigator: only the ABI + the canonical registration block."""

    def __init__(self, reg):
        self.reg, self.observed, self.started, self.commands = reg, 0, None, 0

    def observe(self, frame):
        self.observed += 1
        return dict(memory_registration=dict(self.reg), handoff_ready=True,
                    destination_arrived=True, holding_status='held',
                    drive_reason='driving',
                    evidence_revision=self.reg['evidence_revision'],
                    map_correction_active=True)

    def task_candidates(self, completed):
        return []

    def start(self, instruction, phase):
        self.started = (dict(instruction), phase)

    def command(self, now):
        self.commands += 1
        pwm = {str(k): int(v) for k, v in SEARCH_PWM.items()}
        return dict(t=float(now), wheels=[0.] * 4, duration_s=[0.] * 4, pwm=pwm)

    def confirm_act(self, frame, skill):
        return True

    def on_messages(self, rows):
        pass


def memory_nav(owner, *, static=None, loaded_fk=True):
    toggles = {mc.OPTION_NAV: 'on', mc.OPTION_MEMORY: 'on'}
    if loaded_fk:
        toggles[mc.OPTION_LOADED_FK] = 'on'
    return mc.navigation_factory('r1', static, toggles=toggles, owner_navigation=owner)


# -- selfnav canonical registration -------------------------------------------
def test_selfnav_memory_registration_is_canonical_and_hash_bound():
    nav = sn.navigation_factory('r1', {'orders': [], 'destination_zone': 'B'},
                                option=sn.OPTION,
                                detector=lambda frame: LANDMARKS, odometry=sn.OwnCommandOdometry(
                                    forward_m_per_pct_s=.01, yaw_deg_per_pct_s=.5))
    report = nav.observe(OwnFrame('r1', 0, 0, 0., own_jpeg(), ()))
    reg = report['memory_registration']
    assert reg['schema'] == sn.SCHEMA and reg['owner'] == sn.OWNER
    assert reg['ready'] is True and reg['registered'] is True
    assert reg['destination_registered'] is True
    assert reg['pose_estimate'] == dict(frame='self_centric', position_xy=[0.0, 0.0])
    assert reg['static_map_used'] is False
    assert reg['memory_sha256'] == sn.memory_sha256(report['self_centric_memory'], reg['evidence_revision'])
    assert len(reg['memory_sha256']) == 64
    # A different revision is a different snapshot (replay binding).
    assert sn.memory_sha256(report['self_centric_memory'], reg['evidence_revision'] + 1) != reg['memory_sha256']


def test_selfnav_registration_is_not_ready_without_owner_components():
    nav = sn.navigation_factory('r1', {'destination_zone': 'B'}, option=sn.OPTION)
    reg = nav.observe(OwnFrame('r1', 0, 0, 0., own_jpeg(), ()))['memory_registration']
    assert reg['ready'] is False and reg['registered'] is False
    assert reg['destination_registered'] is False


# -- loaded-FK memory binding -------------------------------------------------
def test_memory_mode_accepts_order_sheet_and_refuses_static_map():
    reg = registration()
    nav = memory_nav(MemoryOwner(reg), static={'orders': [{'id': 'o1'}]})
    assert nav.memory_mode is True and nav.correction is None
    assert nav.static_sha256 is None
    with pytest.raises(ValueError, match='static map input is forbidden'):
        memory_nav(MemoryOwner(reg), static={'static_map': {'bounds_m': [0, 1, 0, 1]}})


def test_memory_mode_is_exclusive_with_map_correction():
    with pytest.raises(ValueError, match='EXCLUSIVE'):
        mc.navigation_factory('r1', {'orders': []}, toggles={
            mc.OPTION_NAV: 'on', mc.OPTION_MEMORY: 'on', mc.OPTION_CORRECTION: 'on'})


def test_memory_mode_fails_closed_without_a_navigator():
    nav = memory_nav(None, loaded_fk=False)
    report = nav.observe(own_frame())
    assert report['registration_mode'] == 'memory_registered'
    assert report['memory_registered'] is False and report['map_correction_active'] is False
    assert report['reason'] == 'selfnav_navigator_missing'
    assert report['static_map_registered'] is False and report['static_map_sha256'] is None
    assert nav.command(.1)['wheels'] == [0.] * 4


def test_memory_mode_fails_closed_when_selfnav_is_not_ready():
    owner = MemoryOwner(registration(ready=False, registered=False, destination_registered=False))
    nav = memory_nav(owner)
    report = nav.observe(own_frame())
    assert report['reason'] == 'selfnav_not_ready'
    assert report['memory_registered'] is False and report['map_correction_active'] is False
    assert owner.commands == 0
    assert issued_command(nav.command(.1))['wheels'] == [0.] * 4


def test_memory_mode_reports_self_centric_registration_with_loaded_fk():
    reg = registration()
    nav = memory_nav(MemoryOwner(reg))
    report = nav.observe(own_frame(grip=1500))   # carry posture: closed command
    assert report['registration_mode'] == 'memory_registered'
    assert report['memory_registered'] is True and report['map_correction_active'] is True
    assert report['memory_sha256'] == reg['memory_sha256']
    assert report['memory_evidence_revision'] == reg['evidence_revision']
    assert report['pose_estimate'] == dict(frame='self_centric', position_xy=[0.0, 0.0])
    assert report['own_gauge_pose'] is None and report['static_map_sha256'] is None
    assert report['static_map_registered'] is False
    assert report['loaded_fk']['qualified'] is True
    assert report['loaded_fk']['command_only'] is True
    assert report['loaded_fk']['load_measured'] is False
    assert report['handoff_ready'] is True and report['destination_arrived'] is True
    assert report['input_audit']['self_centric_memory'] is True
    assert report['input_audit']['static_map_correction'] is False


def test_memory_mode_accepts_release_fix_only_with_bound_evidence():
    reg = registration(revision=9)
    nav = memory_nav(MemoryOwner(reg))
    report = nav.observe(own_frame())
    assert report['memory_registered'] is True
    fix = dict(relocalized=True, memory_registered=True,
               navigator_owner=sn.OWNER, memory_sha256=reg['memory_sha256'],
               navigator_evidence_revision=reg['evidence_revision'],
               memory_landmark=dict(reg['destination_landmark']),
               truth_inputs=0, held_world_reads=0)
    assert nav.accept_release_fix(fix) is True
    assert nav.accept_release_fix(dict(fix, static_map_registered=True)) is False
    assert nav.accept_release_fix(dict(fix, navigator_owner='warp8f')) is False
    assert nav.accept_release_fix(dict(fix, memory_sha256='0' * 63)) is False
    assert nav.accept_release_fix(dict(fix, navigator_evidence_revision=99)) is False
    assert nav.accept_release_fix(dict(fix, memory_landmark={'kind': 'zone_A'})) is False
    assert nav.accept_release_fix(dict(fix, truth_inputs=1)) is False


def test_real_selfnav_binds_loaded_fk_and_release_without_static_map():
    """End-to-end (non-physical): live selfnav memory -> loaded FK -> release -> accept."""
    detections = [dict(kind='zone_B', range_m=.2, bearing_deg=0., last_seen_s=0.,
                       uncertainty_m=.5, range_measured=True)]
    navigator = sn.navigation_factory(
        'r1', {'destination_zone': 'B'}, option=sn.OPTION,
        detector=lambda frame: detections,
        odometry=sn.OwnCommandOdometry(forward_m_per_pct_s=.01, yaw_deg_per_pct_s=.5))
    nav = mc.navigation_factory(
        'r1', {'destination_zone': 'B'},
        toggles={mc.OPTION_NAV: 'on', mc.OPTION_MEMORY: 'on', mc.OPTION_LOADED_FK: 'on'},
        owner_navigation=navigator)
    report = nav.observe(own_frame(grip=1500))
    assert report['registration_mode'] == 'memory_registered'
    assert report['memory_registered'] is True and report['map_correction_active'] is True
    assert report['loaded_fk']['qualified'] is True
    assert report['static_map_registered'] is False and report['static_map_sha256'] is None
    adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                      owner=memory_owner)
    adapter.start(dict(destination_zone='B', object_kind='long_beam', role='teal',
                       order_id='o1'), report)
    assert adapter.binding is not None and adapter.binding_reason is None
    released, _ = collect_views(adapter)
    assert released['relocalized'] is True and released['memory_registered'] is True
    assert released['memory_sha256'] == report['memory_sha256']
    assert nav.accept_release_fix(released) is True


# -- release memory binding ---------------------------------------------------
def start(adapter, instruction=None, report=None):
    adapter.start(instruction or dict(destination_zone='B', object_kind='long_beam',
                                     role='teal', order_id='o1'), report or {})
    return adapter


def collect_views(adapter, start_t=0.0):
    dwell = release._view_dwell_s()
    t, out = start_t, None
    for _ in range(release.PAN_VIEWS):
        pwm = adapter.command(t)['pwm']
        t += dwell
        out = adapter.observe(Frame(t=t, pwm={int(k): int(v) for k, v in pwm.items()}))
        t += 0.1
    return out, t


class Frame:
    def __init__(self, robot_id='r1', t=0.0, jpeg=b'own-rgb', pwm=None):
        self.robot_id, self.sim_s, self.jpeg = robot_id, t, jpeg
        self.issued = tuple([dict(t=t, pwm=dict(pwm or SEARCH_PWM))])


def memory_owner(evidence):
    assert set(evidence) == {'robot_id', 'navigator_owner', 'memory_sha256',
                             'navigator_evidence_revision', 'destination_kind',
                             'instruction', 'views'}
    assert 'static_map_sha256' not in evidence
    last = evidence['views'][-1]
    return dict(owner='warp8f', relocalized=True, memory_registered=True,
                memory_sha256=evidence['memory_sha256'],
                navigator_evidence_revision=evidence['navigator_evidence_revision'],
                memory_landmark=dict(kind=evidence['destination_kind'], range_m=.2,
                                     bearing_deg=0., last_seen_s=last['t'], uncertainty_m=.4),
                source='own_rgb', views=len(evidence['views']),
                truth_inputs=0, held_world_reads=0)


def test_release_memory_mode_binds_navigator_snapshot():
    reg = registration(revision=4)
    adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                      owner=memory_owner)
    start(adapter, report=dict(memory_registration=reg))
    assert adapter.memory_mode is True and adapter.static_sha256 is None
    report, _ = collect_views(adapter)
    assert report['relocalized'] is True and report['memory_registered'] is True
    assert report['static_map_registered'] is False and report['map_pose'] is None
    assert report['pose_estimate'] == dict(frame='self_centric', position_xy=[0.0, 0.0])
    assert report['memory_sha256'] == reg['memory_sha256']
    assert report['navigator_evidence_revision'] == reg['evidence_revision']
    assert report['reason'] == 'owner_accepted_self_centric_memory'
    assert report['audit']['static_map_input'] is False
    assert report['evidence']['memory_sha256'] == reg['memory_sha256']


def test_release_memory_mode_fails_closed_when_selfnav_not_ready():
    for reg, reason in (
            (registration(ready=False), 'selfnav_not_ready'),
            (registration(registered=False), 'selfnav_memory_unregistered'),
            (registration(destination_registered=False), 'selfnav_destination_unregistered'),
            (registration(destination_kind='zone_A'), 'selfnav_destination_mismatch')):
        adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                          owner=memory_owner)
        start(adapter, report=dict(memory_registration=reg))
        report = adapter.observe(Frame(t=0.1))
        assert report['relocalized'] is False and report['memory_registered'] is False
        assert report['reason'] == reason
        assert adapter.rows == [] and adapter.command(.1)['pwm']['6'] == SEARCH_PWM[6]


def test_release_memory_mode_rejects_mixed_and_replayed_owner_evidence():
    reg = registration(revision=4)
    for mutate, reason in (
            (lambda owner: dict(owner, static_map_registered=True), 'owner_mixed_static_map_evidence'),
            (lambda owner: dict(owner, static_map_sha256='0' * 64), 'owner_mixed_static_map_evidence'),
            (lambda owner: dict(owner, memory_sha256='0' * 64), 'owner_memory_hash_mismatch'),
            (lambda owner: dict(owner, navigator_evidence_revision=3), 'owner_navigator_revision_mismatch'),
            (lambda owner: dict(owner, map_pose=[0., 0., 0.]), 'owner_map_pose_forbidden'),
            (lambda owner: dict(owner, memory_landmark={'kind': 'zone_A'}),
             'owner_destination_landmark_mismatch'),
            (lambda owner: dict(owner, truth_inputs=1), 'owner_reports_forbidden_inputs')):
        adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                          owner=lambda evidence, mutate=mutate: mutate(memory_owner(evidence)))
        start(adapter, report=dict(memory_registration=reg))
        report, _ = collect_views(adapter)
        assert report['relocalized'] is False and report['memory_registered'] is False, reason
        assert report['reason'] == reason, reason


def test_release_memory_mode_pending_owner_and_factory():
    adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY)
    start(adapter, report=dict(memory_registration=registration()))
    report, _ = collect_views(adapter)
    assert report['reason'] == 'owner_memory_acquisition_api_pending'
    entry = {'entry': release.ENTRY, 'sha256': hashlib.sha256(
        (ROOT / 'harness/e2e_warp_release.py').read_bytes()).hexdigest()}
    factory = components.factory(entry)
    built = factory(robot_id='r1', static=None, option=release.OPTION_MEMORY)
    assert isinstance(built, release.ReleaseRelocalization) and built.memory_mode is True


# -- admission + mission default-off surface ----------------------------------
def _actor_fixture(tmp_path):
    artifact = tmp_path / 'act'
    artifact.mkdir(exist_ok=True)
    files = {'model.safetensors': b'model',
             'adapter.json': json.dumps(dict(
                 provenance=dict(step=10000, schedule_steps=10000,
                                 contact_profile='warp_native_contact_v1'))).encode(),
             'config.json': b'{}'}
    for name, raw in files.items():
        (artifact / name).write_bytes(raw)
    inventory = {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}
    (artifact / 'SHA256.json').write_text(json.dumps(inventory))
    return dict(ready=True, owner='act16w4', native_contact='warp_native_contact_v1',
                path=str(artifact), selection_evidence='gate',
                inventory_sha256=hashlib.sha256((artifact / 'SHA256.json').read_bytes()).hexdigest())


def _manifest(tmp_path, mode=None):
    (tmp_path / 'nav_mod.py').write_text('def navigation_factory(**kwargs):\n    return kwargs\n')
    (tmp_path / 'rel_mod.py').write_text('def release_factory(**kwargs):\n    return kwargs\n')
    (tmp_path / 'eval_mod.py').write_text('def evaluator_factory(**kwargs):\n    return kwargs\n')
    def record(path):
        return {'entry': 'x:' + 'factory', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest = dict(
        navigation=dict(ready=True, owner='selfnav', evidence='test'),
        loaded_camera_fk=dict(ready=True, owner='mapbuild8', evidence='command-only'),
        memory_registration=dict(ready=True, owner='selfnav_memory_v1', evidence='own-memory',
                                 mode='self_centric_memory', static_map_input=False,
                                 spawn_anchor_used=False),
        selfmap_map_correction=dict(ready=False, owner='mapbuild8', evidence='pending'),
        release_relocalization=dict(ready=True, owner='warp8f', evidence='memory binding'),
        navigation_factory={'entry': 'nav_mod:navigation_factory',
                            'sha256': hashlib.sha256((tmp_path / 'nav_mod.py').read_bytes()).hexdigest()},
        release_factory={'entry': 'rel_mod:release_factory',
                         'sha256': hashlib.sha256((tmp_path / 'rel_mod.py').read_bytes()).hexdigest()},
        evaluator_factory={'entry': 'eval_mod:evaluator_factory',
                           'sha256': hashlib.sha256((tmp_path / 'eval_mod.py').read_bytes()).hexdigest()},
        ACT=_actor_fixture(tmp_path))
    if mode is not None:
        manifest['registration_mode'] = mode
    return manifest


def test_components_memory_registration_admission(tmp_path):
    manifest = _manifest(tmp_path, 'memory_registered')
    path = tmp_path / 'components.json'
    path.write_text(json.dumps(manifest))
    assert components.require_components(path, tmp_path)['registration_mode'] == 'memory_registered'
    manifest['memory_registration']['static_map_input'] = True
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='self-centric memory registration contract'):
        components.require_components(path, tmp_path)
    manifest = _manifest(tmp_path, 'memory_registered')
    manifest['static_map_registration'] = dict(ready=True, owner='mapbuild8', evidence='mixed')
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='mixed static-map and self-centric'):
        components.require_components(path, tmp_path)


def test_components_default_static_path_is_unchanged(tmp_path):
    manifest = _manifest(tmp_path)   # no registration_mode -> static path
    path = tmp_path / 'components.json'
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='DEPENDENCY_WAIT:static_map_registration'):
        components.require_components(path, tmp_path)
