"""Array-only checks: never import a simulator or run physics on the Mac."""
import json
from types import SimpleNamespace
import numpy as np
import pytest
from scripts.simalt_compiled_compat import export_reference, apply_reference


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
