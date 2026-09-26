"""Write prereg_v3.json: the frozen round-3 student and the independent round-3 test set, before that test is touched.

Run once after the dev selection (``dev_variants_v3.json``) and the independence
audit of the round-3 test renders (``results/overlap_v3_test.json``), and BEFORE
any round-3 test segmentation, localization or scoring. The file is committed
and pushed; ``vision_loc_io.require_frozen`` refuses round-3 test episodes
unless every frozen hash still matches, and ``vision_loc_score`` scores the
registered set once, into ``results/metrics_test_v3.json``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN_FILES = ('vision_loc.py', 'vision_pf.py', 'vision_loc_cli.py', 'vision_loc_io.py', 'vision_loc_score.py',
                'seg_model.py', 'episodes.json', 'episodes_v3.json', 'calibration_train.json',
                'maps/zone_wide_door_walls_v3_notags.json', '../2026-09-26-markerless-probe/markerless_probe.py')


def sha_file(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*args) -> str:
    return subprocess.run(['git', *args], cwd=HERE, capture_output=True, text=True).stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--config', required=True, help='selected round-3 dev config (in the experiment folder)')
    ap.add_argument('--dev-selection', required=True, help='dev_variants_v3.json')
    ap.add_argument('--overlap', required=True, help='results/overlap_v3_test.json (independence audit of test)')
    args = ap.parse_args(argv)
    out = HERE/'prereg_v3.json'
    if out.exists():
        raise SystemExit(f'refusing to overwrite {out}')
    dirty = git('status', '--porcelain', '--', *FROZEN_FILES, str(Path(args.config).resolve().relative_to(HERE)))
    if dirty:
        raise SystemExit(f'commit the frozen files first:\n{dirty}')
    tab = json.loads((HERE/'episodes_v3.json').read_text())
    designed = [e['episode_id'] for e in tab['episodes'] if e['split'] == 'test']
    ov = json.loads(Path(args.overlap).read_text())
    audited = {e['episode']: e for e in ov['episodes']}
    missing = [e for e in designed if e not in audited]
    if missing:
        raise SystemExit(f'independence audit missing for {missing}')
    test_eps = [e for e in designed if audited[e]['independent']]
    excluded = [e for e in designed if not audited[e]['independent']]
    cfg = Path(args.config).resolve()
    prereg = {
        'schema': 'ugrp.vision_loc.prereg.v3',
        'registered': ('2026-09-26, Kiro, round 3: after the dev selection and the independence audit of the round-3 '
                       'test renders; before any round-3 test segmentation, localization or scoring'),
        'source_sha_at_registration': git('rev-parse', 'HEAD'),
        'student': {
            'model': {'checkpoint': str(args.checkpoint), 'sha256': sha_file(args.checkpoint),
                      'bytes': Path(args.checkpoint).stat().st_size, 'note': 'seg-v2, unchanged from round 2'},
            'calibration': {'file': 'calibration_train.json', 'sha256': sha_file(HERE/'calibration_train.json')},
            'config': {'file': str(cfg.relative_to(HERE)), 'sha256': sha_file(cfg), 'value': json.loads(cfg.read_text())},
            'm1_motion_model': 'M1 calibration (markerless_probe.load_m1_calibration, hash-checked), unchanged',
            'filters': {'vision': 'student', 'boundary': 'PR #210 detector baseline', 'deadreck': 'baseline',
                        'oracle': 'EVAL-ONLY diagnostic (teacher labels), never a student result'},
            'frozen_files_sha256': {f: sha_file(HERE/f) for f in FROZEN_FILES}},
        'dev_selection': {'file': str(Path(args.dev_selection).resolve().relative_to(HERE)),
                          'sha256': sha_file(args.dev_selection), 'plan': 'dev_plan_v3.json',
                          'plan_sha256': sha_file(HERE/'dev_plan_v3.json')},
        'independence': {'file': str(Path(args.overlap).resolve().relative_to(HERE)), 'sha256': sha_file(args.overlap),
                         'references': ov['references'], 'excluded': excluded},
        'test_episodes': test_eps,
        'scoring': {'once': True, 'output': 'results/metrics_test_v3.json',
                    'metrics': 'vision_loc_cli.py score over exactly the registered test episodes, all at once',
                    'groups': {'door_zone': '|x - 2.2| < 0.6 and -0.45 < y < 0.55 (GT), as PR #210',
                               'door_loaded': 'door_zone and own-command load state loaded (carrying through door_1)',
                               'lateral': '|y_est - y_gt| (door_1 is crossed along x)'},
                    'recovery': 'lost (> 0.30 m), recoveries (back below 0.10 m), injections, injections while < 0.10 m',
                    'false_detections': 'learned column edges outside the teacher-label interval by > 5 px'},
        'gate': {'name': 'door_1 carrying clearance (unchanged from round 2, prereg.json)',
                 'lateral_p99_max_m': .06, 'position_p90_max_m': .05, 'yaw_p90_max_deg': 3.,
                 'min_episodes': 3, 'min_door_loaded_frames_per_episode': 20,
                 'rule': ('PASS iff, over the pooled test door_loaded frames of the vision filter: lateral p99 <= '
                          '0.06 m AND position p90 <= 0.05 m AND yaw p90 <= 3.0 deg, with door_loaded frames (>= 20) '
                          'in >= 3 test episodes (else INSUFFICIENT_DATA)'),
                 'not_rederived': 'the gate is not re-derived in round 3; the round-2 FAIL stands as recorded'},
        'report': ('per filter: door_zone / door_loaded p50 / p90 / p99, lateral p99, yaw p90; all-frame p50 / p90; '
                   'recovery events; the oracle next to the student (diagnostic); offline replay of teacher-driven '
                   'renders, not closed loop'),
    }
    out.write_text(json.dumps(prereg, indent=1) + '\n')
    print(json.dumps({'test_episodes': test_eps, 'excluded': excluded, 'config': prereg['student']['config']},
                     indent=1))


if __name__ == '__main__':
    main()
