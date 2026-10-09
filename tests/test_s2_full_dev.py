"""Full DEV admission, unknown continuity, unchanged trace-off output; no SIM."""
import copy
import json
from types import SimpleNamespace as NS
import numpy as np
import pytest
from harness import zone_s2_realism_contract_v121 as c
from harness.idle_robot_contacts_contract import validate
from harness.zone_solo_cyan_inhand import InhandCheck
from scripts import run_s2_realism_v121 as runner


def test_admission_defaults_fresh_seed_and_no_research(tmp_path):
    args=runner.parser().parse_args(['--expected-source-sha','a'*40,'--output',str(tmp_path)])
    assert args.dev_grasp_policy==args.eval_camera_trace=='off'
    b=c.bundle('a'*40,seed=1045,**c.NEW_OPTIONS);c.require_execution(b)
    for fields in ({'scenario':'S3'},{'transport':'pair'},{'research_result':True},
            {'confirmation_sample':True},{'dev_light':False},{'stage_probe':'pick'},
            {'user_authorization':'unapproved'}):
        x=copy.deepcopy(b);x.update(fields)
        with pytest.raises(ValueError):validate(x)
    for seed in (1042,1043,1044,1029,1030,1031):
        x=copy.deepcopy(b);x['task']['seed']=seed
        with pytest.raises(ValueError,match='unregistered'):c.require_execution(x)
    for k in ('dev_grasp_policy','eval_camera_trace'):
        x=copy.deepcopy(b);x['options'][k]='off'
        with pytest.raises(ValueError):c.require_execution(x)


def test_unknown_grasp_advances_without_success_and_stays_in_result(tmp_path):
    check=InhandCheck();check.pregrasp=dict(frame_id=1)
    logs=[];soft=[]
    r=NS(state='lift',receipt=True,terminal=False,started_at=0,robot_id='r3',
        pose=NS(provider=NS(failure=None)),event=lambda *a,**k:logs.append((a,k)),
        soft=lambda code,t:soft.append(code))
    check.notify=lambda *a:None
    def base(now,idle):r.state='carry';return [dict(kind='hold')]
    assert check.control(r,30,True,base)==[dict(kind='hold')]
    assert r.state=='carry' and check.visual_status=='unknown'
    assert soft==['GRASP_INHAND_UNCONFIRMED']
    b=c.bundle('a'*40,seed=1045,**c.NEW_OPTIONS)
    value=runner.result_record(dict(pickup_site_status='unknown',evaluation={'lifted':True,'inside':False,'success':False}),b,
        dict(dev_light_would_stop={'GRASP_INHAND_UNCONFIRMED':1},events=[]))
    assert value['hold_status']=='unknown' and value['physical_success'] is False
    assert value['visual_unknown_stops'] is False
    def no_world(*a,**k):raise RuntimeError('synthetic IO only')
    result=runner.run(b,tmp_path/'synthetic',backend_factory=no_world)
    assert result==json.loads((tmp_path/'synthetic/result.json').read_text())
    assert result['status']=='HOST_ERROR' and result['physical_success'] is False


def test_eval_trace_off_byte_identical_and_on_read_only():
    from sim.s2_eval_camera_trace import backend_class,camera_row
    class Base:
        def __init__(self,bundle):self.rows=[]
        def capture(self):return {'r3':{'image':'same','frame_id':4}}
        def _append(self,path,row):self.rows.append((path,row))
    a=Base({});b=backend_class(Base)({'options':{}})
    assert json.dumps(a.capture()).encode()==json.dumps(b.capture()).encode()
    assert a.rows==b.rows==[]
    m=NS(cam_bodyid=np.array([0]),cam_pos=np.array([[.1,0,.2]]),
        cam_quat=np.array([[1.,0,0,0]]),body_treeid=np.array([0]))
    d=NS(xpos=np.array([[1.,2,3]]),xmat=np.eye(3).reshape(1,9),
        cam_xpos=np.array([[1.1,2,3.2]]),cam_xmat=np.eye(3).reshape(1,9),tree_asleep=np.array([-1]))
    world=NS(model=m,data=d,robot=lambda rid:NS(robot_cam_cid=0))
    before={k:v.tobytes() for k,v in vars(d).items()}
    row=camera_row(world,'r3',4.)
    assert row['controller_feedback'] is False and row['camera_cached_xyz_m']==row['camera_from_body_xyz_m']
    assert before=={k:v.tobytes() for k,v in vars(d).items()}
