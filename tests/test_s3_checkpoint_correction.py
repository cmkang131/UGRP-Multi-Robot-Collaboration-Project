import copy
import json
from types import SimpleNamespace
import numpy as np
import pytest
from harness import zone_s3_checkpoint_visual as visual
from harness import zone_s3_checkpoint_correction as correction
from sim.s3_release_epoch import PhysicsBackend, Previous, released_supported


def row(**kw):
    return dict(t=1.,states={'r1':'cp_open','r2':'cp_open'},floor_normal_n=3.,cargo_z_m=.016,
        vertical_speed_m_s=0.,cargo_tilt_deg=0.,controller_feedback=False,**kw)


def test_release_epoch_clears_only_supported_bilateral_release_and_rearms(monkeypatch):
    b=PhysicsBackend.__new__(PhysicsBackend);b.bundle=dict(checkpoint_correction=dict(options=dict(release_epoch=True)))
    b.lifted={'beam_1'};b.commands={r:{1:2000} for r in ('r1','r2')};b.setdown_row=lambda:row();audit=[]
    b._append=lambda p,r:audit.append(r)
    def original(host):
        if host.commands['r1'][1]<2000 and 'beam_1' in host.lifted:raise RuntimeError('LOAD_DROP:beam_1')
    monkeypatch.setattr(Previous,'eval_sample',original)
    b.eval_sample();assert not b.lifted and len(audit)==1 and not audit[0]['controller_feedback']
    b.commands['r1'][1]=1500;b.eval_sample() # Grounded next close is not a drop.
    b.lifted.add('beam_1') # Original guard re-arms on a new real lift.
    with pytest.raises(RuntimeError,match='LOAD_DROP'):b.eval_sample()
    for change in ({'floor_normal_n':0.},{'vertical_speed_m_s':-.2},{'cargo_tilt_deg':11.},{'cargo_z_m':.08}):
        value=row();value.update(change);assert not released_supported(value,{r:{1:2000} for r in ('r1','r2')})
    assert not released_supported(row(),{'r1':{1:2000},'r2':{1:1500}})


def test_default_off_and_fixed_six_240_sim_caps(monkeypatch):
    from scripts import run_s3_checkpoint_correction as runner
    from harness import zone_s3_reacquire_expanded as recovery
    marker=object();assert correction.attach(marker) is marker;assert recovery.attach(marker) is marker
    monkeypatch.setattr(runner,'source_closure',lambda *a:())
    monkeypatch.setattr(runner.previous,'bundle',lambda *a:dict(source_sha256={},parent_bundles=[]))
    b=runner.bundle('0'*40,0,'multi-left',14201)
    assert b['cap_sim_s']==b['case_cap_s']==240. and not any(b['checkpoint_correction']['options'].values())
    plan=json.loads((runner.ROOT/runner.PLAN).read_text());assert len(plan['runs'])==6
    assert {r['seed'] for r in plan['runs']}=={14201,15201,14204,15204,14206,15206}
    assert all(r['cap_sim_s']==240 for r in plan['runs'])


def test_rigid_static_floor_registration_and_blank_rejection():
    rng=np.random.default_rng(17);xy=rng.uniform([.15,-.3],[.7,.3],(40,2));desc=rng.integers(0,256,(40,32),dtype=np.uint8)
    a=.07;rot=np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]]);trans=np.array([.15,-.025])
    common=dict(heading=0.,frame_id=1,sha256='a'*64,sim_time=1.)
    ref=dict(**common,points=xy,desc=desc,center=np.array([.5,0.]))
    # Stationary floor points express chassis movement; cargo moved +.13,-.02.
    cur=dict(**{**common,'frame_id':2},points=(xy-trans)@rot,desc=desc,
        center=(ref['center']+np.array([.13,-.02])-trans)@rot)
    delta,report=visual.register(ref,cur)
    assert report['accepted'];np.testing.assert_allclose(delta,[.13,-.02],atol=1e-6)
    assert visual.register(ref,{**cur,'desc':None})[0] is None
    line={**cur,'points':np.c_[np.arange(40)*.01,np.zeros(40)]}
    assert not visual.register(ref,line)[1]['accepted']


def test_corrective_plan_event_is_counted_without_rewriting_raw():
    from scripts.evaluate_s3_checkpoint_correction import normalized_events
    original={'event':'checkpoint_carry_command_plan','seg':2,'robot_id':'r1','sim_s':114.,'pulses':[]}
    adapted=list(normalized_events([original]))
    assert adapted==[original,{**original,'event':'synchronized_carry_plan'}]
    assert original['event']=='checkpoint_carry_command_plan'


def test_corrected_both_endpoints_same_world_pulses_actual_port(tmp_path,monkeypatch):
    from tests.test_s3_full_route import probe
    from harness.zone_s3_synchronized_carry import attach as carry,OPTION
    from harness.zone_s3_integer_carry import attach as integer,OPTION as INTEGER
    from sim.s3_release_epoch import CheckpointCarryPort
    from harness.zone_s3_coarse_fine import attach_endpoint,OPTION as FINE
    from harness.zone_s3_alignment_ownership import ALL
    p=probe(tmp_path,monkeypatch)
    try:
        bus={1:dict(center_m=[1.452,.027],source='synthetic own visual fixture',fit=dict(accepted=True))}
        for rid,ep in p.eps.items():
            attach_endpoint(ep,FINE,refinements=ALL);carry(ep,OPTION);integer(ep,INTEGER)
            ctl=ep.controller;ctl.seg=1;ctl.state='carry';ctl.v3_plan['route']=[[1.3,.05],[1.452,.05],[1.452,.217]]
            p.host.ports[rid]=CheckpointCarryPort(p.host.world,rid,coupled=lambda:True,
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
            correction.attach(ep,True,bus=bus,motion=p.host.bundle['controller_config']['motion_model'])
            p.issue(rid,dict(kind='arm',servo_id=1,pulse=1500),1.)
        plans=[ep.controller.door_schedule(2.) for ep in p.eps.values()]
        assert len(plans[0])==len(plans[1]);assert len(plans[0])>1
        for first,second in zip(*plans):
            assert first[:2]==second[:2]
            for axis in ('forward','left','turn'):assert first[2][axis]==-second[2][axis]
            duration=first[1]-first[0];assert duration>=.1-1e-9
            if any(first[2].values()):
                assert sum(v!=0 for v in first[2].values())==1 and not first[2]['turn']
                for rid,cmd in (('r1',first[2]),('r2',second[2])):
                    p.issue(rid,dict(kind='mecanum',**cmd,duration_s=duration),first[0])
        assert all(p.runtime.localizers[r].pose.provider.failure is None for r in ('r1','r2'))
    finally:p.runtime.close()
