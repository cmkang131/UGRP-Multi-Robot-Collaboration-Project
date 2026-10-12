import json
from types import SimpleNamespace
import pytest
from harness import zone_s3_reacquire as reacquire
from harness.zone_s3_coarse_fine import pose_of


def test_default_off_identity_and_fixed_six_unbroken_horizons():
    from scripts import run_s3_full_route as runner
    from scripts.run_s3_full_route_cohort import commands
    marker=object();assert reacquire.attach(marker) is marker
    with pytest.raises(ValueError):reacquire.Options(canonical_pan=1)
    plan=json.loads((runner.ROOT/runner.PLAN).read_text())
    cc=commands(plan,'0'*40)
    assert len(cc)==len({r['name'] for r,_ in cc})==6
    for r,_ in cc:
        b=runner.bundle('0'*40,r['condition'],r['route_case'],r['seed'],r['candidate'])
        assert b['cap_sim_s']==(len(r['route'])-1)*70+30==r['cap_sim_s']
        assert b['route_resume']['candidate']=='combined'
        assert b['controller_config']['options']['heading_mode']=='path_tangent_v1'
        assert 'coupled_beam_carry' in b['heading_exceptions']


def probe(tmp_path,monkeypatch):
    from tests import s3_stage_probe as module
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    monkeypatch.setattr(module,'contract',contract);monkeypatch.setattr(module,'Runtime',Runtime)
    return module.Probe(tmp_path,monkeypatch)


def test_declared_and_executed_route_caps_agree(monkeypatch):
    from scripts import run_s3_full_route as runner
    monkeypatch.setattr(runner,'source_closure',lambda *a:())
    for legs in (2,3):
        monkeypatch.setattr(runner.previous,'bundle',lambda *a:dict(
            registered_route=[[0,0]]*(legs+1),source_sha256={},parent_bundles=[]))
        b=runner.bundle('0'*40,0,'multi-left',14201)
        assert b['case_cap_s']==b['cap_sim_s']==legs*70+30
        assert b['wall_cap_s']==3600


def test_saved_floor_pan_through_outer_tick_returns_canonical_before_new_look(tmp_path,monkeypatch):
    from harness import zone_s3_coarse_fine as cf
    from harness.zone_s3_alignment_ownership import ALL
    from harness.zone_s3_route_resume import attach, CANDIDATES
    p=probe(tmp_path,monkeypatch)
    try:
        ep=p.eps['r1'];ctl=ep.controller
        cf.attach_endpoint(ep,cf.OPTION,refinements=ALL)
        attach(ep,CANDIDATES['combined'])
        reacquire.attach(ep,reacquire.CANDIDATES['pan'])
        for k,v in {1:2000,3:807,4:1897,5:2187,6:1616}.items():
            p.issue('r1',dict(kind='look',pan_pulse=v) if k==6 else dict(kind='arm',servo_id=k,pulse=v),1.)
        ctl.arm.events.clear();ctl.arm.until=0.;ctl.arm.commanded=dict(ep.own.servo)
        ctl.state='align';ctl.seg=1;ctl.next_look=0.;ctl.beam_grasp_receipt=None
        looked=[]
        def look(now):
            assert all(ep.own.servo[k]==v for k,v in {**pose_of('inspect'),6:1500}.items())
            looked.append(now);return ep.own.last_obs
        ctl.look=look
        monkeypatch.setattr('harness.zone_pair_highpose_frame_gate.controller_gate',lambda c:lambda *a:True)
        class Vision:
            def __init__(self,*a):pass
            def observe_beam(self,*a):return dict(visible=False,end_visible=False,reason='not_visible')
        monkeypatch.setattr(cf,'PairVision',Vision);monkeypatch.setattr(cf,'band_vision',lambda v:v)
        p.refresh(1.1);ctl.tick(1.1)
        assert not looked and ctl.arm.events
        deadline=ctl.arm.until;p.arm(ep,deadline+.05)
        ep.own.last_obs['sim_time']=1.1;ctl.tick(deadline+.05)
        assert not looked
        p.refresh(deadline+.2);ctl.tick(deadline+.2)
        assert looked==[deadline+.2] and ep.own.servo[6]==1500 and not ctl.failure
    finally:p.runtime.close()


def test_rgb_clipped_reverse_actual_port_minimum_single_axis_and_bounded_gate(tmp_path,monkeypatch):
    p=probe(tmp_path,monkeypatch)
    try:
        ep=p.eps['r1'];ctl=ep.controller
        ctl.state='align';ctl.seg=1;ctl.next_look=0.;ctl.beam_grasp_receipt=None
        ctl._align=lambda now,idle:ctl.log(ctl.rid,'beam_obs',now,visible=True,end_visible=False,reason='BAND_CLIPPED')
        ctl.status[0].partner_view=lambda *a:{}
        reacquire.attach(ep,reacquire.Options(clipped_backoff=True))
        for now in (1.,3.,5.):
            p.refresh(now);ctl._align(now,True)
            for action in p.drain(ep,now):
                if action['kind']=='mecanum':
                    assert action['forward']==-.35 and action['left']==action['turn']==0
                    assert action['duration_s']==.1
            ctl.drive_until=0.
        audit=ctl.s3_reacquire['audit']
        assert len(audit)==2 and all(x['phase']=='clipped_backoff' for x in audit)
    finally:p.runtime.close()


def test_complete_route_requires_final_not_first_release_and_contact_transport(tmp_path,monkeypatch):
    from scripts import evaluate_s3_full_route as evaluator
    raw=tmp_path/'raw';raw.mkdir();(raw/'eval_only').mkdir()
    def write(name,value):
        p=raw/name;p.parent.mkdir(exist_ok=True,parents=True)
        p.write_text(json.dumps(value)+'\n')
    def lines(name,values):
        p=raw/name;p.parent.mkdir(exist_ok=True,parents=True)
        p.write_text(''.join(json.dumps(v)+'\n' for v in values))
    write('bundle.json',dict(registered_route=[[0,0],[.1,0],[.2,0]],reacquire=dict(candidate='pan')))
    write('reacquire.json',{})
    write('stage-states.json',[dict(t=2.,robots={r:dict(state='lower') for r in ('r1','r2')})])
    truth=[dict(t=t,items=dict(beam_1=dict(x=x,y=0,z=.1)))
        for t,x in ((0.,0.),(.5,.1),(1.,.1),(1.5,.2),(2.5,.2))]
    lines('eval_only/referee_truth.jsonl',truth)
    contacts=[dict(geom1='cargo_beam_1',geom2=r+'__'+s+'_finger')
        for r in ('r1','r2') for s in ('left','right')]
    lines('eval_only/contacts.jsonl',[dict(t=v['t'],contacts=contacts) for v in truth])
    lines('eval_only/setdown.jsonl',[dict(t=2.1+i*.05,floor_normal_n=1.,cargo_z_m=.02,
        vertical_speed_m_s=0,cargo_tilt_deg=0.) for i in range(8)])
    for r in ('r1','r2'):
        lines(f'robots/{r}/commands.jsonl',[dict(t=.9,servo_id=1,pulse=2000)])
    def inherited(raw):
        return dict(legs=[dict(seg=i,start_sim_s=float(i),end_sim_s=i+.8,
            endpoint_reached=True) for i in range(2)],planned_legs=2,status='DEV_STAGE_FINISHED',
            controller_failures={},drop_aborts=0,tilt_aborts=0,setdown=True)
    monkeypatch.setattr(evaluator,'previous',inherited)
    assert not evaluator.evaluate(raw)['full_route_success']
    for r in ('r1','r2'):
        lines(f'robots/{r}/commands.jsonl',[dict(t=.9,servo_id=1,pulse=2000),
            dict(t=2.05,servo_id=1,pulse=2000)])
    assert evaluator.evaluate(raw)['full_route_success']
    lines('eval_only/contacts.jsonl',[])
    assert not evaluator.evaluate(raw)['full_route_success']
