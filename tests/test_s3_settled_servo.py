import json
import math
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from harness.zone_s3_settled_servo import Options, Selector, SettleGate, attach_endpoint, attach_solo
from harness.zone_s3_pair_alignment import project
from harness.zone_solo_cyan_path_heading import command_reason
from harness.zone_final_pair_vision import GRASP_RADIUS_M

ROOT=Path(__file__).resolve().parents[1]


def profiles():
    return json.loads((ROOT/'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']


def test_all_off_identity_and_each_toggle_is_explicit():
    marker=object()
    assert attach_endpoint(marker) is marker and attach_solo(marker) is marker
    p=profiles();e=[.023,.002,.157]
    assert Selector()(p,e)==project(p,e)
    for flag in asdict(Options()):
        value=Options(**{flag:True});assert value.enabled
        assert Selector(value)(p,e)[2]['options'][flag] is True
    with pytest.raises(ValueError):Options(proportional_pulse='on')


def test_subminimum_error_holds_without_forging_alignment():
    selector=Selector(Options(True,True,True,True))
    # Still outside original3mm success tolerance; minimum12.9mm step cannot fit.
    action,profile,info=selector(profiles(),[.005,0.,0.])
    assert profile is None and not any(action[k] for k in ('forward','left','turn'))
    assert info['reason']=='below_calibrated_resolution' and not info['aligned_receipt']
    assert info['suppressed'][0]['requested_s']<.1
    assert info['thresholds_changed'] is False


def test_hysteresis_entry_and_exit_are_separate_from_success():
    selector=Selector(Options(deadband_hysteresis=True,separate_axes=True))
    p=profiles();selector(p,[.0029,0.,0.])
    assert selector(p,[.004,0.,0.])[2]['reason']=='deadband_hold'
    assert selector.latched[0]
    selector(p,[.0046,0.,0.]);assert not selector.latched[0]


def test_rotation_then_translation_are_single_axis_existing_profiles():
    p=profiles();selector=Selector(Options(True,True,True,True))
    action,profile,info=selector(p,[.023,.002,.157])
    assert action['turn'] and not action['forward'] and not action['left']
    assert command_reason(action) is None and profile in p.values()
    action,profile,info=selector(p,[.023,0.,.02])
    assert action['forward'] and not action['turn'] and not action['left']
    assert info['proportional_requested_s']>=action['duration_s']
    assert Selector(Options(True,True,True,True),angle_required=False)(p,[0,0,1.])[1] is None


def test_settle_gate_rejects_pre_settle_and_repeated_frames():
    gate=SettleGate();assert gate.ready(1.,None)
    gate.issued(1.,dict(times=[0,.2]),{'frame_id':7,'sim_time':1.})
    assert not gate.ready(1.49,{'frame_id':8,'sim_time':1.49})
    assert not gate.ready(1.5,{'frame_id':8,'sim_time':1.49})
    assert not gate.ready(1.5,{'frame_id':7,'sim_time':1.5})
    assert gate.ready(1.5,{'frame_id':8,'sim_time':1.5})


def test_pair_actual_port_and_no_aligned_receipt_on_suppressed_command(tmp_path,monkeypatch):
    from tests import s3_stage_probe as probe
    from harness import zone_s3_recovery_contract as contract
    from harness.zone_s3_recovery_runtime import Runtime
    monkeypatch.setattr(probe,'contract',contract);monkeypatch.setattr(probe,'Runtime',Runtime)
    p=probe.Probe(tmp_path,monkeypatch)
    try:
        p.refresh(1.)
        for ep in p.eps.values():
            attach_endpoint(ep,Options(True,True,True,True))
            ep.controller.set('align',1.)
            ob=ep.controller._align.__func__.__globals__['ob']
            command=ob.align_command(dict(grip_base_m=[GRASP_RADIUS_M+.023,.002],axis_heading_rad=.157))
            ep.controller.drive(command,1.);rows=p.drain(ep,1.)
            assert any(a.get('turn') for a in rows)
            assert all(command_reason(a) is None for a in rows)
            command=ob.align_command(dict(grip_base_m=[GRASP_RADIUS_M+.005,0.],axis_heading_rad=0.))
            assert command is not None and not command['forward'] and not command['turn']
            ep.controller.drive(command,1.6);p.drain(ep,1.6)
            assert not ep.controller.claims.get('aligned')
    finally:p.runtime.close()


def test_solo_fresh_rgb_gate_and_non_alignment_actions_unchanged():
    p=profiles();calls=[]
    own=SimpleNamespace(state='align',target=[GRASP_RADIUS_M+.03,0.],pulse_profiles=p,
        fine_rows=[{'t':1.}],last_obs={'frame_id':1,'sim_time':1.},robot_id='r3',record=lambda:{})
    def step(now):
        calls.append(now);own.fine_rows.append({'t':now})
        return [('r3',dict(kind='mecanum',forward=.35,left=0.,turn=0.,duration_s=.1))]
    own.step=step
    attach_solo(own,Options(True,True,True,True))
    assert own.step(1.)[0][1]['forward']
    assert own.step(1.2)==[] and calls==[1.]
    own.last_obs={'frame_id':2,'sim_time':1.5};assert own.step(1.5)
    assert own.record()['s3_settled_servo']['runtime_gt'] is False
    own.state='lift';assert own.step(1.55)


def test_frozen_whole_batch_includes_all_pair_and_cyan_failures():
    from scripts.run_s3_settled_cohort import PLAN,commands
    plan=json.loads(PLAN.read_text());rows=commands(plan,'a'*40)
    assert len(rows)==10 and plan['max_simultaneous']==10
    assert [r['condition'] for r,a in rows if r['case']=='pair']==list(range(6))
    assert [r['condition'] for r,a in rows if r['case']=='cyan']==[0,3,4,5]
    assert all(set(plan['flags']).issubset(args) for r,args in rows)


@pytest.mark.parametrize('case', ['pair','cyan'])
def test_composed_runner_reaches_loop_with_configured_cap_and_hooks(tmp_path,monkeypatch,case):
    """Exercise both nested bind layers and the real probe loop with no physics."""
    from scripts import run_s3_settled_probe as runner
    from harness import zone_s3_recovery_runtime
    stage=runner.stage;p=stage.previous;hooks=[]
    class Host:
        def __init__(self,b,out,seed):self.now=0.;self.commands={r:{1:2000} for r in p.ROBOTS}
        def reset(self,cap):pass
        def set_deadline(self,t):assert t==5.
        def eval_sample(self):pass
        def capture(self):return {}
        def advance_to(self,t):self.now=t
        def issue(self,*a):pass
        def close(self):pass
    class Own:
        def __init__(self,rid):
            self.robot_id=rid;self.state='init';self.failure=None;self.servo={1:2000};self.last_obs={}
            self.vision=SimpleNamespace(detect=lambda *a:[{'estimated_box_center_base_m':[.24,0.,0.]}])
        def set_state(self,s,t):self.state=s
        def step(self,t):self.state='carry';return []
    class Controller:
        state='init';failure=None;s3_alignment_entry={}
        def set(self,s,*a,**kw):self.state=s
    class Runtime:
        def __init__(self,*a,**kw):
            self.localizers={r:Own(r) for r in p.ROBOTS}
            self.pair=SimpleNamespace(producer=SimpleNamespace(step=lambda t:[],arm_step=lambda t:[]))
        def initial_commands(self,*a):pass
        def on_frames(self,*a):pass
        def on_command(self,*a):pass
        def record(self):return {}
        def close(self):pass
    monkeypatch.setattr(stage,'StageBackend',Host)
    monkeypatch.setattr(zone_s3_recovery_runtime,'Runtime',Runtime)
    monkeypatch.setattr(p,'restore_scene',lambda *a:None)
    monkeypatch.setattr(p,'assert_frame_commands',lambda *a:None)
    monkeypatch.setattr(p,'environment_record',lambda:{})
    monkeypatch.setenv('MUJOCO_GL','osmesa')
    monkeypatch.setattr(p,'enter_pair',lambda rt,*a:{r:SimpleNamespace(own=rt.localizers[r],controller=Controller()) for r in ('r1','r2')})
    monkeypatch.setattr(stage,'attach_endpoint',lambda *a,**kw:None)
    monkeypatch.setattr(runner,'attach_endpoint',lambda ep,opts:hooks.append((ep.own.robot_id,opts)))
    monkeypatch.setattr(runner,'attach_solo',lambda own,opts:hooks.append((own.robot_id,opts)))
    before=dict(p.run.__kwdefaults__)
    options=Options(True,True,True,True)
    result=runner.run(runner.bundle('0'*40,case,0,options,5.),tmp_path/'raw')
    assert result['status']=='DEV_STAGE_FINISHED',result.get('failure')
    assert result['check_sim_s']==5.
    assert hooks==[(rid,options) for rid in (('r1','r2') if case=='pair' else ('r3',))]
    assert p.run.__kwdefaults__==before
    assert json.loads((tmp_path/'raw/environment.json').read_text())['concurrent_probe_limit']==10
