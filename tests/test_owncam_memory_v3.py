"""Memory v3 failure scenarios and boundaries, without a MuJoCo import/run.

Paired tests assert the old v2 behavior explicitly before checking the v3 fix.
These synthetic inputs reproduce mechanisms, not the original seed trajectories.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import owncam_memory as v2
from harness.owncam_drive import LOOK_P20, SEARCH_POSE
from harness.owncam_memory_v3 import (OwnCamMemoryV3, BoxTrackV3, existence_update,
                                    P_ABSENT, P_KEEPOUT, SURVIVAL_HAZARD_S, MIN_HIT_INTERVAL_S)
from harness.owncam_pose_guard_v3 import (PoseGuardV3, FIX_MAX_AGE_S, FIX_MAX_TRAVEL_M,
                                        EVIDENCE_MAX_AGE_S, MIN_LOG_LIKELIHOOD, MAX_NIS)
from harness.owncam_pose_source import PoseReport


def static_map():
    return json.loads((ROOT/'maps/zones/zone_wide_door_tags_v1.json').read_text())


def params():
    return json.loads((ROOT/'experiments/2026-09-26-zone-m1-owncam/calibration_m1_dev.json').read_text())['params']


def report(t=0., x=-.47, y=-.85, sigma=.02):
    return PoseReport(t_est=t, initialized=True, x_m=x, y_m=y, yaw_rad=0.,
                      cov=tuple(map(tuple, np.diag([sigma**2/2]*2 + [.005**2]))),
                      std_xy_m=sigma, std_yaw_rad=.005, since_tag_s=0.)


def consistent(guard, now, start=None):
    start = now - .2 if start is None else start
    # Fixture for independently computed own-image likelihood + innovation.
    guard.good_times = [float(start), float(now)]


class Detector:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def __call__(self, image, servo):
        return [{'kind': k, 'range_class': r, 'estimated_box_center_base_m': [x, y, .016]}
                for k, r, x, y in self.rows]


def memory(cls=OwnCamMemoryV3, rows=()):
    return cls(static_map(), params(), robot_id='r1', detect=Detector(rows))


def feed(mem, now, *, good=True, rep=None, servo=SEARCH_POSE, loaded=False, settled=1.):
    if isinstance(mem, OwnCamMemoryV3):
        if good:
            consistent(mem.guard, now)
        else:
            mem.guard.good_times = []
    return mem.observe_frame(now, frame_id=int(now*100), image=None, servo=servo,
                             report=rep or report(now), arm_settled_s=settled, loaded=loaded)


def fix(mem, now, xy=(-.47, -.85)):
    mem.last_look_fix = {'t': now, 'xy': list(xy)}
    if isinstance(mem, OwnCamMemoryV3):
        mem.last_look_fix.update(mem.guard.stamp())
        consistent(mem.guard, now)
        mem.t = now


def controller(cls=None):
    from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3
    cls = cls or M1OwnCamDeliveryMemV3
    return cls(static_map(), params(), box_kind='cyan', slot_id='A1', slot_xy=(4.6, 0.),
               skill_factory=mock.Mock(), pose_estimate_cls=mock.Mock(), search_rows_y=(-.85, .75))


class PoseFailureTests(unittest.TestCase):
    def test_real_pose_source_consumes_pre_reset_likelihood_and_inflates_small_pf(self):
        from tests.test_owncam_localizer import synthetic_params, synthetic_detections
        from harness.owncam_pose_guard_v3 import OwnCamPoseSourceV3
        from harness.m1_owncam_memory import _RecordingDetector
        p, smap, guard = synthetic_params(), static_map(), PoseGuardV3()
        p['reset']['min_best_loglik'] = -1e9
        source = OwnCamPoseSourceV3(smap, p, guard=guard)
        rng = np.random.default_rng(17)
        servo = {**LOOK_P20, 6: 1500}
        detections = synthetic_detections(smap, (-.47, -.85, 0.), servo, rng, noise_px=0.)
        self.assertTrue(detections)
        source.detector = _RecordingDetector(SimpleNamespace(detect=lambda image: detections))
        source.on_command({'t': 0., 'kind': 'initial_servo_command', 'pulses': servo})
        source.loc.initialized = True
        source.loc.px[:] = [-.47, -.85, 0.]
        source.loc.px += rng.normal(0., .001, source.loc.px.shape)
        source.on_frame(1., None)
        source.on_frame(1.4, None)
        self.assertTrue(guard.consistent(1.4), guard.evidence)
        with mock.patch.object(source.loc, '_loglik', return_value=np.full(source.loc.n, -20.)):
            bad = source.on_frame(1.8, None)
        self.assertLess(source.last_raw_report.std_xy_m, .05)
        self.assertGreaterEqual(bad.std_xy_m, .12)
        self.assertFalse(guard.consistent(1.8))

    def test_s161_stale_fix_after_043m_is_accepted_by_v2_only(self):
        old, new = memory(v2.OwnCamMemory), memory()
        for mem in (old, new):
            fix(mem, 1.)
        consistent(new.guard, 30.)
        self.assertTrue(old.look_fix_fresh(30., (-.04, -.85)))
        self.assertFalse(new.look_fix_fresh(30., (-.04, -.85)))

    def test_time_distance_boundaries_and_future_fixes(self):
        mem = memory()
        fix(mem, 1.)
        consistent(mem.guard, 1. + FIX_MAX_AGE_S)
        self.assertTrue(mem.look_fix_fresh(1. + FIX_MAX_AGE_S, (-.47 + FIX_MAX_TRAVEL_M, -.85)))
        self.assertFalse(mem.look_fix_fresh(1. + FIX_MAX_AGE_S + 1e-5, (-.47, -.85)))
        mem = memory()
        fix(mem, 1.)
        self.assertFalse(mem.look_fix_fresh(2., (-.47 + FIX_MAX_TRAVEL_M + 1e-5, -.85)))
        mem.last_look_fix['t'] = 3.
        self.assertFalse(mem.look_fix_fresh(2., (-.47, -.85)))

    def test_round_trip_accumulates_command_distance_not_displacement(self):
        mem = memory()
        fix(mem, 0.)
        mp = {'gain': np.eye(3)}
        mem.guard.on_command({'t': 0., 'kind': 'mecanum', 'forward': .1, 'left': 0., 'turn': 0., 'duration_s': 1.}, mp)
        mem.guard.on_command({'t': 1., 'kind': 'mecanum', 'forward': -.1, 'left': 0., 'turn': 0., 'duration_s': 1.}, mp)
        consistent(mem.guard, 2.)
        self.assertFalse(mem.look_fix_fresh(2., (-.47, -.85)))
        self.assertAlmostEqual(mem.guard.command_travel_m, .2)
        mem.guard.advance(20.)  # expired command is not integrated forever
        self.assertAlmostEqual(mem.guard.command_travel_m, .2)

    def test_pose_path_accounts_for_uncommanded_estimated_shift(self):
        mem = memory()
        mem.guard.observe_pose(report(0.))
        fix(mem, 0.)
        mem.guard.observe_pose(report(.5, x=-.37))
        mem.guard.observe_pose(report(1., x=-.47))
        consistent(mem.guard, 1.)
        self.assertFalse(mem.look_fix_fresh(1., (-.47, -.85)))

    def test_sigma_inflates_on_likelihood_or_innovation_not_just_spread(self):
        for nis, ll in ((MAX_NIS + .1, -1.), (0., MIN_LOG_LIKELIHOOD - .1), (float('nan'), -1.)):
            guard = PoseGuardV3()
            consistent(guard, 0.)
            guard.observe_evidence(1., 1, nis=nis, log_likelihood=ll, settled=True)
            inflated = guard.effective_report(report(1., sigma=.01), 1.)
            self.assertGreaterEqual(inflated.std_xy_m, .12)
            self.assertGreaterEqual(inflated.std_yaw_rad, math.radians(8.))
            self.assertFalse(guard.consistent(1.))

    def test_guarded_report_is_not_inflated_twice_by_memory_consumer(self):
        guard = PoseGuardV3()
        once = guard.effective_report(report(1.), 1.)
        twice = guard.effective_report(once, 1.)
        np.testing.assert_allclose(once.cov, twice.cov)
        self.assertEqual(once.std_xy_m, twice.std_xy_m)

    def test_consistency_requires_two_new_frames_and_recovers_after_bad_frame(self):
        guard = PoseGuardV3()
        for t, frame, expected in ((1., 1, False), (1.4, 2, True)):
            guard.observe_evidence(t, frame, nis=MAX_NIS, log_likelihood=MIN_LOG_LIKELIHOOD, settled=True)
            self.assertEqual(guard.consistent(t), expected)
        with self.assertRaises(ValueError):
            guard.observe_evidence(1.5, 2, nis=0., log_likelihood=-1., settled=True)
        self.assertTrue(guard.consistent(1.4 + EVIDENCE_MAX_AGE_S))
        self.assertFalse(guard.consistent(1.4 + EVIDENCE_MAX_AGE_S + 1e-6))
        guard.observe_evidence(10., 3, nis=100., log_likelihood=-20., settled=True)
        guard.observe_evidence(10.4, 4, nis=0., log_likelihood=-1., settled=True)
        self.assertFalse(guard.consistent(10.4))
        guard.observe_evidence(10.8, 5, nis=0., log_likelihood=-1., settled=True)
        self.assertTrue(guard.consistent(10.8, since=10.1))
        self.assertFalse(guard.consistent(10.8, since=10.5))

    def test_arm_motion_does_not_erase_prior_good_evidence_or_extend_its_age(self):
        guard = PoseGuardV3()
        consistent(guard, 1.)
        guard.observe_evidence(2., 1, nis=100., log_likelihood=-20., settled=False)
        self.assertTrue(guard.consistent(2.))
        self.assertEqual(guard.good_times[-1], 1.)

    def test_one_new_fix_cannot_reuse_ancient_consistency_sample(self):
        guard = PoseGuardV3()
        consistent(guard, 1.)
        guard.observe_evidence(30., 1, nis=0., log_likelihood=-1., settled=True)
        self.assertFalse(guard.consistent(30.))

    def test_rounded_pose_clock_does_not_reject_a_current_frame(self):
        mem = memory(rows=[('cyan', 'near', .6, 0.)])
        feed(mem, .6 - 1e-15, rep=report(.6))
        self.assertEqual(len(mem.tracks), 1)

    def test_overconfident_short_dwell_stops_v2_but_not_v3(self):
        from harness.m1_owncam_memory import _LegDriverMem
        from harness.owncam_drive_mem_v3 import LegDriverMemV3
        for cls, memcls, expected in ((_LegDriverMem, v2.OwnCamMemory, 1), (LegDriverMemV3, OwnCamMemoryV3, 0)):
            mem = memory(memcls)
            fix(mem, .5, (1.4, .05))
            if memcls is OwnCamMemoryV3:
                mem.guard.observe_evidence(.6, 1, nis=0., log_likelihood=-20., settled=True)
                mem.t = 1.
            rep = report(1., x=1.4, y=.05, sigma=.01)
            est = {'initialized': True, 'x': rep.x_m, 'y': rep.y_m, 'yaw': 0., 'cov': rep.cov,
                   'std_xy_m': .01, 'std_yaw_rad': .005, 't': 1.}
            loc = SimpleNamespace(estimate=lambda: est, predict_to=lambda t: None, t=1.)
            leg = cls(mem, loc, static_map(), params(), loaded=False, goal_xy=(2.65, .05), door_xy=(2.2, .05))
            leg.state, leg.state_since, leg.look_mode = 'look_pan', 0., 'short'
            leg.look_queue, leg.arm_target, leg.servo = [970], {6: 1500}, {6: 1500}
            leg.tick(1.)
            self.assertEqual(leg.look_counts['early_stop'], expected)

    def test_arrival_always_requests_new_look_even_with_good_sigma(self):
        from harness.m1_owncam_memory import _LegDriverMem
        from harness.owncam_drive_mem_v3 import LegDriverMemV3
        for cls, memcls, state in ((_LegDriverMem, v2.OwnCamMemory, 'drive'), (LegDriverMemV3, OwnCamMemoryV3, 'look_arm')):
            mem = memory(memcls)
            fix(mem, .5, (2.65, .05))
            est = {'initialized': True, 'x': 2.65, 'y': .05, 'yaw': 0., 'cov': report().cov,
                   'std_xy_m': .02, 'std_yaw_rad': .005}
            loc = SimpleNamespace(estimate=lambda: est, predict_to=lambda t: None, t=1.)
            leg = cls(mem, loc, static_map(), params(), loaded=False, goal_xy=(2.65, .05), door_xy=(2.2, .05))
            leg.state = 'drive'
            leg._start_look(1., 'arrival_check')
            self.assertEqual(leg.state, state)
            if memcls is OwnCamMemoryV3:
                self.assertEqual(leg.verification_since, 1.)
                leg._arrive(1.1)
                self.assertNotEqual(leg.outcome, 'arrived')

    def test_arrival_retry_budget_survives_other_fix_counter_resets(self):
        ctl = controller()
        ctl._start_leg((2.65, .05), loaded=False)
        leg = ctl.leg
        for t in (1., 2., 3.):
            leg._start_look(t, 'arrival_check')
            leg.unverified_looks = 0
        self.assertEqual(leg.outcome, 'arrival_unverified')


class BoxFailureTests(unittest.TestCase):
    def test_s166_far_box_is_keepout_on_first_hit_without_false_confirmation(self):
        old, new = [memory(cls, [('red', 'far_coarse', 1.5, 0.)]) for cls in (v2.OwnCamMemory, OwnCamMemoryV3)]
        for mem in (old, new):
            feed(mem, 1.)
        self.assertEqual(old.keepouts(), [])
        keep = new.keepouts()
        self.assertEqual(len(keep), 1)
        self.assertGreater(keep[0]['half_extents_m'][0], .5)
        self.assertEqual(new.tracks[0].state, 'tentative')
        self.assertEqual(new.keepouts(exclude=[new.tracks[0].track_id]), [])

    def test_many_correlated_far_hits_keep_uncertainty_radius(self):
        mem = memory(rows=[('red', 'far_coarse', 1.5, 0.)])
        for i in range(20):
            feed(mem, 1. + i*.2)
        tr = mem.tracks[0]
        self.assertGreaterEqual(tr.sigma_m(), tr.last_detection_sigma_m - 1e-9)
        self.assertEqual(tr.state, 'tentative')
        self.assertIsNone(mem.best_target('red', 4.8))

    def test_false_confirmed_tracks_under_bad_pose_are_rejected_by_v3(self):
        for cls in (v2.OwnCamMemory, OwnCamMemoryV3):
            mem = memory(cls, [('cyan', 'near', .6, 0.)])
            for t in (1., 1.4, 1.8):
                feed(mem, t, good=False, rep=report(t, sigma=.01))
            self.assertEqual(mem.tracks[0].state, 'confirmed' if cls is v2.OwnCamMemory else 'tentative')
            if cls is OwnCamMemoryV3:
                self.assertEqual(mem.reverify(mem.tracks[0].track_id, 1.8)['status'], 'stale')
                self.assertEqual(int((mem.free_observed_at > -math.inf).sum()), 0)

    def test_new_near_observation_can_refine_far_track_and_confirm(self):
        mem = memory(rows=[('cyan', 'far_coarse', .65, 0.)])
        feed(mem, 1.)
        mem._detect.rows = [('cyan', 'near', .65, 0.)]
        for i in range(6):
            feed(mem, 1.4 + i*.4)
        self.assertEqual(len(mem.tracks), 1)
        tr = mem.tracks[0]
        self.assertEqual(tr.state, 'confirmed')
        self.assertEqual(mem.reverify(tr.track_id, 3.4)['status'], 'fresh')
        self.assertEqual(mem.reverify(tr.track_id, 3.4, since=3.5)['status'], 'stale')

    def test_existence_equation_and_probability_edges(self):
        self.assertAlmostEqual(existence_update(.5, detected=True, p_miss=.25, p_false=.1), .75/.85)
        self.assertAlmostEqual(existence_update(.5, detected=False, p_miss=.25, p_false=.1), .25/1.15)
        self.assertEqual(existence_update(0., detected=True, p_miss=.25, p_false=.1), 0.)
        self.assertEqual(existence_update(1., detected=False, p_miss=.25, p_false=.1), 1.)
        for p in (-.1, 1.1, float('nan')):
            with self.assertRaises(ValueError):
                existence_update(p, detected=True, p_miss=.25, p_false=.1)

    def test_three_misses_are_not_a_hard_absence_threshold(self):
        old, new = memory(v2.OwnCamMemory), memory()
        for mem in (old, new):
            mem._detect.rows = [('cyan', 'near', .6, 0.)]
            for t in (1., 1.4, 1.8, 2.2):
                feed(mem, t)
            if isinstance(mem, OwnCamMemoryV3):
                mem.tracks[0].existence_p = .99999
            mem._detect.rows = []
            with mock.patch.object(mem.view, 'point_in_view', return_value=True):
                for t in (2.6, 3., 3.4):
                    feed(mem, t)
        self.assertEqual(old.tracks[0].state, 'absent')
        self.assertNotEqual(new.tracks[0].state, 'absent')
        self.assertGreater(new.tracks[0].existence_p, P_ABSENT)
        with mock.patch.object(new.view, 'point_in_view', return_value=True):
            for i in range(15):
                feed(new, 3.8 + .4*i)
        self.assertEqual(new.tracks[0].state, 'absent')

    def test_hidden_far_or_uncertain_box_gets_only_survival_decay(self):
        for why in ('offscreen', 'far', 'uncertain', 'pose_bad', 'loaded'):
            mem = memory(rows=[('red', 'near', .6, 0.)])
            for t in (1., 1.4):
                feed(mem, t)
            tr = mem.tracks[0]
            mem._detect.rows = []
            if why == 'far':
                tr.x += [2., 0.]
            if why == 'uncertain':
                tr.P = np.eye(2)*.2**2
            before, misses = tr.existence_p, tr.misses
            with mock.patch.object(mem.view, 'point_in_view', return_value=why != 'offscreen'):
                feed(mem, 1.8, good=why != 'pose_bad', loaded=why == 'loaded')
            self.assertAlmostEqual(tr.existence_p, before*math.exp(-SURVIVAL_HAZARD_S*.4))
            self.assertEqual(tr.misses, misses)

    def test_full_uncertainty_support_must_be_visible_not_just_center(self):
        mem = memory(rows=[('red', 'near', .6, 0.)])
        feed(mem, 1.)
        tr = mem.tracks[0]
        mem._frame_pose_good = True
        with mock.patch.object(mem.view, 'point_in_view', side_effect=[True, False]):
            self.assertFalse(mem._visible_for_absence(tr, (-.47, -.85, 0.), np.array(report().cov), SEARCH_POSE, []))

    def test_foreground_detection_occludes_absence_evidence(self):
        mem = memory(rows=[('red', 'near', .6, 0.)])
        feed(mem, 1.)
        tr = mem.tracks[0]
        cam = mem.view.camera_world((-.47, -.85, 0.), SEARCH_POSE)[:2]
        rows = [{'map_xy': ((tr.x + cam)/2).tolist(), 'sigma_m': .02}]
        with mock.patch.object(mem.view, 'point_in_view', return_value=True):
            self.assertFalse(mem._visible_for_absence(tr, (-.47, -.85, 0.), np.array(report().cov), SEARCH_POSE, rows))

    def test_ambiguous_detection_does_not_lower_either_existence(self):
        mem = memory(rows=[('red', 'near', .6, 0.)])
        feed(mem, 1.)
        tr = mem.tracks[0]
        other = copy.deepcopy(tr)
        other.track_id = 'other'
        other.x += [.01, 0.]
        mem.tracks.append(other)
        before = [t.existence_p for t in mem.tracks]
        feed(mem, 1.4)
        self.assertEqual(mem.counts['ambiguous_detections'], 1)
        for tr, p in zip(mem.tracks, before):
            self.assertEqual(tr.misses, 0)
            self.assertAlmostEqual(tr.existence_p, p*math.exp(-SURVIVAL_HAZARD_S*.4))

    def test_duplicate_frame_or_repeated_timestamp_cannot_confirm(self):
        mem = memory(rows=[('cyan', 'near', .6, 0.)])
        feed(mem, 1.)
        with self.assertRaises(ValueError):
            feed(mem, 1.)
        feed(mem, 1.1)
        self.assertEqual(mem.tracks[0].independent_near_hits, 1)
        self.assertEqual(mem.tracks[0].state, 'tentative')

    def test_unsettled_frame_does_not_add_box_or_miss_evidence(self):
        mem = memory(rows=[('cyan', 'near', .6, 0.)])
        feed(mem, 1., settled=.1)
        self.assertEqual(mem.tracks, [])

    def test_stale_or_nonfinite_pose_cannot_add_tracks_or_free_floor(self):
        for rep in (report(0.), report(1., sigma=float('nan')), report(1., x=float('inf'))):
            mem = memory(rows=[('cyan', 'near', .6, 0.)])
            feed(mem, 1., rep=rep)
            self.assertEqual(mem.tracks, [])
            self.assertEqual(int((mem.free_observed_at > -math.inf).sum()), 0)

    def test_visible_near_miss_uses_actual_fov_and_static_wall_occlusion(self):
        mem = memory(rows=[('red', 'near', .65, 0.)])
        feed(mem, 1.)
        tr = mem.tracks[0]
        self.assertTrue(mem._visible_for_absence(tr, (-.47, -.85, 0.), np.array(report().cov), SEARCH_POSE, []))
        # No geometry mocking: the static divider blocks the opposite-side point.
        tr.x = np.array([2.4, -.85])
        self.assertFalse(mem.view.point_in_view((1.8, -.85, 0.), SEARCH_POSE, False, (*tr.x, .016)))

    def test_far_obstacle_shadow_is_not_recorded_as_free(self):
        mem = memory(rows=[('red', 'far_coarse', .65, 0.)])
        feed(mem, 1.)
        obstacle = mem.tracks[0]
        cells = np.linalg.norm(mem.view.cells - obstacle.x, axis=1) < .15
        self.assertTrue(cells.any())
        self.assertTrue(np.all(mem.free_observed_at[cells] == -math.inf))

    def test_slot_free_requires_recent_visible_evidence(self):
        old, new = memory(v2.OwnCamMemory), memory()
        for mem in (old, new):
            mem.log_odds[:] = -2.
        new.free_observed_at[:] = 1.
        self.assertEqual(old.slot_state(20., (4.6, 0.), (.06, .06))['state'], 'free')
        self.assertEqual(new.slot_state(20., (4.6, 0.), (.06, .06))['state'], 'unknown')
        new.free_observed_at[:] = 20.
        self.assertEqual(new.slot_state(20., (4.6, 0.), (.06, .06), since=19.)['state'], 'free')
        self.assertEqual(new.slot_state(20., (4.6, 0.), (.06, .06), since=21.)['state'], 'unknown')

    def test_far_keepout_overlapping_slot_is_occupied(self):
        mem = memory(rows=[('red', 'far_coarse', 1.5, 0.)])
        feed(mem, 1.)
        self.assertEqual(mem.slot_state(1., mem.tracks[0].x, (.06, .06))['state'], 'occupied')


class ControllerAndBoundaryTests(unittest.TestCase):
    def test_far_target_standoff_stays_outside_uncertainty_keepout(self):
        ctl = controller()
        ctl.memory = memory(rows=[('cyan', 'far_coarse', 1.5, 0.)])
        feed(ctl.memory, 1.)
        tr = ctl.memory.tracks[0]
        with mock.patch.object(ctl, '_start_leg') as start:
            ctl._search_decide(1.)
        goal = start.call_args.args[0]
        half = ctl.memory.keepouts()[0]['half_extents_m'][0]
        self.assertGreater(tr.x[0] - goal[0], half + ctl.params['map']['robot_clearance_m'])

    def test_abandonment_does_not_forge_absence_or_select_same_target_again(self):
        ctl = controller()
        ctl.memory = memory(rows=[('cyan', 'near', .6, 0.)])
        for t in (1., 1.4, 1.8):
            feed(ctl.memory, t)
        tr = ctl.memory.tracks[0]
        ctl.target_track_id = tr.track_id
        ctl.memory.claim(tr.track_id, 1.8)
        ctl.viewpoints = [(-.47, .75)]
        ctl.view_index = -1
        before = tr.existence_p
        with mock.patch.object(ctl, '_start_leg'):
            ctl._abandon_target(1.8, 'stale')
        self.assertEqual(tr.existence_p, before)
        self.assertNotEqual(tr.state, 'absent')
        self.assertIsNone(ctl.memory.best_target('cyan', 1.8))
        self.assertTrue(ctl.memory.keepouts())

    def test_boundary_requires_sigma_limit_and_release_evidence_even_for_free_slot(self):
        ctl = controller()
        ctl.verification['place'] = {'since': 1., 'looks': 0}
        ctl.last_obs = {'sim_time': 2.}
        fix(ctl.memory, 2.)
        ctl.memory.log_odds[:] = -2.
        ctl.memory.free_observed_at[:] = 2.
        ctl.pose.report = lambda t: report(t, sigma=.2)
        with mock.patch.object(ctl, '_gate_look', return_value=ctl._hold()):
            self.assertIsNotNone(ctl._boundary_gate(2., 'place'))
        ctl.pose.report = lambda t: report(t)
        with mock.patch.object(ctl, '_gate_look', return_value=ctl._hold()):
            # Free floor alone says nothing about the held box at release.
            self.assertIsNotNone(ctl._boundary_gate(2., 'place'))

    def test_new_far_box_invalidates_active_leg_path(self):
        ctl = controller()
        ctl.memory._detect = Detector()
        ctl._start_leg((1., -.85), loaded=False)
        leg = ctl.leg
        leg.path = [(1., -.85)]
        ctl.memory._detect.rows = [('red', 'far_coarse', 1.5, 0.)]
        feed(ctl.memory, 1.)
        # Ended driver does not move; tick still refreshes its obstacle snapshot.
        leg.outcome = 'fixture_end'
        leg.tick(1.)
        self.assertIsNone(leg.path)
        self.assertEqual(len(leg.keepouts), 1)

    def test_unknown_slot_cannot_release_and_retry_is_bounded(self):
        ctl = controller()
        ctl.last_obs = {'sim_time': 1.}
        from harness.owncam_slot_inspection_v3 import MAX_SLOT_VIEWS
        with mock.patch.object(ctl, '_start_leg') as start:
            for _ in range(MAX_SLOT_VIEWS):
                self.assertEqual(ctl._boundary_gate(1., 'place')['mode'], 'tick')
            result = ctl._boundary_gate(1., 'place')
            self.assertEqual(result['outcome'], 'SLOT_UNVERIFIED')
            self.assertTrue(result['handoff']['requires_upper_level_decision'])
            self.assertEqual(start.call_count, MAX_SLOT_VIEWS)
        self.assertEqual(ctl.skill_factory.call_count, 0)

    def test_reverify_failure_never_falls_through_to_skill_after_second_abandon(self):
        from harness.m1_owncam_memory import M1OwnCamDeliveryMem
        old, new = controller(M1OwnCamDeliveryMem), controller()
        for ctl in (old, new):
            ctl.abandoned = 1
            with mock.patch.object(ctl, '_start_skill', return_value={'unsafe': True}) as start:
                result = ctl._abandon_target(1., 'stale')
            if ctl is old:
                start.assert_called_once()
            else:
                start.assert_not_called()
                self.assertEqual(result['outcome'], 'TARGET_UNVERIFIED')

    def test_grasp_needs_new_own_evidence_even_if_old_target_is_confirmed(self):
        ctl = controller()
        ctl.memory = memory(rows=[('cyan', 'near', .6, 0.)])
        for t in (1., 1.4, 1.8):
            feed(ctl.memory, t)
        ctl.target_track_id = ctl.memory.tracks[0].track_id
        ctl.last_obs = {'sim_time': 2.}
        fix(ctl.memory, 1.8)
        ctl.pose.report = lambda t: report(t)
        with mock.patch.object(ctl, '_gate_look', return_value=ctl._hold()) as look:
            self.assertIsNotNone(ctl._boundary_gate(2., 'grasp'))
            look.assert_called_once()
        for t in (2.2, 2.6):
            feed(ctl.memory, t)
        fix(ctl.memory, 2.6)
        ctl.last_obs = {'sim_time': 2.6}
        self.assertIsNone(ctl._boundary_gate(2.6, 'grasp'))

    def test_search_blind_spot_gets_bounded_second_viewpoint_pass(self):
        from harness.m1_owncam_memory import M1OwnCamDeliveryMem
        for cls in (M1OwnCamDeliveryMem, None):
            ctl = controller(cls)
            ctl.viewpoints, ctl.view_index = [(-.47, .75)], 0
            ctl.pose.report = lambda t: report(t, x=-.47, y=.75)
            with mock.patch.object(ctl, '_start_leg') as start:
                ctl._search_decide(1.)
            if cls is not None:
                self.assertEqual(ctl.outcome, 'SEARCH_NOT_FOUND')

            else:
                self.assertTrue(ctl.blind_spot_retry)
                self.assertTrue(ctl.revisit)
                self.assertLess(start.call_args.args[0][0], -.47)
                self.assertGreater(start.call_args.args[0][0], -.92)
                ctl._search_decide(2.)
                self.assertEqual(ctl.outcome, 'SEARCH_NOT_FOUND')

    def test_blind_strip_enters_actual_camera_view_after_retreat(self):
        mem = memory()
        box = (-.2, .75, v2.BOX_CENTRE_Z_M)
        self.assertFalse(mem.view.point_in_view((-.47, .75, 0.), SEARCH_POSE, False, box))
        self.assertTrue(mem.view.point_in_view((-.92, .75, 0.), SEARCH_POSE, False, box))

    def test_peer_claims_share_reference_fields_without_fusing_own_tracks(self):
        for content in ('청록 상자가 A에 있음. 1초에 봄.', {'item': 'cyan', 'zone': 'A', 'state': 'present'}):
            mem = memory()
            row = mem.remember_peer_claim(sender='r2', observed_at=1., received_at=2., content=content)
            self.assertEqual(set(row), {'sender', 'observed_at', 'received_at', 'expires_at', 'content', 'status'})
            mem.remember_peer_claim(sender='r2', observed_at=1., received_at=10., content=content)
            self.assertEqual(len(mem.peer_claims), 1)
            self.assertEqual(mem.peer_claims[0]['received_at'], 2.)
            self.assertEqual(mem.active_peer_claims(13.), [])
            self.assertEqual(len(mem.active_peer_claims(12.99)), 1)
            self.assertEqual(mem.tracks, [])
            self.assertEqual(mem.keepouts(), [])
            self.assertEqual(mem.reverify(None, 2.)['status'], 'missing')
            row['status'] = 'confirmed'
            self.assertEqual(mem.peer_claims[0]['status'], 'unverified')
        mem = memory()
        for sender, observed in (('r1', 1.), ('r2', 3.), ('r2', float('nan'))):
            with self.assertRaises(ValueError):
                mem.remember_peer_claim(sender=sender, observed_at=observed, received_at=2., content='claim')

    def test_no_frames_stop_without_grasp(self):
        ctl = controller()
        now = 0.
        for _ in range(2200):
            result = ctl.decide(now)
            if result['mode'] == 'done':
                break
            for cmd in result.get('commands', []):
                ctl.on_command({'t': now, **cmd})
            now += .1
        self.assertEqual(ctl.outcome, 'NOT_INITIALIZED')
        ctl.skill_factory.assert_not_called()

    def test_no_mujoco_needed_even_to_import_controller(self):
        code = "import sys; sys.modules['mujoco']=None\nimport harness.m1_owncam_memory_v3\n"
        out = subprocess.run([sys.executable, '-c', code], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        forbidden = {'xpos', 'qpos', 'qvel', 'MjData', 'GtStubPoseSource', 'gt_trajectory', 'cctv_top', 'nav_cam'}
        for p in (ROOT/'harness').glob('*_v3.py'):
            if 'owncam' not in p.name:
                continue
            tree = ast.parse(p.read_text())
            names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            self.assertFalse(names & forbidden, str(p))

    def test_v2_records_preserved_with_explicit_v5h_clock_successor(self):
        record = json.loads((ROOT/'experiments/2026-09-27-zone-owncam-memory-v3/v2_preservation.json').read_text())
        # PR #240 v5h audit: last_fix/last_look_fix are control inputs, so keep
        # raw capture time. Historical v2 hashes/results remain untouched;
        # These exact successors add raw_sim_v1 identity/standalone labels,
        # without inheriting historical experiment qualification.
        successors = {
            'harness/owncam_memory.py': '7bd8caa80e035db4a17da2e68e72e5b23aff85bfbccd3e6ce347d9ecb21d2c2a',
            'scripts/run_m1_owncam_memory.py': '674d250d073bb990341826be604f95dcaefd19c8d56707d1039662af257960e5',
        }
        for name, sha in record['sha256'].items():
            self.assertIn(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),
                          {sha, successors.get(name)}, name)

    def test_runner_selects_all_versions_and_draft_is_refused_before_launch(self):
        from scripts import run_m1_owncam_memory_v3 as runner
        from harness.m1_owncam_memory import M1OwnCamDeliveryMem
        from harness.m1_owncam_memory_v3 import M1OwnCamDeliveryMemV3, M1OwnCamDeliveryOffV3
        from harness.m1_owncam_delivery import M1OwnCamDelivery
        self.assertIs(runner.controller_class('off'), M1OwnCamDeliveryOffV3)
        self.assertIs(runner.controller_class('off_legacy'), M1OwnCamDelivery)
        self.assertIs(runner.controller_class('memory_v2'), M1OwnCamDeliveryMem)
        self.assertIs(runner.controller_class('memory_v3'), M1OwnCamDeliveryMemV3)
        draft = ROOT/'experiments/2026-09-27-zone-owncam-memory-v3/prereg_DRAFT.json'
        with mock.patch.object(runner, 'run_episode') as run:
            with self.assertRaisesRegex(SystemExit, 'DRAFT'):
                runner.main(['--prereg', str(draft), '--condition', 'memory_v3', '--output', '/tmp/do-not-run-v3'])
            run.assert_not_called()
        from scripts.run_ci_tests import TEST_PATTERNS
        self.assertIn('tests/test_owncam_memory_v3.py', TEST_PATTERNS)
        from sim.workflow_manager import plan
        manifest = plan(ROOT, 'zone-m1-owncam-memory-v3-run', ['--prereg', str(draft), '--condition', 'memory_v3'])
        self.assertFalse(manifest['execution_started'])


if __name__ == '__main__':
    unittest.main()
