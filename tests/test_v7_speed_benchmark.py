"""Completeness and raw-byte checks without simulation."""
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts import benchmark_v7_speed as b
from sim import workflow_manager as wm


def test_catalog_fragment_plan_only(tmp_path):
    root = Path(__file__).resolve().parents[1]
    data, _ = wm.catalog(root)
    catalog = {r['id']: r for r in data['workflows']}
    assert 'v7-exact-speed-benchmark' in catalog
    assert catalog['v7-exact-speed-benchmark']['entry'] == 'scripts/benchmark_v7_speed.py'
    with patch('subprocess.Popen', side_effect=AssertionError('must not run')):
        result = wm.plan(root, 'v7-exact-speed-benchmark', ['--suite',
            str(root/'experiments/2026-10-09-sim-speed-core/suite.json'),
            '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'new')])
    assert not (tmp_path/'new').exists()


def fixture(root):
    root.mkdir()
    state = dict(sim_s=.2, steps=800, dt=.00025, start=1.3, end=1.5, period=.2,
                 frames=2, robots=['r3'], chain_sha256='fixed')
    b.write(root/'state-chain.json', state)
    (root/'scene.xml').write_text('<mujoco/>')
    b.write(root/'judgement.json', {'success':False})
    for name in b.PROVENANCE: b.write(root/name, {'mode':'off'})
    (root/'eval_only').mkdir()
    (root/'eval_only/contacts.jsonl').write_text('{}\n{}\n')
    (root/'robots/r3').mkdir(parents=True)
    rows=[]
    for i,t in enumerate((1.3,1.5)):
        name=f'robots/r3/{i}.jpg';(root/name).write_bytes(b'frame')
        rows.append(dict(sim_time=t,path=name,sha256=b.sha(root/name)))
    (root/'robots/r3/frames.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
    (root/'robots/r3/commands.jsonl').write_text('{"kind":"initial_servo_command"}\n')


def test_comparison_rejects_shared_missing_evidence_and_byte_difference(tmp_path):
    a,bdir=tmp_path/'a',tmp_path/'b';fixture(a);fixture(bdir)
    assert b.compare(a,bdir)['identical']
    b.write(bdir/'v7-speedups.json', {'mode':'relay-cache-v1'})
    assert b.compare(a,bdir)['identical']
    (bdir/'judgement.json').write_text('{"success": false}\n')
    assert not b.compare(a,bdir)['identical']
    for root in (a,bdir): (root/'eval_only/contacts.jsonl').write_text('{}\n')
    with pytest.raises(AssertionError): b.compare(a,bdir)
