"""gcp6 CPU only: recompile persisted exact XML; no simulation or GPU context.

Derived from the frozen experiments/2026-10-16-warp8/prepare_native_references.py
at source 3170d909089865c45e2cbc6089beb6a2d05e576f. The only behavioral change
is the assigned-host assertion (gcp3 -> gcp6). The approved profile changes only
model options. Prove every exported actuator, material and geometry array agrees
with its old C312 reference before admission.
"""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import sys

BASE_SOURCE_SHA = '3170d909089865c45e2cbc6089beb6a2d05e576f'
EXPECTED_HOST = 'ugrp-act-l4-gcp6'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--old-export', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert socket.gethostname().split('.')[0] == EXPECTED_HOST
    sys.path[:0] = [str(a.source), str(a.source / 'scripts')]
    import mujoco
    import numpy as np
    from sim.warp_native_contact import apply
    from warp_flow_model import canonical_xml
    from simalt_compiled_compat import export_reference, export_geometry
    assert mujoco.__version__ == '3.12.0'
    assert digest(a.source / 'sim/warp_native_contact.py') == 'a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a'
    script_sha = digest(Path(__file__))
    old = json.loads((a.old_export / 'per-world-references.json').read_text())
    canonical = apply((a.old_export / 'canonical-scene.xml').read_text(), 'warp_native_contact_v1')
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'canonical-scene.xml').write_text(canonical)
    references = {}
    proof = []
    seen = set()
    for world in sorted(a.old_export.glob('world-*')):
        xml = world / 'raw/scene.xml'
        if not xml.is_file():
            continue
        old_sha = digest(xml)
        if old_sha in seen:
            continue
        seen.add(old_sha)
        previous = old[old_sha]
        native = canonical_xml(apply(xml.read_text(), 'warp_native_contact_v1'), canonical, world_parameters=True)[0]
        sha = hashlib.sha256(native.encode()).hexdigest()
        folder = a.out / 'references' / sha
        folder.mkdir(parents=True)
        path = folder / 'scene.xml'
        path.write_text(native)
        model = mujoco.MjModel.from_xml_string(native)
        # Exact world-constructor visual setup, not contact/physics tuning:
        # sim/multi_masterpi_production.py:930-933 hides these three housing
        # geoms for each robot via c._n(name). Preserve those prefixed names.
        for gid in range(model.ngeom):
            name = model.geom(gid).name or ''
            if name.split('__')[-1] in ('camera_bracket', 'camera_body', 'camera_lens_visual'):
                model.geom_group[gid] = 5
        ref = export_reference(model, path, mujoco.__version__, folder / 'compiled-312.json')
        geo = export_geometry(model, path, mujoco.__version__, folder / 'compiled-geometry312.npz')
        before = json.loads(Path(previous['actuator']).read_text())
        assert ref['arrays'] == before['arrays'] and ref['actuator_names'] == before['actuator_names']
        with np.load(previous['geometry'], allow_pickle=False) as old_geo, np.load(folder / 'compiled-geometry312.npz', allow_pickle=False) as new_geo:
            assert set(old_geo.files) == set(new_geo.files)
            assert all(np.array_equal(old_geo[k], new_geo[k]) for k in old_geo.files)
        references[sha] = dict(actuator=str(folder / 'compiled-312.json'), geometry=str(folder / 'compiled-geometry312.npz'))
        proof.append(dict(old_xml=str(xml), old_xml_sha256=old_sha, native_xml_sha256=sha,
                          previous=previous, actuator_material_arrays_exact=True, all_geometry_arrays_exact=True,
                          native_actuator_sha256=digest(folder / 'compiled-312.json'), native_geometry_sha256=geo['npz_sha256']))
    assert seen == set(old), 'every original reference must be recompiled'
    (a.out / 'per-world-references.json').write_text(json.dumps(references, indent=2) + '\n')
    (a.out / 'proof.json').write_text(json.dumps(dict(
        profile='warp_native_contact_v1', base_source_sha=BASE_SOURCE_SHA,
        source=str(a.source), script_sha256=script_sha,
        host=EXPECTED_HOST, old_export=str(a.old_export), compiled_N=len(proof),
        proof=proof, physics_steps=0, GPU_contexts=0), indent=2) + '\n')
    print(json.dumps(dict(out=str(a.out), compiled_N=len(proof), arrays_exact=True, physics_steps=0)))


if __name__ == '__main__':
    main()
