import copy
from types import SimpleNamespace
import pytest
from harness import e2e_explore_idle as m
from tests.test_pair_llm_s4_host import setup_data, no_external_work  # noqa: F401


@pytest.mark.parametrize('option', m.OPTIONS)
def test_registration_scope_roundtrip_and_runtime_instance(option):
    parent = dict(execution_bundle_id=m.PARENT, e2e_options=dict(
        explore_deadlock='replan_v1', dialogue_decider='code_v1'))
    b = copy.deepcopy(parent)
    assert m.compose(b, option)
    restored = m.parent_for_validation(b)
    assert restored['e2e_options'] == parent['e2e_options']
    assert restored['execution_bundle_id'] == m.PARENT
    bad = copy.deepcopy(b); bad['explore_idle_parameters']['idle_s'] = 0
    with pytest.raises(ValueError): m.parent_for_validation(bad)
    robots = {rid: SimpleNamespace(goal=SimpleNamespace(explore_deadlock=SimpleNamespace(idle_threshold_s=30.))) for rid in ('r1', 'r2')}
    m.install(robots, option)
    assert all(r.goal.explore_deadlock.idle_threshold_s == m.OPTIONS[option][1] for r in robots.values())
    parent['e2e_options']['body_controller'] = 'jev_v1'
    with pytest.raises(ValueError): m.compose(parent, option)


def test_default_off_no_changes():
    b = {}
    assert m.compose(b) == () and b == {}
    m.install({})


def test_actual_code_protocol_idle_and_combined_body_registration(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle, ROOT
    from harness.e2e_runtime_registration import require_current
    from harness.e2e_code_stack import parent_for_validation
    args, kw = [], {}
    def capture(*a, **k):
        args.extend(a); kw.update(k); return bundle(*a, **k)
    monkeypatch.setattr(p, 'bundle', capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1', 276, 'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1', relook_giveup='dev_light_rest_v1')
    protocol = dict(post_relook='carry_nominal_v1', perception_fast='shadow_axes_v1',
                    controller_timing='phase_v1', llm_memory='v1_commands', dialogue_decider='code_v1')
    for option, version in [('off', 346), ('idle5_v1', 347), ('idle10_v1', 348)]:
        b = bundle(*args, **kw, **protocol, explore_idle=option)
        assert b['execution_bundle_id'] == f'e2e18-v{version}'
        require_current(b, ROOT)
        last_seed = list(args); last_seed[1] = 61013
        expanded = bundle(*last_seed, **kw, **protocol, explore_idle=option)
        require_current(expanded, ROOT)
        assert expanded['seed'] == 61013
    body = dict(post_relook='carry_through_v1', body_controller='jev_v1', body_backend='code_v1')
    old = bundle(*args, **kw, **body)
    b = bundle(*args, **kw, **body, body_protocol_stack='code_v1')
    assert old['execution_bundle_id'] == 'e2e18-v349'
    assert b['execution_bundle_id'] == 'e2e18-v350'
    require_current(b, ROOT)
    expanded = bundle(*last_seed, **kw, **body, body_protocol_stack='code_v1')
    require_current(expanded, ROOT)
    assert expanded['seed'] == 61013
    with pytest.raises(ValueError, match='REGISTERED_MODEL_SEED_REQUIRED'):
        bundle(*last_seed, **kw, **body)
    assert parent_for_validation(b)['e2e_options'] == old['e2e_options']
    bad = copy.deepcopy(b); bad['e2e_options']['dialogue_decider'] = 'd1_v1'
    with pytest.raises(ValueError): require_current(bad, ROOT)
