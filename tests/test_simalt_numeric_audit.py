"""Numeric audit tests use arrays only; no simulator or GL context."""
from types import SimpleNamespace
import numpy as np
from scripts.simalt_numeric_audit import inactive_efm_field, scan_arrays


def test_reports_every_bad_index_including_nonfinite():
    arrays, bad = scan_arrays(SimpleNamespace(x=np.array([0., 3.4e38, 3.5e38, np.nan, np.inf, -np.inf])), 'data')
    assert arrays[0]['bad_count'] == 4
    assert [x['index'] for x in bad] == [[2], [3], [4], [5]]
    assert [x['value'] for x in bad] == [3.5e38, 'nan', 'inf', '-inf']


def test_adapter_never_accepts_state_contacts_or_active_effective_metric():
    for field in ('qpos', 'qvel', 'friction', 'contact', 'efc_D', 'efm_ck'):
        assert not inactive_efm_field(field, 3, 0, 0, 0, 0, 0)
    for i in range(1, 7):
        args = [3, 0, 0, 0, 0, 0]
        args[i-1] = 4 if i == 1 else 1
        assert not inactive_efm_field('efm_c', *args)
    assert inactive_efm_field('efm_c', 3, 0, 0, 0, 0, 0)
