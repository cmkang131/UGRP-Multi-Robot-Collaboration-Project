import pytest
from scripts.warp_flow_model import canonical_xml, model_arrays_equal


def test_only_free_pose_can_change():
    a='<mujoco><worldbody><body name="cargo" pos="1 2 3"><freejoint/><geom size="1" mass="2" friction=".5"/></body><body name="wall" pos="4 0 0"/></worldbody></mujoco>'
    b=a.replace('pos="1 2 3"','pos="2 3 4"')
    result,audit=canonical_xml(b,a)
    assert audit['moved'][0]['body']=='cargo'
    assert audit['mass_size_friction_unchanged']
    assert canonical_xml(result,a)[0]==result
    for old,new in [('size="1"','size="2"'),('mass="2"','mass="3"'),('friction=".5"','friction=".6"'),('pos="4 0 0"','pos="5 0 0"')]:
        with pytest.raises(ValueError,match='non-pose'):
            canonical_xml(b.replace(old,new),a)


def test_dof_length_is_not_exempted():
    import numpy as np
    from types import SimpleNamespace
    models=[SimpleNamespace(dof_length=np.array([1.])),SimpleNamespace(dof_length=np.array([2.]))]
    audit=model_arrays_equal(models)
    assert not audit['exact']
    assert audit['differences'][0]['field']=='dof_length'
