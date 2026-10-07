"""S2 command-only option + counterfactual evaluator checks; no simulation."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest
from test_solo_cyan_v106 import static,cal,FakePose,FakeVision,rt
from harness.zone_solo_cyan_real_carry import Runtime,Previous,CARRY,at_carry,transition,OPTION
from harness import zone_s2_realism_contract_v123 as contract
from scripts.red_block.poses import servo_steps
from sim.masterpi_camera_review_v3 import PROFILE_ID


def make(static,cal,cls=Runtime,**kw):
    return cls(static,None,None,provider_factory=lambda *a,**k:FakePose(copy.deepcopy(cal)),vision_factory=FakeVision,**kw)


def test_off_commands_and_record_byte_equal(static,cal):
    rs=[make(static,cal,cls,**kw) for cls,kw in
        [(Previous,{}),(Runtime,{}),(Runtime,dict(carry_pose='off'))]]
    try:
        for r in rs:
            r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
            r.last_report=r.pose.report(1.);r.state='lift';r.receipt=True
        for t in (1.,1.05,1.1,1.2,1.65,1.8):
            commands=[r.step(t) for r in rs]
            assert len(set(json.dumps(c).encode() for c in commands))==1
            for r,rows in zip(rs,commands):
                for rid,a in rows:r.on_command(rid,t,a)
        assert len(set(json.dumps(r.record()).encode() for r in rs))==1
    finally:
        for r in rs:r.close()


def test_real_stack_targets_and_order_are_reused():
    # AST literal only: importing this real executable would touch real modules.
    import ast
    path=Path('scripts/red_block/physical_state_machine_reference.py')
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.Assign)
              and any(isinstance(t,ast.Name) and t.id=='DELIVERY_CARRY_POSE' for t in n.targets))
    assert ast.literal_eval(node.value)=={k:v for k,v in CARRY.items() if k!=6}
    previous={1:1500,**rt.high.HIGH}
    path=transition(previous,CARRY)
    assert [next(iter(p)) for p,_,_ in path]==[5,4,3]
    assert [(next(iter(p)),next(iter(p.values())),d) for p,d,_ in path]==servo_steps(previous,CARRY,lowering=False)
    assert all(s==.15 for _,_,s in path)


def test_real_transport_and_high_return_before_descent(static,cal):
    r=make(static,cal,carry_pose=OPTION,setdown_relook='off',camera_profile=PROFILE_ID)
    try:
        r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
        r.last_report=r.pose.report(0.);r.state='lift';r.receipt=True
        r.drive=lambda *a,**k:([{'kind':'hold'}],False)
        seen=set();commands=[]
        for i in range(500):
            t=i*.05
            for rid,a in r.step(t):r.on_command(rid,t,a);commands.append(a)
            seen.add(r.state)
            if r.state=='carry':break
        assert r.state=='carry' and at_carry(r.servo) and r.failure is None
        assert 'real_carry_transition' in seen
        assert all(a.get('pulse')!=2000 for a in commands if a['kind']=='arm')
        assert r.record()['carry_pose']['runtime_admitted'] is False
        r.route_i=len(r.route)-1;r.drive=lambda *a,**k:([{'kind':'hold'}],True)
        for j in range(1,500):
            now=t+j*.05
            for rid,a in r.step(now):r.on_command(rid,now,a)
            seen.add(r.state)
            if r.state=='lower':break
        assert 'real_carry_return' in seen and r.state=='lower'
        assert rt.high.at_high(r.servo) and r.servo[1]==1500
    finally:r.close()


def test_on_still_enforces_command_state_and_no_bundle_admission(static,cal):
    with pytest.raises(ValueError,match='setdown_relook'):
        make(static,cal,carry_pose=OPTION)
    r=make(static,cal,carry_pose=OPTION,setdown_relook='off',camera_profile=PROFILE_ID)
    try:
        r.initial_commands(0.,{'r3':{1:1500,**rt.high.HIGH}})
        r.last_report=r.pose.report(0.);r.state='carry';r.receipt=True
        r._control(1.,True)
        assert r.failure=='LOADED_COMMAND_STATE_LOST'
    finally:r.close()
    b=contract.bundle('a'*40,seed=1047,**contract.NEW_OPTIONS)
    b['options']['carry_pose']=OPTION
    with pytest.raises(ValueError):contract.require_execution(b)


def test_real_provider_does_not_reuse_high_calibration(static):
    from harness.zone_solo_cyan_camera_v3 import build_provider
    from harness.zone_solo_cyan_contract_v106 import ROOT,CALIBRATION,CALIBRATION_SHA
    source=build_provider(static,ROOT/CALIBRATION,CALIBRATION_SHA)
    try:
        inner=source.provider;pf=inner.loc._pf;pf.load.loaded=True
        inner.servo=dict(CARRY);inner.high_since=0.
        assert pf.settled(100.) is False
        # No fabricated loaded calibration exists for the new pose.
        with pytest.raises(ValueError):rt.hp.camera_record(inner.calibration,'loaded',CARRY)
    finally:source.close()


def test_geometry_opportunity_is_not_a_fix():
    path=Path('experiments/2026-10-06-s2-realism/analyze_real_carry.py')
    spec=importlib.util.spec_from_file_location('carry_geometry',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.opportunity_metrics([1,2,9],[0,6,0],[0,10])['max_opportunity_gap_sim_s']==8.
    criteria=json.loads(path.with_name('real-carry-criteria.json').read_text())
    models=m.models(criteria)
    assert models['REAL_nominal'][0].origin[2]>models['HIGH_nominal'][0].origin[2]
    assert criteria['runtime_admitted'] is False
    assert criteria['max_opportunity_gap_sim_s']==30.
