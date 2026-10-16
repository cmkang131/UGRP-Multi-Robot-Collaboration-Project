"""DIAGNOSTIC ONLY, not a calibration result. Reproduces the assembler's loaded motion path at
257953ec with IDENTICAL settings to record why fit_shared was rejected (the assembler kept only the
exception string). verify_fit is wrapped only to dump the optimizer state, then the original is called.
No bounds/max_nfev/criterion changes. Output: diagnostic.json next to this script."""
import json, sys, hashlib
from pathlib import Path
import numpy as np
from scripts import assemble_final_pair_calibration_v92 as A
from scripts import final_pair_calibration_v92_motion as V
from scripts import fit_consumer_criterion_b as r4
from scripts import validate_consumer_criterion_b as b
from scripts.final_pair_calibration_motion import split_data
from scripts.final_pair_calibration_v92_io import Inputs, load_collection, loaded_mask, selected_segments

root, out = Path(sys.argv[1]), Path(sys.argv[2])
blob = (A.CRITERION).read_bytes(); assert hashlib.sha256(blob).hexdigest() == A.CRITERION_SHA256
prime = json.loads(blob)
inputs = Inputs(); inputs.protect(root)
col = load_collection(root, 'loaded', inputs)
valid, selection = loaded_mask(col, inputs, prime['loaded_selection'])
col['valid_load'] = valid
for robot in col['robots'].values():
    robot['segments'] = selected_segments(col['segments'], valid)
robots = list(col['robots'].values())
bounds = prime['loaded_motion_bounds']
names = ['gain_forward', 'gain_left', 'gain_turn', 'tau_axis_forward', 'tau_axis_left', 'tau_axis_turn', 'tau_stop',
         'c0_forward', 'c0_left', 'c0_turn', 'u1_forward', 'u1_left', 'u1_turn']
lower = np.r_[np.log([.05]*3+[.01]*3+[.005]), bounds['c0_lower'], bounds['u1_lower']]
upper = np.r_[np.log([4.]*6+[.5]), bounds['c0_upper'], bounds['u1_upper']]
dump = {}
orig = V.verify_fit
def wrapped(opt, count):
    x = np.asarray(opt.x)
    dump.update(status=int(opt.status), message=str(opt.message), success=bool(opt.success), nfev=int(opt.nfev),
        njev=None if opt.njev is None else int(opt.njev), cost=float(opt.cost),
        rmse=float(np.sqrt(np.mean(opt.fun**2))), rank=int(np.linalg.matrix_rank(opt.jac)), count=count,
        optimality=float(opt.optimality),
        params={n: {'raw': float(x[i]), 'value': float(np.exp(x[i]) if i < 7 else x[i]),
                    'lower': float(np.exp(lower[i]) if i < 7 else lower[i]), 'upper': float(np.exp(upper[i]) if i < 7 else upper[i]),
                    'dist_lower_raw': float(x[i]-lower[i]), 'dist_upper_raw': float(upper[i]-x[i]),
                    'active_mask': int(opt.active_mask[i])} for i, n in enumerate(names)})
    return orig(opt, count)
V.verify_fit = wrapped
candidates = []
for data in robots:
    cand = {}
    for axis, name in enumerate(b.AXES):
        try:
            cand[name] = r4.fit_mean(split_data(data, 'steps'), axis, prime['parent_text'])
        except ValueError as exc:
            cand[name] = {'accepted': False, 'reason': str(exc)}
    candidates.append(cand)
try:
    V.fit_profile(robots, prime); error = None
except ValueError as exc:
    error = str(exc)
report = {'label': 'DIAGNOSTIC ONLY - not a calibration result; identical settings to assembler run',
          'selection': selection, 'error': error, 'optimizer': dump, 'axis_candidates_r4_fit_mean': candidates,
          'reproduces_recorded_run': error == 'fit convergence/rank/boundary failure: rank 13/13'
              and selection == {'not_lifted': 475, 'lifted': 13926}}
out.write_text(json.dumps(report, indent=2, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o)) + '\n')
print(json.dumps({'error': error, 'status': dump.get('status'), 'nfev': dump.get('nfev'),
                  'active': [n for n, p in dump.get('params', {}).items() if p['active_mask']],
                  'reproduces': report['reproduces_recorded_run']}))
