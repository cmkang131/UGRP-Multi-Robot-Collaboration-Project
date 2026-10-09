import copy
import importlib.util
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

from harness.cohort_host_error_guard import HostErrorGuard
from scripts import run_goal_route_preflight as runner
from sim import goal_route_assets as assets
from sim.zone_masterpi_v3_scene import static_map


def load_cohort():
    spec=importlib.util.spec_from_file_location('p1_cohort',runner.EXP/'code/run_cohort.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_off_identity_and_previous_scene_dispatch(monkeypatch):
    class Poison:
        def __getattribute__(self,k):raise AssertionError(k)
    xml='  <mujoco/>\n'
    assert assets.decorate(xml,Poison(),assets=Poison()) is xml
    sentinel=object();calls=[]
    monkeypatch.setattr(assets.previous,'make_scene',lambda b,s:(calls.append((b,s)) or sentinel))
    b={'options':{}}
    assert assets.make_scene(b,1) is sentinel and calls==[(b,1)]


def test_same_map_generates_wall_and_tape_geometry(tmp_path):
    m=copy.deepcopy(static_map('zone_wide_door_geometry_v3'))
    original=assets.geometry(m)
    wall=next(w for w in m['obstacles'] if w.get('kind')=='wall')
    wall['half_extents_m'][0]+=.01
    dest=assets.generate(m,tmp_path)
    receipt=assets.validate(m,dest)
    record=json.loads((dest/'layout.json').read_text())
    assert receipt['walls']==6 and receipt['faces']==24
    assert record['wall_geometry']==assets.geometry(m)!=original
    assert dest.name==assets.digest(assets.geometry(m))


@pytest.mark.parametrize('seed',runner.SEEDS)
def test_all_registered_xml_without_constructing_physics(monkeypatch,seed):
    import mujoco
    def forbidden(*a,**kw):raise AssertionError('PHYSICS_STARTED')
    for name in ('MjModel','MjData','mj_step','mj_forward','Renderer'):
        monkeypatch.setattr(mujoco,name,forbidden)
    b=runner.bundle(seed,'a'*40)
    receipt,xml=assets.xml_preflight(b,seed)
    assert receipt['walls']==6 and receipt['faces']==24 and receipt['physics_steps']==0
    walls=assets.geometry(static_map(b['map_id']))
    divider=next(w for w in walls if w['name']=='zone_wall_divider_1')
    assert 2*divider['size'][1]==pytest.approx(2.950)
    root=ET.fromstring(xml)
    geoms=[g for g in root.findall('worldbody/geom') if g.get('name','').startswith('tape_v1_')]
    assert len(geoms)==24
    assert all(g.get('contype')==g.get('conaffinity')==g.get('mass')=='0' for g in geoms)


@pytest.mark.parametrize('fault',['map','layout','image','xml'])
def test_stale_or_tampered_assets_rejected(tmp_path,fault):
    m=copy.deepcopy(static_map('zone_wide_door_geometry_v3'))
    dest=assets.generate(m,tmp_path)
    if fault=='map':m['map_id']='wrong'
    elif fault=='layout':
        p=dest/'layout.json';r=json.loads(p.read_text());r['faces'][0]['length_m']+=.1;p.write_text(json.dumps(r))
    elif fault=='image':
        p=next(dest.glob('*.png'));p.write_bytes(p.read_bytes()+b'x')
    xml=None
    if fault=='xml':
        _,xml=assets.xml_preflight(runner.bundle(55001,'a'*40),55001)
        root=ET.fromstring(xml);g=root.find("worldbody/geom[@name='zone_wall_divider_1']");g.set('size','.05 .9625 .1');xml=ET.tostring(root,encoding='unicode')
    with pytest.raises(ValueError,match={'map':'P1_ASSET_MAP','layout':'P1_ASSET_LAYOUT','image':'P1_ASSET_PNG','xml':'P1_XML_MAP'}[fault]):
        assets.validate(m,dest,xml)


def test_preflight_rejection_precedes_lock_or_backend(monkeypatch,tmp_path):
    from scripts import agent_lock
    def fail(*a):raise ValueError('P1_XML_MAP_MISMATCH')
    def forbidden(*a,**kw):raise AssertionError('MUST_NOT_ACQUIRE_OR_START')
    monkeypatch.setattr(runner,'RAW',tmp_path)
    monkeypatch.setattr(runner,'source_check',lambda source:{})
    monkeypatch.setattr(runner,'xml_preflight',fail)
    monkeypatch.setattr(agent_lock,'acquire',forbidden)
    monkeypatch.setattr(assets,'PhysicsBackend',forbidden)
    monkeypatch.setattr(sys,'argv',['run','--seed','55001','--expected-source-sha','a'*40,'--output',str(tmp_path/'seed55001'),'--execute'])
    with pytest.raises(ValueError,match='P1_XML_MAP_MISMATCH'):runner.main()
    assert not (tmp_path/'seed55001').exists()


def test_two_identical_errors_stop_all_remaining_and_report_both():
    called=[];reported=[]
    def execute(seed):
        called.append(seed)
        return dict(status='HOST_ERROR',failure=dict(type='ValueError',message='bad geometry'))
    r=load_cohort().run_slots(runner.SEEDS,execute,lambda s,r:reported.append(s))
    assert called==reported==list(runner.SEEDS[:2])
    assert r['remaining']==list(runner.SEEDS[2:])
    assert r['stopped']=='two_consecutive_identical_HOST_ERROR'


def test_guard_resets_on_different_error_or_task_outcome():
    g=HostErrorGuard()
    a=dict(status='HOST_ERROR',failure=dict(type='ValueError',message='a'))
    b=dict(status='HOST_ERROR',failure=dict(type='ValueError',message='b'))
    for r in (a,b,dict(status='RECORDED'),b,dict(status='PHYSICAL_FAILURE'),b):assert not g.observe(r)
    assert g.observe(b)


def test_retry_preserves_all_controller_gates_and_shared_heading():
    for seed in runner.SEEDS:
        old=runner.previous.bundle(seed,'a'*40);new=runner.bundle(seed,'a'*40)
        for key in ('execution_bundle_id','tape_source','previous_attempts'):new.pop(key,None);old.pop(key,None)
        new['options'].pop('wall_assets')
        assert json.dumps(new,sort_keys=True)==json.dumps(old,sort_keys=True)
    assert runner.run.__code__ is runner.previous.run.__code__


def test_workflow_uses_preflight_entrypoint():
    from sim.workflow_manager import plan
    p=plan(runner.ROOT,'goal-route-preflight-dev',['--seed','55001','--output','/tmp/no-physics','--expected-source-sha','a'*40])
    assert 'scripts.run_goal_route_preflight' in p['command']
