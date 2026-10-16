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


def export_geometry(model, xml, version, path):
    """Compiled geometry and its accelerator caches, not an XML approximation."""
    import numpy as np
    fields = {name: getattr(model, name).copy() for name in dir(model)
              if name.startswith(('geom_', 'mesh_', 'bvh_'))
              and isinstance(getattr(model, name), np.ndarray)}
    metadata = {'mujoco': version, 'xml_sha256': digest(xml),
        'geom_names': [model.geom(i).name for i in range(model.ngeom)],
        'fields': {name: {'shape': list(value.shape), 'dtype': str(value.dtype),
                          'sha256': hashlib.sha256(value.tobytes()).hexdigest()}
                   for name, value in fields.items()}}
    with Path(path).open('xb') as stream:
        np.savez_compressed(stream, **fields)
    metadata['npz_sha256'] = digest(path)
    Path(str(path)+'.json').write_text(json.dumps(metadata, indent=2)+'\n')
    return metadata


def apply_geometry(model, xml, path):
    import numpy as np
    reference = json.loads(Path(str(path)+'.json').read_text())
    if (reference['mujoco'] != '3.12.0' or reference['xml_sha256'] != digest(xml)
            or reference['npz_sha256'] != digest(path)):
        raise ValueError('compiled geometry reference version/XML/hash mismatch')
    if reference['geom_names'] != [model.geom(i).name for i in range(model.ngeom)]:
        raise ValueError('compiled geometry geom ordering mismatch')
    arrays = np.load(path, allow_pickle=False)
    # Check the complete transfer before writing anything. Structure and all
    # physical parameters must already agree. Only the principal-axis mesh
    # representation and its associated compiled caches are replaced together.
    structural = ('geom_type', 'geom_bodyid', 'geom_dataid', 'geom_friction',
        'geom_solref', 'geom_solimp', 'geom_margin', 'geom_gap', 'geom_condim',
        'geom_contype', 'geom_conaffinity', 'geom_solmix', 'geom_priority')
    for name in arrays.files:
        target = getattr(model, name, None)
        if target is None or target.shape != arrays[name].shape or target.dtype != arrays[name].dtype:
            raise ValueError('compiled geometry layout mismatch: '+name)
        if name in structural and not np.array_equal(target, arrays[name]):
            raise ValueError('compiled geometry physical/structural difference: '+name)
    changes=[]
    for name in arrays.files:
        target = getattr(model, name)
        if not np.array_equal(target, arrays[name]):
            changes.append({'array': name, 'entries': int(np.count_nonzero(target != arrays[name])),
                'before_sha256': hashlib.sha256(target.tobytes()).hexdigest(),
                'after_sha256': hashlib.sha256(arrays[name].tobytes()).hexdigest()})
        target[:] = arrays[name]
    return {'mode': 'compiled-geometry-312-v1', 'reference': str(path),
        'reference_sha256': digest(path), 'fields_copied': len(arrays.files), 'changes': changes,
        'basis': 'same XML and same physical geometry; C312 compiled mesh principal axes, vertices and caches transferred as a unit',
        'new_physical_parameters': False}
