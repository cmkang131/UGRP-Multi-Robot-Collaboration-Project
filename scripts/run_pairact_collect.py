"""pairact-r1 P3 success-filtered collection runner (COLLECT_PREREG_DRAFT.json).

Batch loop: plan slots from the ledger -> setup-only cases -> one episode command
(the unchanged MJWarp root runner) -> judge every world -> append to the ledger ->
refresh report.json.  Restart-safe: rerunning the same command continues from the
ledger; a batch whose episode output has a final summary is ingested, not rerun;
an interrupted batch is retried once for its un-ingested slots in a new try dir.
Nothing is overwritten: every try writes a new directory.

    python scripts/run_pairact_collect.py collect --prereg P --run-root R --mode measurement \
        --batch-size 20 --max-batches 3 --dependency-root TEACHER --frozen-root ROOT --adapter-root ADAPTER \
        --episode-cmd 'python WRAPPER --flow beampair ... --cases {cases} --indices {indices} --out {out}'
    python scripts/run_pairact_collect.py report --prereg P --run-root R
    python scripts/run_pairact_collect.py convert-input --prereg P --run-root R --teacher-sha SHA --out DIR
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import pairact_collect as pc  # noqa: E402

MAX_TRIES = 2       # SMOKE.md rule: one rerun, then stop and report


def read_json(path):
    path = Path(path)
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return json.loads(raw)


def raw_result(raw_dir):
    raw_dir = Path(raw_dir)
    for name in ('result.json', 'result.json.zst'):
        if (raw_dir / name).exists():
            return read_json(raw_dir / name)
    return None


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=1, allow_nan=False, default=str) + '\n')
    tmp.replace(path)


def final_summary(out):
    """The root runner rewrites summary.json in ``finally`` with ``worlds``; earlier copies lack it."""
    path = Path(out) / 'summary.json'
    if not path.exists():
        return None
    s = json.loads(path.read_text())
    return s if 'worlds' in s else None


def ingest(ledger, batch, try_no, slots, cases, summary, *, mode, noise, done_slots):
    by_seed = {int(w['seed']): w for w in summary.get('worlds', [])}
    for s in slots:
        if s['slot'] in done_slots:
            continue
        w = by_seed.get(int(s['seed']))
        result = raw_result(w['raw']) if w else None
        j = pc.judge(result, mode=mode)
        if w is None and j['outcome'] == 'host_error':
            j['reason'] = summary.get('error_type') or 'world_missing_from_summary'
        row = dict(type='attempt', batch=batch, attempt_try=try_no, slot=s['slot'], seed=s['seed'], bin=s['bin'],
                   split=s['split'], requeue=s.get('requeue', False), noise=noise,
                   start=pc.start_from_case(cases[s['slot']]),
                   raw=w['raw'] if w else None, sim_s=(w or {}).get('sim_s'),
                   summary_carry_success=(w or {}).get('carry_success'), **j)
        if result is not None and noise == 'on':
            row['perturbed'] = pc.perturbed_ratio(w['raw'])
        if result is not None and row['summary_carry_success'] is not None and \
                bool(row['summary_carry_success']) != bool((result.get('carry_eval') or {}).get('success')):
            raise ValueError(f'summary/result carry_success disagree for seed {s["seed"]}')
        pc.append(ledger, row)
    pc.append(ledger, dict(type='batch_done', batch=batch, attempt_try=try_no, split=slots[0]['split'],
                           status=summary.get('status'), host_error=summary.get('HOST_ERROR'),
                           wall_s=summary.get('wall_s'), vm_cost_estimate_usd=summary.get('vm_cost_estimate_usd'),
                           source_sha=summary.get('source_sha')))


def run(run_root, prereg, prereg_sha, *, mode, noise, batch_size, max_batches, make_cases, run_episode,
        deadline=None, now=None):
    """Returns the stop reason (or 'MAX_BATCHES' / 'DEADLINE'). Fakes plug in via make_cases / run_episode."""
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    ledger = run_root / 'ledger.jsonl'
    hdr = pc.header(prereg_sha, mode=mode, noise=noise, batch_size=batch_size)
    pc.repair_ledger(ledger)
    rows = pc.read_ledger(ledger)
    if not rows:
        pc.append(ledger, hdr)
    elif rows[0] != hdr:
        raise ValueError('ledger header mismatch: same prereg sha, mode, noise and batch size required')
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    started = 0
    while True:
        st = pc.replay(prereg, pc.read_ledger(ledger))
        write(run_root / 'report.json', pc.report(prereg, st, prereg_sha=prereg_sha))
        k = st['open_batch']
        if k is None:
            slots = pc.plan_batch(prereg, st, batch_size)
            if not slots:
                return pc.stop_reason(prereg, st)
            if started >= max_batches:
                return 'MAX_BATCHES'
            if deadline is not None and now() >= deadline:
                return 'DEADLINE'
            k = max(st['batches'], default=-1) + 1
            bdir = run_root / 'batches' / f'b{k:03d}'
            bdir.mkdir(parents=True, exist_ok=False)
            cases = make_cases(slots)
            write(bdir / 'cases.json', cases)
            write(bdir / 'slots.json', slots)
            pc.append(ledger, dict(type='batch_planned', batch=k, slots=slots, split=slots[0]['split']))
            st = pc.replay(prereg, pc.read_ledger(ledger))
        bdir = run_root / 'batches' / f'b{k:03d}'
        slots = st['batches'][k]['slots']
        cases = json.loads((bdir / 'cases.json').read_text())
        if [c['plan']['seed'] for c in cases] != [s['seed'] for s in slots]:
            raise ValueError(f'batch {k}: cases.json does not match planned slots')
        done = st['batches'][k]['ingested']
        tries = sorted(int(p.name.split('-')[1]) for p in bdir.glob('try-*') if p.is_dir())
        last = tries[-1] if tries else 0
        summary = final_summary(bdir / f'try-{last}') if last else None
        if summary is None:
            if last >= MAX_TRIES:
                # interrupted twice: remaining slots become host errors, batch closed as HOST_ERROR
                ingest(ledger, k, last, slots, cases, dict(status='HOST_ERROR', HOST_ERROR=1,
                       error_type='interrupted_twice', worlds=[]), mode=mode, noise=noise, done_slots=done)
                continue
            if started >= max_batches:
                return 'MAX_BATCHES'
            if deadline is not None and now() >= deadline:
                return 'DEADLINE'
            last += 1
            out = bdir / f'try-{last}'
            todo = [s['slot'] for s in slots if s['slot'] not in done]
            started += 1
            code = run_episode(bdir / 'cases.json', todo, out)
            write(bdir / f'exit-try-{last}.json', dict(exit=code, indices=todo))
            summary = final_summary(out)
            if summary is None:
                continue        # interrupted / crashed before the final summary: retried or closed above
        ingest(ledger, k, last, slots, cases, summary, mode=mode, noise=noise, done_slots=done)


def shell_episode(template):
    def go(cases, indices, out):
        cmd = template.format(cases=shlex.quote(str(cases)), indices=','.join(map(str, indices)),
                              out=shlex.quote(str(out)))
        return subprocess.call(cmd, shell=True)
    return go


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=('collect', 'report', 'convert-input'))
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--mode', choices=pc.MODES, default='measurement')
    p.add_argument('--noise', choices=pc.NOISE_MODES, default='off')
    p.add_argument('--batch-size', type=int, default=20)
    p.add_argument('--max-batches', type=int, default=1)
    p.add_argument('--deadline-utc', help='do not start a new batch at or after this ISO time (e.g. 2026-10-22T00:00Z)')
    p.add_argument('--episode-cmd', help='shell template with {cases} {indices} {out}')
    p.add_argument('--dependency-root', type=Path)
    p.add_argument('--frozen-root', type=Path)
    p.add_argument('--adapter-root', type=Path, help='pinned adapter checkout (runtime placement filter family)')
    p.add_argument('--candidate', default='pairact_p2_r13')
    p.add_argument('--teacher-sha')
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    prereg, sha = pc.load_prereg(a.prereg, mode=a.mode)
    if a.command == 'report':
        st = pc.replay(prereg, pc.read_ledger(a.run_root / 'ledger.jsonl'))
        rep = pc.report(prereg, st, prereg_sha=sha)
        write(a.run_root / 'report.json', rep)
        print(json.dumps(dict(stop=rep['stop'], A=rep['A']['text']), ensure_ascii=False))
        return
    if a.command == 'convert-input':
        if not a.teacher_sha or not a.out:
            p.error('--teacher-sha and --out required')
        st = pc.replay(prereg, pc.read_ledger(a.run_root / 'ledger.jsonl'))
        if (st['header'] or {}).get('mode') != 'training':
            p.error('convert input needs a training-mode ledger (measurement runs have no tensors)')
        print(json.dumps(pc.convert_input(st, a.out, teacher_sha=a.teacher_sha)))
        return
    if not a.episode_cmd or '{out}' not in a.episode_cmd or '{cases}' not in a.episode_cmd:
        p.error('--episode-cmd with {cases} {indices} {out} required')
    sys.path.insert(0, str(ROOT / 'experiments/2026-10-21-pairact-r1'))
    import collect_cases
    geo = collect_cases.Geometry(a.dependency_root, a.frozen_root, setup_validity=True, adapter_root=a.adapter_root)
    deadline = dt.datetime.fromisoformat(a.deadline_utc.replace('Z', '+00:00')) if a.deadline_utc else None
    stop = run(a.run_root, prereg, sha, mode=a.mode, noise=a.noise, batch_size=a.batch_size,
               max_batches=a.max_batches, deadline=deadline,
               make_cases=lambda slots: collect_cases.make_cases(geo, prereg, slots, candidate=a.candidate),
               run_episode=shell_episode(a.episode_cmd))
    rep = json.loads((a.run_root / 'report.json').read_text())
    print(json.dumps(dict(stop=stop, A=rep['A']['text']), ensure_ascii=False))


if __name__ == '__main__':
    main()
