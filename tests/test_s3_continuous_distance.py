"""Offline contracts, motor stub sweep and evaluator counterexamples; no physics."""
import json
import math
from types import SimpleNamespace
from pathlib import Path
import pytest


def test_frozen_twelve_distance_seed_conditions_preserve_plant_and_inputs(monkeypatch):
    from scripts import run_s3_continuous_distance as runner
    from scripts.run_s3_continuous_cohort import commands
    monkeypatch.setattr(runner,'source_closure',lambda *a:())
    plan=json.loads((runner.ROOT/runner.PLAN).read_text())
    base=json.loads((runner.ROOT/runner.TEMPLATE).read_text())
    cases=commands(plan,'a'*40)
    assert len(cases)==len({r['name'] for r,_ in cases})==12
    for r,args in cases:
        b=runner.bundle('a'*40,r['distance_m'],r['seed'])
        assert len(b['registered_route'])==2
        assert math.dist(*b['registered_route'])==pytest.approx(r['distance_m'])
        assert b['model_calls']==0 and b['weld']=='off' and not b['known_start_information']
        assert b['options']['heading_mode']=='path_tangent_v1'
        assert 'coupled_beam_carry' in b['heading_exceptions']
        assert b['continuous_distance']['intermediate_release'] is False
        for key in ('drive_profile','contact_profile','s3_camera_binding','render_nearclip','controller_config'):
            assert b[key]==base[key]
        assert '--execute' in args
    with pytest.raises(ValueError):runner.bundle('a'*40,5.,18601)


def test_all_long_routes_statically_fit_unchanged_map_door_and_bounds():
    from scripts import run_s3_integer_carry as integer
    root=Path(__file__).resolve().parents[1]
    static=json.loads((root/'maps/zones/zone_wide_door_geometry_v3.json').read_text())
    for d in (.85,1.5,2.5,4.):
        route=[[0.,.05],[d,.05]]
        plan=integer.route_plan({},static,route)
        assert plan['route']==route and len(plan['route'])==2


def test_full_distance_pulses_pass_real_ports_once_and_never_turn(tmp_path,monkeypatch):
    from tests.test_s3_full_route import probe
    from harness.zone_s3_synchronized_carry import attach as coupled,OPTION as CARRY
    from harness.zone_s3_integer_carry import attach,OPTION,PulseWindows
    p=probe(tmp_path,monkeypatch)
    try:
        for d in (.85,1.5,2.5,4.):
            plans=[]
            for rid,ep in p.eps.items():
                ctl=ep.controller;ctl.v3_plan['route']=[[0,.05],[d,.05]];ctl.seg=0;ctl.segments=[d]
                coupled(ep,CARRY);attach(ep,OPTION)
                schedule=ctl.door_schedule(2.)
                window=PulseWindows(schedule);motions=[]
                for n in range(40,round(schedule[-1][1]*20)+1):
                    _,command=window.select(n/20)
                    if command and any(command.values()):
                        action=dict(kind='mecanum',**command,duration_s=ctl.s3_carry_pulse_s)
                        p.host.ports[rid].apply(action,n/20)
                        motions.append(command)
                assert len(motions)==len(schedule)-1>40
                assert all(sum(v!=0 for v in c.values())==1 and c['turn']==c['left']==0 for c in motions)
                plans.append(motions)
            assert len(plans[0])==len(plans[1])
            assert all(a['forward']==-b['forward'] for a,b in zip(*plans))
    finally:p.runtime.close()


def synthetic_raw(tmp_path):
    raw=tmp_path/'raw';raw.mkdir()
    def write(name,value):
        path=raw/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
    def lines(name,value):
        path=raw/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(''.join(json.dumps(x)+'\n' for x in value))
    tt=[i*.05 for i in range(7)]
    write('artifacts.sha256.json',{})
    write('bundle.json',dict(continuous_distance=dict(target_m=.85),seed=18601,source_sha='a'*40))
    write('result.json',dict(status='DEV_STAGE_FINISHED',model_calls=0,wall_s=1,check_sim_s=1,
        final={r:dict(state='released',failure=None) for r in ('r1','r2')}))
    write('stage-states.json',[dict(t=t,robots={r:dict(state='carry') for r in ('r1','r2')}) for t in tt]
        +[dict(t=.35,robots={r:dict(state='lower') for r in ('r1','r2')})])
    lines('eval_only/setdown.jsonl',[dict(t=t,fingers={r:[True,True] for r in ('r1','r2')},cargo_tilt_deg=1.,body_origin_z_m=.1) for t in tt])
    lines('eval_only/referee_truth.jsonl',[dict(t=t,items=dict(beam_1=dict(x=t/.3*.85,y=0,z=.1))) for t in tt])
    lines('eval_only/continuous-poses.jsonl',[dict(t=t,robots={r:dict(actual_xy_m=[t/.3*.85+i,0.],actual_yaw_rad=i*math.pi,
        estimated_xy_m=[t/.3*.85+i+.01,0.]) for i,r in enumerate(('r1','r2'))}) for t in tt])
    return raw,write,lines


def test_evaluation_only_safe_distance_and_persistent_grip_loss_counterexample(tmp_path):
    from scripts.evaluate_s3_continuous_distance import evaluate
    raw,write,lines=synthetic_raw(tmp_path)
    limits=dict(tilt_deg=10.,persistent_grip_loss_s=.2,endpoint_shortfall_m=.020,
        axis_displacement_disagreement_m=.020,opposed_heading_drift_rad=.10)
    good=evaluate(raw,limits)
    assert good['safe'] and good['actual_continuous_distance_m']==pytest.approx(.85)
    assert good['carrier_axis_error_max_m']==pytest.approx([0.,0.])
    # Whole-episode terminal remains a failure; an unrelated, supported-floor
    # guard after carry must not be labelled a load drop inside the carry window.
    write('result.json',dict(status='PHYSICAL_STOP',failure='PhysicalStop: LOAD_DROP:beam_1',
        model_calls=0,wall_s=1,check_sim_s=1,final={}))
    terminal=evaluate(raw,limits)
    assert terminal['safe'] and not terminal['drop']
    assert not terminal['whole_episode_completed'] and terminal['post_carry_guard_abort']
    samples=[json.loads(x) for x in (raw/'eval_only/setdown.jsonl').read_text().splitlines()]
    for x in samples:x['fingers']['r2']=[False,True]
    lines('eval_only/setdown.jsonl',samples)
    bad=evaluate(raw,limits)
    assert not bad['safe'] and bad['max_grip_loss_s']['r2']>=.2
    assert bad['reasons']==['persistent_grip_loss']
