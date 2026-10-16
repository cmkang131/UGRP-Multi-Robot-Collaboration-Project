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
    assert len(rows[:6])*.5+2.35<=10  # separate path check, never calibration input


def test_measurement_setup_uses_same_issued_inspect_and_free_east_room():
    from scripts.run_s3_x86_pulse_measure import measurement_setup
    from harness.owncam_pair_beam_v2 import pose_of
    for i in range(6):
        data=measurement_setup(i)
        for rid,row in data['robots'].items():
            assert row['frame']['commanded_servo']=={1:2000,**pose_of('inspect')}
            x,y,z=row['pose']['robot_xyz_m']
            assert 2.4<x<5.1 and y==-1 and z==.0325


def model():
    from harness.zone_solo_cyan_pulse_cal import profile_key
    profiles={}
    for a in sequence()[:18]:
        axis=next(k for k in ('forward','left','turn') if a[k]);j=('forward','left','turn').index(axis)
        delta=[0.,0.,0.];delta[j]=math.copysign(a['duration_s']*(1. if j==2 else .10),a[axis])
        profiles[profile_key(a,False)]=dict(loaded=False,axis=axis,u=a[axis],duration_s=a['duration_s'],
            mean_delta=delta,mean_curve=[[0,0,0],delta],times=[0,.5],prediction_variance=[.0001]*3,
            transfer=None,s3_trim_measured=True)
    return dict(qualified=True,profiles=profiles,runtime_gt=False)


def test_measured_selector_off_identity_and_full_pose_legal_actions():
    from harness.zone_s3_measured_visual_servo import Selector,attach_endpoint
    marker=object();assert attach_endpoint(marker) is marker
    profiles=model()['profiles'];selector=Selector(profiles)
    for errors in ([.023,.002,.157],[-.011,.016,-.073],[.005,0,0]):
        action,p,row=selector(profiles,errors)
        assert p is not None and command_reason(action) is None
        assert row['after']<row['before'] and row['thresholds_changed'] is False
        assert row['goal_distance_m']<=.10
    assert selector(profiles,[0,0,0])[1] is None
    assert Selector(profiles,angle_required=False)(profiles,[0,0,1.])[1] is None


def test_solo_callback_keeps_fresh_rgb_waits_and_native_legal_lateral():
    from harness.zone_s3_measured_visual_servo import attach_solo,OPTION
    marker=object();assert attach_solo(marker) is marker
    profiles=model()['profiles']
    own=SimpleNamespace(pulse_profiles={},pulse_model={'profiles':{}},
        pose=SimpleNamespace(provider=SimpleNamespace(loc=SimpleNamespace(_pf=SimpleNamespace(pulse_calibration={'profiles':{}})))),
        state='align',target=[.2032,.015],fine_rows=[{'t':1.}],robot_id='r3',last_obs={'frame_id':4},
        step=lambda now:[('r3',dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1))],record=lambda:{})
    attach_solo(own,model(),option=OPTION)
    row=own.step(1.)[0][1]
    assert row['left'] and command_reason(row) is None
    assert own.heading_align_settled==1.5
    assert own.record()['visual_pose_servo']['option']==OPTION


def test_measured_selector_reaches_actual_pair_apply_with_shared_predictor(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    from harness.zone_s3_measured_visual_servo import attach_endpoint,OPTION
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    p=probe.Probe(tmp_path,monkeypatch)
    try:
        p.refresh(1.)
        for rid,ep in p.eps.items():
            p.host.ports[rid]=TrimPort(p.host.world,rid,coupled=lambda:False,
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
            predictor=ep.own.pose.localizer.pose.provider.loc._pf.predict_to
            attach_endpoint(ep,model(),option=OPTION)
            assert ep.own.pose.localizer.pose.provider.loc._pf.predict_to is predictor
            ep.controller.set('align',1.)
            ob=ep.controller._align.__func__.__globals__['ob']
            command=ob.align_command(dict(grip_base_m=[.2032,.015],axis_heading_rad=0.))
            ep.controller.drive(command,1.)
            rows=p.drain(ep,1.)
            assert any(a.get('left') for a in rows)
            assert ep.s3_alignment_audit[-1]['phase']==OPTION
            assert all(command_reason(a) is None for a in rows)
    finally:p.runtime.close()


def test_all_six_measurements_required_and_holdout_can_veto(tmp_path):
    import json
    from scripts.fit_s3_x86_trim import fit
    from harness.zone_solo_cyan_pulse_cal import profile_key
    profiles=model()['profiles'];runs=[]
    for i in range(6):
        raw=tmp_path/str(i);(raw/'eval_only').mkdir(parents=True);runs.append(raw)
        (raw/'result.json').write_text(json.dumps(dict(status='COLLECTED_UNQUALIFIED',host='oracle-x86',condition=i)))
        (raw/'eval_only/contacts.jsonl').write_text('')
        rows=[dict(action=a,times=[0,.5],curve=[[0,0,0],profiles[profile_key(a,False)]['mean_delta']]) for a in sequence() for rid in ('r1','r2','r3')]
        (raw/'pulse-responses.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=fit(runs,profiles);assert result['qualified'] and len(result['profiles'])==18
    with pytest.raises(ValueError,match='all six'):fit(runs[:5],profiles)
    path=runs[-1]/'pulse-responses.jsonl';rows=[json.loads(s) for s in path.read_text().splitlines()]
    rows[0]['curve'][-1][0]+=.01
    path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    assert not fit(runs,profiles)['qualified']


def test_cohort_submits_all_frozen_conditions_with_same_source():
    import json
    from scripts.run_s3_x86_cohort import commands,PLAN
    plan=json.loads(PLAN.read_text());sha='a'*40
    for phase,n in [('measure',6),('candidate',12)]:
        rows=commands(plan,phase,sha,'model.json','b'*64)
        assert len(rows)==n and len({r['name'] for r,args in rows})==n
        assert all(args[args.index('--expected-source-sha')+1]==sha for r,args in rows)
        assert all(r['seed']==14201+r['condition'] for r,args in rows)
