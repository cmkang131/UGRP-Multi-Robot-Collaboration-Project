import copy
import hashlib
import io
import json

import numpy as np
import pytest
from PIL import Image

from harness import grasp_act_contract as c
from harness.grasp_act_data import (GraspDataset, TRAIN_KEYS, convert, paired_segments,
                                    sha256, write_json)


def episode(root, seed, *, pwm=1500, robot='r1', role='west', kind='cyan'):
    run = root / f'run-{seed}'
    raw = run / 'raw'
    (raw / 'rgb' / robot).mkdir(parents=True)
    (run / 'SOURCE_SHA').write_text('a' * 40)
    (run / 'EXIT').write_text('0')
    write_json(raw / 'result.json', {'status': 'complete', 'source_sha': 'a' * 40,
        'physical_success': True, 'training_rgb': True, 'student_execution': False, 'recording_mode': 'training'})
    write_json(raw / 'plan.json', {'seed': seed})
    write_json(raw / 'student-camera.json', {'schema': c.SCHEMA, 'width': 640, 'height': 480,
        'period_s': .1, 'hz': 10., 'camera': 'robot_cam',
        'sources': {'harness/grasp_act_contract.py': sha256(c.__file__)}})
    encoded = io.BytesIO()
    Image.new('RGB', (640, 480), (30, 80, 120)).save(encoded, 'JPEG')
    jpeg = encoded.getvalue()
    obs, labels = [], []
    for i in range(5):
        t = 1. + i * .1
        rel = f'rgb/{robot}/{i}.jpg'
        (raw / rel).write_bytes(jpeg)
        command = {'t': t-.1, 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                   'pwm': {str(s): pwm for s in c.SERVOS}}
        ref = {'path': rel, 'sha256': hashlib.sha256(jpeg).hexdigest(), 't': t, 'robot_id': robot}
        obs.append({'schema': c.SCHEMA, 'robot_id': robot, 'sample_id': f'ep{seed}:{i}:{robot}',
            't': t, 'skill': 'grasp', 'object_kind': kind, 'role': role, 'destination_zone': 'none',
            'issued': [copy.deepcopy(command) for _ in range(c.HISTORY)], 'rgb': [dict(ref) for _ in range(4)],
            'skill_elapsed_s': i*.1, 'pwm_elapsed_s': i*.1})
        labels.append({'sample_id': obs[-1]['sample_id'], 'skill': 'grasp', 'object_kind': kind,
            'done': i == 4, 'terminal_reason': 'command_sequence_complete' if i == 4 else None,
            'local_skill_sample': i != 2, 'clean_teacher_command': {**command, 't': t},
            'privileged_diagnostic': {'qpos': [999], 'contact': True}})
    for name, rows in ((f'student-{robot}.jsonl', obs), (f'teacher-{robot}.jsonl', labels)):
        (raw / name).write_text(''.join(json.dumps(r) + '\n' for r in rows))
    return raw, obs, labels


def protocol():
    return {'teacher_sha': 'a' * 40, 'run_pattern': 'run-{seed}', 'train_seeds': [1], 'validation_seeds': [2]}


@pytest.mark.parametrize('where,key', [('root', 'qpos'), ('root', 'contact'), ('root', 'object_pose'),
    ('root', 'text'), ('issued', 'measured_joints'), ('rgb', 'segmentation')])
def test_nested_privileged_inputs_rejected(tmp_path, where, key):
    _, obs, labels = episode(tmp_path, 1)
    if where == 'root':
        obs[0][key] = [1]
    else:
        obs[0][where][0][key] = [1]
    with pytest.raises(ValueError):
        paired_segments(obs, labels)


def test_excluded_intervals_do_not_bridge_chunks(tmp_path):
    _, obs, labels = episode(tmp_path, 1)
    groups = paired_segments(obs, labels)
    assert list(map(len, groups)) == [2, 2]
    windows = c.training_windows([x[0] for x in groups[0]], [x[1] for x in groups[0]])
    assert windows[0]['action_is_pad'] == [False, False] + [True] * 6
    assert not any(row[-1] for row in windows[0]['action'])
    labels[4]['terminal_reason'] = 'timeout'
    with pytest.raises(ValueError, match='timeout'):
        paired_segments(obs, labels)


def test_conversion_no_teacher_leak_and_train_only_stats(tmp_path):
    episode(tmp_path, 1, pwm=1000)
    episode(tmp_path, 2, pwm=2400, robot='r2', kind='long_beam', role='blue')
    out = tmp_path / 'dataset'
    report = convert(tmp_path, protocol(), out)
    assert report['complete']
    stats = json.loads((out / 'normalization.json').read_text())
    assert stats['train_seeds'] == [1] and stats['rows'] == 4
    assert stats['action_mean'][8:13] == [-.5] * 5
    data = GraspDataset(out, 'validation')
    assert len(data) == 4
    batch = data[0]
    assert set(batch) == TRAIN_KEYS
    assert batch['observation.state'].shape == (c.CONTEXT_DIM,)
    assert batch['observation.images.own_history'].shape == (3, 480, 640)
    assert batch['action'].shape == (8, 14)
    assert np.all(batch['action'][batch['action_is_pad']] == 0)
    assert report['episodes'][1]['robot_id'] == 'r2'
    # Mutated artifact cannot bypass admission via an already generated manifest.
    (out / '2-r2' / 'samples.json').write_text('[]')
    with pytest.raises(ValueError, match='hash mismatch'):
        GraspDataset(out, 'validation')


def test_partial_cannot_train_and_hash_mismatch_fails(tmp_path):
    raw, obs, labels = episode(tmp_path, 1)
    out = tmp_path / 'partial'
    convert(tmp_path, protocol(), out, seeds=[1])
    with pytest.raises(ValueError, match='complete'):
        GraspDataset(out, 'train')
    (raw / 'rgb/r1/0.jpg').write_bytes(b'corruption')
    with pytest.raises(ValueError, match='RGB hash'):
        convert(tmp_path, protocol(), tmp_path / 'broken', seeds=[1])
    assert json.loads((tmp_path / 'broken/manifest.json').read_text())['status'] == 'HOST_ERROR'


def test_split_overlap_and_label_alignment_fail(tmp_path):
    _, obs, labels = episode(tmp_path, 1)
    labels[1]['clean_teacher_command']['t'] = 999.
    with pytest.raises(ValueError, match='time mismatch'):
        paired_segments(obs, labels)
    p = protocol(); p['validation_seeds'] = [1]
    with pytest.raises(ValueError, match='split overlap'):
        convert(tmp_path, p, tmp_path / 'bad')


def test_release_done_is_not_synthesized(tmp_path):
    _, obs, labels = episode(tmp_path, 1)
    for o, label in zip(obs, labels):
        o['skill'] = label['skill'] = 'release'; o['destination_zone'] = 'pickup_site'
    labels[-1]['local_skill_sample'] = False
    groups = paired_segments(obs, labels)
    assert all(not label['done'] for group in groups for _, label, _ in group)


def test_camera_contract_and_symlink_escape_fail(tmp_path):
    raw, _, _ = episode(tmp_path, 1)
    path = raw / 'student-camera.json'
    camera = json.loads(path.read_text()); camera['period_s'] = .2; write_json(path, camera)
    with pytest.raises(ValueError, match='camera contract'):
        convert(tmp_path, protocol(), tmp_path / 'bad', seeds=[1])
    from harness.grasp_act_data import safe_path
    with pytest.raises(ValueError, match='escapes'):
        safe_path(raw, '../outside')


def test_incomplete_recording_is_not_admitted(tmp_path):
    raw, _, _ = episode(tmp_path, 1)
    result = json.loads((raw / 'result.json').read_text()); result['status'] = 'running'
    write_json(raw / 'result.json', result)
    with pytest.raises(ValueError, match='completed successful'):
        convert(tmp_path, protocol(), tmp_path / 'not-ready', seeds=[1])
