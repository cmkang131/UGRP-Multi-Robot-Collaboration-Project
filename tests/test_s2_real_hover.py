"""Pure controller/geometry checks; no physics, renderer, or model calls."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
from test_solo_cyan_v106 import static, cal, FakePose, FakeVision, rt
from test_s2_realism_alignment import make
from harness.zone_solo_cyan_align_pulse import Runtime as Previous
from harness.zone_solo_cyan_real_hover import Runtime, OPTION


def image(now, index, visible=True):
    a=np.full((480,640,3),128,np.uint8)
    if visible:a[320:450,230:370]=(255,255,0)
    data=cv2.imencode('.jpg',a)[1].tobytes()
    return dict(robot_id='r3',camera='robot_cam',sim_time=now,frame_id=index,
        image=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())


def controller(static,cal,cls=Runtime,hover_check=OPTION,**kwargs):
    r=cls(static,None,None,**kwargs,**({'hover_check':hover_check} if cls is Runtime else {}),
        provider_factory=lambda *a,**k:FakePose(cal),vision_factory=FakeVision)
    r.initial_commands(0.,{'r3':{1:2000,**rt.pose_of('inspect')}})
    r.state='align';r.align_view='inspect';r.last_report=r.pose.report(0.)
    r.detections=lambda:r.vision.detect(r.last_obs,r.servo)
    r.vision.hover_support=lambda *a:pytest.fail('REAL path must not require hover pixels')
    return r


def tick(r,t,i,visible=True):
    r.last_obs=image(t,i,visible)
    r.last_report=r.pose.report(t)
    commands=r.step(t)
    for rid,cmd in commands:r.on_command(rid,t,cmd)
    return commands


def test_default_off_bytes_match_previous(static,cal):
    a,b=make(Previous,static,cal),make(Runtime,static,cal)
    try:
        for t in (1.,1.05,1.65,1.7,1.75):
            x,y=a.step(t),b.step(t)
            assert json.dumps(x).encode()==json.dumps(y).encode()
            for obj,cmds in ((a,x),(b,y)):
                for rid,cmd in cmds:obj.on_command(rid,t,cmd)
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
    finally:a.close();b.close()
    # Exercise the real inherited align/hover refusal, not only output conversion.
    a=controller(static,cal,cls=Previous)
    b=controller(static,cal,hover_check='off')
    a.vision.hover_support=b.vision.hover_support=lambda *a:False
    try:
        for i in range(70):
            assert json.dumps(tick(a,i*.05,i)).encode()==json.dumps(tick(b,i*.05,i)).encode()
        assert a.failure==b.failure=='CYAN_HOVER_UNCONFIRMED'
        assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
    finally:a.close();b.close()


def test_real_reference_precedes_arm_and_zero_hover_reaches_close(static,cal):
    r=controller(static,cal)
    try:
        for i in range(160):
            before=r.state
            commands=tick(r,i*.05,i,visible=r.state in ('align','real_pregrasp'))
            if before=='real_pregrasp' and not r.pregrasp['accepted']:
                assert all(cmd['kind']=='hold' for _,cmd in commands)
            if r.state=='grasp':break
        assert r.state=='grasp' and r.failure is None
        ref=r.pregrasp
        assert len(ref['samples'])==4 and all(s['area_px']>=500 for s in ref['samples'])
        assert ref['samples'][0]['t']>=ref['start_s']+.45-1e-8
        assert len({s['frame_id'] for s in ref['samples']})==4
        assert r.blind.window['visual_confirmed_at_s']<r.blind.window['confirmed_at_s']
        assert not any(e['event']=='cyan_hover_check' for e in r.events)
    finally:r.close()


def test_missing_reference_stale_frame_and_base_motion_fail_closed(static,cal):
    r=controller(static,cal)
    try:
        tick(r,0.,0);tick(r,.1,1)
        assert r.state=='real_pregrasp'
        r.last_obs=image(.1,1)
        r._control(.8,True);assert r.pregrasp['samples']==[]
        for i in range(2,10):
            tick(r,1.+i*.1,i,visible=False)
            if r.failure:break
        assert r.failure=='REAL_PREGRASP_UNCONFIRMED'
    finally:r.close()
    r=controller(static,cal)
    try:
        tick(r,0.,0);tick(r,.1,1)
        r.on_command('r3',.2,dict(kind='mecanum',forward=.01,left=0.,turn=0.,duration_s=.1))
        tick(r,.3,2)
        assert r.failure=='REAL_PREGRASP_ANCHOR_INVALID'
    finally:r.close()


def test_offline_projection_checks_actual_lens_not_rectangle():
    root=Path(__file__).resolve().parents[1]
    p=root/'experiments/2026-10-06-s2-realism/analyze_hover_projection.py'
    spec=importlib.util.spec_from_file_location('hover_audit',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    audit=json.loads(p.with_name('hover-projection.json').read_text())
    for run in audit['runs']:
        for pose in run['poses']:
            row=pose['eval_pose']
            for name,v in pose['variants'].items():
                replay=m.project(row,dict(origin_m=v['camera_origin_floor_heading_m'],rotation=v['camera_rotation']))
                # Cross-platform BLAS differs at ~6e-14 px. Keep integer lens
                # coverage/bboxes and every other field exact; only floating
                # projected pixel/metric coordinates get a roundoff tolerance.
                float_keys=('corner_uv','corner_bbox_xyxy','positive_depth_min_m',
                            'block_center_floor_heading_m')
                for key in float_keys:
                    np.testing.assert_allclose(replay[key],v[key],rtol=0,atol=1e-10)
                assert {k:x for k,x in replay.items() if k not in float_keys}=={k:x for k,x in v.items() if k not in float_keys}
                if pose['label']=='settled_hover':assert v['valid_ray_pixels']==0
            if pose['label']=='aligned':
                observed=run['frames'][0]['bbox_xyxy'];expected=pose['variants']['v3']['valid_bbox_xyxy']
                assert max(abs(a-b) for a,b in zip(observed,expected))<=3
        assert run['poses'][1]['variants']['previous']['rectangular_ray_pixels']>0


def test_v117_one_fresh_probe_defaults_and_closure():
    from harness import zone_s2_realism_contract_v117 as c
    from scripts.run_s2_realism_v117 import parser
    from sim.workflow_manager import catalog
    p=json.loads((c.ROOT/c.PLAN).read_text());assert len(p['runs'])==1 and p['runs'][0]['seed']==1042
    assert p['historical_failures']['CYAN_HOVER_UNCONFIRMED']==2
    a=parser().parse_args(['--expected-source-sha','a'*40,'--output','/tmp/no-run','--seed','1042'])
    assert all(getattr(a,k)=='off' for k in c.NEW_OPTIONS)
    b=c.bundle('a'*40,seed=1042,stage_probe='pick',pickup_slot='P1-2',**c.NEW_OPTIONS)
    assert b['options']['hover_check']==OPTION
    assert 'harness/zone_solo_cyan_real_hover.py' in b['source_sha256']
    assert any(w['id']==c.BUNDLE_ID and w['version']=='7.10.0' for w in catalog(c.ROOT)[0]['workflows'])
    with pytest.raises(ValueError):c.bundle('a'*40,seed=1041,stage_probe='pick',pickup_slot='P1-2')


def test_dev_unknown_records_and_descends_without_claiming_visual_success(static,cal):
    r=controller(static,cal,pregrasp_policy='log_only_v1')
    try:
        for i in range(160):
            tick(r,i*.05,i,visible=r.state=='align')
            if r.state=='grasp':break
        assert r.state=='grasp' and r.failure is None
        assert r.soft_counts['REAL_PREGRASP_UNCONFIRMED']==1
        assert r.pregrasp['accepted'] is False
        assert r.blind.window['visual_confirmed_at_s'] is None
        assert r.blind.window['visual_confirmed'] is False
        assert r.blind.window['source']=='dev_pregrasp_log_only_v1'
    finally:r.close()
