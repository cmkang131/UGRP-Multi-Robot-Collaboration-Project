import numpy as np
import pytest
from scripts.audit_s2_consistency import summarize


def test_bias_variance_and_centering_are_retrospective_only():
    rows=[dict(error=[x,0,0],cov=np.diag([.01,.01,.01]).tolist(),alarm=False,miss=False) for x in (.9,1.1)]
    q=summarize(rows)
    assert q['bias_xy_m_yaw_deg']==pytest.approx([1,0,0])
    assert q['mse_xy_m2_yaw_deg2'][0]==pytest.approx(1.01)
    assert q['variance_xy_m2_yaw_deg2'][0]==pytest.approx(.01)
    assert q['xy_nees_rate']==1 and q['xy_nees_centered_rate']==0
    assert q['xy_nees_centered_mean']==pytest.approx(1)
    assert rows[0]['error'][0]==.9


def test_centering_does_not_hide_underdispersion():
    rows=[dict(error=[x,0,0],cov=np.diag([.001,.001,.001]).tolist(),alarm=True,miss=False) for x in (-1,1)]
    q=summarize(rows)
    assert q['xy_bias_mse_fraction']==0
    assert q['xy_nees_rate']==q['xy_nees_centered_rate']==1
    assert summarize([])==dict(n=0)
