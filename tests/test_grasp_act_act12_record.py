import ast
import copy

import pytest

from scripts.run_grasp_act_act12_record import own_review_source
from scripts.audit_grasp_act_recording import audit
from tests.test_grasp_act_data import episode


def test_only_two_evaluation_statements_removed():
    source = '''def run(out, world, static, tick):
    (out/'review-top').mkdir()
    own = world.own_rgb()
    if tick % 10 == 0:
        (out/'review-top'/f'{tick:06d}.jpg').write_bytes(world.render_team_jpeg(camera=static['top_cameras'][0]['name']))
        world.control(own)
    return own
'''
    effective, removed = own_review_source(source)
    original = ast.parse(source)
    original.body[0].body.pop(0)
    original.body[0].body[1].body.pop(0)
    assert ast.dump(ast.parse(effective)) == ast.dump(original)
    assert len(removed) == 2
    with pytest.raises(ValueError):
        own_review_source(source.replace('world.own_rgb()', 'world.render_team_jpeg()'))
    with pytest.raises(ValueError):
        own_review_source(source.replace("(out/'review-top').mkdir()", 'pass'))


def test_recording_audit_fails_closed(tmp_path):
    import json
    raw, observations, _ = episode(tmp_path, 1)
    result = json.loads((raw/'result.json').read_text())
    result['input_audit'] = {'invisible_measurements': 0, 'held_world_reads': 0}
    (raw/'result.json').write_text(json.dumps(result))
    assert audit(raw)['training_frames'] == 5
    for where in ('root', 'issued', 'rgb'):
        rows = copy.deepcopy(observations)
        target = rows[0] if where == 'root' else rows[0][where][0]
        target['measured_joints'] = [1]
        (raw/'student-r1.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        with pytest.raises(ValueError):
            audit(raw)


def test_disabled_handoff_and_unreviewed_pilot_rejected(tmp_path):
    from scripts.queue_grasp_act_act12_record import build, TEACHER, FLAGS
    source = tmp_path/'summary.json'
    source.write_text('{}')
    run = {'audit_status': 'PASS', 'visual_review_status': 'PASS',
           'camera': {'width': 640, 'height': 480}, 'command': ['exact-pilot'],
           'retrieval_receipt': 'actual-receipt'}
    summary = {'teacher_source_sha': TEACHER, 'pilot_success': 2, 'pilot_N': 2,
        'review_status': 'PASS', 'recording_wrapper_source_sha': 'a'*40,
        'teacher_dependency_sha': 'b'*40, 'storage': {'reserved_per_run_mib': 256},
        'gate_report': {}, 'pilot_gate_receipt': {}, 'runs': [run, run]}
    q = build(summary, source)
    assert [len(j['runs']) for j in q['jobs']] == [2, 48, 10]
    assert len({r['seed'] for j in q['jobs'] for r in j['runs']}) == 60
    for node in [q, *q['jobs'], *(r for j in q['jobs'] for r in j['runs'])]:
        assert all(node[k] is False for k in FLAGS)
        assert node['training_rgb'] is True
    assert q['source_sha'] == TEACHER and q['max_parallel'] == 16
    assert q['jobs'][0]['runs'][0]['command'] == ['exact-pilot']
    bad = copy.deepcopy(summary)
    bad['runs'][0]['visual_review_status'] = 'PENDING'
    with pytest.raises(ValueError):
        build(bad, source)


def test_wrapper_default_does_not_transform_teacher(tmp_path, monkeypatch):
    import sys
    from scripts import run_grasp_act_act12_record as wrapper
    from scripts import run_grasp_act_recovery as adapter
    calls = []
    original_scope = adapter.dependency_modules
    monkeypatch.setattr(wrapper.subprocess, 'check_output',
        lambda command, **kw: wrapper.ACT11+'\n' if command[-1] == 'HEAD' else b'')
    monkeypatch.setattr(adapter, 'main', lambda: calls.append(sys.argv.copy()))
    monkeypatch.setattr(sys, 'argv', ['record', '--teacher-source', str(tmp_path),
        '--', '--out', str(tmp_path/'run/raw')])
    wrapper.main()
    assert len(calls) == 1 and adapter.dependency_modules is original_scope
    assert not (tmp_path/'run/review-policy.json').exists()
