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
              'steps': 0, 'training': False, 'option_overrides': {}, 'status': 'running'}
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
        report['model_counts'] = {k: int(getattr(m, k)) for k in
                                  ('nq','nv','nu','ngeom','nbody','neq','nplugin','nhistory')}
        report['source_options'] = {f: encoded_number(getattr(m.opt, f)) for f in dir(m.opt)
                                    if not f.startswith('_') and isinstance(getattr(m.opt, f), (int, float))}
        save()
        wp.init()
        wm = mjw.put_model(m)
        report['converted_options'] = {f.name: encoded_number(getattr(wm.opt, f.name))
                                       for f in dataclasses.fields(wm.opt)
                                       if isinstance(getattr(wm.opt, f.name), (int, float))}
        original = io._create_array
        def annotated(data, spec, sizes, batch_size=1):
            try:
                return original(data, spec, sizes, batch_size)
            except Exception:
                caller = inspect.currentframe().f_back
                field = caller.f_locals.get('f')
                report['conversion_failure'] = {'field': getattr(field, 'name', None),
                                                'caller': caller.f_code.co_name,
                                                'caller_lineno': caller.f_lineno,
                                                'target_dtype': str(spec.dtype)}
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
