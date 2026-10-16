"""Frozen own-RGB evidence, negative controls and byte-equivalence; no physics."""
import base64
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS
import cv2
import numpy as np
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision
from test_s2_realism_alignment import make
from harness.zone_solo_cyan_real_site import Runtime as Previous
from harness.zone_solo_cyan_inhand import Runtime,Evidence,InhandCheck,VIEWS,PROBABLE
from harness import zone_s2_realism_contract_v120 as c

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'tests/fixtures/s2_inhand'


def observation(seed,view,t,fid):
    row=next(r for r in json.loads((FIX/'source.json').read_text()) if r['seed']==seed and r['pose']==view)
    data=(FIX/row['name']).read_bytes();assert hashlib.sha256(data).hexdigest()==row['sha256']
    return dict(robot_id='r3',camera='robot_cam',sim_time=t,frame_id=fid,
        image=base64.b64encode(data).decode(),sha256=row['sha256'])


def fill(e,seed,*,shift=False):
    for j,view in enumerate(VIEWS):
        servo={1:1500,**VIEWS[view]};start=10.*j
        e.add(observation(seed,view,start,100*j),servo,start,'r3')
        for i in range(9):
            t=start+.5+.05*i;obs=observation(seed,view,t,100*j+i+1)
            if shift and j:
                data=base64.b64decode(obs['image']);im=cv2.imdecode(np.frombuffer(data,np.uint8),1)
                im=np.roll(im,-100,axis=0);data=cv2.imencode('.jpg',im)[1].tobytes()
                obs.update(image=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())
            e.add(obs,servo,t,'r3')
    return e.result()


def test_saved_positive_and_occluded_hold_remains_unknown():
    a=fill(Evidence(),1042);b=fill(Evidence(),1043)
    assert a['status']==PROBABLE and a['hits']==dict(via110=9,high=9)
    assert a['mask_iou']>.98 and a['centroid_shift_px']<1
    assert b['status']=='unknown' and b['hits']==dict(via110=0,high=0)
    assert a['physical_success'] is b['physical_success'] is None
    old=json.loads((ROOT/'experiments/2026-10-06-s2-realism/grasp-verifier-comparison.json').read_text())
    assert [r['evaluation_only']['lifted'] for r in old['runs']]==[True,True]
    assert [r['visual']['status'] for r in old['runs']]==[PROBABLE,'unknown']


def test_negative_controls_moving_color_commands_stale_corrupt_and_no_frames():
    assert fill(Evidence(),1042,shift=True)['status']=='unknown'
    for cmd in (dict(kind='mecanum',forward=-.35),dict(kind='arm',servo_id=1,pulse=2000)):
        e=Evidence();e.command(cmd);assert fill(e,1042)['status']=='unknown'
    e=Evidence();servo={1:1500,**VIEWS['via110']}
    e.add(observation(1042,'via110',0,0),servo,0,'r3')
    o=observation(1042,'via110',1,1);e.add(o,servo,1,'r3');e.add(o,servo,1.05,'r3')
    assert len(e.samples['via110'])==1
    stale=observation(1042,'via110',0,2);e.add(stale,servo,2,'r3')
    corrupt=observation(1042,'via110',2,3);corrupt['sha256']='0'*64;e.add(corrupt,servo,2,'r3')
    assert len(e.samples['via110'])==1
    assert e.result()['status']=='unknown' and Evidence().result()['status']=='unknown'


def test_off_commands_records_byte_identical_and_checker_does_not_move_arm(static,cal):
    for kw in ({},dict(site_check='real_floor_v1',grasp_check='pickup_site_v1',
                      camera_profile=c.OPTIONS['camera_profile'],setdown_relook='off')):
        a,b=make(Previous,static,cal,**kw),make(Runtime,static,cal,**kw)
        try:
            for t in (1.,1.05,1.65,1.7,1.75):
                x,y=a.step(t),b.step(t);assert json.dumps(x).encode()==json.dumps(y).encode()
                for r,cmds in ((a,x),(b,y)):
                    for rid,cmd in cmds:r.on_command(rid,t,cmd)
            assert json.dumps(a.record()).encode()==json.dumps(b.record()).encode()
        finally:a.close();b.close()
    sc=InhandCheck();fill(sc.evidence,1042);sc.pregrasp=dict(frame_id=1)
    called=[];r=NS(state='lift',receipt=True,terminal=False,started_at=0,
        pose=NS(provider=NS(failure=None)),event=lambda *a,**k:called.append(a))
    out=sc.control(r,30,True,lambda *a:[dict(kind='hold')])
    assert out==[dict(kind='hold')] and sc.visual_status==PROBABLE
    assert sc.phase is None and sc.retries==0 and len(sc.checks)==1


def test_bundle_seed_scope_and_saved_result(tmp_path):
    from harness.idle_robot_contacts_contract import validate
    from scripts import run_s2_realism_v120 as runner
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path/'preview')])
    assert args.hold_check==args.site_check==args.idle_robot_contacts=='off'
    b=c.bundle('a'*40,seed=1044,**c.NEW_OPTIONS);c.require_execution(b)
    for change in ({'scenario':'S3'},{'research_result':True},{'transport':'pair'},
                   {'confirmation_sample':True},{'user_authorization':'unknown'}):
        bad=copy.deepcopy(b);bad.update(change)
        with pytest.raises(ValueError):validate(bad)
    bad=copy.deepcopy(b);bad['task']['seed']=1043
    with pytest.raises(ValueError,match='unregistered'):c.require_execution(bad)
    def no_world(*a,**k):raise RuntimeError('synthetic IO; no physics')
    result=runner.run(b,tmp_path/'synthetic',backend_factory=no_world)
    assert result==json.loads((tmp_path/'synthetic/result.json').read_text())
    assert result['options']['hold_check']=='inhand_rgb_v1'
    assert result['options']['idle_robot_contacts']=='freeze_v1'
    assert result['pickup_site_status']=='not_evaluated_inhand_selected'
    assert result['probe_gate_passed'] is False and result['status']=='HOST_ERROR'
