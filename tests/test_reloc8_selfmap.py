from dataclasses import replace
from types import SimpleNamespace
import numpy as np
import pytest
from harness.active_relocalization import OPTION, LOOK
from harness.self_map_integration import Options
from harness.self_map_executor import SelfMapExecutor
from test_self_map_integration import fixture_mapper
from test_self_map_executor import Sweep


def test_toggle_requires_existing_safety_and_bundle_roundtrip():
    from scripts.run_self_map_diagnostic import bundle
    assert Options().active_relocalization == 'off'
    with pytest.raises(ValueError): Options(active_relocalization=OPTION)
    b = bundle('a'*40, 93570, 30, bootstrap='command_prior_v1', initial_sweep='required_360_v1',
        recovery_profile='selfmap4_recovery_v1', revision_gate='selfmap4_revision_gate_v2',
        multiframe_registration='selfmap4_multiframe_registration_v1',
        correction_safety='selfmap6_correction_safety_v1', active_relocalization=OPTION)
    assert b['check'] == 'selfmap7' and b['options']['active_relocalization'] == OPTION


def test_recovery_issues_real_arm_then_pan_without_pose_or_map_fix(monkeypatch):
    mapper, _ = fixture_mapper(monkeypatch)
    mapper.options = replace(mapper.options, recovery_profile='selfmap4_recovery_v1',
        revision_gate='selfmap4_revision_gate_v2', multiframe_registration='selfmap4_multiframe_registration_v1',
        correction_safety='selfmap6_correction_safety_v1', active_relocalization=OPTION)
    calls = []
    static = dict(obstacles=[dict(kind='wall', center_m=[1.5, 0], half_extents_m=[.05, 2])],
                  regions={}, passages=[])
    mapper.registration = SimpleNamespace(begin_sweep=lambda t:calls.append(t),
        static=static, last=dict(world_pose=[0, 0, 0], covariance=(np.eye(3)*.01).tolist()), active_hypotheses=[])
    mapper.servo = {1:2000, 3:740, 4:2320, 5:1320, 6:1500}
    c = SelfMapExecutor('r1', mapper=mapper, sweep=Sweep(), cap_s=180)
    c.stage = 'drive'; c.relocalize(20., {}, 'path_blocked_or_no_progress')
    assert calls == [20.] and c.stage == 'active_reloc8'
    arm = c.active_look(20., np.zeros(3))
    assert arm == dict(t=20., kind='arm', servo_id=3, pulse=LOOK[3])
    mapper.servo[3] = LOOK[3]
    assert c.active_look(20.5, np.zeros(3))['kind'] == 'hold'
    assert c.active_look(21., np.zeros(3))['kind'] == 'look'
    assert c.recovery_attempts == 1 and c.active_count == 0
    assert c.events[-1]['view']['predicted_only']


def test_new_queue_serial_no_execution_flags_or_texture_dependency():
    from scripts.prepare_selfmap7_queue import make_queue
    q=make_queue('a'*40)
    assert [r['cap_sim_s'] for r in q['runs']]==[30,180,180]
    assert q['runs'][0]['depends_on'] is None
    for a,b in zip(q['runs'],q['runs'][1:]):assert b['depends_on']==a['name']
    for obj in [q,q['coordinator_approval'],*q['runs'],*q['stages']]:
        assert all(obj[k] is False for k in ('approved','enabled','ready','stage_ready','execute','submitted'))
    assert all('--execute' not in r['command'] for r in q['runs'])
    assert not q['texture_deferred']['code_dependency_connected']
