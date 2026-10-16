import copy
import pytest
from scripts.audit_s2_formal_stops import decisions, truth_at, uncertain


def test_exact_alarm_reconstruction_includes_arrivals_and_sparse_receipts():
    p=dict(std_xy_m=.06,std_yaw_rad=.01,last_fix_t=0.)
    record=dict(poses=[dict(t=t,**p) for t in (1.,2.,3.)],
        pulse_motion_model=dict(transformations=[dict(t=1.,state='search_move'),dict(t=2.,state='carry')]),
        events=[dict(event='carry_checkpoint',t=3.),dict(event='dev_light_would_stop',code='POSE_UNCERTAIN',t=1.,occurrence=1)],
        dev_light_would_stop=dict(POSE_UNCERTAIN=3))
    assert [q['phase'] for q in decisions(record)]==['start_approach','carry','carry']
    wrong=copy.deepcopy(record);wrong['dev_light_would_stop']['POSE_UNCERTAIN']=2
    with pytest.raises(AssertionError):decisions(wrong)
    wrong=copy.deepcopy(record);wrong['events'][-1]['t']=2.
    with pytest.raises(AssertionError):decisions(wrong)


def test_gt_score_time_is_explicit_no_silent_endpoint_clamping():
    truth=[dict(t=0.,robot_xyz_m=[0,0,0],robot_yaw_rad=3.1),
           dict(t=2.,robot_xyz_m=[2,4,0],robot_yaw_rad=-3.1)]
    assert truth_at(truth,1.)[:2]==[1.,2.]
    assert truth_at(truth,1.)[2]==pytest.approx(3.141592653589793)
    with pytest.raises(ValueError):truth_at(truth,-.1)
    assert uncertain(dict(std_xy_m=.05,std_yaw_rad=0.,last_fix_t=None))
    assert not uncertain(dict(std_xy_m=.05,std_yaw_rad=0.,last_fix_t=0.))
