import hashlib
from pathlib import Path

import pytest

from harness.s4_live_transport import validate_receipt
from harness.zone_study_llm_driver import HostError
from scripts import openrouter_upstream as orp
from scripts.s4_proxy_relay import accepted_call_id


def receipt():
    sha = hashlib.sha256(Path(orp.__file__).read_bytes()).hexdigest()
    return dict(schema='ugrp.s4_ssh_proxy.v1', remote_url='http://127.0.0.1:18393/v1/chat/completions',
                proxy=dict(source_sha256=sha), driver_profile='study_gemma4_31b_v1', single_model=True,
                fallback_enabled=False, upstream='openrouter_v1', openrouter_v1=dict(orp.config(), source_sha256=sha),
                checked_unix=100, valid_for_s=27000, audit_per_post=True,
                authentication='existing_mac_proxy_no_credentials_transferred')


def test_long_receipt_requires_profile_and_expires_before_vm_guard():
    r = receipt()
    with pytest.raises(HostError):
        validate_receipt(r, now=101, remote_url=r['remote_url'])
    r['session_profile'] = 'e2e13_7h_v1'
    assert validate_receipt(r, now=25300, remote_url=r['remote_url']) == r
    for bad in ({**r, 'valid_for_s': 27001}, {**r, 'session_profile': 'unbounded'}):
        with pytest.raises(HostError):
            validate_receipt(bad, now=101, remote_url=r['remote_url'])
    with pytest.raises(HostError):
        validate_receipt(r, now=27101, remote_url=r['remote_url'])


def test_only_six_registered_long_cells_reach_relay():
    for condition, seeds in [('a', range(61001, 61005)), ('b', (61001, 61002))]:
        for seed in seeds:
            assert accepted_call_id(f'e2e13-long-{condition}-s{seed}:call-0001-r1:1')
    for name in ('e2e13-long-b-s61003', 'e2e13-long-c-s61001', 'e2e13-long-a-s61005',
                 'other-e2e13-long-a-s61001', 'e2e13-long-a-s61001-r2'):
        assert not accepted_call_id(name + ':call-0001-r1:1')


def test_seven_hour_wall_cap_keeps_v199_sim_and_controller_options():
    from scripts.run_e2e_ownmap_live import bundle
    from harness.e2e_exact_speedups import OFF
    kwargs = dict(enabled=True, path_follow='rpp_v1', dev_light=True,
                  stall_bundle=True, mapping_budget='case_cap_v1')
    default = bundle('a' * 40, 61001, 'study_gemma4_31b_v1', **kwargs)
    long = bundle('a' * 40, 61001, 'study_gemma4_31b_v1', wall_cap_s=25200, **kwargs)
    assert default['wall_cap_s'] == 12600
    assert long['wall_cap_s'] == 25200
    assert long['execution_bundle_id'] == 'e2e-stall-budget-v199'
    assert long['case_cap_s'] == long['e2e_options']['mapping_budget_s'] == 1800
    assert long['e2e_options'] == default['e2e_options']
    assert not any(vars(OFF).values())
    for cap in (25201, float('inf'), float('nan'), 0):
        with pytest.raises(ValueError, match='FINITE_WALL_CAP_REQUIRED'):
            bundle('a' * 40, 61001, 'study_gemma4_31b_v1', wall_cap_s=cap, **kwargs)
