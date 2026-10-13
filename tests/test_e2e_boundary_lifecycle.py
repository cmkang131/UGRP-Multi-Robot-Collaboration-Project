import copy
import numpy as np
import pytest
from harness import e2e_boundary_lifecycle as m
from tests.test_e2e_boundary_views import fixture
from tests.test_pair_llm_s4_host import setup_data, no_external_work


def test_off_reproduces_missing_target_without_changing_baseline():
    n,g,c=fixture(); n.update(c,np.zeros(3),0.)
    n.target=None; m.install_navigator(n)
    with pytest.raises(TypeError): n.update(c,np.zeros(3),.2)


@pytest.mark.parametrize('option', ['abort_v1','restore_v1'])
def test_external_target_invalidation_preserves_map_and_revalidates(option):
    n,g,c=fixture(); n.update(c,np.zeros(3),0.)
    owned=n.view_target_own.copy(); before=c.raw.copy(); transform=g.explorer.map_to_odom.copy()
    n.target=None; m.install_navigator(n,option); n.update(c,np.zeros(3),.2)
    assert np.array_equal(before,c.raw) and np.array_equal(transform,g.explorer.map_to_odom)
    assert not g.e2e_gate.references
    if option=='abort_v1':
        assert not n.view_active
        assert any(e['reason']=='B_view_external_target_invalidated' for e in n.events)
    else:
        assert n.view_active and np.allclose(n.target,owned)
        n.target=None; c.raw[:]=255; c.costs=c.inflate()
        n.update(c,np.zeros(3),.4)
        assert not n.view_active
        assert any(e['reason']=='B_view_coverage_lost' for e in n.events)


def test_actual_registration_and_narrow_relay_namespace(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle,ROOT
    from harness.e2e_runtime_registration import require_current
    from scripts.s4_proxy_relay import accepted_call_id
    args,kw=[],{}
    def capture(*a,**k): args.extend(a);kw.update(k);return bundle(*a,**k)
    monkeypatch.setattr(p,'bundle',capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1',276,'range_wall_v1')
    args[1]=61013;kw.update(stage_physics='release_dt1_v1',relook_giveup='dev_light_rest_v1')
    for (parent,option),version in m.VERSIONS.items():
        if parent=='e2e18-v350':
            flags=dict(post_relook='carry_through_v1',body_controller='jev_v1',body_backend='code_v1',body_protocol_stack='code_v1')
        else:
            flags=dict(post_relook='carry_nominal_v1',perception_fast='shadow_axes_v1',controller_timing='phase_v1',llm_memory='v1_commands',dialogue_decider='code_v1',explore_idle='idle5_v1' if parent.endswith('347') else 'idle10_v1')
        b=bundle(*args,**kw,**flags,boundary_lifecycle=option);require_current(b,ROOT)
        assert b['execution_bundle_id']==f'e2e18-v{version}'
        assert m.parent_for_validation(b)['e2e_options']==bundle(*args,**kw,**flags)['e2e_options']
        bad=copy.deepcopy(b);bad['boundary_lifecycle_parameters']['preserve_map_pose']=False
        with pytest.raises(ValueError):require_current(bad,ROOT)
        assert accepted_call_id(f'speed-gate-e2e18-v{version}-s61013-r76:call-0001-r1:1')
    assert not accepted_call_id('e2e18-v351-s61014-r76:call-0001-r1:1')
