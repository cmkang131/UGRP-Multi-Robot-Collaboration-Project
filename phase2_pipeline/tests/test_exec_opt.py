import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import numpy as np

from harness import exec_opt as opt
from harness.render_cull_v1 import TopCardTiles
from scripts import compare_exec_opt as compare
from scripts import run_grasp_act_student as solo
from scripts import run_team_carry as team
from sim.camera_robot_port import CameraRobotPort


def parsed(*argv):
    p = argparse.ArgumentParser()
    p.add_argument('--overhead', action='store_true')
    opt.add_arguments(p)
    return opt.from_args(p, p.parse_args(argv))


class OptionsTest(unittest.TestCase):
    def test_off_no_new_keywords_or_xml_serialization(self):
        self.assertIsNone(parsed())
        xml = "<mujoco>  <!-- unmodified -->  </mujoco>"
        self.assertIs(opt.Options(wheel_deadlines=True).transform(xml), xml)
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'empty.json'
            src.write_text('{}')
            argv = ['team', '--plan', str(src), '--protocol', str(src), '--scene-source', tmp,
                    '--model', tmp, '--actor-python', 'python', '--output', tmp]
            for flags in ([], ['--wheel-deadlines', '--decision-audit', '--physics-dt-ms', '0.5']):
                with mock.patch('sys.argv', argv + flags), mock.patch.object(team, 'run_team') as run, \
                     mock.patch('scripts.run_grasp_act_recovery.dependency_modules', return_value=contextlib.nullcontext()):
                    team.main()
                kw = run.call_args.kwargs
                if flags:
                    self.assertEqual(kw['exec_options'], opt.Options(wheel_deadlines=True, physics_dt_ms=.5))
                    self.assertTrue(kw['decision_audit'])
                else:
                    self.assertNotIn('exec_options', kw)
                    self.assertNotIn('decision_audit', kw)

    def test_zero_and_unrelated_xml_fields_survive(self):
        x = parsed('--physics-dt-ms', '0.5', '--noslip-iterations', '0', '--solver-tolerance', '0',
                   '--solver-iterations', '30', '--render-offsamples', '0', '--render-segments', '12')
        root = ET.fromstring(x.transform('<mujoco><option cone="elliptic"/><visual><global offheight="960"/></visual></mujoco>'))
        self.assertEqual(root.find('option').attrib, {'timestep': '0.0005', 'iterations': '30', 'tolerance': '0.0',
                                                     'noslip_iterations': '0', 'cone': 'elliptic'})
        self.assertEqual(root.find('visual/quality').attrib, {'offsamples': '0', 'numslices': '12', 'numstacks': '12'})
        self.assertEqual(root.find('visual/global').get('offheight'), '960')
        self.assertEqual(x.settings()['noslip_iterations'], 0)
        model = NS(opt=NS(timestep=.00025), vis=NS(quality=NS()))
        with self.assertRaisesRegex(ValueError, 'compiled timestep'):
            x.compiled_settings(model)

    def test_bad_inputs(self):
        for flags in (['--physics-dt-ms', 'nan'], ['--solver-tolerance', 'inf'], ['--solver-tolerance', '-1'],
                      ['--noslip-iterations', '-1'], ['--robot-render-every', '0'], ['--overhead-every', '10'],
                      ['--verify-overhead-tiles'], ['--solver-iterations', '0'], ['--physics-until-act']):
            with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parsed(*flags)

    def test_refresh_cadence_first_frame_and_on_demand(self):
        for every in (None, 1, 2, 3):
            self.assertIsNone(opt.reused_frame_reason('door_wait', every, 1, None))
        self.assertIsNone(opt.reused_frame_reason(None, 2, 4, b'frame'))
        self.assertEqual(opt.reused_frame_reason(None, 2, 3, b'frame'), 'cadence')
        self.assertEqual(opt.reused_frame_reason('door_wait', 2, 4, b'frame'), 'door_wait')

    def test_restore_original_global_physics_once_for_every_robot(self):
        mode = parsed('--physics-dt-ms', '0.5', '--noslip-iterations', '0', '--physics-until-act')
        xml = '<mujoco><option timestep="0.00025" noslip_iterations="10"/></mujoco>'
        self.assertIs(mode.transform(xml), xml)
        world = NS(model=NS(opt=NS(timestep=.00025, noslip_iterations=10)), data=NS(time=2.))
        state = mode.start_before_act(world)
        self.assertEqual(world.model.opt.timestep, .0005)
        self.assertEqual(world.model.opt.noslip_iterations, 0)
        world.data.time = 16.2
        opt.restore_at_first_act(world)
        world.data.time += 1
        opt.restore_at_first_act(world)
        self.assertEqual(state['restore_world_s'], 16.2)
        self.assertEqual((world.model.opt.timestep, world.model.opt.noslip_iterations), (.00025, 10))


class Robot:
    def __init__(self):
        self.servo_command_pulses = {3: 1500}
        self.wheels = (0.,) * 4
        self.writes = 0
        self.arm = 1500

    def set_motor_commands(self, w):
        self.wheels = tuple(w)
        self.writes += 1

    def set_servo_pulses(self, updates):
        self.arm = updates[3]


def run_ports(fast, advance=None, steps=1):
    robots = {k: Robot() for k in ('a', 'b', 'idle')}
    world = NS(data=NS(time=0.), robot=robots.__getitem__, _exec_wheel_deadlines=fast)
    ports = [CameraRobotPort(world, k) for k in robots]
    req = [dict(port=p, robot=r, wheels=(-0., .35, -.35, 1.), deadlines=[.001, .0023, .004, .100])
           for r, p in zip(robots.values(), ports)]
    req[-1].update(wheels=None, deadlines=None)
    for p in ports:
        p.apply({'kind': 'arm', 'servo_id': 3, 'pulse': 1511}, 0.)
    ports[0]._command_expires_at = .003
    ports[1]._drive_expires_at = .0025
    trace = []

    def step(robot):
        trace.append(b''.join(struct.pack('4di', *r.wheels, r.arm) for r in robots.values()))
        if advance:
            world.data.time = advance(robots['a'].wheels)
        else:
            world.data.time += .00025

    world._physics_step_for = step
    for i in range(steps):
        solo.advance_physics(world, req, .1 * (i + 1))
    return trace, sum(r.writes for r in robots.values())


class WheelsTest(unittest.TestCase):
    def test_every_substep_matches_even_at_expiry_and_port_revocation(self):
        base, n = run_ports(False)
        fast, writes = run_ports(True)
        self.assertEqual(fast, base)
        self.assertEqual(len(base), 400)
        self.assertGreater(n, 800)
        self.assertLess(writes, 18)

    @unittest.skipUnless(importlib.util.find_spec('mujoco'), 'MuJoCo unavailable')
    def test_native_contact_world_and_compiled_quality(self):
        import mujoco
        xml = ('<mujoco><option timestep=".00025"/><worldbody><geom type="plane" size="1 1 .1"/>'
               '<body pos="0 0 .05"><freejoint/><geom size=".045"/></body></worldbody></mujoco>')
        tapes = []
        for mode in (False, True):
            model = mujoco.MjModel.from_xml_string(xml)
            data = mujoco.MjData(model)
            tape = []

            def advance(w):
                data.xfrc_applied[1, 0] = w[1]
                mujoco.mj_step(model, data)
                tape.append((data.qpos.tobytes(), data.qvel.tobytes(), data.qacc_warmstart.tobytes(), data.ncon))
                return data.time

            run_ports(mode, advance, steps=2)
            self.assertTrue(any(row[-1] for row in tape))
            tapes.append(tape)
        self.assertEqual(*tapes)
        opts = parsed('--physics-dt-ms', '0.5', '--noslip-iterations', '0', '--render-offsamples', '0', '--render-segments', '12')
        self.assertEqual(opts.compiled_settings(mujoco.MjModel.from_xml_string(opts.transform(xml)))['timestep'], .0005)


class TileTest(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('mujoco') and os.environ.get('MUJOCO_GL') in ('osmesa', 'egl'),
                         'needs headless MuJoCo')
    def test_native_frustum_pixels_and_actual_top_card_pose(self):
        import mujoco
        from harness.render_cull_v1 import install
        xml = """<mujoco><worldbody>
          <light pos="0 0 2" castshadow="false"/><camera name="top" pos="0 0 1"/>
          <camera name="far" pos="8 0 1"/><geom name="r1__tag_top" type="box" size=".1 .1 .01" rgba=".9 .1 .1 1"/>
          <geom pos="8 0 0" type="sphere" size=".2"/></worldbody></mujoco>"""
        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        mujoco.mj_forward(model, data)
        tiles = TopCardTiles(model, [('top', None), ('far', None)], ['r1'], 96, 64)
        self.assertEqual(tiles.needed(data), {'top'})
        renderer = mujoco.Renderer(model, 64, 96)
        self.addCleanup(renderer.close)
        scene_option = mujoco.MjvOption()
        renderer.update_scene(data, camera='top', scene_option=scene_option)
        full = renderer.render().copy()
        self.assertGreater(int(np.ptp(full)), 0)
        cull = install(verify=True)
        self.addCleanup(cull.uninstall)
        renderer.update_scene(data, camera='top', scene_option=scene_option)
        self.assertTrue(np.array_equal(full, renderer.render()))
        self.assertEqual((cull.compared, cull.mismatches), (1, 0))

    def test_deformed_pose_overlapping_tiles_and_fallback(self):
        xyz = np.array([[0., 0., 0.]])
        data = NS(geom_xpos=xyz, cam_xpos=np.array([[x, 0., 2.] for x in (-1., 1., 9.)]),
                  cam_xmat=np.tile(np.eye(3).ravel(), (3, 1)))
        cameras = [('a', None), ('b', None), ('c', None)]
        model = NS(geom=lambda name: NS(id=0), camera=lambda name: NS(id='abc'.index(name)), geom_rbound=np.array([.06]),
                   cam_mode=np.zeros(3), cam_sensorsize=np.zeros((3, 2)), cam_intrinsic=np.zeros((3, 4)),
                   cam_fovy=[75] * 3, light_active=np.array([]), geom_matid=np.array([-1]))
        selector = TopCardTiles(model, cameras, ['r1'], 1280, 960)
        self.assertEqual(selector.needed(data), {'a', 'b'})
        xyz[0] = [9., 0., 1.7]
        self.assertEqual(selector.needed(data), {'c'})
        model.cam_mode[0] = 2
        self.assertEqual(TopCardTiles(model, cameras, ['r1'], 1280, 960).needed(data), set('abc'))

    def test_verify_compares_real_reader_outputs_and_counts_false_positives(self):
        cams = [(c, ()) for c in 'abc']
        stats = dict(selected=0, omitted=0, checks=0, mismatches=0)
        captures = []

        def capture(name):
            captures.append(name)
            return name

        reader = NS(read=lambda pics: tuple(c for c in pics if c != 'c'))
        self.assertEqual(opt.read_tiles(cams, {'a', 'b'}, capture, reader, False, stats), ('a', 'b'))
        self.assertEqual(captures, ['a', 'b'])
        opt.read_tiles(cams, {'a', 'b'}, capture, reader, True, stats)
        with self.assertRaisesRegex(ValueError, 'poses differ'):
            opt.read_tiles(cams, {'a'}, capture, reader, True, stats)
        self.assertEqual(stats, dict(selected=5, omitted=4, checks=2, mismatches=1))


class AnalysisTest(unittest.TestCase):
    def test_rate_identical_small_and_powered_asymmetric(self):
        self.assertFalse(compare.paired_rate([(False, False)] * 8)['ok'])
        all_same = compare.paired_rate([(True, True)] * 256)
        self.assertTrue(all_same['ok'])
        self.assertAlmostEqual(all_same['ci95_pp'][1], 100 * (1 - .0125 ** (1 / 256)))
        biased = compare.paired_rate([(True, True)] * 240 + [(True, False)] * 16)
        self.assertEqual(biased['delta_pp'], -6.25)
        self.assertLess(biased['ci95_pp'][1], 0)
        self.assertFalse(biased['ok'])

    def test_unmatched_decisions_and_phases_are_in_denominator(self):
        a = {('r1', 'pick', 0): ['red'], ('r1', 'door', 0): ['go']}
        self.assertEqual(compare.compare_decisions(a, {('r1', 'pick', 0): ['blue']})['mismatches'], 2)
        t = {'r1': dict(move=1., door=2., grasp=3., place=4.)}
        r = compare.compare_durations(t, {'r1': dict(t['r1'], door=None, move=1.2)})
        self.assertFalse(r['door']['ok'])
        self.assertFalse(r['move']['ok'])
        self.assertTrue(r['grasp']['ok'])

    def test_exact_stream_checks_line_endings_and_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = (Path(tmp) / n for n in 'ab')
            row = json.dumps({'rgb': [{'sha256': 'a'}]}).encode()
            a.write_bytes((row + b'\n') * 2)
            b.write_bytes(row)
            result = compare.compare_file(a, b, 'student-inputs')
            self.assertEqual((result['byte_differences'], result['payload_differences']), (2, 1))
            self.assertEqual(result['first_different_line'], 1)

    def test_pose_gap_and_staged_plans(self):
        pose = [[0., 0., 0.], np.eye(3).ravel().tolist()]
        p = {'item': 'box', 'poses': dict.fromkeys(['base', 'box', 'finger0', 'finger1'], pose)}
        self.assertEqual(compare.pose_gap(p, p), (0., 0.))
        turned = [[.001, 0., 0.], np.diag([-1., -1., 1.]).ravel().tolist()]
        q = dict(p, poses=dict(p['poses'], finger1=turned))
        self.assertEqual(compare.pose_gap(p, q), (.001, 180.))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = {'item_id': 'box', 'robot_id': 'r1', 'spawns': {'r1': [.8, 0., 0., 0.]}, 'target_setup_xy': [0., 0.]}
            (root / 'plan.json').write_text(json.dumps(base))
            for dest in ('a', 'b'):
                compare.poses(NS(plan=root / 'plan.json', directory=root / dest, n=4))
            self.assertEqual(compare.read(root / 'a/manifest.json'), compare.read(root / 'b/manifest.json'))
            points = [compare.read(f)['spawns']['r1'] for f in sorted((root / 'a').glob('0*.json'))]
            self.assertEqual(len({tuple(pt) for pt in points}), 4)

    def test_window_interpolates_only_inside_actual_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'timeline'
            path.write_text('\n'.join(json.dumps({'sim_s': t, 'wall_s': 4 * t + 7}) for t in (1., 2., 3.)))
            self.assertAlmostEqual(compare.window(path, 1.1, 2.9)['s_per_sim_s'], 4.)
            with self.assertRaises(ValueError):
                compare.window(path, .5, 2.9)
