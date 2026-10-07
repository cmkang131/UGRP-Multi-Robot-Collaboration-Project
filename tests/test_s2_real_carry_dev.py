import copy,json
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt,observation
from harness.zone_solo_cyan_real_carry_dev import Runtime,apply,approximate,SAG_DELTA_RAD
from harness.zone_solo_cyan_real_carry import CARRY
from harness.zone_solo_cyan_visual_fix import Runtime as Previous
from harness.zone_solo_cyan_camera_v3 import build_provider
from harness.zone_final_pair_camera import floor_camera
from harness.zone_solo_cyan_pulse_cal import action_of
from harness import zone_s2_realism_contract_v124 as c
from scripts import run_s2_realism_v124 as runner


def table():return c.old.hp.base.read(c.ROOT/c.EXTRINSIC)


def full(static):
    b=c.bundle('a'*40,seed=1049,**c.NEW_OPTIONS)
    options={k:v for k,v in b['options'].items() if k not in
             ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
    r=Runtime(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA,seed=1049,
        **options,motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],
        extrinsic_calibration=b['extrinsic_calibration'],vision_factory=FakeVision)
    return b,r


def test_full_default_and_off_byte_equal(static,cal):
    rs=[cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)
        for cls,kw in [(Previous,{}),(Runtime,{}),(Runtime,dict(camera_calibration='off',carry_pose='off',measurement_model='off',visibility_mask='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}});r.last_report=r.pose.report(1.);r.state='lift';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            commands=[r.step(t) for r in rs]
            assert len(set(json.dumps(v).encode() for v in commands))==1
            for r,rows in zip(rs,commands):
                for rid,a in rows:r.on_command(rid,t,a)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_new_table_covers_real_pose_and_sag_is_fixed_not_gt(static):
    t=table();models=approximate(t)
    assert len(models['unloaded'])==22 and not t['measured_loaded']
    empty=floor_camera(models['unloaded']['600,2200,1400,1500'])
    loaded=floor_camera(models['loaded']['600,2200,1400,1500'])
    np.testing.assert_array_equal(empty['origin_m'],loaded['origin_m'])
    p=lambda x:np.arcsin(np.array(x['rotation'])[2,2])
    assert p(loaded)-p(empty)==pytest.approx(SAG_DELTA_RAD,abs=2e-7)
    bad=copy.deepcopy(t);bad['sag_approximation']['delta_rad']=0.
    with pytest.raises(ValueError):approximate(bad)
    a=build_provider(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA)
    b=build_provider(static,c.ROOT/c.old.CALIBRATION,c.old.CALIBRATION_SHA)
    try:
        old=json.dumps(b.provider.calibration);captured=a.provider.calibration
        apply(a,t);assert a.provider.calibration is captured
        a.provider.on_command(dict(t=0.,kind='initial_servo_command',pulses=CARRY))
        pf=a.provider.loc._pf;pf.load.loaded=True
        assert not pf.settled(7.9) and pf.settled(8.1)
        cm=pf.column_model_for(CARRY)
        np.testing.assert_allclose(cm.origin,loaded['origin_m'],atol=1e-12)
        np.testing.assert_allclose(cm._rot,loaded['rotation'],atol=1e-12)
        a.provider.on_command(dict(t=8.2,kind='arm',servo_id=5,pulse=1900,duration_s=.1))
        assert not pf.settled(30.)
        assert json.dumps(b.provider.calibration)==old
    finally:a.close();b.close()


def test_real_pose_rgb_measurement_visibility_and_lk_are_live(static):
    # The fixed XML geometry builder imports MuJoCo even though this test
    # never constructs/steps a world. Run it in the simulator CI job.
    pytest.importorskip('mujoco')
    b,r=full(static)
    try:
        r.initial_commands(0.,{'r3':dict(CARRY)})
        # Drain initial delayed command; synthetic known-pose belief only in test.
        r.pose.report(1.)
        inner=r.pose.provider;pf=inner.loc._pf;pf.load.loaded=True
        pf.init_gaussian((1.6,1.,0.),(.01,.01,.01));r.state='carry';r.receipt=True
        assert pf.settled(10.) and r.visual_pose_supported(CARRY)
        from harness import vision_loc_protocol as vp
        vl=vp.load_vis3()[0];vb,_=pf.expected(np.array([[1.6,1.,0.]]),CARRY)
        valid=(vb[0]>=4)&(vb[0]<=470);n=len(pf.columns)
        obs=vl.ColumnObs(pf.columns.copy(),np.where(valid,vl.EDGE,vl.NONE),vb[0],vb[0],np.zeros(n,int),np.full(n,np.nan),np.full(n,np.nan))
        calls=[]
        inner.worker.observe=lambda image:(calls.append(image.shape) or obs)
        r.on_frames(10.,{'r3':observation(10.,100)})
        r.pose.report(10.3)
        assert calls and r.visibility.audit['rows'] and r.soft_measurement['candidates']>=1
        assert r.soft_measurement['updates']>=1
        assert r.flow_frame is not None
        p=next(p for p in r.pulse_profiles.values() if p['loaded'] and np.linalg.norm(p['mean_delta'][:2])>.05)
        action=action_of(p);r.on_command('r3',10.4,action)
        assert r.flow_pending is not None
        end=10.4+p['times'][-1]+.1
        r.on_frames(end,{'r3':observation(end,101)})
        assert r.flow_rows and r.flow_rows[-1]['policy']=='DEV log only'
        report=r.record();assert report['camera_calibration']['runtime_gt'] is False
        assert report['visibility_mask']['gt_inputs'] is False
        assert 'real_delivery_v1' in report['soft_measurement']['scope']
    finally:r.close()


def test_v124_complete_options_fresh_seed_and_no_research(tmp_path):
    b=c.bundle('a'*40,seed=1049,**c.NEW_OPTIONS);c.require_execution(b)
    assert b['options']['idle_robot_contacts']=='freeze_v1' and not b['research_result']
    for key in ('carry_pose','camera_calibration','measurement_model','visibility_mask'):
        bad=copy.deepcopy(b);bad['options'][key]='off'
        with pytest.raises(ValueError):c.require_execution(bad)
    for key,value in [('scenario','S3'),('transport','pair'),('research_result',True)]:
        bad=copy.deepcopy(b);bad[key]=value
        with pytest.raises(ValueError):c.require_execution(bad)
    bad=copy.deepcopy(b);bad['task']['seed']=1047
    with pytest.raises(ValueError):c.require_execution(bad)
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert all(getattr(args,k)=='off' for k in ('carry_pose','camera_calibration','measurement_model','visibility_mask'))
    r=runner.result_record(dict(status='STAGE_REACHED_UNQUALIFIED',pickup_site_status='unknown',evaluation={'success':False}),b,{})
    assert r['visual_unknown_stops'] is False and r['full_dev_run_limit']==1
