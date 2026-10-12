import json
import math
from types import SimpleNamespace
import pytest
from scripts import run_s3_capture_diagnostic as r
from sim.s3_capture_diagnostic import DiagnosticPort, PhysicsBackend, OPTION


def test_grid_complete_unique_and_eval_setup_only():
    for robot in ('r1','r2','r3'):
        rows=[p for y in range(3) for p in r.capture_grid(robot,y)]
        assert len(rows)==75 and len({(p['dx'],p['dy'],p['dyaw']) for p in rows})==75
        nominal=r.capture_setup(dict(robot=robot,dx=0.,dy=0.,dyaw=0.))
        shifted=r.capture_setup(dict(robot=robot,dx=.012,dy=.024,dyaw=.14))
        assert shifted['runtime_gt'] is False
        for peer in ('r1','r2','r3'):
            if peer!=robot:assert nominal['robots'][peer]==shifted['robots'][peer]
        assert nominal['truth']==shifted['truth']
        from harness.zone_final_pair_vision import GRASP_RADIUS_M as radius
        q0=nominal['robots'][robot]['pose'];q1=shifted['robots'][robot]['pose']
        a0,a1=q0['robot_yaw_rad'],q1['robot_yaw_rad']
        gx=q0['robot_xyz_m'][0]+radius*math.cos(a0)
        gy=q0['robot_xyz_m'][1]+radius*math.sin(a0)
        dx,dy=gx-q1['robot_xyz_m'][0],gy-q1['robot_xyz_m'][1]
        assert math.cos(a1)*dx+math.sin(a1)*dy-radius==pytest.approx(.012)
        assert -math.sin(a1)*dx+math.cos(a1)*dy==pytest.approx(.024)
        assert a1-a0==pytest.approx(.14)


def test_open_loop_tape_uses_existing_postures_and_finite_horizon():
    from harness.owncam_pair_beam_v2 import pose_of
    from harness.zone_final_pair_vision import grasp_postures
    tape,timing=r.arm_tape({1:2000,**pose_of('inspect')})
    assert timing['close_start']<timing['lift_start']<timing['settled_at']<12
    last={sid:p for _,sid,p in sorted(tape)}
    assert last=={1:1500,**grasp_postures()[0]}
    assert set(last)=={1,3,4,5,6}


def test_diagnostic_actual_apply_and_reject_short_mixed_nonfinite():
    port=DiagnosticPort.__new__(DiagnosticPort)
    port.robot_id='r1';wheels=[];port._set_motors=wheels.append;port._actuator_state=lambda:{}
    sequence=r.low_sequence();assert len(sequence)==48
    for action in sequence:
        got=port.apply(action,1.);assert got['busy_until']==1.1
        assert max(map(abs,wheels[-1])) in (.15,.20,.25,.35)
    for bad in (dict(sequence[0],duration_s=.06),dict(sequence[0],left=.2),dict(sequence[0],turn=float('nan'))):
        with pytest.raises(ValueError):port.apply(bad,1.)


def test_low_speed_capability_cannot_enable_on_student_and_off_delegates(monkeypatch):
    from sim.s3_capture_diagnostic import Previous
    monkeypatch.setattr(Previous,'reset',lambda self,cap:17.)
    host=PhysicsBackend.__new__(PhysicsBackend);host.bundle={};host.ports={'r1':object()}
    before=dict(host.ports);assert host.reset(1.)==17. and host.ports==before
    for student in (None,True):
        host.bundle=dict(diagnostic_low_pulse=OPTION,student_control=student)
        with pytest.raises(ValueError,match='forbids student'):host.reset(1.)


def test_frozen_whole_batch_has_all_capture_and_low_pulse_cases():
    from scripts.run_s3_capture_cohort import PLAN,commands
    plan=json.loads(PLAN.read_text());rows=commands(plan,'a'*40)
    assert len(rows)==15 and plan['max_simultaneous']==10 and plan['LP_NUM_THREADS']==4
    assert sum(x['kind']=='capture' for x,a in rows)==9
    assert sum(x['kind']=='pulse' for x,a in rows)==6
    assert all('--execute' in a and 'outputs/'+x['name']+'/raw' in a for x,a in rows)
    assert len(r.low_sequence())==48 and all(x['duration_s']==.1 for x in r.low_sequence())


def test_capture_selection_requires_whole_region_and_physical_pulse_fit():
    from scripts.evaluate_s3_capture_diagnostic import admissible_box
    trials=[dict(grid=g,status='COLLECTED',grasp=True,lift=True)
        for y in range(3) for g in r.capture_grid('r1',y)]
    q=admissible_box(trials,[.013,.014,.11]);assert q['admissible']
    assert q['selected_capture_box']['inner_halfwidth_m_m_rad']==[.019200000000000002,.019200000000000002,.11200000000000002]
    assert not admissible_box(trials,[.020,.014,.11])['admissible']
    nominal=next(t for t in trials if t['grid']['dx']==t['grid']['dy']==t['grid']['dyaw']==0.)
    nominal['lift']=False;assert not admissible_box(trials,[.013,.014,.11])['admissible']
    with pytest.raises(ValueError):admissible_box(trials[:-1],[.013,.014,.11])


def test_diagnostic_bundle_records_the_actual_base_supervisor():
    b=r.bundle('0'*40,'capture',0)
    assert b['case']=='pair' and b['student_control'] is False
    assert b['physical_supervisor']=='S3_drop_tilt_nonfinite_v1'
    assert b['diagnostic_low_pulse']=='off'
    assert r.bundle('0'*40,'pulse',0)['diagnostic_low_pulse']==OPTION
