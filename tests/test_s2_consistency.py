import numpy as np
import pytest
from scripts.audit_s2_consistency import summarize
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from harness.zone_solo_cyan_consistency import attach,covariance_basis

spec=importlib.util.spec_from_file_location('noise_fit',Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/fit_consistency_noise.py')
fit_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(fit_module)


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


def test_default_off_is_identity_and_never_reads_calibration():
    runtime=SimpleNamespace(record=lambda:dict(commands=[dict(turn=.35)],cov=[1,2,3]))
    before=json.dumps(runtime.record()).encode();state=vars(runtime).copy()
    assert attach(runtime,calibration=object()) is runtime
    assert vars(runtime)==state and json.dumps(runtime.record()).encode()==before


def test_nav2_omni_covariance_and_unidentifiable_fit():
    alpha=np.array([.1,.2,.3,.4,.5]);q=np.einsum('i,ijk->jk',alpha,covariance_basis([0,2,.3]))
    assert np.diag(q)==pytest.approx([.5*4+.4*.09,.3*4+.4*.09,.1*.09+.2*4])
    sample=dict(basis=covariance_basis([0,2,.3]).tolist(),R=np.eye(3).tolist(),error=[0,0,0])
    result=fit_module.fit([sample]*20)
    assert not result['fit_admitted'] and result['rank']==3


def test_gaussian_mle_uses_only_residual_measurement_covariance():
    rng=np.random.default_rng(4);alpha=np.array([.1,.2,.3,.4,.5]);samples=[]
    for i in range(1200):
        delta=[.2 if i%2 else .02,.05,.03 if i%2 else .3]
        basis=covariance_basis(delta);r=np.eye(3)*1e-5
        err=rng.multivariate_normal(np.zeros(3),np.einsum('i,ijk->jk',alpha,basis)+r)
        samples.append(dict(basis=basis.tolist(),R=r.tolist(),error=err.tolist()))
    original=copy.deepcopy(samples);result=fit_module.fit(samples)
    assert result['fit_admitted'] and result['rank']==5
    assert np.allclose(result['alpha'],alpha,rtol=.18)
    assert samples==original
