"""Read-only postprocessing of completed local diagnostics, including failures.

No model/physics imports. Raw originals are never changed. New output only.
"""
import hashlib
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

RAW = Path('/Users/changmin/projects/ugrp/outputs')
ROOT = Path(__file__).resolve().parents[2]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def write(p, v):
    p.write_text(json.dumps(v, indent=2, ensure_ascii=False, allow_nan=False)+'\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--set', action='append', help='label=raw folder below primary outputs; completed sources only')
    parser.add_argument('--qualification', default='NOT_READY: lateral/yaw coupling remains; public v2 removes near-stall but not residual drift; motor/floor uncalibrated. No pair or v106 validation.')
    parser.add_argument('--stopped-reason', default='same unwanted lateral/yaw coupling repeated unloaded and cyan-loaded; no additional physics')
    args = parser.parse_args()
    out = args.out; snapshot = args.snapshot
    out.mkdir(parents=True, exist_ok=False)
    sets = {
        'old-shape': 'drive-friction-5f04f473-empty2',
        'new-empty': 'drive-friction-f323a7b7-empty',
        'baseline': 'drive-friction-f323a7b7-legacy',
        'new-cyan': 'drive-friction-f323a7b7-cyan',
        'host-error': 'drive-friction-995ff901-forward',
    }
    if args.set:
        sets = dict(item.split('=', 1) for item in args.set)
    sources = []; rows = []; files = []
    for label, directory in sets.items():
        raw = RAW/directory
        for result in sorted(raw.glob('*/result.json')):
            r = json.loads(result.read_text()); name = label+'-'+result.parent.name
            dest = out/name; dest.mkdir()
            source = {'path': str(result), 'sha256': sha(result)}
            scalars = {'offline/record_completed': int(r['status'] == 'MEASURED_DEV')}
            for key in ('steady_contact_slip_mps','wall_per_sim','stop_drift_m','cargo_min_z_m',
                        'wheel_input','peak_command_com_xy_m'):
                if key in r: scalars['offline/'+key] = r[key]
            if 'yaw_change_rad' in r:
                scalars['offline/yaw_change_deg'] = math.degrees(r['yaw_change_rad'])
            if r.get('steady_velocity'):
                for k, i in (('forward_mps',0),('lateral_mps',1),('yaw_radps',5)):
                    scalars['offline/'+k] = r['steady_velocity'][i]
            for field in ('displacement_m', 'com_displacement_m'):
                for k, value in enumerate(r.get(field, [])):
                    scalars['offline/'+field+'_'+str(k)] = value
            view = {'schema':'ugrp.offline_audit_view.v1','derived_view_only':True,
                'offline_source':source, 'offline_scalar_scope':'Short staged drive physics diagnostic; same normalized commands but different actuator scale. Not hardware performance or mission success.',
                'offline_scalars':scalars,'policy':r['profile'],'condition':label,'case':result.parent.name,
                'source_sha':json.loads((raw/'manifest.json').read_text())['source_sha'],
                'outcome':r['status'], 'model_calls':0,
                'texts':{'evaluation/qualification': args.qualification},
                'hparam_metrics':[k for k in ('offline/steady_contact_slip_mps','offline/wall_per_sim','offline/yaw_radps') if k in scalars]}
            for field in ('sim_s','wall_s','commands'):
                if field in r: view[field] = r[field]
            write(dest/'result.json',view)
            sources += ['--source',str(dest)]
            rows.append({'run':name, 'source':source, **r})
        for f in raw.rglob('*'):
            if f.is_file(): files.append({'path':str(f),'bytes':f.stat().st_size,'sha256':sha(f)})
    write(out/'summary.json', {'verdict':'NOT_READY','rows':rows,
        'remaining':['lateral/yaw coupling','roller contact envelope and source-to-MasterPi adaptation','installed motor/floor measurements','paired beam and v106 replay'],
        'stopped_reason':args.stopped_reason,
        'model_calls':0, 'raw_remote_backup':False})
    write(out/'artifacts.sha256.json',files)
    subprocess.run([sys.executable,'-m','scripts.export_offline_audit',*sources,'--output',str(snapshot)], cwd=ROOT, check=True)
    print(json.dumps({'runs':len(rows),'raw_files':len(files),'summary':str(out/'summary.json'),'snapshot':str(snapshot)}))

if __name__ == '__main__':
    main()
