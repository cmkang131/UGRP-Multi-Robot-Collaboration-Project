"""Build TensorBoard derived views (ugrp.offline_audit_view.v1) for the v92 D5 assembly.

Every number is read from the hashed source file named in offline_source. Gates that were
never evaluated (loaded B'' motion/spread/pair) are NOT emitted (no zero-fill); see texts.
"""
import hashlib, json, sys
from collections import Counter
from pathlib import Path

OUT = Path(sys.argv[1])
COL = Path('/Users/changmin/projects/ugrp/outputs/final-pair-v92-loaded-257953ec-20261003')
MEAS = Path('/Users/changmin/projects/ugrp/outputs/final-pair-v92-measured-20261003T091812Z')
VID = Path('/Users/changmin/projects/ugrp/outputs/v92-loaded-videos-20261003')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def src(p):
    return {'path': str(p), 'sha256': sha(p)}


def base(run_id, outcome, case, condition, source_sha):
    return {'schema': 'ugrp.offline_audit_view.v1', 'derived_view_only': True, 'run_id': run_id,
            'family': 'calibration-assembly', 'policy': 'v92-d5', 'case': case, 'condition': condition,
            'split': 'calibration', 'seed': 911, 'outcome': outcome, 'source_sha': source_sha}


def write(name, view):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=False)
    (d / 'result.json').write_text(json.dumps(view, ensure_ascii=False, indent=2) + '\n')


videos = {p.name: sha(p) for p in sorted(VID.glob('*.mp4'))}

# 1) collection summary
result = json.loads((COL / 'result.json').read_text())
case = result['cases'][0]
kinds = {rid: Counter(json.loads(l)['kind'] for l in open(COL / 'zone_wide_two_doors_final_v3/robots' / rid / 'commands.jsonl'))
         for rid in ('r1', 'r2')}
frames = {rid: sum(1 for _ in open(COL / 'zone_wide_two_doors_final_v3/robots' / rid / 'frames.jsonl')) for rid in ('r1', 'r2')}
issued = sum(sum(v for k, v in c.items() if k != 'initial_servo_command') for c in kinds.values())
v = base('v92-collection', case['status'], 'zone_wide_two_doors_final_v3', 'loaded-HIGH-720s', '257953ec')
v.update({
    'offline_source': src(COL / 'result.json'),
    'offline_scalar_scope': 'v92 HIGH loaded calibration collection (teacher-only, CALIBRATION_TRAINING): completion flags from result.json; command/frame counts from robots/*/commands.jsonl and frames.jsonl of the same folder.',
    'offline_scalars': {'offline/protocol_complete': float(case['protocol_complete'] is True),
                        'offline/frames_r1': float(frames['r1']), 'offline/frames_r2': float(frames['r2']),
                        'offline/unattempted': float(len(result['unattempted']))},
    'sim_s': round(case['check_sim_s'], 6), 'commands': float(issued), 'model_calls': 0.0,
    'hparam_metrics': ['result/sim_s', 'result/commands', 'result/model_calls', 'offline/protocol_complete'],
    'scope': 'collection record; not a calibration acceptance, not a task success',
    'texts': {'notes/collection': {'commands_by_kind': {k: dict(c) for k, c in kinds.items()},
                                   'commands_metric': 'scheduled issued commands of both robots, excluding the 2 initial_servo_command state records',
                                   'host_loadavg_start_end': [case['loadavg_start'], case['loadavg_end']],
                                   'source': str(COL)},
              'media/videos': {'dir': str(VID), 'sha256': videos,
                               'own_rgb': 'robots/r1/rgb | robots/r2/rgb, 5 Hz frames at 20 fps = 4x SIM',
                               'top_replay': 'REPLAY of recorded eval_only qpos (not physics rerun, not robot input)',
                               'registration': 'offline-audit exporter has no video registration; open the files locally'}},
})
write('v92-collection', v)

# 2) assembly status (calibration.json)
cal_path = MEAS / 'assembly/calibration.json'
cal = json.loads(cal_path.read_text())
miss = [m['field'] for m in cal['missing']]
groups = {'unloaded_by_design': sum(f.startswith('params.motion.') for f in miss),
          'loaded_motion': sum(f.startswith('params.motion_loaded.') for f in miss),
          'pair_model': sum(f.startswith('pair_model.') for f in miss)}
assert sum(groups.values()) == len(miss), miss
started = (MEAS / 'started_utc.txt').read_text().strip(); finished = (MEAS / 'finished_utc.txt').read_text().strip()
from datetime import datetime
wall = (datetime.fromisoformat(finished.replace('Z', '+00:00')) - datetime.fromisoformat(started.replace('Z', '+00:00'))).total_seconds()
v = base('v92-assembly', cal['status'], 'three_collections', 'frozen-Bpp-257953ec', '257953ec')
v.update({
    'offline_source': src(cal_path),
    'offline_scalar_scope': 'Single assembler run at 257953ec (pinned hashes verified): loader status and missing-field counts from calibration.json.',
    'offline_scalars': {'offline/fields_missing': float(len(miss)),
                        'offline/missing_unloaded_by_design': float(groups['unloaded_by_design']),
                        'offline/missing_loaded_motion': float(groups['loaded_motion']),
                        'offline/missing_pair_model': float(groups['pair_model']),
                        'gate/measured_sim': float(cal['status'] == 'MEASURED_SIM')},
    'wall_s': wall, 'model_calls': 0.0,
    'success': cal['status'] == 'MEASURED_SIM',
    'success_definition': 'calibration.json status == MEASURED_SIM (all required loader fields accepted + loader acceptance). Not a robot task success.',
    'hparam_metrics': ['evaluation/reported_success', 'offline/fields_missing', 'result/wall_s', 'result/model_calls'],
    'scope': 'offline calibration assembly; no student/P03/carry or physical task acceptance',
    'texts': {'notes/missing': cal['missing'],
              'notes/run': {'rc': (MEAS / 'rc.txt').read_text().strip(), 'started_utc': started, 'finished_utc': finished,
                            'command': (MEAS / 'command.sh').read_text()}},
})
write('v92-assembly', v)

# 3) evaluated gates (fit_report.json); unevaluated ones are absent on purpose
fr_path = MEAS / 'assembly/fit_report.json'
fr = json.loads(fr_path.read_text())
fine = fr['fine']['motion']
cam = fr['camera']
sel = fr['loaded']['load_selection']
v = base('v92-fit-gates', 'PARTIAL', 'three_collections', 'frozen-Bpp-257953ec', '257953ec')
v.update({
    'offline_source': src(fr_path),
    'offline_scalar_scope': "Gates actually evaluated in fit_report.json: fine B-prime acceptance, camera pose/pan acceptance (unloaded v88, loaded v92 HIGH), loaded selection sample counts. Loaded B'' motion/spread/pair gates were never evaluated (shared fit rejected) and are deliberately not emitted.",
    'offline_scalars': {'gate/fine_bprime_pass': float(fine['accepted'] is True),
                        'gate/unloaded_camera_poses_accepted': float(sum(1 for k, x in cam['unloaded'].items() if k != 'pan' and x['accepted'])),
                        'gate/loaded_camera_poses_accepted': float(sum(1 for k, x in cam['loaded'].items() if k != 'pan' and x['accepted'])),
                        'gate/unloaded_pan_pass': float(cam['unloaded']['pan']['accepted']),
                        'gate/loaded_pan_pass': float(cam['loaded']['pan']['accepted']),
                        'offline/loaded_lifted_samples': float(sel['lifted']),
                        'offline/loaded_not_lifted_samples': float(sel['not_lifted']),
                        'offline/fine_tau_stop_s': fine['candidate']['tau_stop_s'],
                        'offline/loaded_pan_rad_per_pwm': cam['loaded']['pan']['rad_per_pwm']},
    'hparam_metrics': ['gate/fine_bprime_pass', 'gate/loaded_camera_poses_accepted', 'offline/loaded_lifted_samples'],
    'scope': 'evaluated gates only; not evaluated: loaded B-double-prime training/validation numerical_pass, spread, deadband support, pair model',
    'texts': {'notes/not_evaluated': 'loaded shared fit raised at verify_fit (c0 at lower bounds) -> spread, deadband support, pair_rows/fit_pair never ran. No 0 is recorded for them.'},
})
write('v92-fit-gates', v)

# 4) loaded optimizer diagnostic (identical settings; not a calibration result)
dg_path = MEAS / 'diagnostic-loaded-optimizer/diagnostic.json'
dg = json.loads(dg_path.read_text())
o = dg['optimizer']
assert dg['reproduces_recorded_run'] is True
scal = {'offline/opt_status': float(o['status']), 'offline/opt_nfev': float(o['nfev']), 'offline/opt_rank': float(o['rank']),
        'offline/params_at_bound': float(sum(1 for p in o['params'].values() if p['active_mask']))}
for n in ('c0_forward', 'c0_left', 'c0_turn', 'u1_forward', 'u1_left', 'u1_turn', 'tau_stop'):
    scal['offline/' + n] = o['params'][n]['value']
v = base('v92-loaded-diag', 'DIAGNOSTIC_BOUNDARY', 'loaded', 'frozen-Bpp-257953ec', '257953ec')
v.update({
    'offline_source': src(dg_path),
    'offline_scalar_scope': 'DIAGNOSTIC ONLY (not a calibration result): same-settings replay of the loaded shared fit at 257953ec that reproduced the recorded error and selection; dumps optimizer state that the assembler discarded.',
    'offline_scalars': scal,
    'hparam_metrics': ['offline/params_at_bound', 'offline/opt_status'],
    'scope': 'diagnostic; explains rejection only',
    'texts': {'notes/diagnosis': {'message': o['message'], 'success': o['success'],
                                  'at_bound': {n: p for n, p in o['params'].items() if p['active_mask']}}},
})
write('v92-loaded-diag', v)
print(json.dumps({'views': sorted(p.name for p in OUT.iterdir()), 'groups': groups, 'wall_s': wall}))
