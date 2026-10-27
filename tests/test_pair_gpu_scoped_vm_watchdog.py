"""Cloud stop calls are mocked; the namesake zone can never be selected."""
from pathlib import Path
from subprocess import CompletedProcess
import json
import tempfile
import unittest
from unittest.mock import patch

from scripts.pair_gpu_scoped_vm_watchdog import main


class VMWatchdogTests(unittest.TestCase):
    def test_completed_vm_exits_without_a_cloud_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'VM_FINAL.json').write_text('{"status":"TERMINATED"}')
            with patch('sys.argv', ['watchdog', '--root', tmp, '--stop-utc', '2100-01-01T00:00:00+00:00']), \
                    patch('scripts.pair_gpu_scoped_vm_watchdog.subprocess.run') as run:
                main()
                run.assert_not_called()

    def test_expired_resource_budget_stops_only_exact_tokyo_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('sys.argv', ['watchdog', '--root', tmp, '--stop-utc', '2000-01-01T00:00:00+00:00']), \
                    patch('scripts.pair_gpu_scoped_vm_watchdog.subprocess.run', side_effect=[
                        CompletedProcess([], 0, '[]', ''),
                        CompletedProcess([], 0, '{"status":"TERMINATED"}', '')]) as run:
                main()
                self.assertEqual(run.call_count, 2)
                for call, verb in zip(run.call_args_list, ('stop', 'describe')):
                    self.assertEqual(call.args[0][1:], ['ugrp-sim-f-1016', 'compute', 'instances', verb,
                        'ugrp-act-l4-gcp6', '--zone=asia-northeast1-c', '--format=json'])
                result=json.loads((Path(tmp)/'VM_BUDGET_STOP.json').read_text())
                self.assertEqual(result['reason'], 'HOST_RESOURCE_ESTIMATED_GLOBAL_GPU_BUDGET')


if __name__ == '__main__':
    unittest.main()
