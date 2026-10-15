"""Native ACT12 allowlists and observer boundary; no physics/render on Mac."""
import io
import json
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from harness.grasp_act_contract import SCHEMA, validate_observation
from harness.grasp_act_release_recording import ReleaseRecorder, RenderAudit, validate


def test_pair_native_frames_commands_destinations_and_done(tmp_path):
    teachers = {r: SimpleNamespace(pwm={s: 1500 for s in (1, 3, 4, 5, 6)}) for r in ('r1', 'r2')}
    wheels = {r: SimpleNamespace(levels=[0.]*4, until=[0.]*4) for r in teachers}
    recorder = ReleaseRecorder(tmp_path, dict(seed=88600, roles=dict(r1='teal', r2='blue'),
                                             destination_region='B'), teachers, wheels, 2.)
    b = io.BytesIO(); Image.new('RGB', (640, 480)).save(b, format='JPEG'); jpeg = b.getvalue()
    for i in range(3):
        now = 2.+i*.1
        teachers['r1'].pwm[6] = 1500+i
        recorder.target(now, {r: jpeg for r in teachers}, phase='done' if i else 'open',
                        phase_after='done', teachers=teachers, wheels=wheels, complete=i == 2)
    recorder.close()
    for rid in teachers:
        obs = [json.loads(s) for s in (tmp_path/f'student-{rid}.jsonl').read_text().splitlines()]
        labels = [json.loads(s) for s in (tmp_path/f'teacher-{rid}.jsonl').read_text().splitlines()]
        assert len(obs) == len(labels) == len(list((tmp_path/'rgb'/rid).glob('*.jpg'))) == 3
        assert SCHEMA == 'ugrp.grasp_act.student.v6'
        for row, label in zip(obs, labels):
            validate_observation(row)
            assert row['destination_zone'] == 'B' and row['skill'] == 'release'
            assert row['sample_id'] == label['sample_id']
            assert row['t'] == label['clean_teacher_command']['t']
            assert not any(k in row for k in ('holding_belief', 'teacher_phase', 'contacts', 'pose'))
        assert [v['done'] for v in labels] == [False, False, True]
        assert obs[2]['issued'][-1] == labels[1]['clean_teacher_command']
        assert all((tmp_path/ref['path']).read_bytes() == jpeg for ref in obs[-1]['rgb'])
    assert recorder.record()['prefix_recorded'] is False


def test_render_audit_rejects_mutation_without_restoring_it(monkeypatch):
    world = SimpleNamespace(value=0)
    def render(**kw):
        world.value += 1
        return b'jpeg'
    world.render_jpeg = render
    audit = RenderAudit()
    monkeypatch.setattr(audit, 'state', lambda w: w.value)
    with pytest.raises(RuntimeError, match='mutated'):
        audit.capture(world, 'r1')
    assert world.value == 1 and audit.calls == 0 and audit.changes == 1


def test_native_clock_rejects_dropped_frame(tmp_path):
    from harness.grasp_act_solo_recording import SoloRecorder
    initial = dict(t=0., wheels=[0.]*4, duration_s=[0.]*4,
                   pwm={str(s):1500 for s in (1,3,4,5,6)})
    writer = SoloRecorder(tmp_path, dict(robot_id='r1', kind='long_beam', role='teal', episode_id='e'),
                          initial, destination_zone='A')
    frame = np.zeros((480,640,3), dtype=np.uint8)
    writer.observe(0., b'jpeg', frame, skill='release', phase='open', previous=initial)
    writer.target(initial, skill_after='release', phase_after='open', complete=False)
    with pytest.raises(ValueError, match='period mismatch'):
        writer.observe(.2, b'jpeg', frame, skill='release', phase='open', previous=initial)
    writer.close()


@pytest.mark.parametrize('change', [dict(review_top='on'), dict(render_dr='on_v1'),
                                    dict(release21='off'), dict(release_profile='release18_v1')])
def test_adapter_is_opt_in_and_requires_gate_B(change):
    options = dict(review_top='off', render_dr='off', release21='release21_v1', release_profile='release19_v1')
    validate('off', False, {})
    validate('act12_observer_v1', True, options)
    with pytest.raises(ValueError):validate('act12_observer_v1', True, {**options, **change})
    with pytest.raises(ValueError):validate('act12_observer_v1', False, options)
