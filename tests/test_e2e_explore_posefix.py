"""Frontier lifecycle, real mapper wiring and durable shutdown; no physics."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from harness.e2e_exploration import Navigator, install, OPTION
from harness.e2e_result_writer import Finalizer, write
from harness.public_navigation_unknown import UnknownCostmap


def navigator():
    driver=SimpleNamespace(pose=np.zeros(3))
    n=Navigator(driver)
    n.core.frontiers=lambda *a:np.array([[1.,0.,1.,0.,1.,15.,-1.],[0.,1.,0.,1.,1.,15.,0.]])
    n.plan_to=lambda c,p,g:[list(p[:2]),list(g)]
    return n,driver,UnknownCostmap(np.zeros((120,120),np.uint8),[-3,-3],.05)


def test_frontier_moves_without_mandatory_scan_and_goal_is_committed():
    n,d,c=navigator();plan=n.update(c,np.zeros(3),0.)
    assert n.phase is None and n.locked and plan['path_m'][-1]==[1,0]
    for t in (1,2,3):
        n.update(c,np.zeros(3),t,static_goal=np.array([-3.,2.]))
    assert [e['reason'] for e in n.events].count('frontier_selected')==1
    assert n.target.tolist()==[1,0]


def test_spin_without_translation_blacklists_and_reselects_without_new_spin():
    n,d,c=navigator();plan=n.update(c,np.zeros(3),0.)
    d.pose[2]=3.
    # A localization jump is not translation in command odom.
    n.command(c,np.array([2.,2.,2.]),plan,10.2)
    assert n.blocked([1,0],.05) and not n.locked and n.sweep_pending is None
    n.update(c,np.zeros(3),10.4)
    assert n.target.tolist()==[0,1]


def test_no_reachable_frontier_has_one_bounded_scan():
    n,d,c=navigator();n.core.frontiers=lambda *a:[]
    plan=n.update(c,np.zeros(3),0.)
    n.command(c,np.zeros(3),plan,0.)
    assert n.phase=='sensor_sweep'
    n.command(c,np.zeros(3),plan,30.1)
    assert n.phase is None
    n.update(c,np.zeros(3),30.2)
    assert n.finished and n.sweep_pending is None


def test_off_identity_and_real_innovation_constructor():
    x=object();assert install(x) is x
    from harness.e2e_live_mapping import Robot
    from harness.s4_event_policy import Options
    cov=json.loads(Path('configs/e2e_nees_egomap70_dev_v1.json').read_text())
    off=Robot('r1',61001,cov,Options())
    assert not hasattr(off.goal,'_pose_continuity_view')
    on=Robot('r1',61001,cov,Options(),exploration_progress=OPTION,pose_fix='innovation')
    view=on.goal._pose_continuity_view
    assert view.options.correction_gate=='mahalanobis_v1'
    assert view.options.pose_continuity=='rep105_offset_v1'
    import cv2,base64,hashlib
    rgb=np.zeros((480,640,3),np.uint8);ok,data=cv2.imencode('.jpg',rgb);data=data.tobytes()
    for i in range(2):
        trace=on.receive(dict(frame_id=i,sim_time=i*.2,sha256=hashlib.sha256(data).hexdigest(),image=base64.b64encode(data).decode()),rgb)
    assert trace['pose_continuity']['control_frame']=='command_odom'
    assert trace['exploration']['option']==OPTION
    transform=on.goal.heading_host.pose_frame_transform
    pose,path,goal=transform(np.array([2.,3.,0.]),[[3.,3.]],np.array([4.,3.]))
    np.testing.assert_allclose(pose,view.base.driver.pose)
    np.testing.assert_allclose(path,[[1.,0.]])
    np.testing.assert_allclose(goal,[2.,0.])


def test_outlier_map_correction_rejected_but_command_prediction_continues():
    from harness.ego_pose_continuity import Reporter,Options
    r=Reporter([0,0,0],np.eye(3)*.0001,Options(correction_gate='mahalanobis_v1'))
    r.predict([.02,0,0],np.eye(3)*.0001)
    assert not r.measure([.7,0,0],np.eye(3)*.0001)['accepted']
    assert r.pose[0]==pytest.approx(.02)
    assert np.linalg.eigvalsh(r.covariance).min()>0


def test_atomic_failed_replace_preserves_previous_result(tmp_path,monkeypatch):
    p=tmp_path/'result.json';write(p,{'status':'RUNNING'})
    def fail(*a):raise OSError('injected rename failure')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):write(p,{'status':'FINISHED'})
    assert json.loads(p.read_text())=={'status':'RUNNING'}
    assert list(tmp_path.iterdir())==[p]


def test_finalizer_keeps_result_after_optional_saver_failure_and_signals(tmp_path):
    r={'status':'EARLY_STOP'};f=Finalizer(tmp_path,r);f.install()
    try:
        with pytest.raises(KeyboardInterrupt):f.signal(signal.SIGTERM,None)
        f.finalizing=True
        f.signal(signal.SIGINT,None);f.signal(signal.SIGTERM,None)
        def fail():raise RuntimeError('snapshot failed')
        f.attempt('snapshot',fail)
        f.attempt('remaining-evidence',lambda:write(tmp_path/'evidence.json',{'saved':True}))
    finally:f.finish()
    saved=json.loads((tmp_path/'result.json').read_text())
    assert saved['finalization_complete'] and saved['status']=='HOST_ERROR'
    assert len(saved['shutdown_signals'])==3 and len(saved['finalization_errors'])==1
    assert json.loads((tmp_path/'summary.json').read_text())==saved
    assert (tmp_path/'evidence.json').exists()


def test_registered_bundle_and_relay_ids():
    from scripts.run_e2e_ownmap_live import bundle
    from scripts.s4_proxy_relay import accepted_call_id
    b=bundle('a'*40,61001,'study_gemma4_31b_v1',enabled=True,exploration_progress=OPTION,pose_fix='innovation')
    assert b['execution_bundle_id']=='e2e-explore-posefix-v194'
    assert 'harness/ego_pose_continuity.py' in b['source_sha256']
    assert 'harness/e2e_result_writer.py' in b['source_sha256']
    assert accepted_call_id('e2e9-b-s61001:call-0001-r1:1')
    assert not accepted_call_id('e2e9-b-s99999:call-0001-r1:1')


def test_managed_timeout_waits_for_registered_finalization_grace(tmp_path):
    from sim.workflow_manager import run_workflow
    (tmp_path/'scripts').mkdir();(tmp_path/'configs').mkdir()
    (tmp_path/'scripts/__init__.py').write_text('')
    (tmp_path/'scripts/finish_fixture.py').write_text('''import argparse,signal,time,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output');a=p.parse_args()
out=Path(a.output);out.mkdir()
def stop(*args):
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    time.sleep(3.2)
    (out/'result.json').write_text(json.dumps({'finalized':True}))
    raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
time.sleep(30)
''')
    row=dict(id='fixture',version='1',entry='scripts/finish_fixture.py',runner='scripts.finish_fixture',
             output_flag='--output',output_kind='directory',required_inputs=[],side_effect='fixture',shutdown_grace_s=5)
    (tmp_path/'configs/simulation_workflows.json').write_text(json.dumps(dict(schema='ugrp.local_workflow_catalog.v1',workflows=[row])))
    record=run_workflow(tmp_path,'fixture',[],timeout=.5)
    manifest=json.loads((record/'manifest.json').read_text())
    assert manifest['status']=='timeout'
    assert json.loads((Path(manifest['output'])/'result.json').read_text())['finalized']
