import numpy as np
from scripts.diagnose_s3_endpoint_visibility import project

def test_eval_projection_camera_convention_and_fov():
    uv,inside=project([[0,0,-1],[0,1,-1],[0,0,1]],[0,0,0],np.eye(3))
    assert inside.tolist()==[True,False,False]
    assert np.allclose(uv[0],[287.68910608896766,218.69686648455726])
