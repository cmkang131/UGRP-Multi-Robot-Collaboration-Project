"""Non-physical tests for warp8f owner-side self-centric memory evidence.

No simulator, GPU, mujoco, static map or GT.  The owner is driven with fake
navigator ``memory_registration`` snapshots; the release adapter is driven with
synthetic own frames whose only evidence is own JPEG/issued PWM.
"""
import hashlib
from pathlib import Path

import pytest

from harness import e2e_warp_release as release
from harness import e2ewarp_selfnav as sn
from harness import warp8f_memory
from harness.e2e_warp_runtime import OwnFrame

ROOT = Path(__file__).resolve().parents[1]
SEARCH_PWM = {1: 2000, 3: 740, 4: 2320, 5: 1320, 6: 1500}


def landmark(kind='zone_B', *, range_m=.2, bearing_deg=0., last_seen_s=1.0,
             uncertainty_m=.4):
    return dict(kind=kind, range_m=range_m, bearing_deg=bearing_deg,
                last_seen_s=last_seen_s, uncertainty_m=uncertainty_m,
                range_measured=True)


def registration(*, revision=7, kind='zone_B', landmarks=None, ready=True,
                 registered=True, destination_registered=True):
    landmarks = [landmark(kind)] if landmarks is None else list(landmarks)
    destination = next((dict(item) for item in landmarks if item['kind'] == kind), None)
    return dict(schema=sn.SCHEMA, owner=sn.OWNER, ready=ready,
                registered=registered, destination_registered=destination_registered,
                evidence_revision=int(revision),
                memory_sha256=sn.memory_sha256(landmarks, revision),
                landmarks=len(landmarks), destination_kind=kind,
                destination_landmark=destination,
                pose_estimate=dict(frame='self_centric', position_xy=[0.0, 0.0]),
                static_map_used=False, truth_inputs=0, held_world_reads=0,
                source='own_rgb_and_own_issued_commands')


def evidence(bound, *, views=None):
    views = views or [dict(t=1.0, rgb_sha256=hashlib.sha256(b'a').hexdigest(), pwm=dict(SEARCH_PWM)),
                      dict(t=2.0, rgb_sha256=hashlib.sha256(b'b').hexdigest(), pwm=dict(SEARCH_PWM)),
                      dict(t=3.0, rgb_sha256=hashlib.sha256(b'c').hexdigest(), pwm=dict(SEARCH_PWM))]
    return dict(robot_id='r1', navigator_owner=sn.OWNER,
                memory_sha256=bound['memory_sha256'],
                navigator_evidence_revision=bound['evidence_revision'],
                destination_kind=bound['destination_kind'],
                instruction=dict(destination_zone='B', object_kind='long_beam', role='teal'),
                views=list(views))


class Frame:
    def __init__(self, robot_id='r1', t=0.0, jpeg=b'own-rgb', pwm=None):
        self.robot_id, self.sim_s, self.jpeg = robot_id, t, jpeg
        self.issued = tuple([dict(t=t, pwm=dict(pwm or SEARCH_PWM))])


def collect_views(adapter, start_t=0.0):
    dwell = release._view_dwell_s()
    t, out = start_t, None
    for _ in range(release.PAN_VIEWS):
        pwm = adapter.command(t)['pwm']
        t += dwell
        out = adapter.observe(Frame(t=t, pwm={int(k): int(v) for k, v in pwm.items()}))
        t += 0.1
    return out, t


# -- owner: accepted echo ------------------------------------------------------
def test_owner_echoes_bound_navigator_snapshot_and_landmark_kind():
    bound = registration(revision=7, kind='zone_B')
    owner = warp8f_memory.Warp8fMemoryOwner(bound)
    result = owner(evidence(bound))
    assert result['owner'] == 'warp8f' and result['source'] == warp8f_memory.SOURCE
    assert result['relocalized'] is True and result['memory_registered'] is True
    assert result['memory_sha256'] == bound['memory_sha256']
    assert result['navigator_evidence_revision'] == bound['evidence_revision']
    assert result['navigator_current_revision'] == bound['evidence_revision']
    assert result['navigator_current_memory_sha256'] == bound['memory_sha256']
    assert result['memory_landmark']['kind'] == 'zone_B'
    assert result['truth_inputs'] == 0 and result['held_world_reads'] == 0
    for field in ('static_map_registered', 'static_map_sha256', 'map_pose', 'ground_truth'):
        assert field not in result, field


def test_owner_echoes_bound_snapshot_when_navigator_memory_advanced():
    """Release lookaround frames advance navigator revision; echo stays bound."""
    bound = registration(revision=7, kind='zone_B')
    live_landmarks = [landmark('zone_B', range_m=.12, bearing_deg=2., last_seen_s=7.25)]
    live = registration(revision=9, landmarks=live_landmarks)
    views = evidence(bound)['views']
    views[-1]['t'] = 7.25
    result = warp8f_memory.Warp8fMemoryOwner(live)(dict(evidence(bound), views=views))
    assert result['relocalized'] is True and result['memory_registered'] is True
    assert result['memory_sha256'] == bound['memory_sha256']
    assert result['navigator_evidence_revision'] == 7
    assert result['navigator_current_revision'] == 9
    assert result['navigator_current_memory_sha256'] == live['memory_sha256']
    assert result['memory_landmark']['last_seen_s'] == 7.25


# -- owner: fail-closed codes --------------------------------------------------
def test_owner_rejects_mismatched_hash_and_revision():
    bound = registration(revision=7)
    assert warp8f_memory.Warp8fMemoryOwner(registration(revision=6))(
        evidence(bound))['reason'] == 'owner_navigator_snapshot_stale'
    tampered = registration(revision=7, landmarks=[landmark('zone_B', range_m=.9)])
    assert tampered['memory_sha256'] != bound['memory_sha256']
    assert warp8f_memory.Warp8fMemoryOwner(tampered)(
        evidence(bound))['reason'] == 'owner_navigator_snapshot_hash_mismatch'
    assert warp8f_memory.Warp8fMemoryOwner(None)(
        evidence(bound))['reason'] == 'owner_navigator_snapshot_missing'

    def down():
        raise RuntimeError('navigator memory unavailable')

    assert warp8f_memory.Warp8fMemoryOwner(down)(
        evidence(bound))['reason'] == 'owner_navigator_snapshot_unavailable'
    invalid = dict(bound, static_map_used=True)
    assert warp8f_memory.Warp8fMemoryOwner(invalid)(
        evidence(bound))['reason'] == 'owner_navigator_snapshot_invalid'


def test_owner_rejects_wrong_landmark_kind_and_future_landmark():
    bound = registration(revision=7, kind='zone_B')
    # Keep the snapshot hash/revision identical to the bound one and vary only
    # the destination claim, so these cases exercise the landmark checks rather
    # than the hash-mismatch guard.
    wrong_destination = registration(revision=7, kind='zone_B')
    wrong_destination['destination_kind'] = 'zone_A'
    assert warp8f_memory.Warp8fMemoryOwner(wrong_destination)(
        evidence(bound))['reason'] == 'owner_navigator_destination_mismatch'
    inconsistent = registration(revision=7, kind='zone_B')
    inconsistent['destination_landmark'] = landmark('zone_A')
    assert warp8f_memory.Warp8fMemoryOwner(inconsistent)(
        evidence(bound))['reason'] == 'owner_navigator_landmark_mismatch'
    missing = registration(revision=7, kind='zone_B')
    missing['destination_landmark'] = None
    assert warp8f_memory.Warp8fMemoryOwner(missing)(
        evidence(bound))['reason'] == 'owner_navigator_landmark_missing'
    future = registration(revision=7, kind='zone_B')
    future['destination_landmark'] = landmark('zone_B', last_seen_s=9.0)
    assert warp8f_memory.Warp8fMemoryOwner(future)(
        evidence(bound))['reason'] == 'owner_navigator_landmark_from_future'


def test_owner_rejects_missing_destination_registration():
    bound = registration(revision=7)
    for snapshot, reason in (
            (registration(revision=7, ready=False), 'owner_navigator_not_ready'),
            (registration(revision=7, registered=False), 'owner_navigator_memory_unregistered'),
            (registration(revision=7, destination_registered=False),
             'owner_navigator_destination_unregistered')):
        assert warp8f_memory.Warp8fMemoryOwner(snapshot)(
            evidence(bound))['reason'] == reason


# -- release adapter integration ----------------------------------------------
def test_release_adapter_accepts_owner_memory_echo():
    bound = registration(revision=7)
    adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                      memory_source=bound)
    assert isinstance(adapter.owner, warp8f_memory.Warp8fMemoryOwner)
    adapter.start(dict(destination_zone='B', object_kind='long_beam', role='teal',
                       order_id='o1'), dict(memory_registration=bound))
    report, _ = collect_views(adapter)
    assert report['relocalized'] is True and report['memory_registered'] is True
    assert report['reason'] == 'owner_accepted_self_centric_memory'
    assert report['memory_sha256'] == bound['memory_sha256']
    assert report['navigator_evidence_revision'] == bound['evidence_revision']
    assert report['static_map_registered'] is False and report['map_pose'] is None
    assert report['evidence']['navigator_current_revision'] == bound['evidence_revision']
    assert report['audit']['static_map_input'] is False


def test_release_adapter_accepts_while_real_selfnav_revision_advances():
    """The live navigator observes every lookaround frame; release still binds."""
    navigator = sn.navigation_factory(
        'r1', {'destination_zone': 'B'}, option=sn.OPTION,
        detector=lambda frame: [dict(kind='zone_B', range_m=.2, bearing_deg=0.,
                                     uncertainty_m=.4, range_measured=True)],
        odometry=sn.OwnCommandOdometry(forward_m_per_pct_s=.01, yaw_deg_per_pct_s=.5))
    first = navigator.observe(OwnFrame('r1', 0, 0, 0.0, b'own-rgb', ()))
    adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                      memory_source=navigator.memory_registration)
    adapter.start(dict(destination_zone='B', object_kind='long_beam', role='teal'),
                  first)
    bound = adapter.binding
    dwell, t, released = release._view_dwell_s(), 0.0, None
    for tick in range(release.PAN_VIEWS):
        pwm = adapter.command(t)['pwm']
        t += dwell
        navigator.observe(OwnFrame('r1', 0, tick, t, b'own-rgb',
                                   (dict(t=t, wheels=[0.] * 4, duration_s=[0.] * 4,
                                         pwm={int(k): int(v) for k, v in pwm.items()}),)))
        released = adapter.observe(Frame(t=t, pwm={int(k): int(v) for k, v in pwm.items()}))
        t += 0.1
    current = navigator.memory_registration()
    assert current['evidence_revision'] > bound['navigator_evidence_revision']
    assert released['relocalized'] is True and released['memory_registered'] is True
    assert released['memory_sha256'] == bound['memory_sha256']
    assert released['evidence']['navigator_current_revision'] == current['evidence_revision']
    assert navigator.accept_release_fix(released) is True


def test_release_adapter_surfaces_owner_missing_and_stale_codes():
    bound = registration(revision=7)
    cases = (
        (lambda: None, 'owner_navigator_snapshot_missing'),
        (registration(revision=6), 'owner_navigator_snapshot_stale'),
    )
    for source, reason in cases:
        adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                          memory_source=source)
        adapter.start(dict(destination_zone='B'), dict(memory_registration=bound))
        report, _ = collect_views(adapter)
        assert report['relocalized'] is False and report['memory_registered'] is False
        assert report['reason'] == reason, reason


def test_release_adapter_rejects_static_map_fields_as_mixed_evidence():
    bound = registration(revision=7)
    good = warp8f_memory.Warp8fMemoryOwner(bound)
    for field, value in (('static_map_registered', False),
                         ('static_map_registered', True),
                         ('static_map_sha256', None),
                         ('static_map_sha256', '0' * 64)):
        def owner(ev, field=field, value=value):
            return dict(good(ev), **{field: value})
        adapter = release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                          owner=owner)
        adapter.start(dict(destination_zone='B'), dict(memory_registration=bound))
        report, _ = collect_views(adapter)
        assert report['relocalized'] is False and report['memory_registered'] is False
        assert report['reason'] == 'owner_mixed_static_map_evidence', field


def test_release_adapter_owner_and_memory_source_are_exclusive():
    bound = registration(revision=7)
    with pytest.raises(ValueError, match='exclusive'):
        release.release_factory('r1', None, option=release.OPTION_MEMORY,
                                owner=lambda ev: {}, memory_source=bound)
    with pytest.raises(ValueError, match='requires release_relocalization_memory_v1'):
        release.release_factory('r1', None, option=release.OPTION_OFF, memory_source=bound)
    with pytest.raises(ValueError, match='OWNER_MEMORY_SOURCE_REQUIRED'):
        warp8f_memory.Warp8fMemoryOwner(object())


def test_owner_module_has_no_static_map_gt_or_file_reads():
    source = (ROOT / 'harness' / 'warp8f_memory.py').read_text()
    forbidden = ('static_map_registered', 'static_map_sha256', 'map_pose',
                 'ground_truth', 'hidden_state', 'truth_inputs=1',
                 'held_world_reads=1', 'open(', 'mujoco', 'sim.', 'evaluator')
    for token in forbidden:
        assert token not in source, token
    allowed_imports = ('__future__', 'math', 'harness.e2ewarp_selfnav')
    for line in source.splitlines():
        line = line.strip()
        if line.startswith('from ') or line.startswith('import '):
            assert any(token in line for token in allowed_imports), line
