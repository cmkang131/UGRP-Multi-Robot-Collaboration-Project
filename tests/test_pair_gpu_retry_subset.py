"""Pure plan checks: no simulator/model imports or physics execution."""
import unittest
import subprocess
import sys

from scripts.pair_gpu_retry_subset import subset_plan


class SubsetPlanTests(unittest.TestCase):
    def test_execute_refuses_before_loading_remote_stack(self):
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'scripts.pair_gpu_retry_subset',
             '--arm', 'arm_s', '--indices', '0,1', '--out',
             '/nonexistent-pair-gpu-retry-test/output', '--execute'],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('GPU-only retry refused:', result.stderr)
        self.assertIn('CPU mujoco.mj_step', result.stderr)
        self.assertNotIn('FileNotFoundError', result.stderr)

    def test_preserves_every_other_argument_and_original_plan(self):
        argv = ['runner', '--indices', ','.join(map(str, range(20))),
                '--rejection-table', '/prior', '--cap-s', '60', '--student-eval', '/fixed']
        original = dict(argv=argv, cwd='/frozen', arm='arm_s')
        actual = subset_plan(original, '0,1')
        expected = argv.copy()
        expected[2] = '0,1'
        self.assertEqual(actual['argv'], expected + ['--physics-backend', 'mjwarp_batch_v1'])
        self.assertEqual(original['argv'][2], ','.join(map(str, range(20))))
        self.assertEqual(actual['cwd'], original['cwd'])

    def test_rejects_unapproved_selection_and_plan_drift(self):
        for indices in ('', '1', '0,1,2'):
            with self.assertRaises(ValueError):
                subset_plan(dict(argv=[]), indices)
        for argv in (['--indices', '0'],
                     ['--indices', ','.join(map(str, range(20))), '--physics-backend', 'c_pilot_v1']):
            with self.assertRaises(ValueError):
                subset_plan(dict(argv=argv), '0')


if __name__ == '__main__':
    unittest.main()
