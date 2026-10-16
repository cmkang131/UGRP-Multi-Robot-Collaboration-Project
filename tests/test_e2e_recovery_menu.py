"""Saved own-fact replay with explicit synthetic safety rejection; no physics/API."""
import copy,json
from pathlib import Path
import pytest
from harness import e2e_recovery_menu as m
from harness import e2e_body_semantics as sem
from tests.test_e2e_body_code import gate


def saved_case():
    row=json.loads((Path(__file__).parents[1]/'experiments/2026-10-12-e2e18/r79-body-hold-own-input.json').read_text())['saved_own_input']
    assert row['choice']=='hold_and_reobserve' and list(row['candidates'])==['hold_and_reobserve']
    g,tr,robots=gate('align');g.facts('r1',0)
    facts=copy.deepcopy(row['facts']);g.memory['r1'].history.extend(facts['recent_decisions'])
    # The raw row contains only the filtered menu. These commands deliberately
    # model a rejected standoff and available safe detour/camera, not a claim
    # to replay the unsaved map-filter internals.
    def recovery(rid,now,f):
        if 'recover_standoff' not in f['recovery_strategies_tried']:
            return 'recover_standoff',('synthetic rejected standoff',('script',1.,[(0.,sem.pulse('forward_short'))]))
        return 'recover_camera_pan',('camera reacquisition',('script',.6,[(0.,dict(kind='look',pan_pulse=1450))]))
    g.recovery=recovery;g.map_safe=lambda rid,c:c.get('forward',0)<=0
    menu={'detour_right':('safe right step',('script',1.,[(0.,sem.pulse('strafe_right_small'))])),
          'hold_and_reobserve':('hold',('script',1.,[]))}
    return g,facts,menu


@pytest.mark.parametrize('option',['off','alternatives_v1','skip_rejected_v1'])
def test_rejected_recovery_does_not_erase_safe_alternative(option):
    g,facts,menu=saved_case();before=copy.deepcopy(facts['recovery_strategies_tried']);m.install(g,option)
    safe=g.safe_menu('r1',160.8,menu,facts)
    _,choice,f=g.prepare_decision('r1',160.8,'motion',safe,'detour_right',facts)
    if option=='off':assert choice=='hold_and_reobserve' and list(safe)==['hold_and_reobserve']
    elif option=='alternatives_v1':assert choice=='detour_right' and f['recovery_menu_fallback']==option
    else:assert choice=='recover_camera_pan' and f['safety_rejected_recovery_candidates']==['recover_standoff']
    assert 'recover_standoff' not in safe
    assert facts['recovery_strategies_tried']==before


@pytest.mark.parametrize('option',['alternatives_v1','skip_rejected_v1'])
def test_required_safety_hold_and_all_unsafe_are_preserved(option):
    g,facts,menu=saved_case();facts['partner_stop']=True;m.install(g,option)
    safe=g.safe_menu('r1',160.8,menu,facts)
    assert list(safe)==['hold_and_reobserve']
    assert not safe['hold_and_reobserve'][1][2]
    facts['partner_stop']=False;g.map_safe=lambda rid,c:False
    assert list(g.safe_menu('r1',160.8,menu,facts))==['hold_and_reobserve']


def test_registered_recovery_candidates(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    args,kw=[],{}
    def capture(*a,**k):args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture);p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1',boundary_lifecycle='abort_v1',dialogue_call_policy='event_v1',call_snapshot='prepared_v1',speech_context='recent4_v1',post_relook='carry_through_v1',body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1',approach_efficiency='regulated_v1',admission_clock='tick_v1')
    for v,option in [(379,'alternatives_v1'),(380,'skip_rejected_v1')]:
        b=bundle(*args,**kw,recovery_menu=option);require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert accepted_call_id(f'speed-gate-e2e18-v{v}-s61013-r80:call-0001-r1:1')
        assert m.parent_for_validation(b)['e2e_options']==bundle(*args,**kw)['e2e_options']
        bad=copy.deepcopy(b);bad['recovery_menu_parameters']['safety_filters']='disabled'
        with pytest.raises(ValueError):require_current(bad,ROOT)
