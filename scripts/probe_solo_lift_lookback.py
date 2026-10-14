"""Static command geometry + saved-file eligibility audit; never runs a world."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from sim.grasp_act_solo_lookback import MODE, plan_lookback, regions

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(raw_root):
    manifest = ROOT/'tests/fixtures/solo_rgb_lift_v3/manifest.json'
    data = json.loads(manifest.read_text())
    rows, reviewed = [], []
    for run in data['runs']:
        low, high = [{int(k): v for k, v in run['commands'][i]['pwm'].items()} for i in (0, -1)]
        p = plan_lookback(run['kind'], low, high)
        raw = raw_root/run['run']/'raw'
        files = json.loads((raw/'manifest.json').read_text())
        verified = []
        for sample in run['samples'].values():
            path = raw/'lift-rgb'/Path(sample['path']).name
            if sha(path) != sample['sha256']:
                raise ValueError(f'saved-frame hash mismatch: {path}')
            verified.append({'path': str(path), 'sha256': sha(path)})
        trace_path = raw/'teacher-commands.jsonl.zst'
        if sha(trace_path) != files['teacher-commands.jsonl.zst']['sha256']:
            raise ValueError('saved command trace hash mismatch')
        trace = [json.loads(s) for s in subprocess.check_output(['zstd', '-dc', str(trace_path)], text=True).splitlines()]
        for path in sorted((raw/'review-own').glob('*.jpg')):
            tick = int(path.stem)
            if sha(path) != files[str(path.relative_to(raw))]['sha256']:
                raise ValueError(f'review-frame hash mismatch: {path}')
            reviewed.append({'run': run['run'], 't': trace[tick]['t'], 'phase': trace[tick]['phase'],
                             'path': str(path), 'sha256': sha(path)})
        phases = sorted({r['phase'] for r in trace})
        rows.append({'run': run['run'], 'kind': run['kind'], 'grasp_pwm': low,
                     'lift_pwm': high, 'lookback_plan': p,
                     'old_unmoved_lift_geometry': regions(run['kind'], low, high)[2],
                     'saved_lookback_frames_eligible': 'lookback' in phases,
                     'saved_phases': phases, 'verified_samples': verified,
                     'raw': str(raw), 'trace_sha256': sha(trace_path)})
    sources = ['sim/grasp_act_solo_lookback.py', 'sim/grasp_act_solo_teacher.py',
               'scripts/run_solo_grasp_act_teacher.py', 'scripts/probe_solo_lift_lookback.py',
               'harness/data/servo_camera_v3_chain.json', 'sim/masterpi_camera_profile.py',
               'harness/grasp_act_visible_world.py']
    return {'schema': 'solo_lift_lookback_static_v1', 'mode': MODE,
            'scope': 'nominal command geometry and saved-frame eligibility; not physical success',
            'parent_sha': '1b72b3ee7c1d56e7630d94fcb335d6d9a2b982e9',
            'saved_source_sha': data['source_sha'], 'manifest_sha256': sha(manifest),
            'source_sha256': {p: sha(ROOT/p) for p in sources}, 'runs': rows,
            'reviewed_own_frames': reviewed,
            'totals': {'planned_geometry_n': sum(r['lookback_plan']['geometry']['qualified'] for r in rows),
                       'N': len(rows), 'eligible_saved_positive_pairs': sum(r['saved_lookback_frames_eligible'] for r in rows),
                       'verified_exact_frames': sum(len(r['verified_samples']) for r in rows),
                       'verified_review_frames': len(reviewed)},
            'new_remote_runs': 0, 'physics_runs': 0, 'render_runs': 0,
            'limitations': ['commanded motion is not measured displacement; wheel slip and loaded sag unmeasured',
                            'empty site cannot distinguish held cargo from cargo knocked away',
                            'held cargo occlusion is a catalogue bounding box enlarged by 1 mm, not measured grip pose',
                            'uniform floor-coloured occluders and wrong-site registration remain diagnostic risks']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out = audit(a.raw_root)
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(out['totals']))


if __name__ == '__main__':
    main()
