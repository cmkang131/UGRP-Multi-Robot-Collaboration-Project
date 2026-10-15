import math
import pytest
from test_reloc9_carry import pose
from sim.grasp_act_port import duty_wheels
from harness.reloc10_rotation import calibration


def test_direction_gains_default_off_and_single_shared_integration():
    a, b, c = pose(), pose(reloc10_rotation_calibration_v1=False), pose(reloc10_rotation_calibration_v1=True)
    for i, drive in enumerate(([0,0,.065], [0,0,-.065], [.1,0,.02], [0,0,0])):
        wheels, durations = duty_wheels(drive)
        command = dict(t=i*.1,wheels=wheels,duration_s=durations)
        for p in (a,b,c): p.issue(command,.1)
        assert a.record() == b.record()
        gain = calibration()['left_scale' if drive[2]>0 else 'right_scale'] if i<2 else 1.
        assert c.last_delta[2] == pytest.approx(a.last_delta[2]*gain)
        assert c.cached_delta(command,.1) == c.last_delta
        assert c.last_delta[:2] == a.last_delta[:2]
    assert c.record()['rotation_error_fraction'] >= .4
    with pytest.raises(ValueError): pose(reloc9_rotation_calibration_v1=True,reloc10_rotation_calibration_v1=True)


def test_four_rotation_holdouts_and_matched_seed_layouts():
    import json
    from pathlib import Path
    from scripts.run_reloc10_rotation_check import TARGETS_DEG
    from scripts.run_solo_grasp_act_teacher import validate_carry
    assert TARGETS_DEG == (90.,-90.,180.,-180.)
    es=json.loads(Path('experiments/2026-10-15-reloc10/diagnostic-plan.json').read_text())['episodes']
    assert len(es)==22
    for a,b in zip(es[::2],es[1::2]):
        assert a['seed']==b['seed'] and a['spawns']==b['spawns'] and a['cargo_pose_m']==b['cargo_pose_m']
        for e in (a,b): validate_carry(e,enabled=True,training_rgb=False,truth_free=True,lift='solo_lift_lookback_v1',negative=False)


def test_disabled_queues_four_turn_gate_then_matched_layouts():
    from scripts.prepare_reloc10_queues import carry_queue,selfmap_queue
    flags=('approved','enabled','ready','stage_ready','execute','submitted')
    a,b=carry_queue('a'*40),selfmap_queue('b'*40)
    assert a['max_parallel']==b['max_parallel']==16
    assert len(a['runs'])==23 and len(b['runs'])==5
    assert a['runs'][0]['targets_deg']==[90.,-90.,180.,-180.]
    assert [r['seed'] for r in b['runs']]==[93571,93580,93581,93582,93583]
    for q in (a,b):
        for obj in [q,q['coordinator_approval'],*q['runs'],*q['execution_stages']]:
            assert all(obj[k] is False for k in flags)
        assert not q['previous_results_combinable']
        assert all('--execute' not in r['command'] for r in q['runs'])
