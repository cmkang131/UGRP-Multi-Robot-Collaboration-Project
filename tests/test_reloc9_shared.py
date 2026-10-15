from types import SimpleNamespace
import math
import numpy as np
import pytest
from harness.reloc9_wall_guard import filter_observation
from harness.reloc9_rotation import selfmap_model
from scripts.reloc9_metrics import correction_metrics, counts


def test_wall_guard_needs_actual_height_matched_in_frame_top_and_preserves_off():
    image=np.full((480,640,3),100,np.uint8);image[:100]=30
    obs=SimpleNamespace(columns=np.array([100,200,300,400]),b_kind=np.ones(4,int),t_kind=np.ones(4,int),
        b_lo=np.full(4,300.),b_hi=np.full(4,300.),t_lo=np.array([100.,np.nan,180.,100.]),
        t_hi=np.array([100.,np.nan,180.,100.]))
    cm=SimpleNamespace(columns=obs.columns,t_of_row=lambda b:b,rows=lambda t,h:np.array([100.,100.,100.,-20.]))
    assert filter_observation(obs,None,None)[0] is obs
    out,audit=filter_observation(obs,image,cm,True)
    assert out.b_kind.tolist()==[1,0,0,0]
    assert np.isnan(out.b_lo[1:]).all() and obs.b_kind.tolist()==[1,1,1,1]
    assert audit['top_supported_columns']==1
    flat=np.full_like(image,100)
    assert not filter_observation(obs,flat,cm,True)[0].b_kind.any()
    with pytest.raises(ValueError):filter_observation(obs,image,cm,'on')


def test_selfmap_reuses_verified_pulse_response_without_double_carry_scaling():
    from harness.self_pulse_rotation import OPTION
    assert selfmap_model('off',False)=='off'
    assert selfmap_model(OPTION,True)==OPTION
    assert selfmap_model('s2_pulse_v122',True)==OPTION
    with pytest.raises(ValueError):selfmap_model('off',True)
    with pytest.raises(ValueError):selfmap_model(OPTION,'on')


def test_absolute_risk_and_relative_improvement_are_distinct():
    g=[0.,0.,0.]
    r=correction_metrics([.166,0.,math.radians(-69.)],[.17,0.,math.radians(-.6)],g)
    assert r['dangerous'] and r['xy_worsened'] and not r['yaw_worsened'] and not r['worsened']
    r2=correction_metrics([0,0,0],[0,0,math.radians(6)],g)
    assert r2['dangerous'] and not r2['legacy_dangerous'] and r2['worsened']
    summary=counts([dict(evaluation_only=r),dict(evaluation_only=r2)],lambda _:True)
    assert summary['dangerous_accepted_N']==2 and summary['worsened_accepted_N']==1
