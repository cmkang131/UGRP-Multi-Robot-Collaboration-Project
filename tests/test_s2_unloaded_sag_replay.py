import importlib.util
from pathlib import Path
import copy
import math
import numpy as np
import pytest

PATH=Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/replay_unloaded_sag.py'
spec=importlib.util.spec_from_file_location('s2_offline_sag',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_geometry_adds_only_load_delta_and_preserves_input():
    original=copy.deepcopy(m.TABLE)
    base=m.approximation('unloaded')
    out=m.approximation('unloaded_constant_delta')
    for key,rec in base['camera_models']['loaded'].items():
        got=out['camera_models']['loaded'][key]
        assert got['origin_m']==rec['origin_m']
        assert got['chassis_to_floor']==rec['chassis_to_floor']
        r=np.asarray(got['rotation']);np.testing.assert_allclose(r.T@r,np.eye(3),atol=1e-12)
    key='896,2035,1894,1500'
    pitch=lambda table:math.asin(table['camera_models']['loaded'][key]['rotation'][2][2])
    assert pitch(out)-pitch(base)==pytest.approx(m.CRITERIA['constant_delta_rad'],abs=1e-7)
    assert out['camera_models']['unloaded']==original['camera_models']['unloaded']
    assert m.TABLE==original and out['runtime_admitted'] is False


def test_sag_delta_is_difference_not_full_bias():
    delta=m.sag_delta('896,2035,1894,1500')
    assert -0.1<delta<0
    table=m.approximation('unloaded_pr405_sag_delta')
    assert table['load_delta_rad']['896,2035,1894,1500']==delta
    with pytest.raises(ValueError):m.approximation('legacy')


def test_fix_receipts_are_unique_and_window_endpoints_count():
    rows=[{'last_fix_t':t} for t in [None,1,10,10,10.2,11,12,13,14,15,90]]
    got=m.fix_metrics(rows,(10,100))
    assert got['accepted_fixes']==8 and got['independent_fixes']==7
    assert got['max_fix_gap_sim_s']==75 and not got['admission_pass']
    assert not m.fix_metrics([], (10,100))['admission_pass']
    assert m.fix_metrics([{'last_fix_t':t} for t in range(10,101,10)],(10,100))['admission_pass']
