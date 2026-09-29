"""List the usable recorded stage-probe cases (frames + robots.json + eval-only trace). Read-only."""
import glob
import json
import os
import sys

OUT = '/Users/changmin/projects/ugrp/outputs'


def inventory():
    rows = []
    for cdir in sorted(glob.glob(f'{OUT}/pair-stage-probes-*/cases/*/')):
        cdir = cdir.rstrip('/')
        need = [f'{cdir}/{n}' for n in ('case.json', 'robots.json', 'eval_only/trace.jsonl', 'result.json')]
        if not all(os.path.isfile(p) for p in need) or not os.path.isdir(f'{cdir}/frames'):
            continue
        root = cdir.split('/cases/')[0]
        try:
            case = json.load(open(f'{cdir}/case.json'))
            man = json.load(open(f'{root}/manifest.json'))
        except (OSError, ValueError):
            continue
        rows.append({'dir': cdir, 'run': os.path.basename(root), 'stage': case.get('stage'), 'leg': case.get('leg'),
                     'policy': case.get('pair_policy'), 'cell': case.get('cell'), 'seed': case.get('seed'),
                     'setup_variant': case.get('setup_variant'), 'source': case.get('source'),
                     'render_profile': (man.get('render_profile') or {}).get('name'),
                     'probe_version': man.get('probe_version'), 'map': case.get('map')})
    return rows


if __name__ == '__main__':
    rows = inventory()
    json.dump(rows, open(sys.argv[1], 'w'), indent=1)
    print(len(rows))
