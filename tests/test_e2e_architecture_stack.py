"""Existing runtime hooks combined without changing the body or GO/ACK guard."""
import copy
import json
import pytest
from harness import e2e_architecture_stack as m
from tests.test_pair_llm_s4_host import setup_data, no_external_work  # noqa: F401


def test_registration_parent_roundtrip_and_tamper_rejection(monkeypatch):
    from tests import test_e2e_camera_hold as p
    from scripts.run_e2e_ownmap_live import bundle, ROOT
    from harness.e2e_runtime_registration import require_current
    args, kw = [], {}
    def capture(*a, **k):
        args.extend(a); kw.update(k)
        return bundle(*a, **k)
    monkeypatch.setattr(p, 'bundle', capture)
    p.test_registered_wheel_wait_candidate('zero_wheel_v1', 276, 'range_wall_v1')
    kw.update(stage_physics='release_dt1_v1', relook_giveup='dev_light_rest_v1',
              post_relook='carry_through_v1', body_controller='jev_v1')
    for backend in ('jev', 'liquid_d1'):
        old = bundle(*args, **kw, body_backend=backend)
        for mode in ('fast_v1', 'memory_v1'):
            b = bundle(*args, **kw, body_backend=backend, architecture_stack=mode)
            version = m.VERSIONS[(old['execution_bundle_id'], mode)]
            assert b['execution_bundle_id'] == f'e2e18-v{version}'
            require_current(b, ROOT)
            parent = m.parent_for_validation(b)
            for key in ('e2e_options', 'body_controller_parameters', 'body_controller_parent'):
                assert parent[key] == old[key]
            for key, value in [('vote_ref', 'off' if mode == 'memory_v1' else 'v1'),
                               ('dev_light', False)]:
                bad = copy.deepcopy(b); bad['e2e_options'][key] = value
                with pytest.raises(ValueError):
                    require_current(bad, ROOT)
            assert '--architecture-stack' in json.loads((ROOT / f'configs/simulation_workflows.d/e2e18_v{version}.json').read_text())['workflows'][0]['required_inputs']
    x = copy.deepcopy(old)
    assert m.compose(x) == () and x == old


def test_body_and_memory_projection_keep_current_key_and_body_separation(tmp_path, setup_data):
    from harness.e2e_s4_live import project
    from harness.s4_event_policy import Options
    from types import SimpleNamespace
    from tests.test_e2e_vote_ref import opened
    from harness.e2e_llm_memory import windows_of
    # Same real request fixture as the live prompt tests: each hook must retain
    # exactly one own image and the current host-provided dialogue key.
    host, dialogue = opened(tmp_path, setup_data, 'off')
    call = SimpleNamespace(call_id='combined-r1', actor='r1', started_sim_s=6.)
    host.trial.snapshot(call)
    r = host.trial.prepare_call(call).request
    b = json.loads(r['messages'][1]['content'])
    out = project(r, options=Options(True, True, 'en'), body_controller='jev_v1',
                  llm_memory='v1', memory=dict(decisions=[], windows=windows_of(dialogue)))
    new = json.loads(out['messages'][1]['content'])
    assert new['dialogue']['key'] == b['dialogue']['key']
    assert out['images'] == r['images'] and out['image_refs'] == r['image_refs']
    assert new['body_controller'] == 'jev_v1'
