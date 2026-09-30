"""Remove candidate decisions in isolated Python processes; production bytes untouched.

Run with the existing test interpreter, from the repository root:
  python experiments/2026-09-30-beam-approach/mutation_check.py /absolute/NEW-output
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'harness/beam_approach.py'
TEST = 'tests/test_pair_navigation_beam_approach.py'
MUTATIONS = {
    'navigation_removed': "ba.BeamApproach._navigate = lambda self, now, report: self._hold(now)",
    'pose_gate_removed': "ba.BeamApproach._trusted = lambda self, report, now: True",
    'relative_alignment_removed': "ba.BeamApproach._align = lambda self, now, report: self._hold(now)",
    'handoff_posterior_reinitialized': '''
original = ba.BeamApproach._navigate
def replaced(self, now, report):
    result = original(self, now, report)
    if self.phase == 'aligning':
        self.memory.provider.loc = object()
    return result
ba.BeamApproach._navigate = replaced
''',
    'command_guard_removed': '''
original = ba.BeamApproach._offer
def replaced(self, action, now, report=None):
    self.command_clear = lambda *args: True
    return original(self, action, now, report)
ba.BeamApproach._offer = replaced
''',
}
REPLACEMENTS = {
    'image_hash_check_removed': ("if hashlib.sha256(data).hexdigest() != obs['sha256']:", 'if False:'),
    'delivered_abort_check_removed': ("if peer['state'] == 'abort':", 'if False:'),
    'sim_cap_boundary_weakened': ("if now - self.started_at >= CONFIG['sim_cap_s']:",
                                "if now - self.started_at > CONFIG['sim_cap_s']:"),
}


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    prefix = '''
import offline_guard
import sys, types
from pathlib import Path
import harness
'''
    rows = []
    for name in ('normal', *MUTATIONS, *REPLACEMENTS):
        if name in REPLACEMENTS:
            before, after = REPLACEMENTS[name]
            code = prefix + f'''
src = Path({str(SOURCE)!r}).read_text()
assert src.count({before!r}) == 1
src = src.replace({before!r}, {after!r})
ba = types.ModuleType('harness.beam_approach')
ba.__file__ = {str(SOURCE)!r}
sys.modules[ba.__name__] = ba
harness.beam_approach = ba
exec(compile(src, ba.__file__, 'exec'), ba.__dict__)
'''
        else:
            code = prefix + '\nfrom harness import beam_approach as ba\n' + MUTATIONS.get(name, '')
        code += '\nimport pytest\nsys.exit(pytest.main(sys.argv[1:]))\n'
        log, junit = output / (name+'.txt'), output / (name+'.xml')
        env = {**os.environ, 'PYTHONPATH': str(ROOT)+os.pathsep+str(Path(__file__).parent),
               'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
        with log.open('w') as stream:
            result = subprocess.run([sys.executable, '-c', code, TEST, '-q', '--junitxml='+str(junit)],
                                    cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
        xml = ET.parse(junit).getroot()
        suites = list(xml.iter('testsuite'))
        counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
                  for key in ('tests', 'failures', 'errors', 'skipped')}
        failed = [case.attrib['name'] for case in xml.iter('testcase') if case.find('failure') is not None]
        row = {'mutation': name, 'exit_code': result.returncode, **counts, 'failed_tests': failed,
               'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()}
        rows.append(row)
        print({k: v for k, v in row.items() if k != 'failed_tests'}, flush=True)
    report = {'source_sha256': source_sha, 'test_sha256': hashlib.sha256((ROOT/TEST).read_bytes()).hexdigest(),
              'production_bytes_unchanged': source_sha == hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'physics_sim_render_model_calls': 0, 'host_lock_used': False, 'runs': rows}
    (output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
    assert report['production_bytes_unchanged']
    assert rows[0]['exit_code'] == 0 and rows[0]['errors'] == rows[0]['failures'] == 0
    assert all(r['exit_code'] == 1 and r['failures'] > 0 and r['errors'] == 0 for r in rows[1:])


if __name__ == '__main__':
    main()
