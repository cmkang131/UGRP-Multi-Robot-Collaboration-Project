"""crate11: assemble crate11-summary.json from the analysis outputs (offline; reads files only).
Usage: python crate11_build_summary.py <analysis_dir> <hashcheck.json> <out.json>"""
import json, sys, hashlib
from pathlib import Path

A = Path(sys.argv[1]); H = json.loads(Path(sys.argv[2]).read_text())
an = json.loads((A / 'an.json').read_text()); t2 = json.loads((A / 't2.json').read_text())
dv = json.loads((A / 'div_join.json').read_text()); pa = json.loads((A / 'plan_audit.json').read_text())
sums = {l.split()[1]: l.split()[0] for l in (A / 'SHA256SUMS').read_text().splitlines()}
t2b = {r['run']: r for r in t2}
near = [r for r in t2 if r['near_wall_flag']]
def rate(rows, sha):
    rr = [r for r in rows if r['sha8'] == sha]
    return {'n': len(rr), 'success': sum(r['success'] for r in rr)}
by_sha = {s: {'all': rate(t2, s), 'near_wall': rate(near, s), 'not_near_wall': rate([r for r in t2 if not r['near_wall_flag']], s)}
          for s in ('c5a76175', '5644e3dd', 'bf31840f', '49d11b8e')}
gate = {f: {'episodes': len(v), 'infeasible_stance_planner': sum(x['infeasible'] for x in v), 'near_wall_flag': sum(bool(x['near_wall']) for x in v),
            'flag_equals_geometry': all(bool(x['near_wall']) == x['infeasible'] for x in v),
            'infeasible_seeds': [x['seed'] for x in v if x['infeasible']]} for f, v in pa.items()}
out = {
    'schema': 'ugrp.crate11.measure_summary.v1', 'scope': 'measure only; offline replay of saved inputs; no code/physics/render/remote; GT fields are evaluation-only',
    'sources': {'bf31840f': 'bf31840fe16cd2d37631d8a8e50ff077e3d42575', '49d11b8e': '49d11b8e603c54fd42e6707f735fca8f55c11a0e',
                '5644e3dd': '5644e3dd114c34c2ee0e5e09b4bdaba10754621e'},
    'raw_runs_root': '/Users/changmin/projects/ugrp/outputs/gcp1-runs', 'analysis_dir': str(A),
    'analysis_file_sha256': sums, 'raw_hash_check': {k: H[k] for k in ('runs', 'files_checked', 'frames_checked', 'mismatch', 'not_in_sums')},
    'replay_bit_exact_runs': '33 of 33 replayed runs reproduce ledger commands (t, wheels, pwm, duration<=1e-10, done, phase)',
    'not_pooled_note': 'different source SHAs / seed sets; only seeds 77969/77978/77979 are paired (diag-77978/79 bf31840f vs reproduction 49d11b8e)',
    'success_by_sha_eval_only': by_sha, 'gate_plan_stance_audit': gate,
    'table1_failures': an['failures'], 'toggle_attribution_49d11b8e': dv,
    'table2_seed_geometry_eval_only': t2, 'pinned_yaw_drift_77979_bf31840f_r1_eval_only': an['pinned_yaw_drift_77979_bf31840f_r1'],
    'frames_viewed': {k: json.loads((A / f'{k}.json').read_text()) for k in ('77978-bf31', '77979-bf31', '77969-5644')},
    'frames_not_viewed': 'crate-diag-77981/77982/77988/77989-49d11b8e and crate-reproduction-77969/77978/77979-49d11b8e have no jpg locally; GT path plot paths.png used instead',
}
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
print('ok', json.dumps(by_sha), json.dumps({k: (v['episodes'], v['infeasible_stance_planner']) for k, v in gate.items()}))
