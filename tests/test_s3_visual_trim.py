import math
from types import SimpleNamespace
import pytest
from sim.s3_visual_trim import TrimPort,DURATIONS
from scripts.run_s3_x86_pulse_measure import sequence
from harness.zone_solo_cyan_path_heading import command_reason


def port():
    p=object.__new__(TrimPort);p.coupled=lambda:False;p.robot_id='r1'
    p.min_wheel_cmd='real_v1';p.alignment_pulse='real_fine_v1'
    p._set_motors=lambda wheels:setattr(p,'wheels',wheels)
    p._actuator_state=lambda:{}
    return p


def test_measured_lateral_port_keeps_minimum_and_single_axis():
    p=port()
    for duration in DURATIONS:
        action=dict(kind='mecanum',forward=0.,left=.35,turn=0.,duration_s=duration)
        assert p.apply(action,2.)['busy_until']==pytest.approx(2.+duration)
        assert p.wheels==(-.35,.35,.35,-.35)
        assert command_reason(action) is None
    with pytest.raises(ValueError):p.apply(dict(action,forward=.1),2.)
    with pytest.raises(ValueError):p.apply(dict(action,duration_s=.09),2.)
    with pytest.raises(ValueError):p.apply(action,math.nan)


def test_measurement_sequence_is_fixed_bounded_and_passes_actual_motor_port():
    rows=sequence();assert len(rows)==36
    assert rows[:18]==rows[18:]
    p=port()
    for i,row in enumerate(rows):
        assert command_reason(row) is None
        p.apply(row,i*.5)
        assert p._drive_expires_at==pytest.approx(i*.5+row['duration_s'])
    assert len(rows)*.5<=60
