"""Offline reproducibility checks in isolated copies; never edit the worktree.

Each mutation removes one runtime-seal check. A passing baseline and an actual
pytest assertion failure (not collection/setup errors) are required. This small
set verifies the named checks, not complete mutation coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


COPIED = (
    'harness/execution_dependency_contract.py', 'harness/python_source_closure.py',
    'harness/python_source_closure_v2.py', 'sim/workflow_manager.py',
    'harness/runtime_provenance.py', 'scripts/trace_execution_dependencies.py',
    'tests/test_seal_runtime_provenance.py',
)
MUTATIONS = (
    ('unseen-file',
     "if self.expected and (path not in self.expected['files'] or self.expected['files'][path] != state):",
     'if False:',
     'test_unseen_read_aborts_before_consumer_even_if_exception_caught'),
    ('environment-drift',
     "if self.expected['environment'][name] != state:", 'if False:',
     'test_environment_runtime_comparison'),
    ('path-binding',
     "return {'realpath': str(real), 'links': links, 'sha256': hasher.hexdigest()}",
     "return {'sha256': hasher.hexdigest()}",
     'test_N3_same_bytes_source_symlink_target or test_N3_declared_xml_link_selects_other_declared_asset'),
    ('static-union', "for path in request['seed']:", 'for path in []:',
     'test_static_unobserved_union_and_multiple_cases'),
    ('identity-drift', "if identity() != value['identity']:", 'if False:',
     'test_identity_abort_or_warn'),
    ('unknown-environment', "if name not in self.expected['environment']:",
     "if name not in self.expected['environment']:\n                return",
     'test_unknown_environment_name_is_never_covered_by_warn'),
)


def run(root, output, name, source, selector):
    with tempfile.TemporaryDirectory(prefix='seal-mutation-') as folder:
        staged = Path(folder)
        for rel in COPIED:
            target = staged / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, target)
        (staged / 'harness/runtime_provenance.py').write_text(source)
        report = output / (name + '.xml')
        command = [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                   '--rootdir=.', '--confcutdir=.', 'tests/test_seal_runtime_provenance.py',
                   '-k', selector, '--junitxml=' + str(report)]
        env = dict(os.environ, PYTHONPATH=str(staged), PYTHONDONTWRITEBYTECODE='1')
        with (output / (name + '.log')).open('x') as log:
            result = subprocess.run(command, cwd=staged, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=180)
        suite = ET.parse(report).getroot().find('testsuite')
        counts = {key: int(suite.get(key, '0')) for key in ('tests', 'failures', 'errors', 'skipped')}
        valid = (counts['tests'] > 0 and counts['errors'] == counts['skipped'] == 0
                 and (result.returncode == 0 and counts['failures'] == 0 if name == 'baseline'
                      else result.returncode == 1 and counts['failures'] > 0))
        return {'name': name, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'selector': selector, 'exit_code': result.returncode, **counts, 'verified': valid}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.root.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    original = (root / 'harness/runtime_provenance.py').read_text()
    selector = ' or '.join('(' + mutation[3] + ')' for mutation in MUTATIONS)
    results = [run(root, output, 'baseline', original, selector)]
    if results[0]['verified']:
        for name, old, new, selector in MUTATIONS:
            if original.count(old) != 1:
                raise ValueError('mutation anchor must match exactly once: ' + name)
            results.append(run(root, output, name, original.replace(old, new), selector))
    value = {'scope': 'offline isolated mutation checks; no physics', 'results': results,
             'passed': len(results) == len(MUTATIONS) + 1 and all(r['verified'] for r in results)}
    (output / 'summary.json').write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps(value, indent=2))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
