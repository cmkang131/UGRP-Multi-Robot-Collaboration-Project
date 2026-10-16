"""Array-only checks: never import a simulator or run physics on the Mac."""
import json
from types import SimpleNamespace
import numpy as np
import pytest
from scripts.simalt_compiled_compat import export_reference, apply_reference, export_geometry, apply_geometry


def model():
    m = SimpleNamespace(nu=2, actuator=lambda i: SimpleNamespace(name=['a', 'b'][i]))
    for name in ('actuator_gainprm', 'actuator_biasprm', 'body_mass', 'body_inertia',
                 'dof_damping', 'dof_armature', 'geom_friction', 'geom_solref', 'geom_solimp'):
        setattr(m, name, np.ones((2, 3)))
    return m


def test_exact_compiled_copy_and_fail_closed(tmp_path):
    xml = tmp_path/'scene.xml'; xml.write_text('fixed XML')
    path = tmp_path/'compiled.json'
    reference = model(); reference.actuator_biasprm[:, 2] = [-2., -3.]
    export_reference(reference, xml, '3.12.0', path)
    target = model()
    record = apply_reference(target, xml, path)
    assert np.array_equal(target.actuator_biasprm, reference.actuator_biasprm)
    assert len(record['changes']) == 2
    target.body_mass[0, 0] = 7.
    with pytest.raises(ValueError, match='body_mass'):
        apply_reference(target, xml, path)
    target = model(); target.actuator = lambda i: SimpleNamespace(name='wrong')
    with pytest.raises(ValueError, match='order'):
        apply_reference(target, xml, path)
    xml.write_text('different XML')
    with pytest.raises(ValueError, match='XML'):
        apply_reference(model(), xml, path)


def test_geometry_transfer_checks_layout_before_any_mutation(tmp_path):
    xml=tmp_path/'scene.xml';xml.write_text('fixed XML')
    def geometry():
        return SimpleNamespace(ngeom=1, geom=lambda i: SimpleNamespace(name='g'),
            geom_type=np.array([7],dtype=np.int32), geom_quat=np.ones((1,4)),
            mesh_vert=np.ones((2,3)), bvh_aabb=np.ones((2,6)))
    source=geometry();path=tmp_path/'geometry.npz'
    export_geometry(source,xml,'3.12.0',path)
    target=geometry();target.mesh_vert[:]=2
    target.bvh_aabb=np.ones((3,6))
    with pytest.raises(ValueError,match='layout mismatch'):
        apply_geometry(target,xml,path)
    assert np.all(target.mesh_vert==2)
    target=geometry();target.mesh_vert[:]=2
    record=apply_geometry(target,xml,path)
    assert np.array_equal(target.mesh_vert,source.mesh_vert)
    assert record['changes'][0]['array']=='mesh_vert'
    target.geom_type[0]=6
    with pytest.raises(ValueError,match='structural'):
        apply_geometry(target,xml,path)
