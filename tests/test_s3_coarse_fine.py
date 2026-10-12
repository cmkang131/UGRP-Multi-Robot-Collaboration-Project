import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from harness import zone_s3_coarse_fine as cf
from harness.zone_solo_cyan_path_heading import command_reason

ROOT = Path(__file__).resolve().parents[1]


def profiles():
    return json.loads((ROOT/'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']


def test_default_off_identity_and_frozen_bounds():
    marker=object()
    assert cf.attach_endpoint(marker) is marker and cf.attach_solo(marker) is marker
    assert cf.PARAMS['runtime_gt'] is False
    assert .0166858 < cf.PARAMS['pair_dx_half_m'] < .024
    assert .101446559 < cf.PARAMS['yaw_half_rad'] < .14
    assert cf.PARAMS['cyan_dx_half_m'] < .012 < .0166858
    assert cf.PARAMS['dy_center_m']==-.006
    with pytest.raises(ValueError):cf.plan([float('nan'),0.],0.,'r1')


def test_arm_quantization_workspace_and_vertical_descent():
    for rid in ('r1','r2','r3'):
        for dx in (-.008,0.,.012):
            for dy in (-.018,0.,.018):
                p=cf.plan([cf.GRASP_RADIUS_M+dx,dy],0.,rid)
                h,path=cf.postures(p)
                assert 1300<=p['pan']<=1700 and p['pan']%4==0
                xyz=np.array([cf.arm.forward_grip(v) for v in [h,*path]])
                assert np.max(np.linalg.norm(xyz[:,:2]-xyz[-1,:2],axis=1))<.002
                assert 0<xyz[0,2]-xyz[-1,2]<=.075
    assert cf.angle(1504)-cf.angle(1500)==pytest.approx(math.radians(.36))
    assert .155*math.sin(math.radians(.36))<.001


def test_fine_pan_needs_fresh_settled_rgb_and_preserves_negative_capture_center():
    s=cf.Servo('r1',profiles());grip=[cf.GRASP_RADIUS_M,0.]
    obs=lambda t,f:dict(frame_id=f,sim_time=t,sha256='a'*64)
    phase,pan=s.observe(1.,obs(1.,1),{6:1500},grip,0.)
    assert phase=='pan' and pan>1500
    assert s.observe(1.7,obs(1.7,2),{6:pan},grip,0.)[0]=='wait'
    assert s.observe(1.8,obs(1.8,3),{6:pan},grip,0.)[0]=='wait'
    assert s.observe(1.9,obs(1.8,3),{6:pan},grip,0.)[0]=='wait'
    phase,p=s.observe(2.,obs(2.,4),{6:pan},grip,0.)
    assert phase=='ready' and abs(p['errors'][1])<.001
    assert -0.009 <= p['errors'][1]-.006 <= -.003


def test_coarse_commands_are_existing_single_axis_100ms():
    from harness.zone_solo_cyan_pulse_cal import action_of
    for rid in ('r1','r2','r3'):
        s=cf.Servo(rid,profiles())
        for grip,heading in [([.24,0.],0.),([.21,.03],.25),([.18,-.02],-.2)]:
            pulse,p=s.proposal(grip,heading)
            if pulse:
                action=action_of(pulse)
                assert command_reason(action) is None
                assert action['duration_s']==.1 and action['left']==0.
                assert sum(bool(action[k]) for k in ('forward','left','turn'))==1
    assert cf.radial_workspace() and min(cf.radial_workspace())>=.148
    assert max(cf.radial_workspace())<=.1701


def test_camera_composition_is_private_identity_at_center():
    from harness.zone_final_pair_contract import camera_record
    from harness.zone_s3_recovery_contract import bundle,ROOT
    from harness.zone_solo_cyan_camera_v3 import camera_calibration
    b=bundle('0'*40);cal=camera_calibration(json.loads((ROOT/b['calibration']).read_text()))
    saved=copy.deepcopy(cal);pose=cf.pose_of('inspect')
    result=cf.yaw_calibration(cal,1500)
    assert camera_record(result,'unloaded',pose)==camera_record(cal,'unloaded',pose)
    changed=cf.yaw_calibration(cal,1540)
    a=camera_record(changed,'unloaded',{**pose,6:1540})
    assert np.linalg.det(a['rotation'])==pytest.approx(1.) and cal==saved


def test_pair_fine_alignment_to_hover_uses_actual_ports(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    p=probe.Probe(tmp_path,monkeypatch)
    try:
        ep=p.eps['r1'];ctl=ep.controller;cf.attach_endpoint(ep,cf.OPTION)
        # Fixed own-camera response; no physical world exists in this sweep.
        beam=dict(visible=True,end_visible=True,grip_base_m=[cf.GRASP_RADIUS_M,0.],
            axis_heading_rad=0.,grip_source='band_centre',std_xy_m=.015,std_yaw_rad=.017)
        class Vision:
            def __init__(self,cal):pass
            def observe_beam(self,*args):return copy.deepcopy(beam)
            def beam_track(self):return SimpleNamespace(_standoff=lambda *a:copy.deepcopy(beam))
        monkeypatch.setattr(cf,'PairVision',Vision)
        # Valid frame fixture; command and timestamp gates stay real.
        monkeypatch.setattr('harness.zone_pair_highpose_frame_gate.controller_gate',lambda c:lambda *a:True)
        ctl._grasp_pose_ready=lambda now:True
        ctl.arm.events.clear();ctl.arm.until=0
        p.refresh(1.)
        for k,v in cf.pose_of('inspect').items():
            p.issue('r1',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),1.)
        ctl.arm.commanded=dict(ep.own.servo);ctl.state='align';ctl.next_look=0
        ctl._align(1.,True);p.arm(ep,1.9)
        assert ep.own.servo[6]>1500
        p.refresh(2.);ctl._align(2.,True);p.refresh(2.2);ctl._align(2.2,True)
        assert ctl.claims.get('aligned',{}).get('option')==cf.OPTION, (ctl.s3_coarse_fine.audit,dict(ep.own.servo),ctl.state,ctl.failure)
        assert ctl.state=='pregrasp_descend' and ctl.blind_phase=='hover'
        assert ctl.hover[6]==ep.own.servo[6]
        p.arm(ep,ctl.arm.until+.1)
        assert not ctl.failure
        assert all(command_reason(a) is None for a in p.issued)
    finally:p.runtime.close()


def test_solo_fine_alignment_to_lift_real_arm_port(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    p=probe.Probe(tmp_path,monkeypatch)
    try:
        own=p.runtime.localizers['r3'];cf.attach_solo(own,cf.OPTION)
        monkeypatch.setattr('harness.zone_pair_highpose_frame_gate.gate',lambda:SimpleNamespace(valid_frame=lambda *a:True))
        monkeypatch.setattr('harness.zone_solo_cyan_vision_v106.CyanVision.detect',
            lambda *a:[dict(estimated_box_center_base_m=[cf.GRASP_RADIUS_M+.012,0.,.02])])
        own.state='align';own.arm.events.clear();own.arm.until=0
        for k,v in cf.pose_of('inspect').items():
            p.issue('r3',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),1.)
        own.arm.commanded=dict(own.servo)
        states=[]
        for t in np.arange(1.1,12.,.05):
            p.refresh(float(t))
            for rid,a in own.step(float(t)):p.issue(rid,a,float(t))
            states.append(own.state)
            if own.state=='lift':break
        assert all(s in states for s in ('hover','blind_descent','grasp','lift')), (states,own.failure)
        assert own.servo[1]==1500 and own.receipt
        assert not any(a.get('forward') or a.get('left') or a.get('turn') for a in p.issued)
    finally:p.runtime.close()


def test_runner_freezes_ten_conditions_and_off_default():
    from scripts.run_s3_coarse_fine_probe import bundle,BUNDLE_ID
    from scripts.run_s3_coarse_fine_cohort import commands,PLAN
    b=bundle('0'*40,'pair',0)
    assert b['servo_option']=='off' and b['execution_bundle_id']==BUNDLE_ID
    rows=commands(json.loads(PLAN.read_text()),'a'*40)
    assert len(rows)==10 and len({r['name'] for r,a in rows})==10
    assert {(r['case'],r['condition']) for r,a in rows}=={('pair',i) for i in range(6)}|{('cyan',i) for i in (0,3,4,5)}


def test_evaluation_requires_receipt_and_contiguous_contact():
    from scripts.evaluate_s3_coarse_fine import events,sustained
    assert sustained([0.,.05,.1,.15,.2])==0.
    assert sustained([0.,.05,.1,.4,.45,.5]) is None
    assert sustained([0.,0.,.05,.05]) is None
    logs=[dict(event='coarse_fine',phase='ready'),dict(event='coarse_fine_aligned',frame_id=4)]
    assert [e['event'] for e in events({'events':logs})]==['coarse_fine','coarse_fine_aligned']


def test_radial_workspace_preregistration(capsys):
    grid=cf.radial_workspace()
    assert len(grid)>1
    print('FEASIBLE_RADII_M',grid)
