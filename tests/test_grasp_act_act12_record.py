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
