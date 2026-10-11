"""Offline Jev/Gemma decider evaluation driver (2026-10-11). No simulation. Usage:
  python3 scripts/run_jev_decider_offline.py suite|phase1|real|report [--raw-dir DIR] [--repr NAME ...]
Keys come from the macOS keychain into memory only."""
import argparse
import glob
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness import jev_decider_eval as ev, jev_decider_suite as su

EXP = Path(__file__).resolve().parents[1] / 'experiments' / '2026-10-11-jev-decider-offline'
RAW = Path('/Users/changmin/projects/ugrp/outputs/jev-decider-offline-20261011')
REPEATS = 3


def load_suite():
    return json.loads((EXP / 'suite.json').read_text())


def real_cases(wire_dir):
    seen, out = {}, []
    for f in sorted(glob.glob(str(Path(wire_dir) / '**' / '*request.json'), recursive=True)):
        d = json.loads(Path(f).read_text())
        try:
            user = json.loads(d['messages'][1]['content'][0]['text'])
            state = ev.real_state_from_request(user)
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        key = json.dumps([state['robot_id'], state['condition'], state['dialogue'], [p['text'] for p in state['peer_reports']],
                          state['own_map']['B_seen_in_own_rgb'], state['own_route_proposal'] is not None], sort_keys=True)
        if key in seen:
            seen[key]['n_stored_requests'] += 1
            continue
        c = dict(id=f'REAL{len(out) + 1:02d}', decision_point='real_e2e', family='dialogue', state=state, acceptable=[],
                 ambiguous=True, label_basis='none_descriptive', pair=None, rule='-', group='real', split='real',
                 n_stored_requests=1, source=str(Path(f).name), model_in_stored_run=d.get('model'))
        c['structurally_admissible'] = su.structural_admissible(state, 'dialogue')
        c['n_structurally_admissible'] = len(c['structurally_admissible'])
        seen[key] = c
        out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('phase', choices=('suite', 'phase1', 'real', 'report'))
    ap.add_argument('--raw-dir', default=str(RAW))
    ap.add_argument('--wire', default='/tmp/jevdec/azwire')
    a = ap.parse_args()
    suite = load_suite()
    cases = suite['cases']
    if a.phase == 'suite':
        print(len(cases), su.suite_sha(su.build()), su.suite_sha(suite))
        return
    jev, gem = ev.keychain('ugrp.typesafe.ai', 'jev'), ev.keychain('ugrp-openrouter', 'openrouter')
    if a.phase == 'phase1':
        run = ev.Runner(Path(a.raw_dir) / 'phase1', jev_key=jev, gemma_key=gem)
        jobs = [(p, r, c, k) for p in ('jev', 'gemma') for r in ev.REPRESENTATIONS for c in cases for k in range(1, REPEATS + 1)]
        run.run(jobs)
        print('done', len(run.done), 'http attempts', run.http_attempts)
    elif a.phase == 'real':
        real = real_cases(a.wire)
        (EXP / 'real_states.json').write_text(json.dumps(real, indent=1, sort_keys=True) + '\n')
        run = ev.Runner(Path(a.raw_dir) / 'real', jev_key=jev, gemma_key=gem)
        jobs = [(p, r, c, k) for p in ('jev', 'gemma') for r in ev.REPRESENTATIONS for c in real for k in (1, 2)]
        run.run(jobs)
        print('done', len(run.done), 'http attempts', run.http_attempts, 'unique real states', len(real))


if __name__ == '__main__':
    main()
