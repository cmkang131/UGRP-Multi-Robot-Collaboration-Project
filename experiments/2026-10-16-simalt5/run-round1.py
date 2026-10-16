"""Round1: reciprocal compiled damping ablation; frozen simalt3 command tape."""
import datetime
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/home/ugrp/ugrp-sim/runs/simalt5')
OLD = ROOT.parent/'simalt3'
PREV = ROOT.parent/'simalt4'
SOURCE = Path('/home/ugrp/ugrp-sim/src/e89ff153')
PROBE = SOURCE/'scripts/simalt_step_probe.py'
PY312 = OLD/'c-env/bin/python'
PY316 = OLD/'warp-env/bin/python'
SHA = 'e89ff153'
ENV = {**os.environ, 'MUJOCO_GL': 'osmesa', 'LP_NUM_THREADS': '1'}


def run(cmd, name):
    with (ROOT/(name+'.log')).open('x') as log:
        completed = subprocess.run(list(map(str, cmd)), stdout=log, stderr=subprocess.STDOUT, env=ENV)
    if completed.returncode:
        raise RuntimeError(f'{name}: process exit {completed.returncode}')


def command(python, name, engine, case='grip', extra=()):
    return [python, '-u', PROBE, '--enabled', '--fixture', OLD/'fixture', '--out', ROOT/name,
            '--engine', engine, '--case', case, '--sha', SHA,
            '--capacity-reference', PREV/'rev5/dense-capacity.json', '--dense-capacity-v1', *extra]


def main():
    lease = Path('/home/ugrp/ugrp-sim/leases/simalt5.json')
    lease.write_text(json.dumps({'task': 'simalt5', 'pid': os.getpid(),
        'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'expected_end': '2026-10-15T19:45:52.759Z', 'source': SHA}, indent=2)+'\n')
    for python, version in ((PY312, '312'), (PY316, '316')):
        run(command(python, 'export'+version, 'cpu', extra=[
            '--export-compiled', ROOT/('compiled-'+version+'.json')]), 'export'+version)
    jobs = [('c312-damping316-grip', command(PY312, 'c312-damping316-grip', 'cpu', extra=[
        '--compiled-reference-v1', ROOT/'compiled-316.json', '--damping-ablation-v1',
        '--record-own-rgb', OLD/'runtime/source'])),
        ('c316-damping312-grip', command(PY316, 'c316-damping312-grip', 'cpu', extra=[
        '--compiled-reference-v1', ROOT/'compiled-312.json', '--record-own-rgb', OLD/'runtime/source']))]
    for case in ('forward', 'side', 'turn', 'grip'):
        name = 'warp-compiled312-'+case
        jobs.append((name, command(PY316, name, 'warp', case, [
            '--compiled-reference-v1', ROOT/'compiled-312.json',
            '--backend-mode', 'legacy-plane-v1', '--record-own-rgb', OLD/'runtime/source'])))
    plan = {'round': 1, 'source': SHA, 'jobs': [[name, list(map(str, cmd))] for name, cmd in jobs],
            'rejection_table': str(ROOT/'rejection-before-round1.json'),
            'inherited_baselines': [str(PREV/'c312-grip'), str(PREV/'c316-grip'), str(PREV/'legacy-r3-grip')]}
    assert Path(plan['rejection_table']).is_file()
    (ROOT/'round1-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    for name, cmd in jobs:
        run(cmd, name)
        result = json.loads((ROOT/name/'result.json').read_text())
        print(name, result['status'], result.get('error', ''), flush=True)
        if result['status'] != 'complete':
            raise RuntimeError(name+' incomplete')
    pairs = [('version-raw', PREV/'c312-grip', PREV/'c316-grip'),
             ('original-total', PREV/'c312-grip', PREV/'legacy-r3-grip'),
             ('damping-only-c312', PREV/'c312-grip', ROOT/'c312-damping316-grip'),
             ('warp-vs-c312-newdamping', ROOT/'c312-damping316-grip', PREV/'legacy-r3-grip'),
             ('warp-damping-effect', PREV/'legacy-r3-grip', ROOT/'warp-compiled312-grip'),
             ('same-version-compiled312', ROOT/'c316-damping312-grip', ROOT/'warp-compiled312-grip')]
    pairs += [('corrected-'+case, PREV/('c312-'+case), ROOT/('warp-compiled312-'+case))
              for case in ('forward', 'side', 'turn', 'grip')]
    summaries = []
    for name, reference, candidate in pairs:
        out = ROOT/('analysis-'+name)
        run([PY316, SOURCE/'scripts/simalt_step_analysis.py', '--fixture', OLD/'fixture',
             '--reference', reference, '--candidate', candidate, '--out', out], 'analysis-'+name)
        summaries.append({'name': name, **json.loads((out/'summary.json').read_text())})
    (ROOT/'round1-summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
    print('ROUND1_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
