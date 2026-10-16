"""Exact MJWarp unsupported-array grouping, with no step/render/teacher call.

XML model_key is intentionally stricter than supported per-world arrays and
would split every seeded scene. Here all scalar/options and every array that
the pinned MJWarp schema cannot batch are hashed exactly, just as the common
combine_models validator does. That validator runs again before every rollout.
"""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

from act16w_runtime import frozen_source, require_gcp2, sha256

ROOT = Path(__file__).resolve().parents[1]
Q = Path('/home/ugrp/ugrp-sim/src/f0db6b1abb842ea65b71c433738210254f300a7c')


def fingerprint(converted, wp):
    rows = {}
    def visit(obj, prefix=''):
        for field in dataclasses.fields(obj):
            name = prefix+field.name; value = getattr(obj, field.name)
            if dataclasses.is_dataclass(value):
                visit(value, name+'.')
            elif isinstance(value, wp.array):
                if name == 'dof_length': continue  # Existing qualified world-indexed sleep adapter.
                array = value.numpy()
                # Different shapes/dtypes cannot share a model even if values batch.
                rows[name] = dict(shape=array.shape, dtype=str(array.dtype))
                if getattr(field.type, 'shape', ())[:1] != ('*',):
                    rows[name]['sha256'] = hashlib.sha256(array.tobytes()).hexdigest()
            elif isinstance(value, (int,float,bool,str,type(None))):
                rows[name] = value
    visit(converted)
    return hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(), rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.enabled: parser.error('explicit grouping opt-in required')
    host = require_gcp2(training=True); source = frozen_source(ROOT)
    sys.path.insert(0, str(Q/'scripts'))
    import mujoco
    import warp as wp
    import mujoco_warp as mjw
    from simalt_compiled_compat import apply_geometry, apply_reference
    from warp_act_core import runtime_sleep_policy
    wp.init(); args.out.mkdir(parents=True, exist_ok=False)
    inventory = json.loads((args.references/'inventory.json').read_text())
    groups, rows = {}, []
    for row in inventory:
        xml = Path(row['scene_xml']); model = mujoco.MjModel.from_xml_path(str(xml))
        apply_geometry(model, xml, Path(row['geometry'])); apply_reference(model, xml, Path(row['actuator']))
        if model.opt.noslip_iterations != 0 or model.opt.impratio != 5:
            raise ValueError('native exact reference profile required')
        enum = mujoco.mjtSleepPolicy
        model.tree_sleep_policy[:] = runtime_sleep_policy(model.tree_sleep_policy,
            auto=int(enum.mjSLEEP_AUTO), auto_never=int(enum.mjSLEEP_AUTO_NEVER),
            auto_allowed=int(enum.mjSLEEP_AUTO_ALLOWED), never=int(enum.mjSLEEP_NEVER), allowed=int(enum.mjSLEEP_ALLOWED))
        converted = mjw.put_model(model)
        key, fields = fingerprint(converted, wp)
        groups.setdefault(key, []).append(row['index'])
        rows.append(dict(index=row['index'],seed=row['seed'],key=key,xml_sha256=sha256(xml)))
        del converted, model
    result = dict(status='complete', complete=True, source_sha=source, host=host,
        contact_profile='warp_native_contact_v1', physics_steps=0, rendering=0, N=len(rows),
        groups=[dict(key=k,indices=v) for k,v in groups.items()], rows=rows,
        unsupported_field_comparison='byte exact; scalar/options exact; shape/dtype exact for all arrays',
        common_combine_models_validation_still_required=True)
    (args.out/'model-groups.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__':
    main()
