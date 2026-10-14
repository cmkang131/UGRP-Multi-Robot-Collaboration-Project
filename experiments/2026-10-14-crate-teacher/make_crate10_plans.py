"""Static plan construction / LOS only; forbidden simulation/render entrypoints."""
import hashlib
import json
from pathlib import Path

import mujoco
from scripts.make_crate_teacher_plan import prepare
from scripts.audit_crate_start_los import CrateStartLOS

EXP = Path(__file__).resolve().parent
RAW = Path('/Users/changmin/projects/ugrp/outputs/gcp1-runs')


def forbidden(*args, **kwargs):
    raise AssertionError('crate10 forbids physics/forward/rendering on Mac')


def main():
    for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_inverse', 'Renderer', 'mjr_render'):
        setattr(mujoco, name, forbidden)
    original = CrateStartLOS.check
    def check(self, episode, **kwargs):
        episode['cargo_scene_version'] = 'crate_mass_025_v1'
        return original(self, episode, **kwargs)
    CrateStartLOS.check = check
    for count, seed, split, name in [(10, 77980, 'crate_diagnostic', 'diag_plan_crate10_77980.json'),
                                     (40, 77400, 'crate_gate_v5', 'gate_plan_crate10_77400.json')]:
        p = prepare(count=count, seed=seed, split=split, scenario_set='v5',
                    start_assigned_los='start_assigned_los_v1')
        p['criteria']['denominators'] = f'full N={count}, including failures and HOST_ERROR; handoff is failure'
        (EXP/name).write_text(json.dumps(p, separators=(',', ':'))+'\n')
        print(name, len(p['episodes']), p['start_los_audit']['accepted'], flush=True)
    episodes = []; sources = []
    for seed, sha in [(77969, '5644e3dd'), (77978, 'bf31840f'), (77979, 'bf31840f')]:
        path = RAW/f'crate-diag-{seed}-{sha}'/'raw/plan.json'
        episodes.append(json.loads(path.read_text()))
        sources.append({'seed': seed, 'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (EXP/'repro_plan_crate10.json').write_text(json.dumps({'episodes': episodes, 'sources': sources,
        'scope': 'exact archived starts, including the earlier Cartesian-source 77969; new runtime uses antipodal profile'},
        separators=(',', ':'))+'\n')


if __name__ == '__main__':
    main()
