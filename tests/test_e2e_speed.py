"""Profiling admission and accounting; no simulator or model execution."""
import pytest
from scripts.s4_proxy_relay import accepted_call_id
from scripts.e2e_speed_measure import profile_rows, measured_run
from types import SimpleNamespace


def test_profile_ledger_is_closed_to_registered_cells():
    for name in ('profile','off','index','validate','both'):
        assert accepted_call_id(f'e2e13-{name}-s61001:call-0001-r1:1')
    assert not accepted_call_id('e2e13-off-s61002:call-0001-r1:1')
    assert not accepted_call_id('e2e13-arbitrary-s61001:call-0001-r1:1')


def test_top20_uses_cumulative_time_with_explicit_denominator():
    stats=SimpleNamespace(stats={(f'{i}.py',i,'f'):(1,2,.1,float(i),{}) for i in range(25)})
    rows=profile_rows(stats,60)
    assert len(rows)==20 and rows[0]['cumulative_s']==24
    assert rows[0]['cumulative_wall_per_sim']==.4


def test_measurement_limit_rejected_before_backend_import():
    with pytest.raises(ValueError):measured_run(None,None,None,None,1,False)
