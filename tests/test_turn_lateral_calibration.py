import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from harness import turn_lateral_calibration as m
from harness.self_pulse_rotation import calibrated_model,RotationPulseOdometry
from scripts.run_turn_lateral_calibration import schedule,SEEDS


def calibration():
    base=calibrated_model()
    return dict(option=m.OPTION,fit_seeds=list(SEEDS[:3]),profiles={
        k:dict(lateral_curve_m=(np.array(p['times'])*(.0015 if p['u']<0 else -.0015)).tolist())
        for k,p in base['profiles'].items() if k in ('0:turn:0.35:0.10','0:turn:-0.35:0.10')})


def test_only_measured_turn_lateral_changes_no_yaw_x_noise_or_input_mutation():
    base=calibrated_model();before=json.dumps(base,sort_keys=True);c=calibration();new=m.apply_model(c)
    assert json.dumps(base,sort_keys=True)==before
    for key,p in base['profiles'].items():
        q=new['profiles'][key]
        if key not in c['profiles']:assert q==p
        else:
            np.testing.assert_array_equal(np.array(q['mean_curve'])[:,[0,2]],np.array(p['mean_curve'])[:,[0,2]])
            assert q['prediction_variance']==p['prediction_variance']
            a=RotationPulseOdometry();b=RotationPulseOdometry();b.profiles=new['profiles']
            action=dict(t=0.,kind='mecanum',turn=p['u'],duration_s=.1)
            a.command(action);b.command(action);a.advance(.2);b.advance(.2)
            assert a.pose[0]==pytest.approx(b.pose[0],abs=1e-12)
            assert a.pose[2]==b.pose[2]
            assert b.pose[1]==pytest.approx(c['profiles'][key]['lateral_curve_m'][-1])


def test_eval_seeds_rejected_and_off_does_not_read():
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    c=Poison();assert m.install(c) is c
    bad=calibration();bad['fit_seeds']=[63001]
    with pytest.raises(ValueError,match='INDEPENDENT'):m.apply_model(bad)


def test_calibration_protocol_separate_seeds_and_fixed_bidirectional_squares():
    assert not set(SEEDS)&set(range(63001,63007))
    for seed in SEEDS:
        blocks,commands,ticks=schedule(seed)
        assert set(x['sign'] for x in blocks if x['kind']=='square' and x['axis']=='turn')=={-1,1}
        assert len([x for x in blocks if x['kind']=='square'])==16
        assert sum(x['n'] for x in blocks)==330
        assert len(commands)==330 and max(commands)+4<ticks


def test_square_validation_integrates_actual_schedule_and_preserves_model():
    from scripts.analyze_turn_lateral_squares import model_displacement
    base=calibrated_model();before=json.dumps(base,sort_keys=True)
    cmd={0:dict(kind='mecanum',turn=.35,duration_s=.1)}
    got=model_displacement(cmd,0,4,base)
    np.testing.assert_allclose(got,base['profiles']['0:turn:0.35:0.10']['mean_delta'],atol=1e-12)
    assert json.dumps(base,sort_keys=True)==before


def test_every_clock_command_passes_actual_real_port_contract_without_physics():
    from sim.s2_real_output import RealPrimitivePort
    from harness.self_pulse_odom import model,profile_key
    p=object.__new__(RealPrimitivePort)
    p.min_wheel_cmd='real_v1';p.robot_id='r3'
    p._set_motors=lambda motors:None;p._actuator_state=lambda:{}
    for seed in SEEDS:
        _,commands,_=schedule(seed)
        for t,cmd in commands.items():
            assert profile_key(cmd,False) in model()['profiles']
            assert p.apply(cmd,t/20)['ok']


def test_CAD_swept_radius_rejects_old_north_start_and_admits_central_fixture():
    from scripts.run_turn_lateral_calibration import preflight
    with pytest.raises(ValueError,match='INTERSECTS_WALL'):preflight(70001,[3.5,1.1,0.])
    for seed in (70001,70002):
        record=preflight(seed)
        assert record['minimum_clearance_m']>.5 and record['cad_radius_m']>.15
