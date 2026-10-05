"""Independent expectations for R1/R2/R3. XML text/FK and fake clocks only."""
import copy
import json
import math
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_final_pair_contract as c
from harness.zone_final_pair_camera import floor_camera, measurement_label
from harness.zone_final_pair_excitation import design, MAP_ID, AXES
from tests.test_zone_final_pair_v3 import offline_only, SERVO


def rotation(axis, angle):
    axis = np.array(axis, float)
    axis /= np.linalg.norm(axis)
    x,y,z=axis
    cross=np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
    return np.eye(3)+math.sin(angle)*cross+(1-math.cos(angle))*(cross@cross)


def quat_matrix(text):
    q=np.fromstring(text,sep=' '); q/=np.linalg.norm(q)
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


@pytest.mark.parametrize('tilt', [False,True])
def test_transform_chain_pinned_against_v3_robot_xml(monkeypatch, tilt):
    # The XML generator imports a module named mujoco, but no native operation
    # is available: even model compilation/forward/render is forbidden here.
    monkeypatch.setitem(sys.modules,'mujoco',SimpleNamespace())
    from sim.masterpi_model_v3 import build_v3_xml
    from sim.masterpi_dynamics_v2 import MasterPiDynamicsV2
    from sim.masterpi_camera_profile import CAMERA_LOCAL_POS_M, CAMERA_LOCAL_QUAT_WXYZ
    from sim.masterpi_geometry_v3 import PHYSICAL_V3
    root=ET.fromstring(build_v3_xml())
    robot=root.find("worldbody/body[@name='robot']")
    assert robot is not None
    np.testing.assert_allclose(np.fromstring(robot.get('pos'),sep=' '),[0.,0.,PHYSICAL_V3.wheel_radius_m])
    chain=[robot]
    for name in ('arm_base','shoulder_link','elbow_link','wrist_link','gripper'):
        chain.append(chain[-1].find("body[@name='%s']" % name))
        assert chain[-1] is not None
    camera=chain[-1].find("camera[@name='robot_cam']")
    np.testing.assert_allclose(np.fromstring(camera.get('pos'),sep=' '),CAMERA_LOCAL_POS_M)
    np.testing.assert_allclose(quat_matrix(camera.get('quat')),quat_matrix(' '.join(map(str,CAMERA_LOCAL_QUAT_WXYZ))))
    targets=MasterPiDynamicsV2.pulse_to_joint_targets(SimpleNamespace(physical_params={'servo6_center_pwm':1500.}),SERVO)
    angles=dict(zip(('arm_yaw','shoulder','elbow','wrist_pitch'),(targets[k] for k in ('yaw','shoulder','elbow','wrist'))))
    # Chain starts at the actual chassis, NOT the robot XML's world/floor z.
    pc=np.zeros(3); rc=np.eye(3)
    for body in chain[1:]:
        pc += rc@np.fromstring(body.get('pos','0 0 0'),sep=' ')
        rc = rc@quat_matrix(body.get('quat','1 0 0 0'))
        for joint in body.findall('joint'):
            assert joint.get('pos','0 0 0') == '0 0 0'
            rc = rc@rotation(np.fromstring(joint.get('axis'),sep=' '),angles[joint.get('name')])
    pc += rc@np.fromstring(camera.get('pos'),sep=' ')
    rc = rc@quat_matrix(camera.get('quat'))
    base_p=np.array([2.,-1.,.03236 if tilt else PHYSICAL_V3.wheel_radius_m])
    yaw=.7
    yaw_r=rotation([0,0,1],yaw)
    rb=yaw_r@(rotation([0,1,0],.04)@rotation([1,0,0],-.025) if tilt else np.eye(3))
    world_p=base_p+rb@pc; world_r=rb@rc
    label=measurement_label(base_p,rb,world_p,world_r)
    projected=floor_camera(label)
    expected_origin=yaw_r.T@(world_p-np.array([base_p[0],base_p[1],0.]))
    expected_rotation=yaw_r.T@world_r@np.diag([1.,-1.,-1.])
    np.testing.assert_allclose(projected['origin_m'],expected_origin,atol=1e-12)
    np.testing.assert_allclose(projected['rotation'],expected_rotation,atol=1e-12)
    # Both actual consumers receive the composition, including pitch/roll.
    from harness.zone_final_pair_vision import PairVision
    from harness.vision_pose_source_final import camera_key
    import harness.zone_final_pair_vision as v
    monkeypatch.setattr(v,'_pixel_rays',lambda step:(np.array([320]),np.array([400]),np.array([[0.,1.]]),np.array([True])))
    cal={'camera_models':{'unloaded':{camera_key(SERVO):label}}}
    origin,rays,*_=PairVision(cal).base_rays(SERVO)
    np.testing.assert_allclose(origin,expected_origin,atol=1e-12)
    expected_ray=expected_rotation@np.array([0.,1.,1.]); expected_ray/=np.linalg.norm(expected_ray)
    np.testing.assert_allclose(rays[0],expected_ray,atol=1e-12)
    from harness.vision_pose_source_final import measured_column_model
    from harness import vision_loc_protocol as vp
    vl,_=vp.load_vis3()
    model=measured_column_model(vl.mp,c.camera_record(cal,'unloaded',SERVO),np.array([320]))
    for z in (0.,.032):
        observed=origin+rays[0]*(z-origin[2])/rays[0,2]
        expected=expected_origin+expected_ray*(z-expected_origin[2])/expected_ray[2]
        np.testing.assert_allclose(observed,expected,atol=1e-12)
    np.testing.assert_allclose(model.origin,expected_origin,atol=1e-12)


@pytest.mark.parametrize('fault',['missing','wrong_frame','nan','reflection','world_translation','yaw'])
def test_floor_transform_is_required_and_validated(tmp_path,fault):
    from tests.test_zone_final_pair_v3 import synthetic
    path,cal=synthetic(tmp_path)
    record=next(iter(cal['camera_models']['unloaded'].values()))
    if fault=='missing': del record['chassis_to_floor']
    elif fault=='wrong_frame': record['frame']='floor'
    elif fault=='nan': record['chassis_to_floor']['origin_m'][2]=float('nan')
    elif fault=='reflection': record['chassis_to_floor']['rotation'][0][0]=-1
    elif fault=='world_translation': record['chassis_to_floor']['origin_m'][0]=1
    elif fault=='yaw': record['chassis_to_floor']['rotation']=rotation([0,0,1],.2).tolist()
    with pytest.raises(ValueError): floor_camera(record)


def test_camera_height_is_validated_in_floor_frame_not_chassis_frame():
    from harness.vision_pose_source_final import camera_key
    record = {'frame': 'optical_to_actual_chassis', 'origin_m': [.15, 0., -.01],
              'rotation': np.eye(3).tolist(),
              'chassis_to_floor': {'origin_m': [0., 0., .03236], 'rotation': np.eye(3).tolist()}}
    cal = {'camera_models': {'unloaded': {camera_key(SERVO): record}}}
    assert c.camera_record(cal, 'unloaded', SERVO)['origin_m'][2] == pytest.approx(.02236)
    record['origin_m'][2] = -.04
    with pytest.raises(ValueError, match='above the floor'):
        c.camera_record(cal, 'unloaded', SERVO)


@pytest.mark.parametrize('check',c.CHECKS[2:])
def test_actual_schedule_matches_hammerstein_design_and_budget(check):
    from harness.zone_final_pair_calibration import schedule
    from sim.camera_robot_port import validate_raw_action
    plan=design(check)
    rows=[e for e in schedule(check) if e['robot_id']=='r1' and e['action']['kind']=='mecanum']
    expected=[]
    for s in plan['segments']:
        assert s['phase']!='step' or s['duration_s']>=10
        expected.extend([tuple(s['value'] if a==s['axis'] else 0. for a in AXES)]*round(s['duration_s']/.05))
    assert [tuple(e['action'][a] for a in AXES) for e in rows]==expected
    np.testing.assert_allclose(np.diff([e['t'] for e in rows]),.05,atol=1e-12)
    for e in schedule(check): validate_raw_action(e['action'],allow_reverse=True,allow_mecanum=True)
    assert max(e['t']+e['action'].get('duration_s',0) for e in schedule(check))<370
    assert c.cases(check)==[{'id':MAP_ID,'map_id':MAP_ID,'checkpoint':None,'sim_cap_s':370.}]
    assert sum(r['sim_cap_s']+5 for r in c.cases(check))==375
    if check != 'calibration-unloaded':
        with pytest.raises(ValueError): c.cases(check,c.registry()['maps'][0])
    if check=='calibration-loaded':
        paired=[e for e in schedule(check) if e['robot_id']=='r2' and e['action']['kind']=='mecanum']
        for a,b in zip(rows,paired):
            assert a['t']==b['t']
            np.testing.assert_allclose([a['action'][k] for k in AXES],[-b['action'][k] for k in AXES])


def fake_guard(monkeypatch,loaded=False):
    from sim.final_pair_v3 import PhysicsBackend
    names=['r1__body','r2__body','beam_geom']
    monkeypatch.setitem(sys.modules,'mujoco',SimpleNamespace(mj_id2name=lambda m,t,i:names[i],mjtObj=SimpleNamespace(mjOBJ_GEOM=1)))
    obj=PhysicsBackend.__new__(PhysicsBackend)
    obj.bundle={'check':'calibration-loaded' if loaded else 'calibration-fine','map_sha256':'test'}
    obj.scene=SimpleNamespace(config={'static_map':c.resolve(MAP_ID)[0]})
    positions=np.array([[3.0768,-.85,.1],[4.0232,-.85,.1],[3.55,-.85,.1]])
    d=SimpleNamespace(time=0.,geom_xpos=positions,body=lambda name:SimpleNamespace(xpos=positions[0 if name=='r1__robot' else 1]))
    m=SimpleNamespace(ngeom=3,geom_rbound=np.array([.1,.1,.31]),geom_bodyid=[0,1,2],body=lambda n:SimpleNamespace(id=2))
    obj.world=SimpleNamespace(model=m,data=d,robot=lambda r:None)
    obj._last_guard_xy={}; obj.saved=[]; obj.held=[]; obj.ticked=[]
    obj.ports={r:SimpleNamespace(hold=lambda t,r=r:obj.held.append(r),tick=lambda t:obj.ticked.append(t)) for r in ('r1','r2')}
    obj._append=lambda p,row:obj.saved.append((p,row))
    obj.dt=.01;obj.deadline=.05
    return obj


@pytest.mark.parametrize('fault',['wall','nan','missing_geometry','envelope','jump','beam_wall'])
def test_collection_clearance_aborts_and_holds_no_command_repair(monkeypatch,fault):
    obj=fake_guard(monkeypatch,True)
    obj.collection_guard()
    if fault=='wall': obj.world.data.geom_xpos[0,0]=2.4
    elif fault=='nan': obj.world.data.geom_xpos[0,0]=float('nan')
    elif fault=='missing_geometry': obj.world.model.ngeom=0
    elif fault=='envelope': obj.world.model.geom_rbound[0]=.5
    elif fault=='jump': obj.world.data.geom_xpos[0,0]+=.02
    elif fault=='beam_wall': obj.world.data.geom_xpos[2,0]=2.4
    with pytest.raises(ValueError): obj.collection_guard()
    assert obj.held==['r1','r2']
    assert obj.saved[0][0]=='eval_only/clearance_abort.jsonl'


def test_clearance_checks_between_samples_and_while_coasting(monkeypatch):
    obj=fake_guard(monkeypatch)
    calls=[]
    def step(_):
        obj.world.data.time+=.01
        calls.append(obj.world.data.time)
        # Intermediate crossing: endpoints at 0/0.05 alone would miss it.
        obj.world.data.geom_xpos[0,0]=2.4 if obj.world.data.time>=.02 else 3.0768
    obj.world._physics_step_for=step
    with pytest.raises(ValueError,match='CLEARANCE_ABORT'):obj.advance_to(.05)
    assert calls==[.01,.02] and obj.held==['r1','r2']


def test_no_clearance_truth_channel_for_student(monkeypatch):
    obj=fake_guard(monkeypatch)
    obj.bundle['check']='p03'
    obj.world=None
    assert obj.collection_guard() is None


def test_bundle_clocks_are_exactly_the_applied_loop_values(tmp_path, monkeypatch):
    from scripts import run_final_pair_v3 as run
    # Fake clocks with real collection admission.
    run_case = run.run_case
    from tests.test_zone_final_pair_v3 import FakePhysics,FakeRuntime
    for check,period,cap in [('p03',.05,120.),('calibration-fine',.2,370.)]:
        row=c.cases(check)[0];b={**c.bundle(row['map_id'],check),'case':row}
        made=[];arm_times=[]
        class Runtime(FakeRuntime):
            def arm_step(self,now):
                arm_times.append(now)
                return []
        def factory(*a,**kw):
            obj=FakePhysics(*a,**kw);made.append(obj);return obj
        result=run_case(b,tmp_path/check,seed=1,backend_factory=factory,runtime_factory=Runtime)
        assert result['protocol_complete']
        assert result['timing']==b['timing']
        assert b['timing']['rgb_capture_period_s']==period
        np.testing.assert_allclose(np.diff(made[0].frames),period,atol=1e-12)
        np.testing.assert_allclose(np.diff(made[0].samples),b['timing']['eval_pose_period_s'],atol=1e-12)
        assert len(made[0].frames)==round(cap/period)+1
        if check=='p03':
            np.testing.assert_allclose(arm_times,1.+np.arange(2400)*.05,atol=1e-12)
        else:
            assert not arm_times


def test_offline_hammerstein_evidence_and_actual_schedule_have_same_design():
    from scripts.check_pair_v88_identifiability import response
    # Exact first-order integral with subtractive deadband: a command below
    # threshold never moves; analytical step displacement is independent proof.
    times=np.arange(201)*.05
    np.testing.assert_allclose(response([(10.,.02)],.05,.84,.08,.005),
                               .015*(times-.84*(1-np.exp(-times/.84))),atol=1e-12)
    assert not response([(10.,.004)],.05,.84,.08,.005).any()
    evidence=json.loads((c.ROOT/'experiments/2026-10-01-v3-pair-adapter/identifiability_v2.json').read_text())
    assert evidence['status']=='SYNTHETIC_DESIGN_ONLY' and evidence['passed']
    for check,axes in evidence['profiles'].items():
        for name,row in axes.items():
            assert row['fisher_rank']==row['parameter_count']
            assert row['practically_separated']
            axis='forward' if name=='runtime_ramp' else name
            assert row['samples']==1+round(sum(s['duration_s'] for s in design(check)['segments'] if s['axis']==axis)/.05)


@pytest.mark.parametrize('check', c.CHECKS[2:])
def test_unsafe_start_rejects_all_entry_points_before_output_or_physics(tmp_path, monkeypatch, capsys, check):
    from scripts import run_final_pair_v3 as run
    from sim.final_pair_v3 import PhysicsBackend
    from harness.zone_final_pair_clearance import CLEARANCE_REVIEW
    from harness import zone_final_pair_calibration as cal, zone_final_pair_excitation as excitation
    if check == 'calibration-loaded':
        starts = cal.teacher_stations(c.resolve(MAP_ID)[0])
        starts['r1'][0] = 2.3
        monkeypatch.setattr(cal, 'teacher_stations', lambda _: starts)
    else:
        monkeypatch.setattr(excitation, 'UNLOADED_POSE', [2.3, -.85, 0.])
    row = c.cases(check)[0]
    bundle = {**c.bundle(row['map_id'], check), 'case': row}
    assert CLEARANCE_REVIEW in bundle['source_sha256']
    assert not bundle['clearance_preflight']['admitted']
    args = ['--check', check, '--expected-source-sha', 'a'*40, '--output', str(tmp_path/'raw')]
    assert run.main(args) == 0
    plan = json.loads(capsys.readouterr().out)
    assert not plan['runnable']
    assert plan['blocked_on'][0].startswith(
        'COLLECTION_PREFLIGHT_REJECTED: START_POSE_TOO_CLOSE_TO_WALL')
    assert plan['clearance_preflight'][0] == bundle['clearance_preflight']
    # Neither a fake saved PASS nor a direct owner constructor may bypass the
    # recomputed start check. Imports themselves are sentinels.
    bundle['clearance_preflight']['admitted'] = True
    monkeypatch.setitem(sys.modules, 'sim.zone_final_v3_scene', None)
    monkeypatch.setitem(sys.modules, 'sim.final_pair_v3', None)
    def forbidden(*args, **kwargs):
        pytest.fail('reached source/lock/backend work before clearance rejection')
    monkeypatch.setattr(run, 'check_source', forbidden)
    with pytest.raises(ValueError, match='COLLECTION_PREFLIGHT_REJECTED'):
        run.main(args + ['--execute'])
    with pytest.raises(ValueError, match='COLLECTION_PREFLIGHT_REJECTED'):
        run.run_case(bundle, tmp_path/'case', seed=911, backend_factory=forbidden)
    with pytest.raises(ValueError, match='COLLECTION_PREFLIGHT_REJECTED'):
        PhysicsBackend(bundle, tmp_path/'native', seed=911)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('check', c.CHECKS[2:])
@pytest.mark.parametrize('fault', ['lower_gain', 'old_exact_path_policy'])
def test_changed_policy_cannot_replace_coordinator_envelope(tmp_path, monkeypatch, check, fault):
    from harness import zone_final_pair_clearance as clearance
    review = c.base.read(c.ROOT/clearance.CLEARANCE_REVIEW)
    if fault == 'lower_gain':
        review['gain_upper']['forward'] = .01
    else:
        review = {'schema': 'ugrp.final_pair_clearance_review.v1', 'profiles': {
            check: {'status': 'QUALIFIED_BOUNDS', 'bounds': {}, 'independent_bound_evidence': {}}}}
    (tmp_path/'configs').mkdir()
    (tmp_path/clearance.CLEARANCE_REVIEW).write_text(json.dumps(review))
    static = c.resolve(MAP_ID)[0]
    monkeypatch.setattr(c, 'ROOT', tmp_path)
    monkeypatch.setattr(c, 'resolve', lambda _: (static, None, None))
    receipt = clearance.path_preflight(check, MAP_ID)
    assert not receipt['admitted']
    assert receipt['reason'] == 'INVALID_CONSERVATIVE_ENVELOPE_INPUT'


@pytest.mark.parametrize('fault', ['robot_z', 'beam_z', 'radius', 'distance', 'computed_gap'])
def test_collection_validates_original_xyz_and_computed_geometry(monkeypatch, fault):
    from harness import zone_final_pair_clearance as clearance
    obj = fake_guard(monkeypatch, True)
    obj.collection_guard()
    if fault == 'robot_z':
        obj.world.data.geom_xpos[1, 2] = float('inf')
    elif fault == 'beam_z':
        obj.world.data.geom_xpos[2, 2] = float('-inf')
    elif fault == 'radius':
        obj.world.model.geom_rbound[2] = float('inf')
    elif fault == 'distance':
        # Move the geom, not the separately held base centre.
        obj.world.data.body = lambda _: SimpleNamespace(xpos=np.array([3.25, -.85, .1]))
        obj.world.data.geom_xpos[1, 0] = 1e308
    else:
        monkeypatch.setattr(np, 'hypot',
                            lambda *args: np.full(1, float('nan')))
    with np.errstate(over='ignore'), pytest.raises(ValueError):
        obj.collection_guard()
    assert obj.held == ['r1', 'r2']
    assert obj.saved[0][0] == 'eval_only/clearance_abort.jsonl'


def test_unloaded_already_has_rotation_steps_and_prbs_at_20hz():
    from harness.zone_final_pair_calibration import schedule
    plan = design('calibration-unloaded')
    turn = [s for s in plan['segments'] if s['axis'] == 'turn']
    for sign in (-1, 1):
        assert len({abs(s['value']) for s in turn if s['phase'] == 'step' and s['value']*sign > 0}) >= 2
    assert len([s for s in turn if s['phase'] == 'prbs']) == 31
    # Existing 84 s rotation block is retained; the conditional <=50 s request
    # concerned adding a missing block. No additional commands or cap increase.
    assert sum(s['duration_s'] for s in turn) == 84.
    rows = [e for e in schedule('calibration-unloaded') if e['action'].get('turn', 0)]
    assert min(e['t'] for e in rows) == 242.
    assert max(e['t']+.05 for e in rows) == pytest.approx(323.5)
    assert plan['eval_pose_period_s'] == .05
    assert plan['sim_cap_s'] + plan['reset_cap_s'] == 375.
