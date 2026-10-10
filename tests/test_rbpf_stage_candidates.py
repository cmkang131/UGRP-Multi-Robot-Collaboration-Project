import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path
import numpy as np
import pytest
from harness.rbpf_stage_candidates import install,local_reference,POPULATION,LOCAL,GATE
from harness.self_map_rbpf import RaoBlackwellizedGrid,GridField,improved_proposal
from harness.self_map_csm import CSMOptions
from harness.self_pulse_odom import PulseOdometry
from scripts.run_active_wall_rotleft import install_profile


def grid():
    g=RaoBlackwellizedGrid('r3',correction_options={'particles':100},wall_confidence='inverse_sensor_v1')
    g.odom.driver=PulseOdometry(0.)
    g.odom.driver.step_callback=g.propagate
    return install_profile(g,profile='egomap27_wide')


def scan():
    p=np.c_[np.ones(15),np.linspace(-.7,.7,15)]
    return p,GridField(np.r_[p,np.c_[np.linspace(0,1,15),np.full(15,.7)]])


def test_off_preserves_object_rng_and_export_bytes():
    g=grid();before=json.dumps(g.export(),sort_keys=True);rng=str(g.rng.bit_generator.state)
    assert install(g) is g
    assert json.dumps(g.export(),sort_keys=True)==before
    assert str(g.rng.bit_generator.state)==rng


def test_legacy_proposal_off_bytes_against_committed_parent():
    source=subprocess.check_output(['git','show','f0ba9ee1:harness/self_map_rbpf.py'],text=True)
    name='test_frozen_rbpf_stage_parent';m=types.ModuleType(name);sys.modules[name]=m
    exec(compile(source,name,'exec'),m.__dict__)
    points,field=scan();args=(field,points,np.zeros(2),np.zeros(3),np.diag([.02,.02,.01]))
    old=m.improved_proposal(*args,np.random.default_rng(4),CSMOptions(),yaw_window_deg=20.)
    new=improved_proposal(*args,np.random.default_rng(4),CSMOptions(),yaw_window_deg=20.)
    assert old[0].tobytes()==new[0].tobytes()
    assert json.dumps(old[1:],sort_keys=True)==json.dumps(new[1:],sort_keys=True)


def test_particle_split_preserves_joint_distribution_axes_and_map_ownership():
    g=grid();g.poses=np.arange(300).reshape(100,3)*.001
    g.weights=np.arange(1,101,dtype=float);g.weights/=sum(g.weights);g.log_weights=np.log(g.weights)
    g._manhattan_axes=np.arange(100)*.01;g.best=2
    before=g.odom.covariance.copy();pose=g.odom.pose;rng=str(g.rng.bit_generator.state)
    install(g,rbpf_population=POPULATION)
    assert len(g.maps)==500 and g.rbpf_options.particles==500 and g.best==10
    assert g.odom.pose==pose and np.allclose(g.odom.covariance,before,atol=1e-14)
    assert np.allclose(g.weights.reshape(100,5).sum(1),np.arange(1,101)/5050)
    assert np.array_equal(g._manhattan_axes,np.repeat(np.arange(100)*.01,5))
    g.maps[0].cells[(1,2)]=7
    assert (1,2) not in g.maps[1].cells
    assert str(g.rng.bit_generator.state)==rng


def test_local_reference_rejects_far_map_without_removing_nearby_evidence():
    p,_=scan();past=np.r_[p,[[100.,100.]]]
    assert np.array_equal(local_reference(past,p,np.zeros(3)),p)
    assert local_reference(past,p[:0],np.zeros(3)).shape==(0,2)


def test_local_window_bounds_and_candidate_count():
    p,f=scan();args=(f,p,np.zeros(2),np.zeros(3),np.diag([.02,.02,.01]))
    a=improved_proposal(*args,np.random.default_rng(8),CSMOptions(),yaw_window_deg=20.)
    b=improved_proposal(*args,np.random.default_rng(8),CSMOptions(),yaw_window_deg=20.,translation_window_m=.1)
    assert b[2]['candidates']<a[2]['candidates']
    assert max(abs(np.array(b[2]['best_offset'])[:2]))<=.1000001


def test_gate_validates_actual_draw_not_only_matched_mode():
    class BadDraw:
        def multivariate_normal(self,mean,cov):return np.asarray(mean)+[.8,0,0]
    p,f=scan()
    _,weight,event=improved_proposal(f,p,np.zeros(2),np.zeros(3),np.diag([.02,.02,.01]),BadDraw(),CSMOptions(),
        yaw_window_deg=20.,observed_sample=True)
    assert event['reason']=='sample_search_boundary' and event['sample_verified'] is False
    assert weight==0. and event['proposal']=='motion_fallback'


@pytest.mark.parametrize('profile',['baseline','a','b','c'])
def test_registered_bundle_keeps_motion_heading_and_scene(profile):
    from scripts.run_own_route_particle_stages import bundle
    b=bundle(60011,'a'*40,profile,'stage');old=bundle(60011,'a'*40,'baseline','stage')
    assert b['host']=='oracle-x86' and b['heading_contract']==old['heading_contract']
    assert b['task']==old['task'] and b['spawn']==old['spawn']
    assert b['options']['motion_model']=='s2_pulse_v122_rotL_v1'


def test_no_mac_physics_guard(monkeypatch):
    from scripts import run_own_route_particle_stages as runner
    monkeypatch.setattr(runner.platform,'system',lambda:'Darwin')
    with pytest.raises(RuntimeError,match='NO_MAC'):
        with runner.server_slot():pytest.fail('must not acquire or construct physics')


def test_return_probe_uses_only_own_temporal_route():
    from scripts.run_own_route_particle_stages import enter_return
    from types import SimpleNamespace
    events=[]
    graph=SimpleNamespace(anchor=3,seal=lambda:None,route=lambda a,b:{'length_m':2.,'samples':[{'pose':[0,0,0]}]})
    c=SimpleNamespace(graph=graph,navigator=SimpleNamespace(reset_action=lambda:None),event=lambda *a,**kw:events.append(kw))
    enter_return(c,60.)
    assert c.stage=='return' and c.cursor==0 and c.leg_start==60.
    assert events[0]['synthetic_task_transition'] is True
