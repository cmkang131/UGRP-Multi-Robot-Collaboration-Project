"""L2 E2E driver: select -> first frames -> LLM end assignment -> runner cases -> evaluate.

Default OFF: every subcommand requires ``E2E_L2=on_v1``.  Physics is NOT run
here; frames and execution come from the unchanged P2 root runner
(``scripts/run_warp_flow_teacher.py``).

    E2E_L2=on_v1 python scripts/run_e2e_l2.py select --cases GEN.json --out RUN/l2-base-cases.json
    (DeepSeek: runner on RUN/l2-base-cases.json with --diagnostic-ticks 1 -> RUN/frames; own camera
     first frame = RUN/frames/world-00k/review-2hz/<robot>/000000.jpg)
    E2E_L2=on_v1 python scripts/run_e2e_l2.py decide --cases RUN/l2-base-cases.json --frames-run RUN/frames \
        --condition peer_en --llm live --relay-url http://127.0.0.1:PORT/v1/chat/completions \
        --arm student --out RUN/peer_en
    E2E_L2=on_v1 python scripts/run_e2e_l2.py rebind --cases RUN/l2-base-cases.json \
        --decisions RUN/peer_en/decisions.json --arm teacher_fallback --out RUN/peer_en-teacher
    (DeepSeek: runner on RUN/peer_en/exec-cases.json [--student-eval ...] -> RUN/peer_en/run)
    E2E_L2=on_v1 python scripts/run_e2e_l2.py evaluate --decisions RUN/peer_en/decisions.json \
        --summary RUN/peer_en/run/summary.json --admissibility RUN/l2-base-cases-admissibility.json \
        --out RUN/peer_en/l2-eval.json

``--llm replay`` reads recorded replies keyed ``"<seed>|<robot>|<round>"``
(dry runs/tests only; never a result).  ``--llm live`` uses the L1-lite
``Planner`` through the SSH-loopback relay (the key stays in the relay).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness import e2e_l2 as l2            # noqa: E402
from harness import e2e_l2_eval as ev       # noqa: E402

N_CASES = 6
FIRST_FRAME = 'review-2hz/{robot}/000000.jpg'


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
        if len(chosen) == n:
            break
        ok, why = l2.case_admissible(case)
        log.append(dict(seed=case['plan']['seed'], admissible=ok, reason=why))
        if ok:
            chosen.append(case)
    if len(chosen) < n:
        raise SystemExit(f'only {len(chosen)} admissible cases, {n} required')
    return chosen, log


def exclusion_summary(log):
    excluded = [r['seed'] for r in log if not r['admissible']]
    return dict(scanned_n=len(log), selected_n=len(log) - len(excluded), excluded_ns_n=len(excluded),
                excluded_seeds=excluded, rule=f'|cos(yaw)| < {l2.MIN_ABS_COS_YAW} excluded before any LLM call')


def load_frames(frames_run, cases_path, cases):
    """``{seed: {robot: jpeg}}`` from a ``--diagnostic-ticks 1`` runner output on the SAME case file."""
    root = Path(frames_run)
    summary = json.loads((root / 'summary.json').read_text())
    if summary.get('cases_sha256') != sha256(cases_path):
        raise SystemExit('frame run was made on a different case file')
    if list(summary.get('world_indices') or []) != list(range(len(cases))):
        raise SystemExit('frame run must cover every case in order')
    out = {}
    for i, case in enumerate(cases):
        out[case['plan']['seed']] = {r: (root / f'world-{i:03d}' / FIRST_FRAME.format(robot=r)).read_bytes()
                                     for r in l2.ROBOTS}
    return out


def replay_ask(replies, seed):
    def ask(robot, dynamic):
        key = f'{seed}|{robot}|{dynamic["round"]}'
        if key not in replies:
            raise l2.L2Error('L2_NO_DECISION', detail=key)
        return replies[key]
    return ask


def decide(cases, condition, ask_for, arm, frames=None):
    records, exec_cases, skipped = [], [], []
    for world_id, case in enumerate(cases):
        seed = case['plan']['seed']
        record = l2.run_stage(condition, case, ask=ask_for(world_id, case))
        if record['success_eligible']:
            exec_cases.append(l2.build_l2_case(case, record, arm=arm))   # sha over the stage record only
        else:
            skipped.append(dict(seed=seed, errors=record['errors']))
        if frames is not None:
            record['frames_sha256'] = {r: hashlib.sha256(frames[seed][r]).hexdigest() for r in l2.ROBOTS}
        record['geometry'] = l2.geometry_record(case)   # EVAL-ONLY, added after the LLM stage
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
    d.add_argument('--frames-run', type=Path, help='runner output with --diagnostic-ticks 1 (required for live)')
    d.add_argument('--relay-url', help='http://127.0.0.1:PORT/v1/chat/completions (live)')
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
    e.add_argument('--admissibility', type=Path, help='select output *-admissibility.json (N-S exclusion count)')
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
              dict(source=str(a.cases), source_sha256=sha256(a.cases), n=N_CASES, log=log, **exclusion_summary(log)))
        print(json.dumps(exclusion_summary(log)))
        return 0

    if a.cmd == 'decide':
        cases = json.loads(a.cases.read_text())
        frames = load_frames(a.frames_run, a.cases, cases) if a.frames_run else None
        relay, planners_by_world = None, {}
        if a.llm == 'live':
            if frames is None or not a.relay_url:
                p.error('--llm live needs --frames-run and --relay-url')
            relay = l2.check_relay(a.relay_url)
            run_id = f'e2e-l2-{a.condition}-{int(time.time())}'

            def ask_for(world_id, case):
                planners = l2.make_planners(a.relay_url, a.out / 'llm' / f'world-{world_id:02d}', case, a.condition,
                                            run_id=run_id, world_id=world_id)
                planners_by_world[case['plan']['seed']] = planners
                return l2.planner_ask(planners, l2.first_frames(frames[case['plan']['seed']], world_id))
        else:
            if a.replies is None:
                p.error('--llm replay needs --replies')
            replies = json.loads(a.replies.read_text())

            def ask_for(world_id, case):
                return replay_ask(replies, case['plan']['seed'])
        records, exec_cases, skipped = decide(cases, a.condition, ask_for, a.arm, frames)
        for r in records:
            if r['seed'] in planners_by_world:
                r['planner_ledger'] = l2.planner_ledger(planners_by_world[r['seed']])
        write(a.out / 'decisions.json', dict(schema=l2.VERSION, condition=a.condition, arm=a.arm,
                                             arm_label=l2.ARM_LABEL[a.arm], llm=a.llm, relay=relay,
                                             planner_pin=l2.PLANNER_PIN, l1lite_source=l2.L1LITE_SOURCE,
                                             llm_note=('REPLAY: dry run, never a result' if a.llm == 'replay' else None),
                                             cases_sha256=sha256(a.cases), records=records, not_executed=skipped))
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
        stage_keys = ('geometry', 'frames_sha256', 'planner_ledger')
        exec_cases = [l2.build_l2_case(by_seed[r['seed']], {k: v for k, v in r.items() if k not in stage_keys},
                                       arm=a.arm)
                      for r in data['records'] if r['success_eligible']]
        write(a.out / 'decisions.json', {**data, 'arm': a.arm, 'arm_label': l2.ARM_LABEL[a.arm],
                                         'rebound_from': dict(path=str(a.decisions), sha256=sha256(a.decisions))})
        if exec_cases:
            write(a.out / 'exec-cases.json', exec_cases)
        print(json.dumps(dict(executable=len(exec_cases))))
        return 0

    summary = json.loads(a.summary.read_text()) if a.summary else None
    admissibility = json.loads(a.admissibility.read_text()) if a.admissibility else None
    results = [ev.seed_result(r, r['geometry'], summary, arm=data['arm'], prices=l2.PRICE_USD_PER_MILLION)
               for r in data['records']]
    write(a.out, dict(schema='ugrp.e2e_l2.eval.v2', condition=data['condition'], arm=data['arm'],
                      arm_label=data['arm_label'], llm=data['llm'], llm_note=data.get('llm_note'),
                      decisions_sha256=sha256(a.decisions),
                      summary_sha256=sha256(a.summary) if a.summary else None,
                      pre_run_exclusion=(None if admissibility is None else
                                         {k: admissibility[k] for k in ('scanned_n', 'selected_n', 'excluded_ns_n',
                                                                        'excluded_seeds', 'rule')}),
                      prices=l2.PRICE_USD_PER_MILLION, aggregate=ev.aggregate(results), seeds=results))
    return 0


if __name__ == '__main__':
    sys.exit(main())
