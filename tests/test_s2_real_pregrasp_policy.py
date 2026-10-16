"""User-confirmed REAL grasp policy through current S2 full DEV; no simulator."""
import copy
import json
import cv2
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from test_s2_real_hover import image
from harness import zone_s2_realism_contract_v123 as contract
from harness.zone_solo_cyan_inhand import InhandCheck
from harness.zone_solo_cyan_scene_change import decode
from scripts import run_s2_realism_v123 as runner


GRASP_OPTIONS=dict(hover_check='real_pregrasp_v1',hold_check='inhand_rgb_v1',
                  site_check='off',dev_grasp_policy='log_only_v1',idle_robot_contacts='freeze_v1')


def test_current_full_bundle_explicit_real_grasp_and_log_only_admission(tmp_path):
    b=contract.bundle('a'*40,seed=1047,**contract.NEW_OPTIONS)
    contract.require_execution(b)
    assert {k:b['options'][k] for k in GRASP_OPTIONS}==GRASP_OPTIONS
    assert b['options']['grasp_check']=='pickup_site_v1' and not b['pickup_site_comparison']
    assert b['dev_light'] and b['registration_kind']=='s2-dev-full'
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert all(getattr(args,k)=='off' for k in GRASP_OPTIONS)
    for key in ('hover_check','hold_check','dev_grasp_policy'):
        bad=copy.deepcopy(b);bad['options'][key]='off'
        with pytest.raises(ValueError):contract.require_execution(bad)
    bad=copy.deepcopy(b);bad['options']['site_check']='real_floor_v1'
    with pytest.raises(ValueError):contract.require_execution(bad)
    for state in ('unknown','failed','probable_held_inhand_rgb'):
        result=runner.result_record(dict(status='STAGE_REACHED_UNQUALIFIED',stage_reached=True,
            pickup_site_status=state,evaluation=dict(success=False,lifted=False,inside=False)),b,{})
        assert result['hold_status']==state and not result['visual_unknown_stops']
        assert result['status']=='STAGE_REACHED_UNQUALIFIED' and not result['physical_success']
        assert 'probe_gate_passed' not in result  # v120's historical probe gate is not called.


def test_full_runtime_prior_view_then_blind_close_and_unknown_carry(static,cal):
    b=contract.bundle('a'*40,seed=1047,**contract.NEW_OPTIONS)
    options={k:v for k,v in b['options'].items() if k not in
        ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')}
    r=runner.Runtime(static,contract.ROOT/contract.old.CALIBRATION,contract.old.CALIBRATION_SHA,
        **options,motion_model=b['motion_model'],pulse_calibration=b['pulse_calibration'],vision_factory=FakeVision)
    # Isolate this policy test from localization accuracy. No physical backend;
    # detections and pose reports are synthetic while the full option stack,
    # frame gate, arm queue, command guards, and in-hand accumulator are real.
    pose=FakePose(cal)
    r.pose.on_frame=pose.on_frame
    r.vision.hover_support=lambda *a:pytest.fail('hover cyan must not be queried')
    r.initial_commands(0.,{'r3':{1:2000,**rt.pose_of('inspect')}})
    r.state='align';r.align_view='inspect';r.last_report=pose.report(0.)
    seen=set()
    try:
        assert isinstance(r.scene_check,InhandCheck)
        for i in range(2000):
            now=i*.05;visible=r.state in ('align','real_pregrasp')
            obs=image(now,i,visible=True)
            if not visible:
                # Valid own RGB with texture, but no cyan after the reference.
                rgb=np.full((480,640,3),128,np.uint8);rgb[:,320:]=180
                import base64,hashlib
                data=cv2.imencode('.jpg',rgb)[1].tobytes()
                obs.update(image=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())
            r.on_frames(now,{'r3':(obs,cv2.cvtColor(decode(obs),cv2.COLOR_BGR2RGB))})
            for rid,action in r.step(now):r.on_command(rid,now,action)
            seen.add(r.state)
            if r.state=='carry' or r.terminal:break
        assert r.state=='carry' and r.failure is None
        assert {'real_pregrasp','hover','blind_descent','grasp','lift','carry'}<=seen
        assert r.pregrasp['accepted'] and len(r.pregrasp['samples'])==4
        assert r.receipt and r.blind.window['visual_confirmed_at_s']<r.blind.window['confirmed_at_s']
        assert not any(e['event']=='cyan_hover_check' for e in r.events)
        assert r.scene_check.visual_status=='unknown' and r.scene_check.retries==0
        assert r.soft_counts['GRASP_INHAND_UNCONFIRMED']==1
        assert all(s['area_px']==0 for samples in r.scene_check.evidence.samples.values() for s in samples)
        record=r.record()
        assert record['hover_check']['hover_visual_confirmation'] is False
        assert record['hold_check']['pickup_site_comparison'] is False
        assert record['scene_grasp_check']['pickup_site_status']=='not_evaluated_inhand_selected'
    finally:r.close()
