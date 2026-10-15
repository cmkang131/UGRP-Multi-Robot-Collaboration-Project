"""Opt-in Linux/L4 numeric import audit. No step, training or physics edits.

The scan threshold 3.4e38 is requested by the simalt2 user; the exact float32
maximum is reported separately. Every offending index is retained, with no
sampling. Conversion instrumentation only adds the upstream field to errors.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
import platform
import socket
import time
import traceback
import warnings


def encoded_number(value):
    import math
    value = float(value)
    return value if math.isfinite(value) else str(value)


UNUSED_EFM_FIELDS = frozenset(('efm_c', 'efm_ca', 'efm_diag', 'efm_fluid'))


def inactive_efm_field(field, integrator, efm_active, nflex, nefmK, nefmT, nefmA):
    # Upstream derivative.eff_build returns immediately unless DISCRETE (enum 4).
    # Limit this adapter to the user's rigid implicitfast (enum 3) scene. Upstream
    # io.make_data initializes precisely these workspace arrays with
    # _create_array(None, ...), i.e. wp.zeros. Never touch contact/state/model data.
    return (field in UNUSED_EFM_FIELDS and integrator == 3 and efm_active == 0
            and nflex == 0 and nefmK == 0 and nefmT == 0 and nefmA == 0)


def scan_arrays(obj, prefix, depth=0):
    import numpy as np
    arrays, offenders = [], []
    for name in sorted(dir(obj)):
        if name.startswith('_'):
            continue
        value = getattr(obj, name)
        path = prefix + '.' + name
        if isinstance(value, np.ndarray) and value.dtype.kind == 'f':
            bad = ~np.isfinite(value) | (np.abs(value) > 3.4e38)
            arrays.append({'field': path, 'shape': list(value.shape),
                           'dtype': str(value.dtype), 'count': int(value.size),
                           'bad_count': int(bad.sum()),
                           'sha256': hashlib.sha256(value.tobytes()).hexdigest()})
            for index in np.argwhere(bad):
                index = tuple(int(i) for i in index)
                v = value[index]
                offenders.append({'field': path, 'index': list(index),
                                  'value': encoded_number(v),
                                  'nonfinite': not bool(np.isfinite(v)),
                                  'exceeds_float32_max': bool(abs(v) > np.finfo(np.float32).max)})
        elif depth < 3 and type(value).__module__.startswith('mujoco') and not callable(value):
            subarrays, suboffenders = scan_arrays(value, path, depth + 1)
            arrays.extend(subarrays)
            offenders.extend(suboffenders)
    return arrays, offenders


def audit(m, d):
    ma, mo = scan_arrays(m, 'model')
    da, do = scan_arrays(d, 'data')
    return {'arrays': ma + da, 'offenders': mo + do,
            'array_count': len(ma) + len(da), 'offender_count': len(mo) + len(do)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xml', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--sha', required=True)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--unused-efm-v1', action='store_true', help='default OFF; upstream make_data zero allocation for inactive EFM workspace only')
    a = p.parse_args()
    if not a.enabled or platform.system() != 'Linux' or socket.gethostname().split('.')[0] != 'ugrp-act-l4-pilot1':
        p.error('explicit Linux/L4-only audit required')
    a.out.mkdir(parents=True, exist_ok=False)
    import numpy as np
    import mujoco
    import warp as wp
    import mujoco_warp as mjw
    from mujoco_warp._src import io
    start = time.perf_counter()
    report = {'sha': a.sha, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'xml': str(a.xml), 'xml_sha256': hashlib.sha256(a.xml.read_bytes()).hexdigest(),
              'mujoco_version': mujoco.__version__, 'warp_version': wp.__version__,
              'io_sha256': hashlib.sha256(Path(io.__file__).read_bytes()).hexdigest(),
              'float32_max': float(np.finfo(np.float32).max), 'threshold': 3.4e38,
              'steps': 0, 'training': False, 'option_overrides': {}, 'status': 'running',
              'unused_efm_v1': a.unused_efm_v1, 'zero_allocated_fields': []}
    def save():
        (a.out / 'result.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    save()
    try:
        warnings.filterwarnings('error', message='.*overflow.*', category=RuntimeWarning)
        m = mujoco.MjModel.from_xml_path(str(a.xml))
        d = mujoco.MjData(m)
        report['fresh'] = audit(m, d)
        mujoco.mj_forward(m, d)
        report['before_put_data'] = audit(m, d)
        report['efm_activity'] = {k: int(getattr(d, k)) for k in ('efm_active','nefmK','nefmT','nefmA')}
        report['arena_probe'] = {}
        for field in sorted(UNUSED_EFM_FIELDS):
            first, second = getattr(d, field), getattr(d, field)
            report['arena_probe'][field] = {'shares_memory_across_getters': bool(np.shares_memory(first, second)),
                                           'owns_data': bool(first.flags.owndata), 'base_is_none': first.base is None}
        report['model_counts'] = {k: int(getattr(m, k)) for k in
                                  ('nq','nv','nu','ngeom','nbody','neq','nplugin','nhistory')}
        report['source_options'] = {f: encoded_number(getattr(m.opt, f)) for f in dir(m.opt)
                                    if not f.startswith('_') and isinstance(getattr(m.opt, f), (int, float))}
        save()
        wp.init()
        wm = mjw.put_model(m)
        report['converted_options'] = {}
        for f in dataclasses.fields(wm.opt):
            v = getattr(wm.opt, f.name)
            if hasattr(v, 'numpy'):
                v = v.numpy()
                if v.size == 1:
                    v = v.item()
            if isinstance(v, (int, float)):
                report['converted_options'][f.name] = encoded_number(v)
        original = io._create_array
        def annotated(data, spec, sizes, batch_size=1):
            caller = inspect.currentframe().f_back
            field = caller.f_locals.get('f')
            name = getattr(field, 'name', None)
            if a.unused_efm_v1 and caller.f_code.co_name == 'put_data' and inactive_efm_field(
                    name, int(m.opt.integrator), int(d.efm_active), int(m.nflex), int(d.nefmK), int(d.nefmT), int(d.nefmA)):
                report['zero_allocated_fields'].append(name)
                return original(None, spec, sizes, batch_size)
            try:
                return original(data, spec, sizes, batch_size)
            except Exception:
                report['conversion_failure'] = {'field': getattr(field, 'name', None),
                                                'caller': caller.f_code.co_name,
                                                'caller_lineno': caller.f_lineno,
                                                'target_dtype': str(spec.dtype)}
                if isinstance(data, np.ndarray) and data.dtype.kind == 'f':
                    bad = ~np.isfinite(data) | (np.abs(data) > 3.4e38)
                    report['conversion_failure']['offenders'] = [
                        {'index': i.tolist(), 'value': encoded_number(data[tuple(i)])}
                        for i in np.argwhere(bad)]
                raise
        io._create_array = annotated
        try:
            mjw.put_data(m, d, nworld=1)
            wp.synchronize()
        finally:
            io._create_array = original
        report['status'] = 'numeric_import_pass_only'
    except Exception as e:
        report.update(status='rejected', error_type=type(e).__name__, error=str(e), traceback=traceback.format_exc())
    finally:
        report['wall_s'] = time.perf_counter() - start
        save()
    print(json.dumps({k: v for k, v in report.items() if k not in ('fresh','before_put_data','source_options','converted_options')}, indent=2))


if __name__ == '__main__':
    main()
