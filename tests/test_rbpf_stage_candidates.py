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


def test_registered_selection_requires_both_seeds_and_all_safety_gates():
    spec=importlib.util.spec_from_file_location('stage_score',Path(__file__).resolve().parents[1]/'experiments/2026-10-10-own-route-particle-stages/code/score.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rows=[]
    for profile,rate in [('baseline',.6),('a',.5),('b',.55),('c',.4)]:
        for seed in (60011,60012):
            rows.append(dict(profile=profile,seed=seed,status='RECORDED',samples=100,over_3sigma_rate=rate,
                final_error_m=.2,B_arrived=True,returned=False,false_declarations=int(profile=='c'),contacts={'wall':0,'robot':0}))
    r=m.select(rows)
    assert r['selected']=='a' and not r['gates']['b']['overconfidence'] and not r['gates']['c']['false']
    assert m.select([r for r in rows if r['seed']==60011])['selected'] is None


def test_checkpoint_registered_sensor_stream_alias_and_stateless_native_core(tmp_path):
    import io,pickle
    from scripts import dev_pair_checkpoint as cp
    from harness.public_navigation.native import PublicCore
    p=tmp_path/'sensor.jsonl'
    with p.open('w') as stream:
        writer=types.SimpleNamespace(_fh=stream)
        raw=io.BytesIO()
        cp.CheckpointPickler(raw,out=tmp_path,renderers={},streams={'sensor.jsonl':stream}).dump(writer)
        cp._LOAD['out']=tmp_path
        try:resumed=pickle.loads(raw.getvalue())
        finally:cp._LOAD['out']=None
        assert isinstance(resumed._fh,cp.Slot)
        cp.restore_stream_aliases([resumed],{'sensor.jsonl':stream})
        assert resumed._fh is stream
    # No simulator/model/steps: only the vendor path-planning library.
    a=PublicCore();b=pickle.loads(pickle.dumps(a))
    costs=np.zeros((20,20),np.uint8)
    assert a.lib is not b.lib and a.plan(costs,[3,3],[14,14]).tobytes()==b.plan(costs,[3,3],[14,14]).tobytes()


def test_relay_cache_checkpoint_preserves_command_bytes_without_physics(tmp_path):
    import io,pickle
    from scripts.dev_pair_checkpoint import CheckpointPickler
    from sim.v7_exact_speedups import CachedParameters
    from sim.masterpi_drive_friction_v7 import DriveParameters
    a=CachedParameters(DriveParameters());u=np.array([.1,.7,-.3,0.]);state=np.zeros(4)
    expected=a.command_step(u,state)
    raw=io.BytesIO();CheckpointPickler(raw,out=tmp_path,renderers={},streams={}).dump(a)
    b=pickle.loads(raw.getvalue())
    assert b.cache_info()['currsize']==0
    assert all(x.tobytes()==y.tobytes() for x,y in zip(expected,b.command_step(u,state)))


def test_whole_controller_checkpoint_without_physics_or_recording(tmp_path):
    import io,pickle
    from scripts.dev_pair_checkpoint import CheckpointPickler
    from scripts import run_goal_route_continuous as old
    from harness.active_camera import SEARCH
    a=old.actor('r3',1.3,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=60012,
        active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
    old.base.install_profile(a.memory.self_map,profile='egomap27_wide');c=old.controller(a)
    raw=io.BytesIO();CheckpointPickler(raw,out=tmp_path,renderers={},streams={},local_caches=True).dump(c)
    d=pickle.loads(raw.getvalue())
    assert d.explorer.memory.self_map.export()==c.explorer.memory.self_map.export()
    assert d.graph.snapshot()==c.graph.snapshot()


def test_smoke_is_four_plus_four_seconds_only():
    from scripts.run_own_route_particle_stages import bundle
    assert bundle(60012,'a'*40,'baseline','smoke_save')['case_cap_s']==4.
    assert bundle(60012,'a'*40,'baseline','smoke_resume')['case_cap_s']==4.
    assert bundle(60012,'a'*40,'baseline','stage')['case_cap_s']==120.


def test_batch_fixed_eight_slots_no_replacement_or_retry(tmp_path):
    from scripts.run_own_route_particle_batch import plan
    jobs=plan(tmp_path)
    assert len(jobs)==8 and len({j['name'] for j in jobs})==8
    assert [j['profile'] for j in jobs if j['seed']==60012]==['baseline','a','b','c']
    assert all(j['status']=='BLOCKED_PREPARE_B_UNOBSERVED' for j in jobs if j['seed']==60011)
