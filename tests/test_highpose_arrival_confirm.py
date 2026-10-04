"""v98 approach arrival confirmed by the own camera (zone_pair_highpose_arrival_confirm; simulator-free).

Record-derived (coordinator practice 2026-10-04). The frames are the recorded own frames of the DEV stage probes at
1f7fb800 (``tests/fixtures/highpose_arrival_confirm``; sha256 in the manifest, originals under outputs/):

* ``false_arrival_r1_t118p50``: r1 of ``raise_high``, the frame at which the approach declared arrival (own estimate
  0.030 m from the goal). Evaluation-only labels (never read by the module or asserted here): the true distance to
  the goal was 0.179 m, true pose (0.399, -0.049, yaw 0.071) against the pre-station (0.227, 0, 0).
* ``stop_r1_t31p30``: the same robot at its drive stop at 31.3 s, already at x = 0.41 m (0.18 m from the goal).
* ``dock_r1_t10p20`` / ``dock_r2_t10p10``: the staged TRUE docks of ``raise_high_align`` (each robot at its true
  pre-station relative to the true beam, which differs from the order sheet by the 0.05 m sheet cell).

All frames are in the drive posture 740/2320/1320/1500. The rule must reject the first two and accept the last two.
Nothing from eval_only enters the module or an assertion; the labels above are documentation.
"""
from __future__ import annotations

import hashlib
import json
import math
import types
from pathlib import Path

import cv2
import numpy as np
import pytest

from harness import zone_pair_highpose_arrival_confirm as ac
from harness.owncam_drive import SEARCH_POSE, SETTLE_S
from harness.pair_owncam_approach import ARRIVE_TOL_YAW_RAD, SHEET_XY_M, SHEET_YAW_RAD
from harness.owncam_drive import ARRIVE_TOL_M

ROOT = Path(__file__).resolve().parents[1]
FIX = Path(__file__).with_name('fixtures')/'highpose_arrival_confirm'
MANIFEST = json.loads((FIX/'manifest.json').read_text())
CALIBRATION = json.loads((ROOT/'experiments'/'2026-10-03-v92-dev-pilot'/'calibration_dev_pilot.json').read_text())
KEY = MANIFEST['posture_key']
PLAN = MANIFEST['plan']


def frame(name):
    path = FIX/MANIFEST['frames'][name]['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == MANIFEST['frames'][name]['sha256']
    return cv2.imread(str(path))


def view(rid='r1', **kw):
    return ac.ArrivalView(CALIBRATION, KEY, PLAN['prestations'][rid], PLAN, **kw)


def verdicts(av):
    return {n: av.check(frame(n)) for n in MANIFEST['frames']}


def test_fixture_is_small_and_frames_are_the_recorded_drive_posture():
    assert sum(p.stat().st_size for p in FIX.iterdir()) < 1024*1024
    for row in MANIFEST['frames'].values():
        assert {int(k): v for k, v in row['commanded_servo'].items()} == SEARCH_POSE
    raw = Path('/Users/changmin/projects/ugrp')/MANIFEST['frames']['false_arrival_r1_t118p50']['source']
    if raw.exists():                                              # primary outputs present: the source is unchanged
        assert hashlib.sha256(raw.read_bytes()).hexdigest() == MANIFEST['frames']['false_arrival_r1_t118p50']['sha256']


def test_tolerance_is_the_hand_formula_of_existing_constants():
    t = ac.tolerance()
    assert t == {'robot_xy_m': ARRIVE_TOL_M, 'robot_yaw_rad': ARRIVE_TOL_YAW_RAD,
                 'sheet_xy_m': SHEET_XY_M/2, 'sheet_yaw_rad': SHEET_YAW_RAD/2}
    assert math.isclose(t['robot_xy_m']+t['sheet_xy_m'], .08) and math.isclose(math.degrees(t['sheet_yaw_rad']), 5., abs_tol=1e-3)
    assert len(list(ac.envelope_poses((0., 0., 0.), (1., 0., 0.)))) == 3**6
    assert ac.MAX_VIEW_RETRIES == 1 and ac.CONFIRM_WAIT_S == 1. and ac.FRAME_SETTLE_S == SETTLE_S+.05


def test_bands_are_derived_from_the_measured_model_and_the_dock_geometry():
    bands = view().bands_px
    assert all(bands[k] == pytest.approx(view('r2').bands_px[k], abs=1e-6) for k in bands)   # mirror-image docks
    assert (bands['top'][0] < 106 < bands['top'][1] and bands['bottom'][0] < 326 < bands['bottom'][1]
            and bands['left'][0] < 256 and bands['right'][1] > 319)      # the recorded docks sit inside
    # the 0.3 m near end of a pose 0.17 m too close has its foot below the band (and below the valid image)
    assert bands['bottom'][1] < 450 < 460


def test_cue_is_a_physical_feature_far_from_the_near_clip():
    d = view().derivation
    assert d['poses'] == 729 and d['min_range_m'] > .3          # lens-to-beam over the whole tolerance box, >> 3 cm


def test_record_false_arrival_and_second_stop_are_rejected_and_true_docks_accepted():
    out = verdicts(view())
    assert not out['false_arrival_r1_t118p50']['ok']
    assert 'BOTTOM_OUT_OF_BAND' in out['false_arrival_r1_t118p50']['reasons']
    assert out['false_arrival_r1_t118p50']['observed']['bottom'] > 450          # the beam runs off the image bottom
    assert not out['stop_r1_t31p30']['ok'] and 'BOTTOM_OUT_OF_BAND' in out['stop_r1_t31p30']['reasons']
    assert out['dock_r1_t10p20']['ok'] and out['dock_r1_t10p20']['reasons'] == []
    assert view('r2').check(frame('dock_r2_t10p10'))['ok']


def test_margin_is_not_a_tuned_parameter_for_the_recorded_verdicts():
    for margin in (0., 1., 2.):
        av = view(margin_px=margin)
        out = verdicts(av)
        assert [out[n]['ok'] for n in ('false_arrival_r1_t118p50', 'stop_r1_t31p30', 'dock_r1_t10p20')] == [False, False, True]
        assert 'BOTTOM_OUT_OF_BAND' in out['false_arrival_r1_t118p50']['reasons']
    # the bottom edge rejects the false arrival by >= 40 px; only a margin that large would let it through
    av = view(margin_px=0.)
    over = av.bands_px['bottom'][1]
    assert out_bottom(av) - over > 40


def out_bottom(av):
    return av.check(frame('false_arrival_r1_t118p50'))['observed']['bottom']


def test_blank_frame_has_no_beam_and_is_rejected():
    r = view().check(np.zeros((480, 640, 3), np.uint8))
    assert not r['ok'] and r['reasons'] == ['BEAM_NOT_VISIBLE']


def test_unmeasured_posture_fails_closed():
    with pytest.raises(KeyError):
        ac.ArrivalView(CALIBRATION, '1,2,3,4', PLAN['prestations']['r1'], PLAN)


# ------------------------------------------------------------------ driver behaviour (stub base, real fixtures)
class Base:
    """The parts of the guarded pair approach driver the mixin touches."""

    def __init__(self):
        self.servo = dict(SEARCH_POSE)
        self.log, self.outcome, self.relocalized, self.arrived = [], None, 0, 0
        self.arrival_checked, self.rotated, self.hold_yaw = True, True, .1
        self.arrival_rechecks, self.path, self.last_look = 2, [(0., 0.)], {'fixed': True}

    def observe(self, now, rgb):
        return {}

    def on_command(self, row):
        pass

    def _event(self, now, kind, **detail):
        self.log.append((kind, detail))

    def _arrive(self, now):
        self.arrived += 1
        return [{'kind': 'arrived'}]

    def _finish(self, now, outcome):
        self.outcome = outcome
        return [{'kind': 'hold'}]

    def _relocalize(self, now):
        self.relocalized += 1
        return [{'kind': 'look'}]


Driver = ac.adopt(Base)


def driver(name='dock_r1_t10p20', *, t_obs=20., changed=10., rid='r1', configured=True):
    d = Driver()
    if configured:
        d.arrival_view = view(rid)
    d.on_command({'t': changed, 'kind': 'arm', 'servo_id': 3, 'pulse': 740})
    d.observe(t_obs, cv2.cvtColor(frame(name), cv2.COLOR_BGR2RGB))
    return d


def test_adopt_is_stable_and_keeps_the_driver_mro():
    assert ac.adopt(Base) is Driver and Driver.__mro__[1] is ac.ViewConfirmedArrival


def test_true_dock_frame_confirms_arrival():
    d = driver()
    assert d._arrive(20.2) == [{'kind': 'arrived'}] and d.arrived == 1 and d.outcome is None
    assert d.log[0][0] == 'arrival_view_confirmed' and d.log[0][1]['reasons'] == []
    assert 'not the PF' in d.log[0][1]['decided_by']


def test_false_arrival_frame_relocalizes_then_aborts_with_its_own_outcome():
    d = driver('false_arrival_r1_t118p50')
    assert d._arrive(20.2) == [{'kind': 'look'}] and d.relocalized == 1 and d.arrived == 0
    assert (d.arrival_checked, d.rotated, d.hold_yaw, d.arrival_rechecks, d.path, d.last_look) == (False, False, None, 0, None, None)
    d.observe(40., cv2.cvtColor(frame('false_arrival_r1_t118p50'), cv2.COLOR_BGR2RGB))   # approaches again, same view
    assert d._arrive(40.2) == [{'kind': 'hold'}]
    assert d.outcome == ac.OUTCOME and d.relocalized == 1 and d.arrived == 0
    assert [k for k, _ in d.log] == ['arrival_view_rejected', 'arrival_view_rejected']
    assert d.log[0][1]['rejections_before'] == 0 and d.log[1][1]['rejections_before'] == 1
    assert ac.FAILURE == 'APPROACH_ARRIVAL_NOT_CONFIRMED_BY_VIEW'


def test_approach_again_can_succeed_on_the_second_arrival():
    d = driver('false_arrival_r1_t118p50')
    d._arrive(20.2)
    d.observe(40., cv2.cvtColor(frame('dock_r1_t10p20'), cv2.COLOR_BGR2RGB))
    assert d._arrive(40.2) == [{'kind': 'arrived'}] and d.outcome is None and d.view_rejections == 1


def test_waits_for_a_settled_frame_then_fails_closed():
    d = driver(t_obs=10.3)                       # captured 0.3 s after the last arm command: not settled
    assert d._arrive(10.4) == [{'kind': 'hold'}] and not d.log
    assert d._arrive(10.4+ac.CONFIRM_WAIT_S-.1) == [{'kind': 'hold'}] and not d.log
    d._arrive(10.4+ac.CONFIRM_WAIT_S+.2)         # window over, still no settled frame: rejection (relocalize)
    assert d.log[0][0] == 'arrival_view_rejected' and d.log[0][1]['reasons'] == ['NO_SETTLED_FRAME'] and d.relocalized == 1
    d2 = driver(t_obs=10.3)
    d2.observe(10.3+ac.FRAME_SETTLE_S, cv2.cvtColor(frame('dock_r1_t10p20'), cv2.COLOR_BGR2RGB))
    assert d2._arrive(10.4+ac.FRAME_SETTLE_S) == [{'kind': 'arrived'}]


def test_base_motion_command_also_restarts_the_settle_wait():
    d = driver(changed=10.)
    d.on_command({'t': 19.9, 'kind': 'mecanum', 'forward': .05, 'left': 0., 'turn': 0.})
    assert d._arrive(20.2) == [{'kind': 'hold'}]
    d.on_command({'t': 19.95, 'kind': 'hold'})                       # a hold is not a change
    d.on_command({'t': 19.96, 'kind': 'mecanum', 'forward': 0., 'left': 0., 'turn': 0.})
    assert d._arrive(20.3) == [{'kind': 'hold'}] and not d.log


def test_wrong_posture_has_no_measured_model_and_is_never_used():
    d = driver()
    d.servo[3] = 1072                                                # arm elsewhere (look posture)
    assert d._arrive(20.2) == [{'kind': 'hold'}] and not d.log


def test_unconfigured_driver_refuses():
    with pytest.raises(RuntimeError):
        driver(configured=False)._arrive(20.)


# ------------------------------------------------------------------ mutation checks (each must flip a verdict)
def test_mutation_no_check_accepts_the_false_arrival(monkeypatch):
    monkeypatch.setattr(ac, 'decide', lambda observed, bands: {'ok': True, 'reasons': [], 'observed': observed, 'bands_px': bands})
    assert view().check(frame('false_arrival_r1_t118p50'))['ok']


def test_mutation_tolerance_three_times_wider_accepts_the_false_arrival(monkeypatch):
    base = ac.tolerance()
    monkeypatch.setattr(ac, 'tolerance', lambda: {k: 3*v for k, v in base.items()})
    assert view().check(frame('false_arrival_r1_t118p50'))['ok']


def test_mutation_huge_margin_accepts_the_false_arrival():
    assert view(margin_px=60.).check(frame('false_arrival_r1_t118p50'))['ok']


def test_mutation_missing_beam_passes(monkeypatch):
    monkeypatch.setattr(ac, 'observe_silhouette', lambda f: {'top': 106, 'bottom': 326, 'left': 256, 'right': 319})
    assert view().check(np.zeros((480, 640, 3), np.uint8))['ok']


def test_mutation_bottom_edge_dropped_leaves_only_the_top_edge(monkeypatch):
    av = view()
    av.bands_px = {**av.bands_px, 'bottom': (-1e9, 1e9)}
    r = av.check(frame('false_arrival_r1_t118p50'))
    assert r['reasons'] == ['TOP_OUT_OF_BAND']                      # the top edge alone still rejects (margin 2 px)
    av.bands_px = {**av.bands_px, 'top': (-1e9, 1e9)}
    assert av.check(frame('false_arrival_r1_t118p50'))['ok']          # both dropped: the false arrival passes


def test_mutation_no_settle_wait_uses_an_unsettled_frame(monkeypatch):
    monkeypatch.setattr(ac, 'FRAME_SETTLE_S', 0.)
    d = driver(t_obs=10.3)
    assert d._arrive(10.4) == [{'kind': 'arrived'}]                  # baseline test_waits_... holds instead


def test_mutation_unbounded_retries_never_ends(monkeypatch):
    monkeypatch.setattr(ac, 'MAX_VIEW_RETRIES', 10**6)
    d = driver('false_arrival_r1_t118p50')
    for i in range(5):
        d.observe(20.+20*i, cv2.cvtColor(frame('false_arrival_r1_t118p50'), cv2.COLOR_BGR2RGB))
        d._arrive(20.2+20*i)
    assert d.outcome is None and d.relocalized == 5


# ------------------------------------------------------------------ record + wiring
def test_own_command_restarts_the_wait_window_review_p1_1():
    # Independent review #363 P1-1 sequence: the wait opens at 10.4 s on an unsettled frame, the estimate on the
    # tolerance edge issues a small base correction at 11.0 s, the next frame (11.4 s) is not yet settled. Before the
    # fix the window of the 10.4 s hold had run out at 11.45 s and the true dock was rejected as NO_SETTLED_FRAME.
    d = driver(t_obs=10.3)
    assert d._arrive(10.4) == [{'kind': 'hold'}]
    d.on_command({'t': 11.0, 'kind': 'mecanum', 'forward': .02, 'left': 0., 'turn': 0.})
    d.observe(11.4, cv2.cvtColor(frame('dock_r1_t10p20'), cv2.COLOR_BGR2RGB))
    assert d._arrive(11.45) == [{'kind': 'hold'}] and not d.log and d.relocalized == 0
    d.observe(11.7, cv2.cvtColor(frame('dock_r1_t10p20'), cv2.COLOR_BGR2RGB))      # 0.7 s after the command: settled
    assert d._arrive(11.75) == [{'kind': 'arrived'}] and d.log[0][0] == 'arrival_view_confirmed'
    # the restarted window still fails closed when no settled frame follows
    d2 = driver(t_obs=10.3)
    d2._arrive(10.4)
    d2.on_command({'t': 11.0, 'kind': 'mecanum', 'forward': .02, 'left': 0., 'turn': 0.})
    assert d2._arrive(11.1) == [{'kind': 'hold'}]
    d2._arrive(11.1+ac.CONFIRM_WAIT_S+.05)
    assert d2.log[0][1]['reasons'] == ['NO_SETTLED_FRAME'] and d2.relocalized == 1


def test_mutation_wait_not_restarted_by_a_command_rejects_the_true_dock(monkeypatch):
    def old_on_command(self, row):                  # the pre-fix rule: the window is cleared only by a verdict
        kind = row.get('kind')
        if kind in ('arm', 'look', 'initial_servo_command') or (
                kind == 'mecanum' and any(row.get(k, 0.) != 0. for k in ('forward', 'left', 'turn'))):
            self._av_changed = float(row['t'])
        return super(ac.ViewConfirmedArrival, self).on_command(row)
    monkeypatch.setattr(ac.ViewConfirmedArrival, 'on_command', old_on_command)
    d = driver(t_obs=10.3)
    d._arrive(10.4)
    d.on_command({'t': 11.0, 'kind': 'mecanum', 'forward': .02, 'left': 0., 'turn': 0.})
    d.observe(11.4, cv2.cvtColor(frame('dock_r1_t10p20'), cv2.COLOR_BGR2RGB))
    d._arrive(11.45)
    assert d.log[0][1]['reasons'] == ['NO_SETTLED_FRAME']


def test_record_states_the_relocalization_keeps_the_belief_review_p1_2():
    r = ac.record()
    assert r['wait_restarts_on_own_command'] is True
    assert 'belief and sigma kept' in r['retry_relocalization'] and 'not a fresh localizer' in r['retry_relocalization']
    assert 'fresh localizer + wide look' not in (ac.__doc__ or '')


def test_record_entry():
    r = ac.record()
    assert r['id'] == ac.ID and r['new_threshold'] is False and r['max_view_retries'] == 1
    assert r['failure'] == 'APPROACH_ARRIVAL_NOT_CONFIRMED_BY_VIEW' and 'ground truth' in r['not_inputs']
    assert any('Chaumette' in x for x in r['references'])


def test_runtime_wiring_and_cause_label():
    src = (ROOT/'harness'/'zone_pair_highpose_runtime.py').read_text()
    assert 'arrival_confirm.adopt(type(ctl.driver))' in src and 'arrival_confirm.configure(ctl.driver, self.plan' in src
    assert "'arrival_confirm': arrival_confirm.record()" in src
    from scripts import run_pair_highpose as runner
    assert runner.failure_cause(ac.FAILURE) == {'code': ac.CAUSE, 'sub': ac.FAILURE}
    assert ac.CAUSE in runner.FAILURE_CAUSE_TEXT


@pytest.fixture(scope='module')
def admitted_runtime(tmp_path_factory):
    from tests import highpose_relook_synthetic as hs
    mp = pytest.MonkeyPatch()
    try:
        cal = hs.admitted_copy(tmp_path_factory.mktemp('arrival'), mp)
        runtime = hs.build(cal, seed=0)
        hs.run(runtime, until_s=20., stop=hs.admitted)
    finally:
        mp.undo()
    return runtime, cal


def test_real_v98_runtime_drivers_are_configured_with_the_derived_bands(admitted_runtime):
    runtime, _ = admitted_runtime
    endpoints = runtime.team.sessions[0]['endpoints']
    assert set(endpoints) == {'r1', 'r2'}
    for rid, ep in endpoints.items():
        drv = ep.controller.driver
        assert isinstance(drv, ac.ViewConfirmedArrival) and drv.arrival_view is not None
        plan = ep.plan
        expect = ac.ArrivalView(CALIBRATION, KEY, (*drv.goal, drv.goal_yaw), plan)
        assert drv.arrival_view.bands_px == expect.bands_px and drv.arrival_view.sheet == tuple(plan['sheet']['beam_xyyaw'])
        assert ac.camera_key(drv.drive_pose) == KEY
    assert runtime.own_image_gates['arrival_confirm'] == ac.record()
