"""Offline command replay of P2B-N09-S01 r9 from the door scan. No world, actor or planner service."""
import contextlib
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from harness import carry_nav_v1 as nav_module
from scripts import run_grasp_act_student as solo, run_team_carry as team


# out-r9/summary.json: list-frame point, then the measured starts recovered from log.pose_after and its pulse spec.
FAR = (3.2303529323434597, -5.917830660554822)
SCAN = (-0.572923491472707, -3.60178399733168, -1.6539375586833371)
APPROACH = (-0.5682611977389684, -3.6095089741525497, -1.737078790571779)
SWEEP = (2.3221913012002005, -5.698175284881888, -0.5467888408892473)
AFTER_SWEEP = (2.315606236432859, -5.699148558623243, -0.6235607321590253)
CLOSE = (2.55, -5.95)  # a distinct synthetic near reading for the recovery case
HOLD = {'1': 1860, '3': 1060, '4': 1850, '5': 1600, '6': 1500}


class Readings:
    """Supply detections at the actual tick windows. Three hits in the door scan, none in the incident close sweep."""
    def __init__(self, found_at):
        self.found_at = found_at
        self.obstacles, self.frames, self.hits = {}, {}, {}

    def door(self, phase):
        return None

    def observe_zone(self, jpeg, posture, colour, *, phase, close=False, **kwargs):
        if close != phase.startswith('zone_close') or colour != 'sign12':
            raise AssertionError((colour, phase, close))
        n = self.frames.get(phase, 0) + 1
        self.frames[phase] = n
        if (phase == 'zone_scan' and 28 <= n <= 30) or (phase == self.found_at and n == 1):
            self.hits[phase] = self.hits.get(phase, 0) + 1

    def zone(self, colour, phase):
        if phase in self.hits:
            x, y = FAR if phase == 'zone_scan' else CLOSE
            return {'kind': 'zone_' + colour, 'x': x, 'y': y, 'points': 30 * self.hits[phase], 'spread_m': [0., 0.]}


def replay(*, found_at=None, blocked=False, known=False, goal='zone_sign12', **nav_options):
    places = Readings(found_at)
    nav = nav_module.CarryNav(solo, places, dict(zip(('x', 'y', 'yaw'), SCAN)), [], goal, held_kind='cyan', **nav_options)
    nav._extend('arm:far')
    nav.phase = 'pass'
    if blocked:
        places.obstacles['back'] = (AFTER_SWEEP[0] - .25, AFTER_SWEEP[1] + .16)
    if known:
        nav.set_destination(FAR)

    def measured():
        # Only the planning boundaries that r9 reached. Later retry poses use the real nominal pulse lengths.
        if nav.i < len(nav.rows):
            return None
        if nav.phase == 'scan':
            pose = APPROACH
        elif nav.phase == 'zone_near' and not getattr(nav, 'zone_retries', 0):
            pose = AFTER_SWEEP if getattr(nav, 'zone_swept', False) else SWEEP
        else:
            return None
        return dict(zip(('x', 'y', 'yaw'), pose))

    nav.pose_source = measured
    commands, pwm, state = [], HOLD, {}
    for tick in range(2000):
        command = solo.carry_navigation_command(nav, b'', pwm, HOLD, state, tick / 10.)
        if command is None:  # the runner can now enter its release replay
            break
        row, source = command
        commands.append((row, source))
        pwm = row['pwm']
        if source == 'zone_unconfirmed':
            break
    else:
        raise AssertionError('carry exceeded the bounded replay')
    return nav, places, commands


class ZoneConfirmation(unittest.TestCase):
    def test_r9_default_matches_base_bytes(self):
        nav, places, commands = replay()
        self.assertEqual(places.frames, {'zone_scan': 36, 'zone_look': 22})
        self.assertEqual(places.hits, {'zone_scan': 3})
        self.assertEqual(nav.zone_seen['from_door']['points'], 90)
        self.assertIsNone(nav.zone_seen['close'])
        self.assertEqual(nav.steps[-1]['spec'], 'back:0p,left:22.28,fwd:0.631')
        self.assertEqual(nav.outcome, 'at_zone')
        # Snapshot of a96e3af with the same input: every issued command and the complete navigation record, including key order.
        data = json.dumps([commands, nav.record()], separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(hashlib.sha256(data).hexdigest(), '2f77522c3b674c062c10437619bd7f3dc03b395f8f177b0a3c25a39f5c380ccb')

    def test_close_fix_stops_the_first_close_look_0_6_m_farther(self):
        def leg(nav):
            spec = next(step for step in nav.steps if step['decision'] == 'go_to_zone')['spec']
            return float(spec.split('fwd:')[1].split(',')[0].split(')')[0])
        plain, _, _ = replay(zone_confirm_close=True)
        fixed, _, _ = replay(zone_confirm_close=True, zone_close_fix=True)
        self.assertAlmostEqual(leg(plain) - leg(fixed), 1.5 - .9, delta=.02)
        # the switch is for the close look only: without --zone-confirm-close the stop stays 0.9 m
        old, _, _ = replay(zone_close_fix=True)
        default, _, _ = replay()
        self.assertEqual(leg(old), leg(default))

    def test_close_far_stops_the_first_close_look_at_2_3_m(self):
        def leg(nav):
            spec = next(step for step in nav.steps if step['decision'] == 'go_to_zone')['spec']
            return float(spec.split('fwd:')[1].split(',')[0].split(')')[0])
        plain, _, _ = replay(zone_confirm_close=True)
        far, _, _ = replay(zone_confirm_close=True, zone_close_fix=True, zone_close_far=True)
        self.assertAlmostEqual(leg(plain) - leg(far), 2.3 - .9, delta=.02)
        near, _, _ = replay(zone_confirm_close=True, zone_close_far=True)       # without --zone-close-fix the switch does nothing
        self.assertEqual(leg(near), leg(plain))

    def test_r9_exhausts_backoffs_and_ends_on_a_closed_grip_stop(self):
        nav, places, commands = replay(zone_confirm_close=True)
        self.assertEqual(places.frames, {'zone_scan': 36, 'zone_close': 22, 'zone_close_1': 22, 'zone_close_2': 22})
        self.assertEqual(places.hits, {'zone_scan': 3})
        self.assertEqual(nav.zone_seen['from_door']['points'], 90)
        self.assertIsNone(nav.zone_seen['close'])
        self.assertEqual(nav.steps[-1], {'decision': 'zone_unconfirmed', 'reason': 'retry_limit', 'retries': 2})
        self.assertEqual((nav.finished, nav.outcome), (True, 'zone_unconfirmed'))
        self.assertNotIn('zone_final', [segment['phase'] for segment in nav.log])
        self.assertNotIn('set_down_in_zone', [step['decision'] for step in nav.steps])
        for retry in nav.log[-2:]:
            self.assertTrue(retry['spec'].startswith('back:'))
            self.assertNotIn('fwd:', retry['spec'])
        self.assertEqual(commands[-1][1], 'zone_unconfirmed')
        self.assertEqual(commands[-1][0]['wheels'], [0.] * 4)
        self.assertEqual(commands[-1][0]['pwm'], commands[-2][0]['pwm'])
        self.assertTrue(all(row['pwm']['1'] == HOLD['1'] for row, _ in commands))

    def test_only_a_close_fix_drives_the_final_leg(self):
        for attempt, window in enumerate(('zone_close', 'zone_close_1', 'zone_close_2')):
            with self.subTest(window=window):
                nav, _, commands = replay(zone_confirm_close=True, found_at=window)
                self.assertEqual(nav.zone_retries, attempt)
                self.assertEqual(nav.outcome, 'at_zone')
                self.assertEqual(nav.steps[-1]['zone'], nav.zone_seen['close'])
                self.assertEqual((nav.zone_seen['close']['x'], nav.zone_seen['close']['y']), CLOSE)
                self.assertEqual(commands[-1][1], 'carry_code')

    def test_a_blocked_reverse_and_an_arena_hint_cannot_authorize_release(self):
        nav, _, commands = replay(zone_confirm_close=True, known=True, blocked=True)
        self.assertEqual(nav.steps[-1]['reason'], 'backoff_blocked')
        self.assertEqual(nav.zone_retries, 0)
        self.assertIsNone(nav.zone_seen['close'])
        self.assertEqual(commands[-1][1], 'zone_unconfirmed')

    def test_planner_named_zone_uses_the_same_confirmation(self):
        remote = team.RemoteBrain('offline')
        fixed = team.FixedPlan({'r9': ('blue', 'sign12')}, ['r9'])
        with mock.patch.object(team, 'ZONES', ('sign11', 'sign12', 'sign13')), \
                mock.patch.object(remote, '_post', return_value={'option': 'zone:sign12'}):
            for planner in (fixed, remote):
                with self.subTest(planner=type(planner).__name__):
                    _, destination, _, state = team.hooks('r9', planner, lambda: 0., [])
                    state['picked'] = 'blue'
                    carry = {}
                    solo.accept_planner_destination(carry, destination(), 0.)
                    nav, _, commands = replay(zone_confirm_close=True, goal=carry['rule'])
                    self.assertEqual(nav.goal, 'zone_sign12')
                    self.assertEqual(commands[-1][1], 'zone_unconfirmed')
                    self.assertIn('still in my gripper', team.carry_end_report(nav.outcome, nav.goal))
                    self.assertEqual(team.carry_end_option_text(nav.outcome), 'finish my run')

    def test_both_cli_entry_points_pass_the_switch_only_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'empty.json'
            src.write_text('{}')
            argv = ['test', '--plan', str(src), '--protocol', str(src), '--model', tmp, '--output', tmp, '--actor-python', 'unused']
            for module, entry, args in ((team, 'run_team', ['--scene-source', tmp]), (solo, 'run', [])):
                for enabled in (False, True):
                    with self.subTest(module=module.__name__, enabled=enabled), mock.patch.object(module, entry) as run, \
                            mock.patch.object(sys, 'argv', argv + args + (['--zone-confirm-close'] if enabled else [])), \
                            mock.patch('scripts.run_grasp_act_recovery.dependency_modules', return_value=contextlib.nullcontext()):
                        module.main()
                        self.assertIs(run.call_args.kwargs.get('zone_confirm_close'), True if enabled else None)


try:
    import cv2
except ImportError:
    cv2 = None


@unittest.skipIf(cv2 is None, 'close sign projection needs OpenCV')
class CloseSignReadings(unittest.TestCase):
    def test_id_whole_card_range_and_projection_filter_the_close_points(self):
        import numpy as np
        from harness import place_memory_v1 as pm, robot_tags_v1 as tags

        # Rectified camera at 0.30 m, facing +x. Provide decoded quadrilaterals; use the real floor projection.
        K = np.array([[350., 0., 320.], [0., 350., 240.], [0., 0., 1.]])
        axes = np.array([[0., -1., 0.], [0., 0., -1.], [1., 0., 0.]])
        places = pm.PlaceMemory(SimpleNamespace(K=K, camera_extrinsics=lambda pwm: (np.array([0., 0., .30]), axes)))
        places._tags, places._tag_reader = tags, mock.Mock()
        for name, number, distance, cx, cy in [('wrong_id', 13, 1.2, 320, None), ('border_cut', 12, 1.2, 609, None),
                                               ('too_far', 12, 3.7, 320, None), ('bad_ray', 12, 1.2, 320, 100),
                                               ('valid', 12, 1.2, 320, None)]:
            with self.subTest(name=name):
                half = 350 * tags.SIGN_MARKER_M / (2 * distance)
                cy = 240 + 350 * (.30 - tags.SIGN_CENTRE_Z) / distance if cy is None else cy
                quad = [[cx-half, cy-half], [cx+half, cy-half], [cx+half, cy+half], [cx-half, cy+half]]
                places._tag_reader.read.return_value = [{'sign': number, 'corners_px': quad}]
                places.observe_zone(b'', {}, 'sign12', phase=name, close=True)
                fix = places.zone('sign12', phase=name)
                if name == 'valid':
                    self.assertAlmostEqual(fix['x'], distance - pm.SIGN_BOX_M)
                    self.assertAlmostEqual(fix['y'], 0.)
                else:
                    self.assertIsNone(fix)
