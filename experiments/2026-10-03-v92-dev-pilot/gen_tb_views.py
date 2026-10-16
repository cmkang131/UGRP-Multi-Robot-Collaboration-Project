"""TensorBoard derived views for the DEV_PILOT_C0_ZERO_v1 run (non-confirmatory). Values read from hashed sources."""
import hashlib, json, sys
from pathlib import Path
OUT = Path(sys.argv[1]); P = Path(sys.argv[2])
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fr_p, cal_p = P / 'result/fit_report_dev.json', P / 'result/calibration_dev_pilot.json'
fr, cal = json.loads(fr_p.read_text()), json.loads(cal_p.read_text())
m, o = fr['motion'], fr['motion']['optimizer']
base = {'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True, 'family': 'calibration-assembly',
        'policy': 'v92-dev-pilot', 'case': 'loaded', 'condition': 'DEV_PILOT_C0_ZERO_v1', 'split': 'calibration',
        'seed': 911, 'source_sha': cal['source_sha'][:8], 'scope': 'NON-CONFIRMATORY dev pilot; not MEASURED_SIM; no task success'}
def write(name, view):
    d = OUT / name; d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps({**base, 'run_id': name, **view}, ensure_ascii=False, indent=2) + '\n')
s = {'gate/dev_motion_accepted': float(m['accepted_under_dev_rule']), 'offline/opt_rank': float(o['rank']),
     'offline/opt_rmse': o['rmse'], 'offline/opt_nfev': float(o['nfev']),
     'offline/train_rows_pass': float(m['training_rows_pass'][0]), 'offline/train_rows': float(m['training_rows_pass'][1]),
     'offline/val_rows_pass': float(m['validation_rows_pass'][0]), 'offline/val_rows': float(m['validation_rows_pass'][1]),
     'offline/tau_stop_s': m['candidate']['tau_stop_s'], 'gate/spread_accepted': float(fr['spread']['accepted']),
     'gate/pair_accepted': float(fr['pair']['accepted']), 'offline/pair_ratio': fr['pair']['candidate']['slope_to_yaw_ratio'],
     'offline/pair_rows': float(fr['pair']['rows'])}
for i, ax in enumerate(('forward', 'left', 'turn')):
    s[f'offline/u1_{ax}'] = m['candidate']['deadband']['u1'][i]; s[f'offline/gain_{ax}'] = m['candidate']['gain'][i][i]
write('dev-fit', {'outcome': 'DEV_MOTION_ACCEPTED' if m['accepted_under_dev_rule'] else 'DEV_MOTION_REJECTED',
    'offline_source': {'path': str(fr_p), 'sha256': sha(fr_p)}, 'offline_scalars': s,
    'offline_scalar_scope': 'Loaded refit with c0 fixed 0 (DEV_PILOT_C0_ZERO_v1) on already-inspected v92 data; unchanged B-double-prime PRBS gates; exploratory.',
    'model_calls': 0.0, 'hparam_metrics': ['gate/dev_motion_accepted', 'offline/val_rows_pass'],
    'texts': {'notes/dev_rule': 'c0=0 fixed all axes; deadband support without stop level; everything else unchanged. Not confirmatory.'}})
filled = sum(1 for v in cal['field_provenance'].values())
write('dev-calibration', {'outcome': cal['status'], 'offline_source': {'path': str(cal_p), 'sha256': sha(cal_p)},
    'offline_scalars': {'offline/fields_filled': float(filled), 'offline/fields_missing': float(len(cal['missing'])),
                        'offline/fields_from_dev_refit': float(sum(v.startswith('dev_refit') for v in cal['field_provenance'].values())),
                        'offline/fields_copied_measured': float(sum(v.startswith('copied') for v in cal['field_provenance'].values()))},
    'offline_scalar_scope': 'Field counts of calibration_dev_pilot.json (DEV_PILOT, non-confirmatory): filled = dev refit + copied measured fields; missing = unloaded combined profile.',
    'success': cal['status'] == 'MEASURED_SIM', 'success_definition': 'status == MEASURED_SIM (always false for DEV_PILOT). Not a robot task success.',
    'model_calls': 0.0, 'hparam_metrics': ['evaluation/reported_success', 'offline/fields_missing'],
    'texts': {'notes/missing': cal['missing']}})
print('ok', filled, len(cal['missing']))
