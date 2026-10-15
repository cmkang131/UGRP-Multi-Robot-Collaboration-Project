"""Local seed inventory + static setup LOS only; no dynamics/render/remote."""
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
ADMIN = Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin')


def main():
    pattern = re.compile(r'"seed"\s*:\s*(791[0-3][0-9])\b')
    files = set((ROOT/'experiments').rglob('*.json'))
    files.update(Path('/Users/changmin/projects/ugrp/experiments').rglob('*.json'))
    files.update((ADMIN/'vm3-queue').glob('*.json'))
    files.update((ADMIN/'gcp-reports').rglob('*inventory*.json'))
    checked = []; hits = []
    for p in sorted(files):
        if HERE in p.parents: continue
        try: data = p.read_bytes(); text = data.decode()
        except (OSError, UnicodeError): continue
        checked.append({'path': str(p), 'sha256': hashlib.sha256(data).hexdigest()})
        for match in pattern.finditer(text): hits.append({'path': str(p), 'seed': int(match.group(1))})
    run_hits = [p.name for p in Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs').iterdir()
                if re.search(r'(?<!\d)791[0-3][0-9](?!\d)', p.name)]
    if hits or run_hits: raise ValueError((hits, run_hits))
    reservation = {'reserved_range': [79100,79139], 'split': 'crate17_diagnostic',
        'local_json_files_checked': len(checked), 'explicit_seed_conflicts': hits, 'local_run_conflicts': run_hits,
        'inventory_sha256': hashlib.sha256(json.dumps(checked,sort_keys=True).encode()).hexdigest(),
        'scope': 'worktree and primary experiment JSON, local queue and saved inventory JSON, local run names',
        'remote_live_inventory_verified': False,
        'required_before_admission': 'operations rechecks live inventory under shared admission lock'}
    (HERE/'seed-reservation.json').write_text(json.dumps(reservation,indent=2)+'\n')
    import mujoco
    def forbidden(*args, **kwargs): raise AssertionError('crate17 forbids physics/forward/render')
    for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_inverse','Renderer','mjr_render'):
        setattr(mujoco,name,forbidden)
    from scripts.make_crate_teacher_plan import prepare, write_plan
    plan = prepare(count=10,seed=79100,split='crate17_diagnostic',scenario_set='v6',
        assignment='fixed_rgb_lugs_v1',crate_profile='crate14_v1',near_wall_policy='exclude_report_v1')
    write_plan(HERE/'diagnostic-plan.json',plan)
    print(json.dumps({'seed_check':reservation,'seeds':[e['seed'] for e in plan['episodes']],
        'proposals':plan['start_distribution']['proposals'],'rejected':plan['start_distribution']['rejected'],
        'near_wall_drawn':plan['near_wall_filter']['drawn_episode_count'],
        'near_wall_excluded':plan['near_wall_filter']['excluded_count']}),flush=True)


if __name__ == '__main__': main()
