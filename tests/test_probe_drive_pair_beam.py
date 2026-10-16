import copy
import math
import pytest
from scripts.probe_drive_pair_beam import design,StopGuard,PhysicalStop,deltas


def row():
    return dict(t=0.,beam_tilt_deg=0.,robot_tilt_deg={'r1':0.,'r2':0.},beam_min_z_m=.15,
        beam_floor_contacts=0,finger_n={'r1':[3.,3.],'r2':[3.,3.]},
        beam_xyz=[3.,-1.,.15],beam_yaw_rad=math.radians(179),
        robot_xyz={'r1':[2.5,-1.,0.],'r2':[3.5,-1.,0.]},
        grip_in_beam_m={'r1':[-.27,0.,.024],'r2':[.27,0.,.024]})


def test_abort_latches_lift_and_detects_drop_tilt_and_persistent_grip_loss():
    p=design();g=StopGuard(p);r=row();r['beam_min_z_m']=0.
    g.check(r)  # authored floor preparation is not a drop
    r['beam_min_z_m']=.15;g.check(r)
    r['finger_n']['r2']=[0.,3.];r['t']=1.;g.check(r)
    r['t']=1.2;g.check(r)  # unchanged teacher .3s debounce
    r['t']=1.31
    with pytest.raises(PhysicalStop,match='GRIP_LOSS_r2'):g.check(r)
    r=row();r['beam_min_z_m']=.004
    with pytest.raises(PhysicalStop,match='LOAD_DROP'):g.check(r)
    r=row();r['robot_tilt_deg']['r1']=10.
    with pytest.raises(PhysicalStop,match='TILT_LIMIT'):StopGuard(p).check(r)


def test_metrics_use_post_staging_reference_world_progress_and_beam_frame_slip():
    a=row();b=copy.deepcopy(a)
    b['beam_xyz'][1]+=.02;b['beam_yaw_rad']=math.radians(-179)
    b['robot_xyz']['r1'][1]+=.03;b['robot_xyz']['r2'][1]+=.01
    b['grip_in_beam_m']['r1'][2]-=.002
    v=deltas(a,b)
    assert v['beam_delta_m']==pytest.approx([0,.02,0])
    assert v['beam_yaw_change_deg']==pytest.approx(2.)
    assert v['progress_difference_m']==pytest.approx(.02)
    assert v['grip_slip_m']==pytest.approx({'r1':.002,'r2':0})


def test_standard_staging_and_asymmetric_schedule_are_profile_independent():
    from harness.zone_pair_highpose_staging import PREROLLS
    from harness.zone_final_pair_excitation import LOADED_BEAM_POSE
    from sim.workflow_manager import plan
    from pathlib import Path
    p=design()
    assert p['staging']==PREROLLS['high_held']
    assert p['beam_pose']==LOADED_BEAM_POSE
    assert p['command']=={'r1':[-.35,.35,.35,-.35],'r2':[0.,0.,0.,0.]}
    for profile in ('legacy_wrench','masterpi_drive_friction_v7'):
        q=plan(Path(__file__).resolve().parents[1],'masterpi-drive-friction-probe',
            ['--expected-source-sha','0'*40,'--drive-profile',profile,'--pair-beam'])
        assert '--pair-beam' in q['command'] and not q['execution_started']
