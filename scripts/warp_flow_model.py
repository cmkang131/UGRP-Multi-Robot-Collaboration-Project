"""Single immutable model: free-root poses belong to the per-world state.

No SLEEP exception, numerical tolerance, mass or geometry substitution is used.
Canonical XML is an explicit, hashed input shared by N1/N16/64/256 runs.
"""
import hashlib
import xml.etree.ElementTree as ET

POSE = ('pos', 'quat', 'euler', 'axisangle', 'xyaxes', 'zaxis')


def xml_differences(left,right):
    differences=[]
    def walk(a,b,path):
        if a.tag!=b.tag or a.attrib!=b.attrib or (a.text or '').strip()!=(b.text or '').strip():
            differences.append(dict(path=path,left=dict(a.attrib),right=dict(b.attrib)))
        if len(a)!=len(b):
            differences.append(dict(path=path,child_counts=[len(a),len(b)]));return
        for i,(x,y) in enumerate(zip(a,b)):
            walk(x,y,path+'/'+x.tag+'['+str(x.get('name',i))+']')
    walk(left,right,left.tag)
    return differences


def free_roots(root):
    return {b.get('name'): b for b in root.iter('body')
            if b.find('freejoint') is not None or
            any(j.get('type') == 'free' for j in b.findall('joint'))}


def canonical_xml(xml, reference):
    """Require exact structure/materials/dynamics; change only free-root pose."""
    current, target = ET.fromstring(xml), ET.fromstring(reference)
    bodies, originals = free_roots(current), free_roots(target)
    if set(bodies) != set(originals) or None in bodies:
        raise ValueError('canonical model free-root names differ')
    moved = []
    for name, body in bodies.items():
        before = {k: body.get(k) for k in POSE if k in body.attrib}
        after = {k: originals[name].get(k) for k in POSE if k in originals[name].attrib}
        if before != after:
            moved.append(dict(body=name, original=before, canonical=after))
        for key in POSE:
            body.attrib.pop(key, None)
        body.attrib.update(after)
    for root in (current,target):
        for element in root.iter():
            attributes=sorted(element.attrib.items())
            element.attrib.clear();element.attrib.update(attributes)
    result = ET.tostring(current, encoding='unicode')
    expected = ET.tostring(target, encoding='unicode')
    if result != expected:
        # Never pool a different cargo shape or static obstacle arrangement.
        import json
        raise ValueError('non-pose scene/model difference; separate model required: '+json.dumps(xml_differences(current,target)))
    return result, dict(profile='single_model_free_pose_v1', moved=moved,
        canonical_xml_sha256=hashlib.sha256(expected.encode()).hexdigest(),
        mass_size_friction_unchanged=True, sleep_exception_used=False)


def model_arrays_equal(models):
    """Exact post-setup array audit before conversion, including dof_length."""
    import numpy as np
    first = models[0]
    differences = []
    for name in dir(first):
        value = getattr(first, name)
        if not isinstance(value, np.ndarray):
            continue
        for world, model in enumerate(models[1:], 1):
            other = getattr(model, name)
            if value.shape != other.shape or not np.array_equal(value, other):
                differences.append(dict(field=name, world=world,
                    first_shape=list(value.shape), shape=list(other.shape)))
    return dict(exact=not differences, differences=differences,
                worlds=len(models), sleep_exception_used=False)
