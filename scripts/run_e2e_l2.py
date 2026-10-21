"""L2 E2E driver: select cases -> LLM end assignment -> runner cases -> evaluate.

Default OFF: every subcommand requires ``E2E_L2=on_v1``.  Physics is NOT run
here; the execution stage is the unchanged P2 root runner
(``scripts/run_warp_flow_teacher.py``, ``--student-eval`` for the learned arm),
fed with the case file this script writes.

    E2E_L2=on_v1 python scripts/run_e2e_l2.py select   --cases P3_GEN.json --out RUN/l2-base-cases.json
    E2E_L2=on_v1 python scripts/run_e2e_l2.py decide   --cases RUN/l2-base-cases.json --condition peer_en \
        --llm replay --replies REPLIES.json --arm student --out RUN/peer_en
    E2E_L2=on_v1 python scripts/run_e2e_l2.py rebind   --cases RUN/l2-base-cases.json \
        --decisions RUN/peer_en/decisions.json --arm teacher_fallback --out RUN/peer_en-teacher
    (DeepSeek: run_warp_flow_teacher ... --cases RUN/peer_en/exec-cases.json [--student-eval ...])
    E2E_L2=on_v1 python scripts/run_e2e_l2.py evaluate --decisions RUN/peer_en/decisions.json \
        --summary RUN/peer_en/run/summary.json --out RUN/peer_en/l2-eval.json

``--llm live`` is NOT wired (``harness.e2e_l2.planner_ask`` raises
NotImplementedError, TODO).  ``--llm replay`` reads recorded replies keyed
``"<seed>|<robot>|<round>"`` and exists for dry runs and tests only; a replay
run is never a result.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import e2e_l2 as l2            # noqa: E402
from harness import e2e_l2_eval as ev       # noqa: E402

N_CASES = 6


def write(path, value):
    path = Path(path)
    if path.exists():
        raise SystemExit(f'refusing to overwrite {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def select(cases, n=N_CASES):
    """First ``n`` admissible cases in ascending seed order (pre-run, outcome-free)."""
    log, chosen = [], []
    for case in sorted(cases, key=lambda c: c['plan']['seed']):
        ok, why = l2.case_admissible(case)
        log.append(dict(seed=case['plan']['seed'], admissible=ok, reason=why))
        if ok and len(chosen) < n:
            chosen.append(case)
    if len(chosen) < n:
        raise SystemExit(f'only {len(chosen)} admissible cases, {n} required')
    return chosen, log


def replay_ask(replies, seed):
    def ask(robot, dynamic):
        key = f'{seed}|{robot}|{dynamic["round"]}'
        if key not in replies:
            raise l2.L2Error('L2_NO_DECISION', detail=key)
        return replies[key]
    return ask


def decide(cases, condition, ask_for_seed, arm):
    records, exec_cases, skipped = [], [], []
    for case in cases:
        seed = case['plan']['seed']
        record = l2.run_stage(condition, case, ask=ask_for_seed(seed))
        if record['success_eligible']:
            exec_cases.append(l2.build_l2_case(case, record, arm=arm))   # sha over the stage record only
        else:
            skipped.append(dict(seed=seed, errors=record['errors']))
        record['geometry'] = l2.geometry_record(case)   # admin/eval-only, written after the stage
        records.append(record)
    return records, exec_cases, skipped


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('select')
    s.add_argument('--cases', type=Path, required=True)
    s.add_argument('--out', type=Path, required=True)
    d = sub.add_parser('decide')
    d.add_argument('--cases', type=Path, required=True)
    d.add_argument('--condition', choices=l2.CONDITIONS, required=True)
    d.add_argument('--llm', choices=('live', 'replay'), required=True)
    d.add_argument('--replies', type=Path)
    d.add_argument('--arm', choices=l2.ARMS, required=True)
    d.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('rebind', help='same recorded LLM decisions, other arm (no LLM call)')
    b.add_argument('--cases', type=Path, required=True)
    b.add_argument('--decisions', type=Path, required=True)
    b.add_argument('--arm', choices=l2.ARMS, required=True)
    b.add_argument('--out', type=Path, required=True)
    e = sub.add_parser('evaluate')
    e.add_argument('--decisions', type=Path, required=True)
    e.add_argument('--summary', type=Path, help='runner summary.json; omit if no seed was executable')
    e.add_argument('--prices', type=Path, default=Path('configs/model_endpoints.json'))
    e.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        l2.require_enabled()
    except l2.L2Error as exc:
        p.error(str(exc))

    if a.cmd == 'select':
        chosen, log = select(json.loads(a.cases.read_text()))
        write(a.out, chosen)
        write(a.out.with_name(a.out.stem + '-admissibility.json'),
              dict(source=str(a.cases), source_sha256=sha256(a.cases), rule=f'|cos(yaw)| >= {l2.MIN_ABS_COS_YAW}',
                   n=N_CASES, log=log))
        return 0

    if a.cmd == 'decide':
        cases = json.loads(a.cases.read_text())
        if a.llm == 'live':
            # TODO([확인 필요]): bind the L1-lite Planner (dsh/l1lite-alloc) here.
            l2.planner_ask(None, None, None)
        if a.replies is None:
            p.error('--llm replay needs --replies')
        replies = json.loads(a.replies.read_text())
        records, exec_cases, skipped = decide(cases, a.condition, lambda seed: replay_ask(replies, seed), a.arm)
        write(a.out / 'decisions.json', dict(schema=l2.VERSION, condition=a.condition, arm=a.arm,
                                             arm_label=l2.ARM_LABEL[a.arm], llm=a.llm,
                                             llm_note=('REPLAY: dry run, never a result' if a.llm == 'replay' else None),
                                             cases_sha256=sha256(a.cases), records=records,
                                             not_executed=skipped))
        if exec_cases:
            write(a.out / 'exec-cases.json', exec_cases)
        print(json.dumps(dict(executable=len(exec_cases), not_executed=len(skipped),
                              exec_cases=str(a.out / 'exec-cases.json') if exec_cases else None)))
        return 0

    data = json.loads(a.decisions.read_text())
    if a.cmd == 'rebind':
        if data['cases_sha256'] != sha256(a.cases):
            p.error('cases file differs from the one the decisions were made on')
        if a.arm == data['arm']:
            p.error('rebind is for the other arm')
        by_seed = {c['plan']['seed']: c for c in json.loads(a.cases.read_text())}
        exec_cases = [l2.build_l2_case(by_seed[r['seed']], {k: v for k, v in r.items() if k != 'geometry'}, arm=a.arm)
                      for r in data['records'] if r['success_eligible']]
        write(a.out / 'decisions.json', {**data, 'arm': a.arm, 'arm_label': l2.ARM_LABEL[a.arm],
                                         'rebound_from': dict(path=str(a.decisions), sha256=sha256(a.decisions))})
        if exec_cases:
            write(a.out / 'exec-cases.json', exec_cases)
        print(json.dumps(dict(executable=len(exec_cases))))
        return 0
    summary = json.loads(a.summary.read_text()) if a.summary else None
    prices = l2.price_table(a.prices)
    results = [ev.seed_result(r, r['geometry'], summary, arm=data['arm'], prices=prices) for r in data['records']]
    write(a.out, dict(schema='ugrp.e2e_l2.eval.v1', condition=data['condition'], arm=data['arm'],
                      arm_label=data['arm_label'], llm=data['llm'], llm_note=data.get('llm_note'),
                      decisions_sha256=sha256(a.decisions),
                      summary_sha256=sha256(a.summary) if a.summary else None,
                      prices=prices, aggregate=ev.aggregate(results), seeds=results))
    return 0


if __name__ == '__main__':
    sys.exit(main())
