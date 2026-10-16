"""The diagnostic scorer must use the unchanged field score, not a GT prior."""
import importlib.util
from pathlib import Path
import numpy as np
from harness.zone_solo_cyan_likelihood_field import Field,likelihood

spec=importlib.util.spec_from_file_location('grid_audit',Path(__file__).resolve().parents[1]/'experiments/2026-10-06-s2-realism/audit_start_likelihood_grid.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def test_same_score_and_translation_equivariance():
    field=Field(dict(obstacles=[dict(kind='wall',center_m=[2,0],half_extents_m=[.025,2])]))
    poses=np.array([[0,0,0],[0,0,np.pi/2],[1,0,0]])
    points=np.array([[2.,0],[2.,.1]])
    views=[dict(raw=points),dict(raw=points)]
    np.testing.assert_allclose(m.score(field,poses,views,'raw'),2*np.log(likelihood(field,poses,points)),rtol=0,atol=0)
    assert np.argmax(m.score(field,poses,views,'raw'))==0
    np.testing.assert_allclose(m.world([1,2,np.pi/2],np.array([[2.,0]])),[[1,4]])
