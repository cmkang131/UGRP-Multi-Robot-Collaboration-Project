import numpy as np
from scripts.diagnose_s3_endpoint_visibility import project

def test_eval_projection_camera_convention_and_fov():
    uv,inside=project([[0,0,-1],[0,1,-1],[0,0,1]],[0,0,0],np.eye(3))
    assert inside.tolist()==[True,False,False]
    assert np.allclose(uv[0],[287.68910608896766,218.69686648455726])

import copy
from types import SimpleNamespace
import pytest
from harness import zone_s3_coarse_fine as cf
from harness.zone_s3_alignment_ownership import Options,ALL,LastVisible,owns_posture
from tests.test_s3_coarse_fine import profiles


def test_optional_refinements_identity_and_frozen_tolerances():
    assert not Options().enabled
    marker=object()
    assert cf.attach_endpoint(marker,refinements=ALL) is marker
    assert cf.attach_solo(marker,refinements=ALL) is marker
    s=cf.Servo('r3',profiles(),ALL)
    for y in (-.012,.016):
        p,q=s.proposal([.24,y],0.)
        assert p['axis']=='forward' and p['u']>0
        assert q['halfwidths']==[.0096,.003,.112]


def test_last_visible_uses_issued_calibration_and_does_not_refresh_anchor():
    from harness.zone_solo_cyan_pulse_cal import action_of
    m=LastVisible(profiles());p=next(p for p in profiles().values() if not p['loaded'] and p['axis']=='forward' and p['u']==.35 and p['duration_s']==.1)
    b=dict(grip_base_m=[.23,0.],axis_heading_rad=0.,std_xy_m=.015,std_yaw_rad=.02)
    m.capture(b,dict(sim_time=1.,frame_id=12,sha256='a'*64),{6:1500},0)
    m.command(dict(t=1.,**action_of(p)),{1:2000})
    assert m.estimate(1.1,0) is None
    got=m.estimate(2.,0)
    assert got['anchor_time_s']==1. and got['anchor_frame_id']==12
    assert got['grip_base_m'][0]<.23 and got['std_xy_m']>=.015
    assert m.estimate(10.,0) is None and m.estimate(2.,1) is None
    assert m.estimate(2.1,0)['grip_base_m']==got['grip_base_m']


def fixture(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    return probe.Probe(tmp_path,monkeypatch)


@pytest.mark.parametrize('retained',[False,True])
def test_outer_pair_tick_preserves_pan_and_partner_abort(tmp_path,monkeypatch,retained):
    p=fixture(tmp_path,monkeypatch)
    try:
        ep=p.eps['r1'];ctl=ep.controller
        beam=dict(visible=True,end_visible=True,grip_base_m=[cf.GRASP_RADIUS_M,0.],
            axis_heading_rad=0.,grip_source='band_centre',std_xy_m=.015,std_yaw_rad=.017)
        class Vision:
            def __init__(self,cal):pass
            def observe_beam(self,*args):
                return {**copy.deepcopy(beam),**(dict(end_visible=False,reason='BAND_CLIPPED') if retained and ep.own.servo[6]!=1500 else {})}
            def beam_track(self):return SimpleNamespace(_standoff=lambda *a:copy.deepcopy(beam))
        monkeypatch.setattr(cf,'PairVision',Vision)
        monkeypatch.setattr('harness.zone_pair_highpose_frame_gate.controller_gate',lambda c:lambda *a:True)
        cf.attach_endpoint(ep,cf.OPTION,refinements=Options(posture_ownership=True,endpoint_memory=retained))
        ctl._grasp_pose_ready=lambda now:True
        ctl.arm.events.clear();ctl.arm.until=0;p.refresh(1.)
        for k,v in cf.pose_of('inspect').items():
            p.issue('r1',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),1.)
        ctl.arm.commanded=dict(ep.own.servo);ctl.state='align';ctl.next_look=0
        keys=copy.deepcopy(ctl.v98_measured_camera_keys)
        ctl.vo_obs=[dict(t=1.,g=[cf.GRASP_RADIUS_M,0.],h=0.,end_visible=True)]
        for t in np.arange(1.1,4.,.05):
            p.refresh(float(t));ctl.arm.tick(float(t));p.drain(ep,float(t));ctl.tick(float(t));p.drain(ep,float(t))
            if ctl.state=='pregrasp_descend':break
        assert ctl.state=='pregrasp_descend',(ctl.state,ctl.failure,ctl.s3_coarse_fine.audit)
        assert ctl.hover[6]>1500 and keys==ctl.v98_measured_camera_keys
        if retained:assert ctl.claims['aligned']['evidence']=='predicted_last_visible'
        assert not owns_posture(ctl)
        # Reentry still checks real partner abort through the outer tick.
        ctl.state='align';p.eps['r2'].status.tick('abort',5.)
        p.refresh(5.);ctl.tick(5.)
        assert ctl.failure=='PARTNER_ABORT'
    finally:p.runtime.close()


def test_outer_solo_step_keeps_calibrated_forward_pulse(tmp_path,monkeypatch):
    p=fixture(tmp_path,monkeypatch)
    try:
        own=p.runtime.localizers['r3'];cf.attach_solo(own,cf.OPTION,refinements=ALL)
        monkeypatch.setattr('harness.zone_pair_highpose_frame_gate.gate',lambda:SimpleNamespace(valid_frame=lambda *a:True))
        monkeypatch.setattr('harness.zone_solo_cyan_vision_v106.CyanVision.detect',lambda *a:[dict(estimated_box_center_base_m=[.24,-.012,.02])])
        own.state='align';own.arm.events.clear();own.arm.until=0
        for k,v in cf.pose_of('inspect').items():
            p.issue('r3',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),1.)
        own.arm.commanded=dict(own.servo);p.refresh(1.1)
        rows=own.step(1.1)
        action=next(a for rid,a in rows if a['kind']=='mecanum')
        assert action==dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1)
        for rid,a in rows:p.issue(rid,a,1.1)
        p.refresh(1.2);rows=own.step(1.2)
        assert any(a['kind']=='hold' for rid,a in rows)
        p.refresh(1.3);assert not any(a['kind']=='mecanum' for rid,a in own.step(1.3))
    finally:p.runtime.close()


def test_manifest_and_bundle_fixed():
    import json
    from dataclasses import asdict
    from scripts.run_s3_alignment_ownership import bundle
    from scripts.run_s3_alignment_ownership_cohort import PLAN,commands
    b=bundle('0'*40,'pair',0,cf.OPTION,60.,ALL)
    assert b['coarse_fine']['params']==cf.PARAMS and b['coarse_fine']['refinements']==asdict(ALL)
    assert len(commands(json.loads(PLAN.read_text()),'0'*40))==10
