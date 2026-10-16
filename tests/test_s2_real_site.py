"""Saved RGB and synthetic control tests; no simulator, renderer, or model."""
import base64
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from test_s2_realism_alignment import make
from test_solo_cyan_v106_scene_check import frame,obs,runtime as old_scene_runtime
from harness.zone_solo_cyan_real_hover import Runtime as Previous
from harness.zone_solo_cyan_real_site import Runtime,FloorMemory,SceneCheck,OPTION,PROBABLE
from harness.zone_solo_cyan_scene_change import SiteMemory,lens_valid
from harness.zone_solo_cyan_camera_v3 import camera_calibration
from harness.zone_solo_cyan_vision_v106 import CyanVision
from harness.zone_solo_cyan_contract_v106 import CALIBRATION
from harness import zone_s2_realism_contract_v119 as c

ROOT=Path(__file__).resolve().parents[1]
SERVO={1:2000,3:508,4:2432,5:1320,6:1500}


def saved():
    p=ROOT/'tests/fixtures/s2_site_roi/s1042-pregrasp.jpg';data=p.read_bytes()
    assert hashlib.sha256(data).hexdigest()=='ecea43e9b8e97c0619c5ef737bd7a6cda2aafdb3f6b78a6156cba32404771919'
    return dict(robot_id='r3',camera='robot_cam',sim_time=95.45,frame_id=1884,
        image=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())


def test_s1042_exact_reference_failure_and_new_complete_target_memory():
    observation=saved();vision=CyanVision(camera_calibration(json.loads((ROOT/CALIBRATION).read_text())))
    fits=vision.detect(observation,SERVO);assert len(fits)==1
    fit=fits[0];assert fit['pixel_bbox']==[218,319,148,142]
    with pytest.raises(ValueError,match='region is clipped'):
        SiteMemory(observation,fit['pixel_bbox'],[.202,0],SERVO)
    m=FloorMemory(observation,fit['pixel_bbox'],[.202,0],SERVO,vision)
    assert m.record['before_cyan_area_px']==19774
    assert m.compare(observation)['decision']=='present'
    audit=json.loads((ROOT/'experiments/2026-10-06-s2-realism/s1042-site-roi.json').read_text())
    assert audit['rows'][0]['requested_roi']['outside_canvas_pixels']==15392
    assert audit['rows'][0]['unchanged_ecc_background_std']<2
    assert audit['actual_check']['before'] is None and audit['actual_check']['samples']==[]


def test_default_off_commands_and_records_byte_identical(static,cal):
    a,b=make(Previous,static,cal),make(Runtime,static,cal)
    try:
        for t in (1.,1.05,1.65,1.7,1.75):
            x,y=a.step(t),b.step(t);assert json.dumps(x).encode()==json.dumps(y).encode()
            for r,cmds in ((a,x),(b,y)):
                for rid,cmd in cmds:r.on_command(rid,t,cmd)
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
    finally:a.close();b.close()
    # Real constructor with pickup-site enabled still installs the legacy checker.
    from harness.zone_solo_cyan_scene_runtime import SceneCheck as OldCheck
    kw=dict(setdown_relook='off',camera_profile=c.OPTIONS['camera_profile'],grasp_check='pickup_site_v1',
        provider_factory=lambda *a,**kw:FakePose(cal),vision_factory=FakeVision)
    a,b=Previous(static,None,None,**kw),Runtime(static,None,None,site_check='off',**kw)
    try:
        assert type(a.scene_check) is type(b.scene_check) is OldCheck
        a.initial_commands(0.,{'r3':{1:2000,**rt.high.HIGH}});b.initial_commands(0.,{'r3':{1:2000,**rt.high.HIGH}})
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
    finally:a.close();b.close()


def active_check(static,cal,fits):
    r=old_scene_runtime(static,cal)
    sc=SceneCheck();sc.phase='position_view';r.scene_check=sc
    r.vision.detect=lambda *a:fits
    sc.memory=FloorMemory(obs(frame()),[280,250,80,65],[.2,0],r.servo,r.vision)
    sc.reference_command_i=len(r.commands)
    r._control(3.,True)
    assert sc.capture_after==3.45
    return r


def test_real_nine_fresh_samples_probable_only_and_no_motion(static,cal):
    r=active_check(static,cal,[])
    try:
        clear=frame(present=False,uniform=True);clear[~lens_valid()]=0
        r.last_obs=obs(clear,3.4,30);r._control(3.4,True)
        assert r.scene_check.samples==[]
        for i in range(9):
            t=3.5+i*.1;r.last_obs=obs(clear,t,31+i);r._control(t,True)
        assert len(r.scene_check.samples)==9
        assert r.scene_check.visual_status==PROBABLE and not r.visual_grasp_confirmed
        assert r.scene_check.phase=='restore_high' and r.queued[-1]=={1:1500,**rt.high.HIGH}
        assert not any(c['kind']=='mecanum' for c in r.commands)
        assert r.record()['physical_success'] is None
    finally:r.close()


def test_visible_floor_failure_black_stale_and_base_motion_not_clear(static,cal):
    r=active_check(static,cal,[dict(range_class='near',area_px=5200)])
    try:
        for i in range(9):
            t=4.+i*.1;r.last_obs=obs(frame(),t,50+i);r._control(t,True)
        assert r.scene_check.visual_status=='failed' and r.scene_check.retries==1
        assert r.scene_check.phase=='retry_lower'
        r.scene_check.finish_check(r,6.);assert r.failure=='CYAN_SCENE_RETRY_EXHAUSTED'
        m=r.scene_check.memory
        assert m.compare(obs(np.zeros((480,640,3),np.uint8)))['decision']=='unknown'
    finally:r.close()
    r=active_check(static,cal,[])
    try:
        r.last_obs=obs(frame(present=False),4.,70)
        r._control(4.,True);r._control(4.1,True);assert len(r.scene_check.samples)==1
        r.commands.append(dict(kind='mecanum',forward=.1))
        r.last_obs=obs(frame(present=False),4.2,71);r._control(4.2,True)
        assert r.scene_check.samples[-1]['decision']=='unknown'
    finally:r.close()


def test_bundle_scope_seed_and_synthetic_result_options(tmp_path):
    from harness.idle_robot_contacts_contract import validate
    from scripts import run_s2_realism_v119 as runner
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path/'preview')])
    assert args.site_check=='off' and args.idle_robot_contacts=='off'
    b=c.bundle('a'*40,seed=1043,**c.NEW_OPTIONS);c.require_execution(b)
    assert b['preregistered_run'] is True and b['research_result'] is False
    for changes in ({'scenario':'S3'},{'transport':'pair'},{'research_result':True},
                    {'registration_kind':'research'},{'confirmation_sample':True}):
        bad=copy.deepcopy(b);bad.update(changes)
        with pytest.raises(ValueError):validate(bad)
    bad=copy.deepcopy(b);bad['task']['seed']=1042
    with pytest.raises(ValueError,match='unregistered'):c.require_execution(bad)
    def no_world(*a,**kw):raise RuntimeError('synthetic IO; no physics')
    result=runner.run(b,tmp_path/'synthetic',backend_factory=no_world)
    assert result==json.loads((tmp_path/'synthetic/result.json').read_text())
    assert result['options']['site_check']==OPTION and result['options']['idle_robot_contacts']=='freeze_v1'
    assert result['probe_gate_passed'] is False and result['status']=='HOST_ERROR'
    assert result['execution_bundle_id']=='zone-s2-realism-v119'
