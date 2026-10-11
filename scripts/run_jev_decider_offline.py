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


def real_cases(wire_dirs):
    seen, out = {}, []
    files = sorted(f for w in wire_dirs for f in glob.glob(str(Path(w) / '**' / '*request.json'), recursive=True))
    for f in files:
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
                 n_stored_requests=1, source=str(Path(f)), source_sha256=hashlib.sha256(Path(f).read_bytes()).hexdigest(), model_in_stored_run=d.get('model'))
        c['structurally_admissible'] = su.structural_admissible(state, 'dialogue')
        c['n_structurally_admissible'] = len(c['structurally_admissible'])
        seen[key] = c
        out.append(c)
    return out


def load_rows(path):
    p = Path(path)
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rule_rows(cases):
    return [dict(call_id='rule.' + c['id'], policy='rule', representation='structural', case_id=c['id'], repeat=1, status='ok',
                 choice=ev.rule_action(c['state'], c['family']), confidence=None, probabilities=None, latency_s=None, usage=None, cost=None)
            for c in cases]


def agreement(rows, cases):
    """Descriptive only: share of matched (case, repeat) calls where Jev and Gemma chose the same action."""
    out = {}
    for rep in ev.REPRESENTATIONS:
        j = {(r['case_id'], r['repeat']): r for r in rows if r['policy'] == 'jev' and r['representation'] == rep and r['status'] == 'ok'}
        g = {(r['case_id'], r['repeat']): r for r in rows if r['policy'] == 'gemma' and r['representation'] == rep and r['status'] == 'ok'}
        both = sorted(set(j) & set(g))
        same = [k for k in both if j[k]['choice'] == g[k]['choice']]
        out[rep] = dict(same=len(same), of=len(both), note='descriptive; not a success criterion')
    return out


def report(a, suite):
    cases = suite['cases']
    raw = Path(a.raw_dir)
    rows = load_rows(raw / 'phase1' / 'calls.jsonl')
    by_split = {c['id']: c['split'] for c in cases}
    real = load_rows(raw / 'real' / 'calls.jsonl')
    imp = load_rows(raw / 'improved' / 'calls.jsonl')
    probe_rows = load_rows(raw / 'probe' / 'calls.jsonl')
    summary = dict(schema='ugrp.jev_decider_offline_summary.v1', raw_dir=str(raw), suite_sha256=sha(EXP / 'suite.json'),
                   n_cases=len(cases), n_phase1_calls=len(rows), n_real_calls=len(real),
                   n_http_attempts=sum(len(r['attempts']) for r in rows + imp + probe_rows + real), call_cap=ev.CALL_CAP)
    pol = {}
    for p in ('jev', 'gemma'):
        for rep in ev.REPRESENTATIONS:
            sub = [r for r in rows if r['policy'] == p and r['representation'] == rep]
            pol[f'{p}.{rep}'] = {split: ev.analyze(sub, [c for c in cases if split == 'all' or c['split'] == split]) for split in ('all', 'dev', 'holdout')}
    for p in ('jev', 'gemma'):
        sub = [r for r in imp if r['policy'] == p]
        if sub:
            pol[f'{p}.{ev.IMPROVED}'] = {sp: ev.analyze([r for r in sub if by_split[r['case_id']] in (sp, *(('dev', 'holdout') if sp == 'all' else ()))],
                                                        [c for c in cases if sp == 'all' or c['split'] == sp]) for sp in ('all', 'dev', 'holdout')
                                         if any(by_split[r['case_id']] == sp or sp == 'all' for r in sub)}
    probe_cases = json.loads((EXP / 'probe_suite.json').read_text())['cases']
    for p in ('jev', 'gemma'):
        sub = [r for r in probe_rows if r['policy'] == p]
        if sub:
            pol[f'{p}.{ev.IMPROVED}.probe'] = ev.analyze(sub, probe_cases)
    summary['probe_rule_choices'] = {c['id']: ev.rule_action(c['state'], 'dialogue') for c in probe_cases}
    rr = rule_rows(cases)
    pol['rule.structural'] = {split: ev.analyze(rr, [c for c in cases if split == 'all' or c['split'] == split]) for split in ('all', 'dev', 'holdout')}
    summary['policies'] = pol
    summary['jev_gemma_agreement'] = agreement(rows, cases)
    by = {c['id']: c for c in cases}
    fails = []
    for r in rows + imp:
        c = by[r['case_id']]
        if c['ambiguous'] or r['status'] == 'ok' and r['choice'] in c['acceptable']:
            continue
        if c['split'] == 'holdout' and not a.reveal_holdout:
            continue
        fails.append(dict(call_id=r['call_id'], split=c['split'], choice=r['choice'], acceptable=c['acceptable'], status=r['status'],
                          confidence=r['confidence'], decision_point=c['decision_point']))
    summary['dev_failures' if not a.reveal_holdout else 'failures_all_splits'] = fails
    summary['rule_choices'] = {r['case_id']: r['choice'] for r in rr}
    cmap = {}
    for r in rows + imp + probe_rows + real:
        cmap[r['call_id']] = dict(status=r['status'], choice=r['choice'], confidence=r['confidence'], latency_s=r['latency_s'],
                                  http_attempts=len(r['attempts']), error=r['error'], request_sha256=r['request_sha256'],
                                  response_sha256=r['response_sha256'], usage=r['usage'], cost=r['cost'], provider=r.get('provider'))
    summary['calls'] = cmap
    summary['journals_sha256'] = {str(p): sha(p) for p in (raw / 'phase1' / 'calls.jsonl', raw / 'improved' / 'calls.jsonl', raw / 'real' / 'calls.jsonl') if Path(p).exists()}
    Path(a.out).write_text(json.dumps(summary, indent=1, sort_keys=True) + '\n')
    print('wrote', a.out, 'phase1 calls', len(rows), 'real calls', len(real))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('phase', choices=('suite', 'phase1', 'real', 'improved', 'probe', 'report'))
    ap.add_argument('--raw-dir', default=str(RAW))
    ap.add_argument('--wire', nargs='+', default=['/tmp/jevdec/azwire', '/Users/changmin/projects/ugrp/outputs/gemma-latency-check-20261011/wire'])
    ap.add_argument('--reveal-holdout', action='store_true', help='list holdout failures (only after the improved representation is frozen)')
    ap.add_argument('--split', choices=('dev', 'holdout'), default='dev')
    ap.add_argument('--out', default=str(EXP / 'summary.json'))
    a = ap.parse_args()
    suite = load_suite()
    cases = suite['cases']
    if a.phase == 'suite':
        print(len(cases), su.suite_sha(su.build()), su.suite_sha(suite))
        return
    if a.phase == 'report':
        return report(a, suite)
    jev, gem = ev.keychain('ugrp.typesafe.ai', 'jev'), ev.keychain('ugrp-openrouter', 'openrouter')
    if a.phase == 'phase1':
        run = ev.Runner(Path(a.raw_dir) / 'phase1', jev_key=jev, gemma_key=gem)
        jobs = [(p, r, c, k) for p in ('jev', 'gemma') for r in ev.REPRESENTATIONS for c in cases for k in range(1, REPEATS + 1)]
        run.run(jobs)
        print('done', len(run.done), 'http attempts', run.http_attempts)
    elif a.phase == 'improved':
        run = ev.Runner(Path(a.raw_dir) / 'improved', jev_key=jev, gemma_key=gem)
        jobs = [(p, ev.IMPROVED, c, k) for p in ('jev', 'gemma') for c in cases if c['split'] == a.split for k in range(1, REPEATS + 1)]
        run.run(jobs)
        print('done', a.split, len(jobs), 'http attempts total', run.http_attempts)
    elif a.phase == 'probe':
        probe = json.loads((EXP / 'probe_suite.json').read_text())['cases']
        run = ev.Runner(Path(a.raw_dir) / 'probe', jev_key=jev, gemma_key=gem)
        run.run([(p, ev.IMPROVED, c, k) for p in ('jev', 'gemma') for c in probe for k in range(1, REPEATS + 1)])
        print('done probe', len(run.done), 'http attempts', run.http_attempts)
    elif a.phase == 'real':
        real = real_cases(a.wire)
        (EXP / 'real_states.json').write_text(json.dumps(real, indent=1, sort_keys=True) + '\n')
        run = ev.Runner(Path(a.raw_dir) / 'real', jev_key=jev, gemma_key=gem)
        jobs = [(p, r, c, k) for p in ('jev', 'gemma') for r in ev.REPRESENTATIONS for c in real for k in (1, 2)]
        run.run(jobs)
        print('done', len(run.done), 'http attempts', run.http_attempts, 'unique real states', len(real))


if __name__ == '__main__':
    main()
