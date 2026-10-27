"""Oracle smoke with fake scheduling boundaries; no GPU/actor required."""
from pathlib import Path
import json
import tempfile
from types import SimpleNamespace
import unittest

from scripts.pair_gpu_cpu_guard import CPUInitGuard


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'provenance.json'
        self.guard = CPUInitGuard(self.path, 'arm_s', [8342000, 8342001])
        self.calls = []
        self.original = lambda *a, **kw: self.calls.append((a, kw))

    def test_init_count_and_per_world_one_way_boundary(self):
        first, second = object(), object()
        with self.guard.episode(0):
            self.guard.step(self.original, None, first)
            self.guard.step(self.original, None, first, nstep=3)
        self.guard.recorder(0, first)
        with self.assertRaisesRegex(RuntimeError, 'CPU_MJ_STEP_DURING_ROLLOUT'):
            self.guard.step(self.original, None, first)
        # Constructing the next lane remains legal before batch takeover.
        with self.guard.episode(1):
            self.guard.step(self.original, None, second, 2)
        self.guard.recorder(1, second)
        self.guard.begin_batch('fake MJWarp loop begins')
        with self.assertRaisesRegex(RuntimeError, 'CPU_MJ_STEP_DURING_ROLLOUT'):
            self.guard.step(self.original, None, object())
        self.assertEqual(len(self.calls), 3)
        record = json.loads(self.path.read_text())
        self.assertEqual(record['cpu_init_mj_step_count'], 6)
        self.assertEqual([r['cpu_init_mj_step_count'] for r in record['episodes']], [4, 2])
        self.assertEqual(len(record['rollout_cpu_denial_events']), 2)
        self.assertTrue(all(r['phase'] == 'ROLLOUT' for r in record['episodes']))
        self.assertEqual(len(record['phase_transitions']), 3)

    def test_template_count_then_unknown_data_denied_after_gpu_start(self):
        self.guard.step(self.original, None, object(), nstep=5)
        self.guard.begin_batch('fake GPU initialize')
        with self.assertRaisesRegex(RuntimeError, '"arm_cpu_init_mj_step_count": 5'):
            self.guard.step(self.original, None, object())
        self.assertEqual(json.loads(self.path.read_text())['template']['cpu_init_mj_step_count'], 5)

    def test_wrappers_keep_original_calls_and_restore_on_exception(self):
        guard = self.guard
        data = object()
        class Lane:
            def invoke(self, method):
                mujoco.mj_step(None, data)
                return method
        class Bridge:
            index = 0
            plan = {'seed': 8342000}
            def install_command_recorder(self, world):
                return 'original recorder'
        class WarpTransport:
            def initialize(self):
                return 'GPU initialize'
            def step(self):
                return 'GPU step'
        flow = SimpleNamespace(Lane=Lane, Bridge=Bridge, make_lane=lambda: (Lane(), Bridge()))
        backend = SimpleNamespace(WarpTransport=WarpTransport)
        mujoco = SimpleNamespace(mj_step=self.original)
        original_lane = flow.make_lane
        with self.assertRaisesRegex(RuntimeError, 'CPU_MJ_STEP_DURING_ROLLOUT'):
            with guard.installed(mujoco, flow, backend):
                lane, bridge = flow.make_lane()
                self.assertEqual(lane.invoke('first'), 'first')
                self.assertEqual(bridge.install_command_recorder(SimpleNamespace(data=data)), 'original recorder')
                self.assertEqual(backend.WarpTransport().initialize(), 'GPU initialize')
                self.assertEqual(backend.WarpTransport().step(), 'GPU step')
                lane.invoke('forbidden')
        self.assertIs(mujoco.mj_step, self.original)
        self.assertIs(flow.make_lane, original_lane)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(json.loads(self.path.read_text())['rollout_cpu_denial_events']), 1)


if __name__ == '__main__':
    unittest.main()
