import json,math
import numpy as np
import pytest
from harness import goal_route_p0 as p


def grid():return dict(robot_id='r3',resolution_m=.1,cells=[])
def feature():return dict(height_m=.23,fy=622,contrast=100,band_std=0,sharpness=100,body_settling=1)
def scan(fid,pose=(0,0,0)):
    return dict(frame_id=fid,t=fid,pose=list(pose),camera=[0,0],segments=[[[1,-.2],[1,.2]]],features=[feature()],insertion_weights=[.8],covariance=np.zeros((3,3)).tolist())


def test_off_does_not_inspect_inputs_and_is_byte_identical():
    original={'untouched':[1,2.5,None],'accepted':True};before=json.dumps(original).encode()
    assert p.hygiene(original,None,None) is original
    assert p.accumulate(original,None,None,None,None,None) is original
    assert p.gate_match(original,None,None) is original
    assert p.pitch_sample(original,reading=None,camera_origin=None,nominal_ray=None,wall_normal=None) is original
    assert json.dumps(original).encode()==before


def test_sequence_can_only_reject_and_requires_order_and_history():
    a={'accepted':True,'reason':'accepted'}
    assert p.gate_match(a,[1,2,3],[3,2,1],place_gate=p.SEQUENCE)['accepted']
    assert not p.gate_match(a,[1,2],[1,2],place_gate=p.SEQUENCE)['accepted']
    assert not p.gate_match(a,[1,2,3],[1,3,2],place_gate=p.SEQUENCE)['accepted']
    assert not p.gate_match({'accepted':False},[1,2,3],[1,2,3],place_gate=p.SEQUENCE)['accepted']
    rows=[dict(t=i,features=[dict(kind='floor_line',hue=h,endpoints=[[0,0],[1,0]])]) for i,h in enumerate([1,1,2,3,4])]
    assert p.color_sequence(rows,3)==[1,2,3]


def test_hygiene_distinct_node_support_swept_free_far_no_hit():
    a=scan(1);b=scan(2,(0,.31,0));b['segments']=[[[1,-.51],[1,-.11]]]
    one=p.hygiene(grid(),[a],[a],route_hygiene=p.HYGIENE)
    assert not any(v>0 for x,y,v in one['cells'])
    both=p.hygiene(grid(),[a,b],[a,b],route_hygiene=p.HYGIENE)
    assert any(v>0 for x,y,v in both['cells'])
    cells={(x,y):v for x,y,v in both['cells']}
    assert all(cells[c]<0 for c in p.footprint_cells([0,0,0]))
    far=scan(1);far['segments']=[[[3,-.2],[3,.2]]]
    q=p.hygiene(grid(),[far],[far],route_hygiene=p.HYGIENE)
    assert not any(v>0 for x,y,v in q['cells'])
    assert q['route_hygiene']['far_free_samples']>0
    assert max(x for x,y,v in q['cells'])<=25


def test_accumulation_flushes_only_at_keyframe_no_duplicate_hit_or_rejected_scan():
    obs=[scan(i) for i in range(1,5)]
    decisions=[dict(frame_id=i,reason=r) for i,r in enumerate(['gmapping_motion_gate','low_overlap','accepted','gmapping_motion_gate'],1)]
    dr={i:[0,0,0] for i in range(1,5)}
    result=p.accumulate(grid(),[obs[2]],obs,obs,dr,decisions,scan_accumulation=p.ACCUMULATE)
    assert result['scan_accumulation']['integrated_frame_ids']==[1,3]
    assert result['scan_accumulation']['unflushed']==1
    assert result['scan_accumulation']['keyframes']==1
    from harness.self_odom_grid import OdomGrid
    assert max(v for x,y,v in result['cells'])<=OdomGrid('r3').hit


@pytest.mark.parametrize('bias',[-.87,.87])
def test_ultrasound_recovers_known_pitch_sign_without_truth_input(bias):
    from harness.ultrasonic_model import DEFAULT_SPEC
    origin=np.array([.1,0,.23]);true_ray=np.array([2.,0,0])-origin
    a=math.radians(bias);c,s=math.cos(a),math.sin(a)
    # Inverse of the estimator's positive elevation rotation.
    nominal=true_ray@np.array([[c,0,-s],[0,1,0],[s,0,c]])
    result=p.pitch_sample(None,reading=dict(valid=True,range_m=2-DEFAULT_SPEC.face_x_m),
        camera_origin=origin,nominal_ray=nominal,wall_normal=[1,0],pitch_bias=p.PITCH)
    assert result['accepted']
    assert math.degrees(result['pitch_offset_rad'])==pytest.approx(bias,abs=1e-7)


def test_synthetic_sensor_invalid_uses_native_json_protocol():
    from harness.ultrasonic_model import invalid,NO_ECHO
    reading=invalid(1.,NO_ECHO).as_dict()
    assert json.loads(json.dumps(reading,allow_nan=False))['range_m'] is None
    assert not p.pitch_sample(None,reading=reading,camera_origin=None,nominal_ray=None,wall_normal=None,pitch_bias=p.PITCH)['accepted']
