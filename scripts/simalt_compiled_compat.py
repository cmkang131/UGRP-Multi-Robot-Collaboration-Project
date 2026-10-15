"""Opt-in compiled actuator compatibility, never a new physical profile.

Only actuator_biasprm[:, 2] may be copied, by actuator name, from the same
XML compiled by MuJoCo 3.12. The official dampratio change is b3dd9e617.
No guessed damping values or source-XML edits are permitted.
"""
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export_reference(model, xml, version, path):
    fields = ('actuator_gainprm', 'actuator_biasprm', 'body_mass', 'body_inertia',
              'dof_damping', 'dof_armature', 'geom_friction', 'geom_solref', 'geom_solimp')
    result = {'mujoco': version, 'xml_sha256': digest(xml),
              'actuator_names': [model.actuator(i).name for i in range(model.nu)],
              'arrays': {k: getattr(model, k).tolist() for k in fields},
              'source': 'https://github.com/google-deepmind/mujoco/commit/b3dd9e617'}
    with Path(path).open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


def apply_reference(model, xml, path, *, ablation=False):
    import numpy as np
    reference = json.loads(Path(path).read_text())
    expected = '3.16.0' if ablation else '3.12.0'
    if reference['mujoco'] != expected or reference['xml_sha256'] != digest(xml):
        raise ValueError('compiled reference version/XML mismatch')
    names = [model.actuator(i).name for i in range(model.nu)]
    if names != reference['actuator_names']:
        raise ValueError('compiled reference actuator order mismatch')
    bias = np.asarray(reference['arrays']['actuator_biasprm'])
    if bias.shape != model.actuator_biasprm.shape or not np.isfinite(bias).all():
        raise ValueError('invalid compiled bias array')
    # Fail closed if any other audited physical array differs. Mesh storage
    # representation changes are not copied; simalt4 audited their geometry.
    for field, values in reference['arrays'].items():
        actual = getattr(model, field)
        expected_array = np.asarray(values)
        if field == 'actuator_biasprm':
            actual = np.delete(actual, 2, axis=1)
            expected_array = np.delete(expected_array, 2, axis=1)
        if not np.array_equal(actual, expected_array):
            raise ValueError('unexpected compiled physical difference: ' + field)
    before = model.actuator_biasprm.copy()
    changed = np.flatnonzero(before[:, 2] != bias[:, 2])
    model.actuator_biasprm[:, 2] = bias[:, 2]
    return {'mode': 'damping-ablation-v1' if ablation else 'compiled-312-v1',
            'reference': str(path), 'reference_sha256': digest(path),
            'reference_version': reference['mujoco'], 'xml_sha256': digest(xml),
            'copied_array': 'actuator_biasprm[:,2]',
            'changes': [{'actuator': names[i], 'before': float(before[i, 2]),
                         'after': float(bias[i, 2])} for i in changed],
            'other_audited_arrays_exact': True,
            'source': reference['source'], 'new_physical_parameters': False}
