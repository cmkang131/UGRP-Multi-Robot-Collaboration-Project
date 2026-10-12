import base64,hashlib,json
from pathlib import Path
import cv2,numpy as np,pytest
from harness.active_camera import SEARCH,transform
from harness.e2e_camera_load import using,OPTION,qualification
from harness.servo_camera_fk import transform_from_commands


def test_closed_command_explicit_nominal_does_not_fabricate_joints_or_load():
    opened=transform(SEARCH);closed={**SEARCH,1:1500}
    with pytest.raises(ValueError,match='loaded_or_unknown'):transform(closed)
    with using(OPTION):
        observed=transform(closed)
        for a,b in zip(opened,observed):np.testing.assert_array_equal(a,b)
        _,reason=transform_from_commands(closed,camera_pose='servo_fk_v1')
        assert reason=='servo_fk_nominal_load_unknown_unqualified'
        q=qualification(closed)
        assert not q['actual_joint_state_observed'] and not q['actual_load_observed']
        assert not q['loaded_geometry_qualified'] and not q['load_deformation_compensated']
        with using('off'):
            with pytest.raises(ValueError,match='loaded_or_unknown'):transform(closed)
    with pytest.raises(ValueError,match='loaded_or_unknown'):transform(closed)


def test_actual_live_closed_grip_receive_retains_command_and_records_scope():
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options
    profile=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    robot=Robot('r1',61004,profile,Options())
    robot.camera_load=OPTION
    robot.commanded(dict(kind='arm',servo_id=1,pulse=1500),0.)
    rgb=np.zeros((480,640,3),np.uint8);_,buf=cv2.imencode('.jpg',rgb);data=buf.tobytes()
    trace=robot.receive(dict(frame_id=1,sim_time=.4,sha256=hashlib.sha256(data).hexdigest(),image=base64.b64encode(data).decode()),rgb)
    assert robot.servo[1]==1500 and trace['camera_geometry']['grip_command_closed']
    assert trace['camera_geometry']['loaded_geometry_qualified'] is False
    robot.camera_load='off'
    with pytest.raises(ValueError,match='loaded_or_unknown'):
        robot.receive(dict(frame_id=2,sim_time=.8,sha256=hashlib.sha256(data).hexdigest(),image=base64.b64encode(data).decode()),rgb)


def test_v227_source_registered_and_default_v226_unchanged():
    from scripts.run_e2e_ownmap_live import bundle
    from tests.test_e2e18 import options,ROOT
    from harness.e2e_runtime_registration import require_current
    kw=dict(**options(),speed5='lean_v3',observation_cadence='on_v1',route_guard='dev_nominal_v1',beam_axis='undirected_v1',route_coverage='native_v1',carrier_axes='beam_v1',carrier_approach='standoff_v1',route_extent='goal_envelope_v1',record_scalars='python_v1',pose_guard='se2_innovation_v1',protocol_recovery='envelope_retry_v1')
    base=bundle('a'*40,61004,'study_gemma4_31b_v1',**kw)
    assert base['execution_bundle_id']=='e2e18-v226'
    new=bundle('a'*40,61004,'study_gemma4_31b_v1',**kw,camera_load=OPTION,route_tokens='1600_v1')
    require_current(new,ROOT);assert new['execution_bundle_id']=='e2e18-v227'
    assert 'harness/e2e_camera_load.py' in new['source_sha256']
    new['e2e_options']['camera_load']='off'
    with pytest.raises(ValueError,match='CAMERA_LOAD'):require_current(new,ROOT)


def test_output_budget_records_finite_override_preserves_registry_and_completion_gate():
    from harness.e2e_route_tokens import profile_override
    from harness.llm_completion import assess_completion,normal_completion
    original=dict(model=dict(model='gemma-4-31b-it',max_tokens=800,temperature=.2))
    changed=profile_override(original,'1600_v1')
    assert changed['model']['max_tokens']==1600 and original['model']['max_tokens']==800
    assert profile_override(original) is original
    truncated=assess_completion(dict(choices=[dict(finish_reason='length',message=dict(content='{"request_id":"cut'))]),study_json=True)
    assert not normal_completion(truncated)
