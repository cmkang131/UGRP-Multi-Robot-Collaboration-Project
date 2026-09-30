#!/usr/bin/env python3
"""Prove T13b fake tests kill removed decisions, without editing any source.

Run with the existing Python test environment and a NEW --output directory.
Each mutant is compiled only into a subprocess module by a temporary pytest
plugin. Sealed files are read, never modified. No physics/model/render calls.
These local offline checks do not acquire or release the host lock (PR #328).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST = 'tests/test_zone_own_executor_recovery.py'
MUTATIONS = (
    ('backend_fault_barrier_removed', 'harness.zone_item_recovery',
     '        if self._backend_fault:', '        if False:',
     'test_backend_errors_do_not_fabricate_recovery[cancel]'),
    ('drop_cancel_removed', 'harness.zone_item_recovery',
     '                self._stop(reason)', '                pass  # mutant: continue after drop',
     'test_observed_drop_cancels_before_refresh_then_regrasp_needs_new_own_frame'),
    ('absence_decision_removed', 'harness.zone_item_recovery',
     'if len(self._empty[oid]) == 2:', 'if False:',
     'test_absence_requires_two_contiguous_clear_region_observations'),
    ('noop_enters_effective_denominator', 'harness.zone_recovery_eval',
     'effective = [r for r in group if r.physical_effect is True]', 'effective = group',
     'test_effective_recovery_denominators_keep_noops_caps_unexecuted_and_unknown'),
    ('held_move_noop_removed', 'sim.zone_hidden_events',
     '            if holders:\n', '            if False:\n',
     'test_hidden_apply_four_branches_with_arrays_only'),
    ('unheld_drop_noop_removed', 'sim.zone_hidden_events',
     '            if not holders:\n', '            if False:\n',
     'test_hidden_apply_four_branches_with_arrays_only'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_mutations(output):
    """Run fake-only checks without affecting another task's host lock."""
    source_paths = {module: ROOT / (module.replace('.', '/') + '.py')
                    for _, module, *_ in MUTATIONS}
    hashes = {str(p.relative_to(ROOT)): sha(p) for p in source_paths.values()}
    output.mkdir(parents=True)
    records = []
    for name, module, old, new, test in MUTATIONS:
        path = source_paths[module]
        source = path.read_text()
        if source.count(old) != 1:
            raise RuntimeError(f'{name}: mutation site is not unique')
        with tempfile.TemporaryDirectory(prefix='t13b-mutant-') as temporary:
            plugin = Path(temporary) / 't13b_mutant.py'
            plugin.write_text('import importlib\ndef pytest_configure(config):\n'
                f'    module = importlib.import_module({module!r})\n'
                f'    exec(compile({source.replace(old, new)!r}, {str(path)!r}, "exec"), module.__dict__)\n')
            command = [sys.executable, '-m', 'pytest', '-q', '-p', 't13b_mutant',
                       f'{TEST}::{test}', '--junitxml', str(output / f'{name}.xml')]
            child = subprocess.Popen(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True,
                env={**os.environ, 'PYTHONPATH': os.pathsep.join((temporary, str(ROOT))),
                     'PYTHONDONTWRITEBYTECODE': '1'})
            try:
                stdout, stderr = child.communicate(timeout=120)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            log = output / f'{name}.log'
            log.write_text(stdout + stderr)
        xml = output / f'{name}.xml'
        tree = ET.parse(xml)
        failures, errors = len(tree.findall('.//failure')), len(tree.findall('.//error'))
        killed = child.returncode == 1 and failures > 0 and errors == 0
        record = {'name': name, 'module': module, 'test': test, 'exit_code': child.returncode,
                  'failures': failures, 'errors': errors, 'killed': killed,
                  'log': str(log), 'log_sha256': sha(log), 'junit': str(xml), 'junit_sha256': sha(xml)}
        records.append(record)
        print(json.dumps(record), flush=True)
    unchanged = hashes == {str(p.relative_to(ROOT)): sha(p) for p in source_paths.values()}
    report = {'schema': 'ugrp.t13b_mutation_check.v1', 'physics_steps': 0, 'model_calls': 0,
              'method': 'in-memory module replacement in isolated pytest subprocess',
              'host_lock': 'not acquired: local offline tests',
              'source_sha256': hashes, 'sources_unchanged': unchanged,
              'mutations': records, 'all_killed': all(r['killed'] for r in records)}
    (output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if unchanged and report['all_killed'] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error('output must be a new directory; prior results are never overwritten')
    return run_mutations(output)


if __name__ == '__main__':
    raise SystemExit(main())
