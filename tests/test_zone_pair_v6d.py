"""v6d: wide beam hue in the close views and the M1 ``fine`` PF motion profile during align (no physics).

Frames are exact own RGB + own issued PWM recorded by the PR #263 ``b-v6c`` stage-2 probe
(``tests/fixtures/zone_pair_v6d/manifest.json``). ``gt_beam_yaw_error_eval_only`` is only a label that the
tests compare the observed heading with; the controller never sees it.
"""
import base64
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from harness import owncam_align_motion_v6d as v6d
from harness import owncam_pair_beam as v1
from harness import owncam_pair_beam_v2 as v2
from harness import owncam_pair_beam_v6d as w6
from harness import owncam_recovery_v6c as v6c_clock
from harness.owncam_pose_source import OwnCamPoseSource
from harness.zone_pair_align import PairAlignRelook
from harness.zone_pair_v6_policy import (POLICIES, REVISION_POLICIES, WIDE_HUE_LO, WIDE_HUE_POSTURES,
                                         PairPolicy, pair_policy)

ROOT = Path(__file__).resolve().parents[1]
V6 = json.loads((ROOT/'tests/fixtures/zone_pair_v6/reports.json').read_text())
FIX = ROOT/'tests/fixtures/zone_pair_v6d'
MAN = json.loads((FIX/'manifest.json').read_text())
CLOSE = ('r1_p45_along+_opp', 'r1_p45_along+_same', 'r1_inspect_along-_opp', 'r1_inspect_corner--_same')
SEARCH = 'r2_search_corner--_same'


def frame(label):
    rec = MAN['frames'][label]
    data = (FIX/rec['file']).read_bytes()
    assert len(data) == rec['bytes'] < 1024*1024 and hashlib.sha256(data).hexdigest() == rec['sha256']
    return base64.b64encode(data).decode(), {int(k): v for k, v in rec['servo_pulses'].items()}, \
        rec['gt_beam_yaw_error_eval_only']


def fold(angle):
    """A beam heading is an axis: fold to (-pi/2, pi/2]."""
    return (angle + math.pi/2) % math.pi - math.pi/2


def heading_error(label, hue_lo):
    image, pose, gt = frame(label)
    beam = w6.observe_beam(image, pose, hue_lo)
    assert beam['visible'] and beam['reason'] == 'BAND_VISIBLE'
    return abs(fold(beam['axis_heading_rad'] - gt))


def provider(seed=628):
    p = OwnCamPoseSource(V6['map'], V6['params'], seed=seed)
    v6c_clock.enable_provider(p)
    p.loc.initialized = True
    p.loc.px[:] = [.6, 0., 0.]
    p.loc.t = 0.
    return p


# ------------------------------------------------------------ wide hue
def test_recorded_frames_are_small_and_hash_checked():
    assert set(MAN['frames']) == {*CLOSE, SEARCH}
    for label in MAN['frames']:
        frame(label)


def test_none_hue_bound_is_exactly_the_v1_mask_and_observation():
    for label in MAN['frames']:
        image, pose, _ = frame(label)
        bgr = v1.decode(image)
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        v1_mask = cv2.inRange(hsv, np.asarray(v1.LIME_LO), np.asarray(v1.LIME_HI)) > 0
        assert np.array_equal(w6.lime_mask(bgr), v1_mask) and np.array_equal(w6.lime_mask(bgr, None), v1_mask)
        assert w6.widen_lime(bgr, None) is bgr                       # the v1/v2 path sees the frame itself
        default = v2.observe_beam(image, pose)
        assert json.dumps(default, sort_keys=True, default=float) == \
            json.dumps(w6.observe_beam(image, pose, None), sort_keys=True, default=float)
        assert default['axis_heading_rad'] == v1.observe_beam(bgr, pose)['axis_heading_rad']


def test_wide_bound_only_adds_pixels_and_keeps_saturation_and_value_limits():
    image, _, _ = frame(CLOSE[0])
    bgr = v1.decode(image)
    base, wide = w6.lime_mask(bgr), w6.lime_mask(bgr, WIDE_HUE_LO)
    assert (base & ~wide).sum() == 0 and wide.sum() > 1.5*base.sum()
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    added = wide & ~base
    assert (hsv[..., 0][added] >= WIDE_HUE_LO).all() and (hsv[..., 0][added] < v1.LIME_LO[0]).all()
    assert (hsv[..., 1][added] >= v1.LIME_LO[1]).all() and (hsv[..., 2][added] >= v1.LIME_LO[2]).all()


def test_frozen_v1_reads_the_wide_mask_through_recoloured_pixels():
    """v1/v2 are hash-checked M2 imports: recolouring exactly the added pixels is the same as a wider mask."""
    for label in MAN['frames']:
        image, _, _ = frame(label)
        bgr = v1.decode(image)
        keep = bgr.copy()
        wide = w6.widen_lime(bgr, WIDE_HUE_LO)
        band = w6.dark_band_mask(bgr)
        added = w6.lime_mask(bgr, WIDE_HUE_LO) & ~w6.lime_mask(bgr)
        assert wide is not bgr and np.array_equal(bgr, keep)          # the recorded frame itself is untouched
        assert np.array_equal(v1.lime_mask(wide), w6.lime_mask(bgr, WIDE_HUE_LO) & ~(added & band))
        assert np.array_equal(np.any(wide != bgr, axis=2), added & ~band)


def test_the_dark_grip_band_class_is_never_recoloured():
    """v2 measures the grip from the dark band; a dark pixel that the wide hue would catch must stay dark."""
    image = np.zeros((4, 6, 3), np.uint8)
    hsv = np.zeros_like(image)
    hsv[0, :] = (30, 80, 50)         # hue 30, S 80 < 90, V 50 <= 60: band class AND inside the wide lime range
    hsv[1, :] = (30, 200, 200)       # bright yellow: added by the wide range, recoloured
    hsv[2, :] = (45, 200, 200)       # already lime: unchanged
    hsv[3, :] = (20, 200, 200)       # below the wide bound: unchanged
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    assert w6.lime_mask(bgr, WIDE_HUE_LO)[0].all() and w6.dark_band_mask(bgr)[0].all()
    wide = w6.widen_lime(bgr, WIDE_HUE_LO)
    assert np.array_equal(wide[0], bgr[0]) and np.array_equal(wide[2], bgr[2]) and np.array_equal(wide[3], bgr[3])
    assert (wide[1] == w6.WIDE_LIME_BGR).all() and not w6.lime_mask(bgr)[1].any() and v1.lime_mask(wide)[1].all()
    assert np.array_equal(w6.dark_band_mask(wide), w6.dark_band_mask(bgr))


@pytest.mark.parametrize('label', CLOSE)
def test_lime_only_mask_misreads_the_close_r1_views_and_the_wide_hue_reads_them(label):
    """The beam top is yellow (hue 25-36) in the r1 p45/inspect views: the lime mask keeps just the end faces."""
    default, wide = heading_error(label, None), heading_error(label, WIDE_HUE_LO)
    assert default > .1 and wide < .03                # true yaw error <= 0.025 rad in every fixture
    assert wide < .3*default


def test_search_view_keeps_the_v1_range_because_the_wide_hue_hurts_there():
    assert heading_error(SEARCH, None) < .01 and heading_error(SEARCH, WIDE_HUE_LO) > .05


def _study():
    spec = importlib.util.spec_from_file_location('study_v6d', ROOT/'scripts/study_owncam_pair_beam.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Port:
    fid = 0

    def capture(self):
        self.fid += 1
        return {'frame_id': self.fid, 'sim_time': 0., 'image': '', 'sha256': 'x'*64,
                'actuator_state': {'servo_pulses': {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}}}

    def apply(self, cmd, now):
        pass

    def hold(self, now):
        pass


class _Arm:
    until, events = 0., []

    def queue(self, pose, now, **kw):
        pass


def _student(study, monkeypatch, policy, posture, seen, events):
    def fake(image, pose, **kw):
        seen.append(kw)
        return {'visible': True, 'end_visible': False, 'reason': 'BAND_CLIPPED'}
    monkeypatch.setattr(study.ob2, 'observe_beam', fake)
    monkeypatch.setattr(w6, 'observe_beam', fake)
    st = study.PairStudent('r1', _Port(), _Arm(), lambda key: None,
                           lambda rid, kind, now, **kw: events.append((kind, kw)))
    st.state, st.look_name, st.policy = 'align', posture, pair_policy(policy)
    return st


@pytest.mark.parametrize('policy,posture,expected', [
    ('b-v6d', 'p45', WIDE_HUE_LO), ('b-v6d', 'inspect', WIDE_HUE_LO), ('b-v6d', 'search', None),
    ('b-v6c', 'p45', None), ('b-v6c', 'inspect', None), ('v5h', 'inspect', None), ('b-only', 'p45', None),
    ('a+b', 'inspect', None)])
def test_align_passes_the_wide_hue_only_for_v6d_in_the_close_views(monkeypatch, policy, posture, expected):
    study = _study()
    seen, events = [], []
    st = _student(study, monkeypatch, policy, posture, seen, events)
    assert st._beam_hue_lo() == expected
    st._align(1., True)
    assert seen == [{} if expected is None else {'hue_lo': expected}]      # non-v6d calls are unchanged
    obs = [kw for kind, kw in events if kind == 'beam_obs']
    assert len(obs) == 1 and obs[0].get('hue_lo') == expected and ('hue_lo' in obs[0]) == (expected is not None)


def test_wide_hue_postures_are_the_close_views():
    assert WIDE_HUE_POSTURES == ('p45', 'inspect') and 'search' not in WIDE_HUE_POSTURES
    assert set(WIDE_HUE_POSTURES) <= set(v2.order())


# ------------------------------------------------------------ fine PF motion profile
def test_fine_profile_is_the_m1_dev_calibration_and_its_hashes_are_recorded():
    profile, info = v6d.load_profile()
    raw = (ROOT/v6d.CALIBRATION).read_bytes()
    assert info['file_sha256'] == hashlib.sha256(raw).hexdigest() == \
        '126cadaa9265ed2ae2b034f675e67c227193a2e1678f6b0c82dd53b186e6fc72'
    assert profile == json.loads(raw)['params']['motion_profiles']['fine']
    assert profile['gain'] and profile['tau_stop_s'] < .1 and info['source'] == v6d.CALIBRATION


def test_enable_injects_fine_without_touching_the_shared_params_and_is_idempotent():
    before = copy.deepcopy(V6['params'])
    p = provider()
    assert not v6d.bound(p) and 'motion_profiles' not in p.loc.params
    info = v6d.enable_provider(p)
    assert v6d.bound(p) and info['origin'] == 'injected' and info['source'] == v6d.CALIBRATION
    profile, expected = v6d.load_profile()
    assert p.loc.params['motion_profiles']['fine'] == profile and info['profile_sha256'] == expected['profile_sha256']
    assert V6['params'] == before and 'motion_profiles' not in V6['params']     # the shared dict is not mutated
    assert 'motion_profiles' not in provider().loc.params                       # neither is another provider
    params = p.loc.params
    assert v6d.enable_provider(p) is info and p.loc.params is params              # idempotent


def test_enable_reaches_the_pf_through_provider_wrappers():
    p = provider()
    wrapper = SimpleNamespace(provider=SimpleNamespace(provider=p))
    v6d.enable_provider(wrapper)
    assert v6d.bound(wrapper) and v6d.bound(p) and 'fine' in p.loc.params['motion_profiles']


def test_a_provider_that_already_carries_fine_is_used_as_is():
    p = provider()
    custom = {**V6['params']['motion'], 'gain': [[1.9, 0, 0], [0, 1.9, 0], [0, 0, 1.9]]}
    p.loc.params = {**p.loc.params, 'motion_profiles': {'fine': custom}}
    info = v6d.enable_provider(p)
    assert info['origin'] == 'provider_params' and p.loc.params['motion_profiles']['fine'] is custom


def test_a_provider_without_a_profile_selecting_pf_is_refused():
    with pytest.raises(ValueError, match='motion profiles'):
        v6d.enable_provider(SimpleNamespace(loc=None))
    with pytest.raises(KeyError):
        provider().set_motion_profile(0., 'fine')        # not enabled: the PF refuses an unknown profile


def _drift(fine):
    """Mean forward PF displacement after four 0.3 s, 0.05 forward align pulses and a 4 s wait."""
    p = provider()
    if fine:
        v6d.enable_provider(p)
        p.set_motion_profile(0., 'fine')
    for t in (0., 1., 2., 3.):
        p.on_command({'kind': 'mecanum', 't': t, 'forward': .05, 'left': 0., 'turn': 0., 'duration_s': .3})
    p.loc.predict_to(8.)
    return float(np.mean(p.loc.px[:, 0]) - .6), float(abs(np.mean(p.loc.px[:, 1])))


def test_fine_profile_predicts_much_shorter_align_pulse_displacement_than_the_default():
    default, _ = _drift(False)
    fine, side = _drift(True)
    assert default > 3*fine > 0 and side < .005      # replay: ~5x (default 0.088 m vs fine 0.017 m for 4 pulses)


def test_default_selection_returns_after_the_align_window():
    p = provider()
    v6d.enable_provider(p)
    p.set_motion_profile(1., 'fine')
    assert p.loc.motion_profile == 'fine'
    p.set_motion_profile(2., None)
    assert p.loc.motion_profile is None and p.loc._motion_params() is p.loc.params['motion']


# ------------------------------------------------------------ controller phase -> profile
def test_profile_is_named_for_the_align_states_only():
    assert v6d.ALIGN_STATES == ('align', 'align_relook_stop', 'align_relook', 'align_relook_return')
    assert [v6d.profile_for(s) for s in ('approach', 'reapproach', *v6d.ALIGN_STATES, 'grasp', 'lift', 'failed')] == \
        [None, None, 'fine', 'fine', 'fine', 'fine', None, None, None]


class _Provider:
    def __init__(self):
        self.calls = []

    def set_motion_profile(self, now, name):
        self.calls.append((now, name))


class _Base:
    def set(self, state, now, **detail):
        self.states.append(state)


class _Controller(PairAlignRelook, _Base):
    def __init__(self, policy):
        self.policy, self.rid, self.states, self.events = pair_policy(policy), 'r1', [], []
        self.port = SimpleNamespace(own=SimpleNamespace(pose=_Provider(), servo={}))

    def _begin_align_relook(self, now, reason):
        self.states.append('align_relook_begin')

    def log(self, rid, kind, now, **kw):
        self.events.append((kind, kw))


def test_v6d_controller_switches_the_pf_profile_at_phase_boundaries_only():
    c = _Controller('b-v6d')
    for now, state in ((1., 'approach'), (2., 'align'), (3., 'align_relook_stop'), (4., 'align_relook'),
                       (5., 'align_relook_return'), (6., 'align'), (7., 'grasp'), (8., 'lift'), (9., 'align'),
                       (10., 'failed')):
        c.set(state, now)
    assert c.port.own.pose.calls == [(2., 'fine'), (7., None), (9., 'fine'), (10., None)]
    motion = [kw for kind, kw in c.events if kind == 'motion_profile']
    assert [m['profile'] for m in motion] == ['fine', 'default', 'fine', 'default']
    assert all('not a measurement' in m['source'] for m in motion)
    assert c.states.count('align_relook_begin') == 3 and 'grasp' in c.states


@pytest.mark.parametrize('policy', ['v5h', 'b-only', 'a+b', 'b-v6c'])
def test_other_policies_never_touch_the_pf_profile(policy):
    c = _Controller(policy)
    for now, state in ((1., 'approach'), (2., 'align'), (3., 'align_relook'), (4., 'grasp')):
        c.set(state, now)
    assert c.port.own.pose.calls == [] and c.events == []


# ------------------------------------------------------------ policy flags and wiring
def test_policy_flags_leave_the_earlier_policies_unchanged():
    for name in ('v5h', 'b-only', 'a+b', 'b-v6c'):
        assert not POLICIES[name].beam_wide_hue and not POLICIES[name].align_fine_motion
    assert POLICIES['b-v6c'] == PairPolicy('b-v6c', posterior_relook=True, exact_fix_clock=True,
                                           grasp_range_entry=True)
    d = POLICIES['b-v6d']
    assert (d.posterior_relook, d.exact_fix_clock, d.grasp_range_entry, d.beam_relative) == (True, True, True, False)
    assert d.beam_wide_hue and d.align_fine_motion
    assert REVISION_POLICIES['v6d'] == ('v5h', 'b-only', 'b-v6d')
    assert REVISION_POLICIES['v6'] == ('v5h', 'b-only', 'a+b') and REVISION_POLICIES['v6c'] == ('v5h', 'b-only', 'b-v6c')


def _team(pose, policy):
    from harness.zone_pair_executor import PairTeam
    ex = type('Ex', (), {'pose': pose})()
    return PairTeam({'r1': ex}, {}, {}, cancel_scheduled=lambda *a: None, contact_profile='cargo_noslip_v1',
                    policy=policy)


def test_team_enables_the_fine_profile_only_for_v6d():
    fresh = provider()
    team = _team(fresh, 'b-v6d')
    assert v6d.bound(fresh) and team.align_motion['r1']['origin'] == 'injected'
    assert v6c_clock.exact_clock_bound(fresh)                       # v6c parts still apply
    other = provider()
    assert _team(other, 'b-v6c').align_motion == {} and not v6d.bound(other)


def test_reused_v6d_provider_is_refused_for_the_other_policies():
    bound = provider()
    v6d.enable_provider(bound)
    for policy in ('v5h', 'b-only', 'a+b', 'b-v6c'):
        with pytest.raises(ValueError, match='fresh provider'):
            _team(bound, policy)
    _team(bound, 'b-v6d')                                         # the same policy may reuse its provider


def test_align_fine_motion_needs_the_posterior_relook_policy(monkeypatch):
    monkeypatch.setitem(POLICIES, 'bad', PairPolicy('bad', align_fine_motion=True))
    with pytest.raises(ValueError, match='posterior-relook'):
        _team(OwnCamPoseSource(V6['map'], V6['params'], seed=628), 'bad')


def test_probe_and_views_know_the_new_policy():
    from harness.pair_stage_probe import POLICIES as PROBE_POLICIES
    assert 'b-v6d' in PROBE_POLICIES and set(PROBE_POLICIES) <= set(POLICIES)
    spec = importlib.util.spec_from_file_location('views_v6d', ROOT/'scripts/build_pair_stage_probe_views.py')
    views = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(views)
    assert set(POLICIES) <= set(views.POLICY_SHORT) and len(set(views.POLICY_SHORT.values())) == len(views.POLICY_SHORT)
    assert views._pol('b-v6d') == 'D-'


def test_execution_bundle_v83_and_separate_v6h_analysis_seal():
    from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID
    from harness.zone_study_integration import RETIRED_BUNDLE_IDS
    from scripts.zone_pair_v6_contract import CURRENT_REVISION, PENDING_REVISION, HISTORICAL_REVISIONS, verify_v6_historical
    catalog = {w['id']: w for w in json.loads((ROOT/'configs/simulation_workflows.json').read_text())['workflows']}
    assert catalog['zone-study-integration-run']['version'] == '2.16.0'
    assert EXECUTION_BUNDLE_ID == 'zone-pair-v83-carry-door-gain'
    assert {'zone-pair-v76-fixclock-grasp-entry', 'zone-pair-v80-align-widehue-finemotion'} <= set(RETIRED_BUNDLE_IDS)
    assert CURRENT_REVISION == 'v6h' and PENDING_REVISION is None
    assert {'v6c', 'v6d', 'v6e'} <= set(HISTORICAL_REVISIONS)
    assert verify_v6_historical(revision='v6c')['execution_bundle_id'] == 'zone-pair-v76-fixclock-grasp-entry'
    assert verify_v6_historical(revision='v6d')['execution_bundle_id'] == 'zone-pair-v80-align-widehue-finemotion'
