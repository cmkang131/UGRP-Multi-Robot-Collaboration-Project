"""One offline mutation subprocess; no host lock is acquired or required."""
import contextlib
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('mujoco', 'torch', 'openai', 'anthropic') or fullname.startswith('google.genai'):
            raise AssertionError('offline mutation forbids import: ' + fullname)
sys.meta_path.insert(0, OfflineOnly())
def audit(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise AssertionError('offline mutation forbids network: ' + event)
sys.addaudithook(audit)

from mutation_variants import install
import pytest
name, destination = sys.argv[1:]
out = Path(destination)
out.mkdir(parents=True, exist_ok=False)
mutation = install(name)
class Reports:
    def __init__(self):
        self.failed, self.passed, self.errors = [], [], []
    def pytest_runtest_logreport(self, report):
        if report.failed:
            (self.failed if report.when == 'call' else self.errors).append(report.nodeid)
        elif report.when == 'call' and report.passed:
            self.passed.append(report.nodeid)
reports = Reports()
with (out / 'pytest.log').open('w') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    code = int(pytest.main(['-q', '-p', 'no:cacheprovider', '--basetemp=' + str(out / 'tmp'),
                           'tests/test_zone_own_executor_corridor_control.py::' + mutation['selected_test']],
                          plugins=[reports]))
path = ROOT / (mutation['module'].replace('.', '/') + '.py')
unchanged = hashlib.sha256(path.read_bytes()).hexdigest() == mutation['original_sha256']
caught = code == 1 and bool(reports.failed) and not reports.errors and unchanged
receipt = {'mutation': mutation, 'pytest_exit_code': code, 'failed_tests': reports.failed,
           'passed_tests': reports.passed, 'setup_teardown_errors': reports.errors,
           'original_file_unchanged': unchanged, 'mutation_caught': caught,
           'host_lock_required': False, 'scope': 'fake only; physics/render/model calls 0'}
(out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'mutation': name, 'caught': caught, 'failed': len(reports.failed),
                  'passed': len(reports.passed)}), flush=True)
raise SystemExit(0 if caught else 1)
