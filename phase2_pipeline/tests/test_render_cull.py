"""Tests of the speed switches --render-cull / --render-cull-verify / --wall-cap-s (all default off). No simulator, no mujoco, no network.

  * harness/render_cull_v1: camera_tans (sensor size, principal point offset, fovy fallback), outside_frustum (no sphere that touches the true view
    frustum is ever culled, for random cameras and both signs of the principal point offset; far outside / behind is culled; an offset widens the
    kept set), cullable (planes, height fields, radius 0 are never culled), guard_problem (shadow-casting light, reflective material);
  * RenderCull on a fake mujoco module: what is drawn while the scene is built, geom_group put back, fail-closed guards, pass-through cases
    (free camera, camera object, no hidable group), verify mode (equal pictures / different pictures), install / uninstall;
  * run_team_carry.main: with the switches off nothing is patched and run_team gets no extra argument (byte-identical call); with them on the
    patch is installed, render-cull.json is written, a verify mismatch ends with exit code 3; run_steps' wall cap (default 14400 / 1800, or the given one).
Run:  python3 -B -m unittest discover -s tests -p 'test_render_cull.py' -v   (in the worktree root)"""
import sys
sys.dont_write_bytecode = True

import contextlib
import importlib.util
import json
import math
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import scripts.run_grasp_act_student as SOLO  # noqa: E402
import scripts.run_team_carry as TEAM  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


RC = load(ROOT / 'harness' / 'render_cull_v1.py', 'render_cull_v1_test')


def random_rotation(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


class Tans(unittest.TestCase):
    def test_sensor_size_and_offset(self):
        tx, ty = RC.camera_tans((4.0, 3.0), (3.0, 3.0, 0.5, -0.2), 45., 640, 480)
        self.assertAlmostEqual(tx, (2.0 + 0.5) / 3.0 * 1.02)
        self.assertAlmostEqual(ty, (1.5 + 0.2) / 3.0 * 1.02)

    def test_offset_sign_does_not_matter(self):
        self.assertEqual(RC.camera_tans((4., 3.), (3., 3., 0.5, -0.2), 45., 640, 480), RC.camera_tans((4., 3.), (3., 3., -0.5, 0.2), 45., 640, 480))

    def test_fovy_fallback_uses_picture_aspect(self):
        tx, ty = RC.camera_tans((0., 0.), (0., 0., 0., 0.), 90., 640, 480)
        self.assertAlmostEqual(ty, 1.02)
        self.assertAlmostEqual(tx, 1.02 * 640 / 480)


class Frustum(unittest.TestCase):
    CAM = np.zeros(3)
    EYE = np.eye(3)           # looks along -z, x right, y up

    def out(self, points, rbound, tx, ty, cam=None, mat=None):
        return RC.outside_frustum(np.atleast_2d(points), np.atleast_1d(rbound), self.CAM if cam is None else cam, self.EYE if mat is None else mat, tx, ty)

    def test_straight_ahead_kept_sides_and_behind_culled(self):
        pts = [(0, 0, -2), (5, 0, -2), (-5, 0, -2), (0, 5, -2), (0, -5, -2), (0, 0, 2), (0.5, 0.2, -1)]
        self.assertEqual(self.out(pts, [0.1] * 7, 1., 1.).tolist(), [False, True, True, True, True, True, False])

    def test_sphere_touching_the_side_plane_is_kept(self):
        # tan 1 at depth 2: the plane passes x = 2; a sphere of radius 0.5 centred at x = 2.4 still touches it (distance 0.4 * cos45 = 0.28 < 0.5)
        self.assertFalse(self.out((2.4, 0, -2), 0.5, 1., 1.)[0])
        self.assertTrue(self.out((3.5, 0, -2), 0.5, 1., 1.)[0])

    def test_sphere_around_the_camera_is_kept(self):
        self.assertFalse(self.out((0, 0, 0.3), 0.5, 1., 1.)[0])      # camera inside the sphere
        self.assertTrue(self.out((0, 0, 0.6), 0.5, 1., 1.)[0])       # wholly behind the camera plane

    def test_camera_pose_is_used(self):
        mat = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])      # camera x axis = world y, camera y axis = -world x ... looks along -world z
        cam = np.array([1., 2., 3.])
        self.assertFalse(self.out(cam + [0., 0., -2.], 0.1, 1., 1., cam, mat)[0])
        self.assertTrue(self.out(cam + [0., 0., 2.], 0.1, 1., 1., cam, mat)[0])
        self.assertTrue(self.out(cam + [9., 0., -2.], 0.1, 1., 1., cam, mat)[0])

    def test_offset_widens_the_kept_set(self):
        # a sensor 4 x 3 with focal 3: without an offset the half view tangent is 2/3 (x); at depth 3 a sphere at x = 2.6 is outside, with an
        # offset of 1 (tan 1) the widest side reaches x = 3
        no_offset = RC.camera_tans((4., 3.), (3., 3., 0., 0.), 45., 640, 480)
        offset = RC.camera_tans((4., 3.), (3., 3., 1., 0.), 45., 640, 480)
        p = (2.6, 0., -3.)
        self.assertTrue(self.out(p, 0.05, *no_offset)[0])
        self.assertFalse(self.out(p, 0.05, *offset)[0])

    def test_never_culls_anything_that_touches_the_true_frustum(self):
        """Random cameras (orientation, sensor, focal, principal point offset of both signs), random spheres: a sphere that has one point inside
        the true (asymmetric) pinhole frustum  (-ss/2+o)/f <= x/depth <= (ss/2+o)/f  is never culled."""
        rng = np.random.default_rng(7)
        for trial in range(200):
            ss = rng.uniform(1., 6., 2)
            f = rng.uniform(1., 6., 2)
            o = rng.uniform(-1.5, 1.5, 2) * rng.choice([0., 0.3, 1.])
            tx, ty = RC.camera_tans(ss, (f[0], f[1], o[0], o[1]), 60., 640, 480)
            mat, cam = random_rotation(rng), rng.uniform(-3, 3, 3)
            lo, hi = (-ss / 2 + o) / f, (ss / 2 + o) / f                  # the true tangent range per axis
            span = hi - lo
            n = 3000
            depth = rng.uniform(0.05, 10., n)
            t = rng.uniform(lo - 0.5 * span, hi + 0.5 * span, (n, 2))      # tangent space: about a quarter of the points is inside
            inside = ((t >= lo) & (t <= hi)).all(1)
            local = np.column_stack([t[:, 0] * depth, t[:, 1] * depth, -depth])
            self.assertGreater(inside.sum(), 200)
            world = cam + local @ mat.T
            # spheres that touch the frustum: centre = the inside point + a random vector shorter than the radius
            radius = rng.uniform(0., 1.5, n)
            shift = rng.normal(size=world.shape)
            shift *= (radius * rng.uniform(0, 1, n) / np.linalg.norm(shift, axis=1))[:, None]
            culled = RC.outside_frustum(world + shift, radius, cam, mat, tx, ty)
            self.assertFalse(culled[inside].any(), 'trial %d culled a sphere that touches the frustum' % trial)
            # the test is not vacuous: points far outside the symmetric bound (and a sphere wholly behind the camera) are culled
            tf = rng.choice([-1., 1.], (n, 2)) * (rng.uniform(1.5, 3., (n, 2)) * [tx, ty] + 0.1)
            far_depth = rng.uniform(1., 10., n)
            far = np.column_stack([tf[:, 0] * far_depth, tf[:, 1] * far_depth, -far_depth])
            self.assertTrue(RC.outside_frustum(cam + far @ mat.T, np.zeros(n), cam, mat, tx, ty).all())
            self.assertTrue(RC.outside_frustum(cam + np.column_stack([t[:, 0], t[:, 1], depth]) @ mat.T, np.zeros(n), cam, mat, tx, ty).all())

    def test_cullable_never_planes_hfields_or_unbounded(self):
        types_ = np.array([0, 1, 2, 5, 6, 7])
        rbound = np.array([0., 0., 1., 1., 0., 1.])
        self.assertEqual(RC.cullable(types_, rbound).tolist(), [False, False, True, True, False, True])
        # a plane or height field with a (nonzero) bound is excluded too
        self.assertEqual(RC.cullable(np.array([0, 1, 3]), np.array([5., 5., 5.])).tolist(), [False, False, True])


class FakeModel:
    def __init__(self, xpos, rbound, gtype, ncam=2, castshadow=(0,), active=(1,), mat_reflectance=(0.,), geom_matid=None):
        n = len(xpos)
        self.ngeom, self.ncam = n, ncam
        self.geom_rbound, self.geom_type = np.array(rbound, float), np.array(gtype)
        self.geom_group = np.full(n, 1, np.int32)
        self.geom_matid = np.full(n, -1) if geom_matid is None else np.array(geom_matid)
        self.cam_mode = np.zeros(ncam, int)
        self.cam_sensorsize = np.array([[4., 3.]] * ncam)
        self.cam_intrinsic = np.array([[3., 3., 0., 0.]] * ncam)
        self.cam_fovy = np.full(ncam, 45.)
        self.light_castshadow, self.light_active = np.array(castshadow), np.array(active)
        self.mat_reflectance = np.array(mat_reflectance)
        self.nlight = len(castshadow)


class FakeData:
    def __init__(self, xpos, cam_xpos, cam_xmat):
        self.geom_xpos, self.cam_xpos, self.cam_xmat = np.array(xpos, float), np.array(cam_xpos, float), np.array(cam_xmat, float)


class FakeOption:
    def __init__(self, groups=(1, 1, 1, 0, 0, 0)):
        self.geomgroup = np.array(groups, np.uint8)


def fake_mujoco(picture):
    """A stand-in for the mujoco module: Renderer.update_scene builds the list of drawn geoms (geom group enabled in the option), render() returns
    picture(renderer) (a function of the drawn geoms)."""
    class Renderer:
        def __init__(self, model, height, width):
            self._model, self.height, self.width = model, height, width
            self._scene_option = FakeOption()
            self.scene = types.SimpleNamespace(ngeom=0)
            self.drawn_log = []

        def update_scene(self, data, camera=-1, scene_option=None):
            option = scene_option or self._scene_option
            drawn = [i for i in range(self._model.ngeom) if option.geomgroup[int(self._model.geom_group[i])]]
            self.drawn, self.scene.ngeom = drawn, len(drawn)
            self.drawn_log.append(list(drawn))

        def render(self, *, out=None):
            return picture(self)

    names = {'cam_a': 0, 'cam_b': 1}
    return types.SimpleNamespace(Renderer=Renderer, mjtGeom=types.SimpleNamespace(mjGEOM_PLANE=0, mjGEOM_HFIELD=1),
                                 mjtObj=types.SimpleNamespace(mjOBJ_CAMERA=7), mj_name2id=lambda m, kind, name: names.get(name, -1))


# the scene of the fake model: a camera at the origin looking along -z (tan 0.667 * 1.02), geoms:
#   0 ahead (kept), 1 far left (culled), 2 behind (culled), 3 plane far left (never culled), 4 radius 0 far left (never culled), 5 big sphere far left that reaches in (kept)
XPOS = [(0, 0, -3), (-30, 0, -3), (0, 0, 5), (-30, 0, -3), (-30, 0, -3), (-5, 0, -3), (0, 40, -3)]
RBOUND = [0.2, 0.2, 0.2, 5., 0., 4., 0.1]
GTYPE = [2, 2, 2, 0, 2, 2, 6]
EXPECT_HIDDEN = [1, 2, 6]


def make_world(**model_kw):
    model = FakeModel(XPOS, RBOUND, GTYPE, **model_kw)
    data = FakeData(XPOS, [(0, 0, 0), (0, 0, 0)], [np.eye(3).ravel()] * 2)
    return model, data


def inside_picture(renderer):
    """A picture that depends only on the geoms inside the view frustum of camera 'cam_a' (what a real render without shadows / reflections does)."""
    drawn = np.zeros((4, 4), np.int64)
    for i in renderer.drawn:
        if i in (0, 5):
            drawn[i % 4, 0] += i + 1
    return drawn


def global_picture(renderer):
    """A picture that depends on every drawn geom (like a shadow would): culling must change it."""
    return np.full((4, 4), len(renderer.drawn), np.int64)


class Controller(unittest.TestCase):
    def setUp(self):
        self.addCleanup(self.cleanup)
        self.live = []

    def cleanup(self):
        for c in self.live:
            c.uninstall()

    def make(self, picture=inside_picture, verify=False, **model_kw):
        mj = fake_mujoco(picture)
        self.mj = mj
        model, data = make_world(**model_kw)
        cull = RC.RenderCull(mj, verify)
        self.live.append(cull)
        cull.install()
        return cull, mj.Renderer(model, 480, 640), model, data

    def test_off_is_untouched_until_install(self):
        mj = fake_mujoco(inside_picture)
        original = (mj.Renderer.update_scene, mj.Renderer.render)
        cull = RC.RenderCull(mj)
        self.assertEqual((mj.Renderer.update_scene, mj.Renderer.render), original)
        cull.install()
        self.live.append(cull)
        self.assertNotEqual(mj.Renderer.update_scene, original[0])
        cull.uninstall()
        self.assertEqual((mj.Renderer.update_scene, mj.Renderer.render), original)
        with self.assertRaises(RuntimeError):
            cull.install().install()

    def test_hides_outside_geoms_while_the_scene_is_built_and_restores_the_groups(self):
        cull, renderer, model, data = self.make()
        before = model.geom_group.copy()
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(renderer.drawn, [i for i in range(len(XPOS)) if i not in EXPECT_HIDDEN])
        self.assertTrue((model.geom_group == before).all())
        r = cull.report()
        self.assertEqual(r['by_size']['640x480']['culled'], 1)
        self.assertEqual(r['by_size']['640x480']['geoms_kept_sum'], len(XPOS) - len(EXPECT_HIDDEN))
        self.assertEqual(r['by_size']['640x480']['geoms_full_sum'], len(XPOS))
        self.assertTrue(r['models'][0]['geom_group_restored'])
        self.assertIsNone(r['models'][0]['reason'])

    def test_picture_equal_with_and_without_the_cull(self):
        cull, renderer, model, data = self.make()
        renderer.update_scene(data, camera=0)
        culled = renderer.render()
        cull.uninstall()
        renderer.update_scene(data, camera=0)
        self.assertEqual(renderer.drawn, list(range(len(XPOS))))
        self.assertTrue((renderer.render() == culled).all())

    def test_groups_restored_when_the_scene_build_fails(self):
        cull, renderer, model, data = self.make()
        before = model.geom_group.copy()
        with mock.patch.object(cull, '_orig_update', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                renderer.update_scene(data, camera='cam_a')
        self.assertTrue((model.geom_group == before).all())

    def test_hide_group_follows_the_scene_option(self):
        cull, renderer, model, data = self.make()
        renderer._scene_option = FakeOption((1, 1, 1, 0, 0, 1))      # group 5 drawn: park in 4
        model.geom_group[:] = 1
        seen = []
        orig = cull._orig_update

        def spy(r, *a, **k):
            seen.append(sorted(set(int(g) for g in r._model.geom_group)))
            return orig(r, *a, **k)
        cull._orig_update = spy
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(seen, [[1, 4]])
        renderer._scene_option = FakeOption((1, 1, 1, 1, 1, 1))     # nothing hidable: pass through
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(renderer.drawn, list(range(len(XPOS))))
        self.assertEqual(cull.report()['by_size']['640x480']['passthrough'], 1)

    def test_pass_through_cases(self):
        cull, renderer, model, data = self.make()
        every = list(range(len(XPOS)))
        for camera in (-1, 'no_such_camera', object(), True):
            renderer.update_scene(data, camera=camera)
            self.assertEqual(renderer.drawn, every, camera)
        model.cam_mode[0] = 1                                         # not a fixed camera
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(renderer.drawn, every)
        self.assertEqual(cull.report()['by_size']['640x480']['culled'], 0)

    def test_scene_option_argument_is_honoured(self):
        cull, renderer, model, data = self.make()
        renderer.update_scene(data, 'cam_a', FakeOption((1, 1, 1, 1, 1, 1)))
        self.assertEqual(renderer.drawn, list(range(len(XPOS))))
        renderer.update_scene(data, camera='cam_a', scene_option=FakeOption())
        self.assertEqual(renderer.drawn, [i for i in range(len(XPOS)) if i not in EXPECT_HIDDEN])

    def test_fail_closed_on_shadow_or_reflection(self):
        every = list(range(len(XPOS)))
        cull, renderer, model, data = self.make(castshadow=(1,), active=(1,))
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(renderer.drawn, every)
        self.assertIn('shadow', cull.report()['models'][0]['reason'])
        cull, renderer, model, data = self.make(castshadow=(1,), active=(0,))        # an inactive light is no shadow
        cull.uninstall()
        cull, renderer, model, data = self.make(mat_reflectance=(0.3,), geom_matid=[0] * len(XPOS))
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(renderer.drawn, every)
        self.assertIn('reflective', cull.report()['models'][0]['reason'])
        cull.uninstall()
        cull, renderer, model, data = self.make(mat_reflectance=(0.3, 0.0), geom_matid=[1] * len(XPOS))     # the reflective material is used by no geom
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(renderer.drawn, [i for i in range(len(XPOS)) if i not in EXPECT_HIDDEN])

    def test_verify_equal_pictures(self):
        cull, renderer, model, data = self.make(verify=True)
        for camera in ('cam_a', 'cam_b'):
            renderer.update_scene(data, camera=camera)
            renderer.render()
        r = cull.report()
        self.assertEqual((r['verify_compared'], r['verify_mismatched']), (2, 0))
        self.assertEqual(cull.mismatches, 0)
        self.assertEqual(renderer.drawn, [i for i in range(len(XPOS)) if i not in EXPECT_HIDDEN])     # the caller's picture is the culled one
        self.assertNotIn('_render_cull_full', renderer.__dict__)

    def test_verify_counts_a_difference(self):
        cull, renderer, model, data = self.make(picture=global_picture, verify=True)
        with contextlib.redirect_stderr(__import__('io').StringIO()) as err:
            renderer.update_scene(data, camera='cam_a')
            picture = renderer.render()
        self.assertEqual(int(picture[0, 0]), len(XPOS) - len(EXPECT_HIDDEN))     # still the culled picture (verify never changes the result)
        r = cull.report()
        self.assertEqual((r['verify_compared'], r['verify_mismatched']), (1, 1))
        self.assertEqual(r['mismatch_notes'][0]['pixels_differing'], 16)
        self.assertIn('RENDER_CULL_MISMATCH', err.getvalue())

    def test_without_verify_no_second_render(self):
        cull, renderer, model, data = self.make()
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(len(renderer.drawn_log), 1)
        cull2 = RC.RenderCull(self.mj, verify=True)
        cull.uninstall()
        cull2.install()
        self.live.append(cull2)
        renderer.drawn_log.clear()
        renderer.update_scene(data, camera='cam_a')
        self.assertEqual(len(renderer.drawn_log), 2)        # full scene first, then the culled one
        self.assertEqual(renderer.drawn_log[0], list(range(len(XPOS))))


class WallCap(unittest.TestCase):
    def test_default_and_given(self):
        self.assertEqual(SOLO.rollout_wall_cap_s(None, True), 14400)
        self.assertEqual(SOLO.rollout_wall_cap_s(None, False), 1800)
        self.assertEqual(SOLO.rollout_wall_cap_s(43200., True), 43200.)
        self.assertEqual(SOLO.rollout_wall_cap_s(43200., False), 43200.)

    def test_run_steps_signature(self):
        import inspect
        self.assertIsNone(inspect.signature(SOLO.run_steps).parameters['wall_cap_s'].default)


class MainWiring(unittest.TestCase):
    """run_team_carry.main with run_team and dependency_modules replaced: which arguments run_team gets and what is patched."""

    def run_main(self, *flags, cull=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ('plan.json', 'protocol.json'):
                (tmp / name).write_text('{}')
            out = tmp / 'out'
            calls = {}

            def fake_run_team(plan, protocol, model, output, **kw):
                calls['kw'] = kw
                Path(output).mkdir(parents=True)

            argv = ['run_team_carry.py', '--plan', str(tmp / 'plan.json'), '--protocol', str(tmp / 'protocol.json'), '--model', str(tmp / 'm'),
                    '--output', str(out), '--actor-python', 'py', '--scene-source', str(tmp), *flags]
            lazy = mock.MagicMock()
            if cull is not None:
                lazy.install.return_value = cull
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(TEAM, 'run_team', fake_run_team), \
                    mock.patch.object(TEAM, 'render_cull_v1', lazy), \
                    mock.patch('scripts.run_grasp_act_recovery.dependency_modules', lambda root: contextlib.nullcontext()):
                try:
                    TEAM.main()
                    code = None
                except SystemExit as e:
                    code = e.code
            report = json.loads((out / 'render-cull.json').read_text()) if (out / 'render-cull.json').exists() else None
            return calls.get('kw'), lazy, report, code

    def test_off_is_byte_identical(self):
        kw, lazy, report, code = self.run_main()
        self.assertNotIn('wall_cap_s', kw)
        self.assertEqual(lazy.mock_calls, [])
        self.assertIsNone(report)
        self.assertIsNone(code)
        # the same argument names as before this change
        self.assertEqual(sorted(kw), sorted(['brain', 'orders', 'knows', 'second_item', 'scene', 'scene_without', 'actor_python', 'cap_s', 'n_action_steps',
                                             'actor_threads', 'teacher_start_v1', 'grasp_transition_rule', 'approach_survey_v1', 'robot_tags',
                                             'truth_every', 'regrasp_max', 'overhead', 'redecide_destination', 'listen_unit_s', 'full_info',
                                             'multi_carry', 'llm_moves', 'aside_mode', 'held_edge_fix', 'look_around', 'fail_robot', 'fail_at_s',
                                             'stop_failed_body']))

    def test_lazy_loader_does_not_read_the_file_until_used(self):
        self.assertIsNone(TEAM._LazyRenderCull._module)

    def test_wall_cap_is_passed_only_when_given(self):
        kw, _, _, _ = self.run_main('--wall-cap-s', '43200')
        self.assertEqual(kw['wall_cap_s'], 43200.)
        with contextlib.redirect_stderr(__import__('io').StringIO()):
            kw, _, _, code = self.run_main('--wall-cap-s', '0')
        self.assertEqual((kw, code), (None, 2))      # argparse error: the run never starts

    def test_render_cull_installs_and_reports(self):
        cull = mock.MagicMock(mismatches=0)
        cull.report.return_value = {'schema': 'render_cull_v1', 'x': 1}
        kw, lazy, report, code = self.run_main('--render-cull', cull=cull)
        lazy.install.assert_called_once_with(verify=False)
        cull.uninstall.assert_called_once()
        self.assertEqual(report, {'schema': 'render_cull_v1', 'x': 1})
        self.assertIsNone(code)
        self.assertNotIn('wall_cap_s', kw)

    def test_verify_implies_cull_and_a_mismatch_fails_the_run(self):
        cull = mock.MagicMock(mismatches=2)
        cull.report.return_value = {'verify_mismatched': 2}
        with contextlib.redirect_stderr(__import__('io').StringIO()) as err:
            kw, lazy, report, code = self.run_main('--render-cull-verify', cull=cull)
        lazy.install.assert_called_once_with(verify=True)
        self.assertEqual(code, 3)
        self.assertEqual(report, {'verify_mismatched': 2})
        self.assertIn('RENDER_CULL_VERIFY_FAILED', err.getvalue())

    def test_report_is_written_and_cull_removed_when_the_run_fails(self):
        cull = mock.MagicMock(mismatches=0)
        cull.report.return_value = {'a': 1}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ('plan.json', 'protocol.json'):
                (tmp / name).write_text('{}')
            out = tmp / 'out'

            def failing_run_team(plan, protocol, model, output, **kw):
                Path(output).mkdir(parents=True)
                raise TimeoutError('rollout wall cap')
            argv = ['x', '--plan', str(tmp / 'plan.json'), '--protocol', str(tmp / 'protocol.json'), '--model', 'm', '--output', str(out),
                    '--actor-python', 'py', '--scene-source', str(tmp), '--render-cull']
            lazy = mock.MagicMock()
            lazy.install.return_value = cull
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(TEAM, 'run_team', failing_run_team), mock.patch.object(TEAM, 'render_cull_v1', lazy), \
                    mock.patch('scripts.run_grasp_act_recovery.dependency_modules', lambda root: contextlib.nullcontext()):
                with self.assertRaises(TimeoutError):
                    TEAM.main()
            cull.uninstall.assert_called_once()
            self.assertEqual(json.loads((out / 'render-cull.json').read_text()), {'a': 1})


if __name__ == '__main__':
    unittest.main()
