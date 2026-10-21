"""pairact-r1 P3 success-filtered collection runner (COLLECT_PREREG_DRAFT.json).

Batch loop: plan slots from the ledger -> setup-only cases -> one episode command
(the unchanged MJWarp root runner) -> judge every world -> append to the ledger ->
refresh report.json.  Restart-safe: rerunning the same command continues from the
ledger; a batch whose episode output has a final summary is ingested, not rerun;
an interrupted batch is retried once for its un-ingested slots in a new try dir.
Nothing is overwritten: every try writes a new directory.

    python scripts/run_pairact_collect.py collect --prereg P --run-root R --mode measurement \
        --batch-size 20 --max-batches 2 --dependency-root TEACHER --frozen-root ROOT --adapter-root ADAPTER \
        --episode-cmd 'python WRAPPER --flow beampair ... --cap-s 60 --rejection-table /abs/rejection_table.json \
                       --cases {cases} --indices {indices} --out {out}'
    python scripts/run_pairact_collect.py collect ... --mode training --run-manifest RUN_MANIFEST.json ...
    python scripts/run_pairact_collect.py report --prereg P --run-root R
    # sharded (v3s, prereg sharding): one process per shard, then merge
    python scripts/run_pairact_collect.py collect ... --shard 0/4 --vm gcp6     # and 1/4, 2/4, 3/4
    python scripts/run_pairact_collect.py merge --prereg P --run-root R --shards 4   # -> R/merged/
    python scripts/run_pairact_collect.py convert-input --prereg P --run-root R --teacher-sha SHA --out DIR

Batch status, required fields and the sidecar check follow COLLECT_PREREG v2 status_table / filter:
an unclean batch (HOST_ERROR, exit != 0 or unknown) admits nothing; a missing field is a record
error (STOP_RECORD), never a default.  Generator budget exhaustion is a setup_rejected ledger row.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

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


def dumps(value):
    return (json.dumps(value, indent=1, allow_nan=False, default=str) + '\n').encode()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(dumps(value))
    tmp.replace(path)


def final_summary(out):
    """The root runner rewrites summary.json in ``finally`` with ``worlds``; earlier copies lack it."""
    path = Path(out) / 'summary.json'
    if not path.exists():
        return None
    s = json.loads(path.read_text())
    return s if 'worlds' in s else None


def exit_code(bdir, try_no):
    path = Path(bdir) / f'exit-try-{try_no}.json'
    return json.loads(path.read_text()).get('exit') if path.exists() else None    # unknown -> batch unclean


def judge_world(s, case, w, summary, *, mode, clean, read_rows):
    """Status-table judgement of one slot (sidecar only for training-mode successes)."""
    if w is None and summary.get('status') == 'admission_rejected':
        return dict(pc.judge(None, mode=mode, batch_clean=False), outcome='admission_error',
                    reason=summary.get('error_type') or 'admission_rejected', requeue_eligible=False), None, None
    result = raw_result(w['raw']) if w else None
    j = pc.judge(result, mode=mode, batch_clean=clean)
    sidecar = None
    if j['outcome'] == 'success' and mode == 'training':
        sidecar = pc.sidecar_check(w['raw'], robots=tuple(case['plan']['roles']), read_rows=read_rows)
        j = pc.judge(result, mode=mode, batch_clean=clean, sidecar=sidecar)
    if w is None and j['outcome'] == 'host_error':
        j['reason'] = summary.get('error_type') or 'world_missing_from_summary'
    # v5: result.carry_eval.success is the single truth.  A summary without worlds[].carry_success (the gcp6
    # wrapper, gcp2 shard smoke 2026-10-21: 25 record_error) is not a disagreement; a present, different value is.
    if j['category'] == 'behavior' and j['failure_stage'] != 'grasp' and 'carry_success' in w and \
            w['carry_success'] != (result.get('carry_eval') or {}).get('success'):
        j = pc._record_error(j, f'summary/result carry_success disagree for seed {s["seed"]}')
    return j, result, sidecar


def ingest(ledger, batch, try_no, slots, cases, summary, code, *, mode, noise, done_slots, read_rows=pc.read_jsonl):
    clean = pc.batch_is_clean(summary, code)
    by_seed = {int(w['seed']): w for w in summary.get('worlds', [])}
    for s in slots:
        if s['slot'] in done_slots:
            continue
        w = by_seed.get(int(s['seed']))
        j, result, sidecar = judge_world(s, cases[s['slot']], w, summary, mode=mode, clean=clean, read_rows=read_rows)
        j = pc.validation_unclean(j, split=s['split'], requeue=s.get('requeue', False), batch_clean=clean)
        row = dict(type='attempt', batch=batch, attempt_try=try_no, slot=s['slot'], seed=s['seed'], bin=s['bin'],
                   split=s['split'], requeue=s.get('requeue', False), noise=noise,
                   start=pc.start_from_case(cases[s['slot']]), raw=w['raw'] if w else None,
                   sim_s=(w or {}).get('sim_s'), summary_carry_success=(w or {}).get('carry_success'),
                   batch_clean=clean, sidecar=sidecar, **j)
        if result is not None and noise == 'on':
            row['perturbed'] = pc.perturbed_ratio(w['raw'], read_rows=read_rows)
        pc.append(ledger, row)
    pc.append(ledger, dict(type='batch_done', batch=batch, attempt_try=try_no, split=slots[0]['split'],
                           status=summary.get('status'), host_error=summary.get('HOST_ERROR'), exit=code, clean=clean,
                           error_type=summary.get('error_type'), rejection_table=summary.get('rejection_table'),
                           artifact_sha256_manifest=summary.get('artifact_sha256_manifest'),
                           wall_s=summary.get('wall_s'), vm_cost_estimate_usd=summary.get('vm_cost_estimate_usd'),
                           source_sha=summary.get('source_sha'), source_contract=summary.get('source_contract')))


def setup_rejected_row(k, slot, audit):
    """Ledger row for a generator budget exhaustion (Codex v2 B4).

    The generator audit already carries seed / bin / split; they must agree with the slot and the
    slot values win (no duplicate keyword expansion).  ``requeue`` is the slot's flag.
    """
    for key in ('seed', 'bin', 'split'):
        if key in audit and audit[key] != slot[key]:
            raise ValueError(f'setup_rejected audit {key}={audit[key]!r} differs from slot {slot[key]!r}')
    return dict(audit, type='setup_rejected', planning_batch=k, seed=slot['seed'], bin=slot['bin'],
                split=slot['split'], requeue=bool(slot.get('requeue', False)))


def plan_new_batch(ledger, run_root, prereg, st, slots, make_cases):
    """Cases first (in memory), generator rejections into the ledger, then batch_planned, then files.

    A crash while building cases leaves nothing behind; a crash after batch_planned is resumed from
    the ledger (cases are regenerated and must hash to the recorded cases_sha256).
    """
    k = max(st['batches'], default=-1) + 1
    built = make_cases(slots)
    keep = []
    for s, c in zip(slots, built):
        if 'setup_rejected' in c:
            pc.append(ledger, setup_rejected_row(k, s, c['setup_rejected']))
        else:
            keep.append((s, c))
    if not keep:
        return None
    slots = [dict(s, slot=i) for i, (s, _) in enumerate(keep)]
    cases = [c for _, c in keep]
    pc.append(ledger, dict(type='batch_planned', batch=k, slots=slots, split=slots[0]['split'],
                           cases_sha256=hashlib.sha256(dumps(cases)).hexdigest()))
    return k


def batch_cases(bdir, planned, slots, make_cases):
    path = Path(bdir) / 'cases.json'
    if not path.exists():
        cases = make_cases([{k: v for k, v in s.items() if k != 'slot'} for s in slots])
        if any('setup_rejected' in c for c in cases):
            raise ValueError(f'{bdir}: regenerated cases differ from the planned batch')
        write(path, cases)
        write(Path(bdir) / 'slots.json', slots)
    if hashlib.sha256(path.read_bytes()).hexdigest() != planned['cases_sha256']:
        raise ValueError(f'{bdir}: cases.json sha256 differs from the ledger')
    cases = json.loads(path.read_text())
    if [c['plan']['seed'] for c in cases] != [s['seed'] for s in slots]:
        raise ValueError(f'{bdir}: cases.json does not match planned slots')
    return cases


def run(run_root, prereg, prereg_sha, *, mode, noise, batch_size, max_batches, make_cases, run_episode,
        episode=None, run_manifest_sha256=None, deadline=None, now=None, validation_after_host_fix=False,
        read_rows=pc.read_jsonl, freeze=None):
    """Returns the run state (stop/decision) or 'MAX_BATCHES' / 'DEADLINE'. Fakes plug in via make_cases / run_episode."""
    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    ledger = run_root / 'ledger.jsonl'
    hdr = pc.header(prereg_sha, mode=mode, noise=noise, batch_size=batch_size, episode=episode,
                    run_manifest_sha256=run_manifest_sha256, freeze=freeze)
    pc.repair_ledger(ledger)
    rows = pc.read_ledger(ledger)
    if not rows:
        pc.append(ledger, hdr)
    elif rows[0] != hdr:
        raise ValueError('ledger header mismatch: same prereg sha, mode, noise, batch size, episode command, '
                         'run manifest and freeze stage / core sha required')
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    started = 0
    while True:
        st = pc.replay(prereg, pc.read_ledger(ledger))
        k = st['open_batch']
        if k is None and mode == 'training' and not any(b['split'] == 'validation' for b in st['batches'].values()):
            limits = pc.pending_bin_limits(prereg, st)
            for row in limits:
                pc.append(ledger, row)
            if limits:
                st = pc.replay(prereg, pc.read_ledger(ledger))
        write(run_root / 'report.json', pc.report(prereg, st, prereg_sha=prereg_sha))
        if k is None:
            slots = pc.plan_batch(prereg, st, batch_size, validation_after_host_fix=validation_after_host_fix)
            if not slots:
                return pc.run_state(prereg, st)
            if started >= max_batches:
                return 'MAX_BATCHES'
            if deadline is not None and now() >= deadline:
                return 'DEADLINE'
            k = plan_new_batch(ledger, run_root, prereg, st, slots, make_cases)
            if k is None:
                continue        # every slot rejected by the generator: seeds consumed, plan again
            st = pc.replay(prereg, pc.read_ledger(ledger))
        bdir = run_root / 'batches' / f'b{k:03d}'
        signal, started = run_batch(ledger, bdir, k, st['batches'][k], st['batches'][k]['ingested'], mode=mode,
                                    noise=noise, make_cases=make_cases, run_episode=run_episode, read_rows=read_rows,
                                    started=started, max_batches=max_batches, deadline=deadline, now=now)
        if signal is not None:
            return signal


def run_batch(ledger, bdir, k, planned, done, *, mode, noise, make_cases, run_episode, read_rows, started,
              max_batches, deadline, now):
    """One step on planned batch k: ingest a finished try, close after MAX_TRIES, or run one try.

    Returns (signal, started): signal 'MAX_BATCHES' / 'DEADLINE' stops the caller, None means the
    caller re-reads the ledger (the batch is ingested, or a try ended without a final summary).
    Shared by the serial run and the shard runner (same retry / ingest rules).
    """
    bdir = Path(bdir)
    bdir.mkdir(parents=True, exist_ok=True)
    slots = planned['slots']
    cases = batch_cases(bdir, planned, slots, make_cases)
    tries = sorted(int(p.name.split('-')[1]) for p in bdir.glob('try-*') if p.is_dir())
    last = tries[-1] if tries else 0
    summary = final_summary(bdir / f'try-{last}') if last else None
    if summary is None:
        if last >= MAX_TRIES:
            # interrupted twice: remaining slots become host errors, batch closed as unclean
            ingest(ledger, k, last, slots, cases, dict(status='HOST_ERROR', HOST_ERROR=1,
                   error_type='interrupted_twice', worlds=[]), None, mode=mode, noise=noise, done_slots=done,
                   read_rows=read_rows)
            return None, started
        if started >= max_batches:
            return 'MAX_BATCHES', started
        if deadline is not None and now() >= deadline:
            return 'DEADLINE', started
        last += 1
        out = bdir / f'try-{last}'
        todo = [s['slot'] for s in slots if s['slot'] not in done]
        started += 1
        code = run_episode(bdir / 'cases.json', todo, out)
        write(bdir / f'exit-try-{last}.json', dict(exit=code, indices=todo))
        summary = final_summary(out)
        if summary is None:
            return None, started    # interrupted / crashed before the final summary: retried or closed above
    ingest(ledger, k, last, slots, cases, summary, exit_code(bdir, last), mode=mode, noise=noise,
           done_slots=done, read_rows=read_rows)
    return None, started


# ------------------------------------------------------------- sharded runs (v3s)

def shard_dir(run_root, i):
    return Path(run_root) / 'shards' / f's{i:02d}'


def read_shards(run_root, count):
    """Every shard ledger visible under run_root/shards (remote shards arrive by ledger sync)."""
    return {i: pc.read_ledger(shard_dir(run_root, i) / 'ledger.jsonl') for i in range(count)}


@contextlib.contextmanager
def shard_lock(sdir):
    """One process per shard index on this file system (a second one fails at once)."""
    sdir.mkdir(parents=True, exist_ok=True)
    with open(sdir / '.lock', 'w') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'{sdir}: shard already running') from None
        yield


def plan_view(prereg, ledgers, count, k, batch_size, validation_after_host_fix):
    """Unchanged planning rules on the shard view of batch k -> (st, slots, inflight) or None (wait)."""
    view = pc.shard_view(ledgers, count, k)
    if view is None:
        return None
    rows, inflight = view
    st = pc.replay(prereg, rows)
    slots = pc.plan_batch(prereg, st, batch_size, validation_after_host_fix=validation_after_host_fix,
                          reserved=pc.inflight_train_slots(rows, inflight))
    return st, slots, inflight


def run_shard(run_root, prereg, prereg_sha, *, shard, count, vm, mode, noise, batch_size, max_batches, make_cases,
              run_episode, episode=None, run_manifest_sha256=None, deadline=None, now=None,
              validation_after_host_fix=False, read_rows=pc.read_jsonl, freeze=None, wait=None):
    """Shard ``shard`` of ``count`` (prereg sharding rule): runs the batches k with k % count == shard.

    Own ledger run_root/shards/sII/ledger.jsonl (only this process writes it); other shard ledgers
    are read only.  ``wait()`` is called while the view of the next own batch is incomplete; it
    returns False to give up ('WAITING').  Returns the run state at run_end, 'STOP_HOST',
    'MAX_BATCHES', 'DEADLINE' or 'WAITING'.  Restart: rerun the same command.
    """
    run_root = Path(run_root)
    sdir = shard_dir(run_root, shard)
    ledger = sdir / 'ledger.jsonl'
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    wait = wait or (lambda: (time.sleep(30), True)[1])
    hdr = pc.header(prereg_sha, mode=mode, noise=noise, batch_size=batch_size, episode=episode,
                    run_manifest_sha256=run_manifest_sha256, freeze=freeze,
                    shard=dict(index=shard, count=count, vm=vm))
    with shard_lock(sdir):
        pc.repair_ledger(ledger)
        rows = pc.read_ledger(ledger)
        if not rows:
            pc.append(ledger, hdr)
        elif rows[0] != hdr:
            raise ValueError('shard ledger header mismatch: same prereg sha, mode, noise, batch size, episode command, '
                             'run manifest, freeze stage / core sha and shard index / count / vm required')
        started = 0
        while True:
            own = pc.shard_index(pc.read_ledger(ledger))
            open_k = sorted(j for j, r in own['complete'].items() if r['type'] == 'batch_planned' and j not in own['done'])
            if open_k:
                k = open_k[0]
                signal, started = run_batch(ledger, sdir / 'batches' / f'b{k:03d}', k, own['complete'][k],
                                            own['ingested'].get(k, set()), mode=mode, noise=noise,
                                            make_cases=make_cases, run_episode=run_episode, read_rows=read_rows,
                                            started=started, max_batches=max_batches, deadline=deadline, now=now)
                if signal is not None:
                    return signal
                continue
            k = max(own['complete'], default=shard - count) + count
            ledgers = read_shards(run_root, count)
            ended = [j for j, rs in ((j, pc.shard_index(r)) for j, r in ledgers.items()) if rs['ended'] is not None]
            if ended:
                end = min(pc.shard_index(ledgers[j])['ended'] for j in ended)
                if end < k:
                    return pc.shard_index(ledgers[pc.owner(end, count)])['complete'][end]['state']
            planned = plan_view(prereg, ledgers, count, k, batch_size, validation_after_host_fix)
            if planned is None:
                blocker = blocked_state(prereg, ledgers, count, k, batch_size, validation_after_host_fix)
                if blocker is not None:
                    return blocker
                if deadline is not None and now() >= deadline:
                    return 'DEADLINE'
                if not wait():
                    return 'WAITING'
                continue
            if started >= max_batches:
                return 'MAX_BATCHES'
            if deadline is not None and now() >= deadline:
                return 'DEADLINE'
            st, slots, inflight = planned
            extra = pc.boundary_rows(prereg, st, k)
            for row in extra:
                pc.append(ledger, row)
            if extra:
                continue            # replan on the view with the bin limits
            control = pc.stop_control(prereg, st, k, inflight)
            if control is not None:
                pc.append(ledger, control)
                continue            # train_barrier hold / release or train_closed, then replan on the same view
            if st.get('barrier') is not None:
                # stop barrier held: no new batch until every in-flight batch is done (no seed consumed)
                pc.append(ledger, dict(type='batch_skipped', batch=k, inflight=inflight, reason='stop_barrier'))
                continue
            if not slots:
                state = pc.run_state(prereg, st)
                if inflight:
                    pc.append(ledger, dict(type='batch_skipped', batch=k, inflight=inflight))
                elif state == 'STOP_HOST':
                    return 'STOP_HOST'        # nothing written: rerun with --validation-after-host-fix
                else:
                    pc.append(ledger, dict(type='run_end', batch=k, state=state))
                continue
            plan_shard_batch(ledger, k, shard, vm, slots, make_cases)


def blocked_state(prereg, ledgers, count, k, batch_size, validation_after_host_fix):
    """While waiting: 'STOP_HOST' if the first unplanned batch would stop there (nobody plans past it)."""
    idx = {i: pc.shard_index(r) for i, r in ledgers.items()}
    first = next((j for j in range(k) if j not in idx[pc.owner(j, count)]['complete']), None)
    if first is None:
        return None
    planned = plan_view(prereg, ledgers, count, first, batch_size, validation_after_host_fix)
    if planned is None:
        return None
    st, slots, inflight = planned
    if not slots and not inflight and not pc.boundary_rows(prereg, st, first) and \
            pc.stop_control(prereg, st, first, inflight) is None and st.get('barrier') is None and \
            pc.run_state(prereg, st) == 'STOP_HOST':
        return 'STOP_HOST'
    return None


def plan_shard_batch(ledger, k, shard, vm, slots, make_cases):
    """plan_new_batch for a fixed batch index k: generator rejections, then batch_planned (or replan)."""
    built = make_cases(slots)
    keep = []
    for s, c in zip(slots, built):
        if 'setup_rejected' in c:
            pc.append(ledger, setup_rejected_row(k, s, c['setup_rejected']))
        else:
            keep.append((s, c))
    if not keep:
        return None                 # every slot rejected: seeds consumed, the same k is planned again
    slots = [dict(s, slot=i) for i, (s, _) in enumerate(keep)]
    cases = [c for _, c in keep]
    pc.append(ledger, dict(type='batch_planned', batch=k, slots=slots, split=slots[0]['split'],
                           cases_sha256=hashlib.sha256(dumps(cases)).hexdigest(), shard=shard, vm=vm))
    return k


def merge(run_root, prereg, prereg_sha, count, *, prereg_core=None, out=None):
    """Shard ledgers -> run_root/merged/{ledger.jsonl, report.json, merge.json} (derived, rewritten).

    The merged ledger is the serial-order view (pc.shard_view k=None); batch_planned rows carry the
    absolute batch_dir so probe-cases / convert-input read the shard batch directories.
    """
    run_root = Path(run_root)
    out = Path(out or run_root / 'merged')
    paths = {f's{i:02d}': shard_dir(run_root, i) / 'ledger.jsonl' for i in range(count)}
    sealed = {n: pc.committed_bytes(q) for n, q in paths.items()}      # v5: view and seal from the same bytes
    ledgers = {i: pc.parse_ledger(sealed[f's{i:02d}']) for i in range(count)}
    view = pc.shard_view(ledgers, count)
    if view is None:
        raise ValueError(f'{run_root}: no shard ledger')
    rows, info = view
    previous = out / 'merge.json'
    if previous.exists():
        # v4 (xreview R7): every shard ledger must extend the bytes the previous merge saw (append-only;
        # a wrong-direction rsync that shortens or rewrites a ledger is refused).  v5: the seal is the committed
        # prefix (pc.committed_bytes), the same bytes the merge read -- an uncommitted tail is never sealed.
        old = json.loads(previous.read_text())
        for name, size in (old.get('shard_ledger_bytes') or {}).items():
            path = shard_dir(run_root, int(name[1:])) / 'ledger.jsonl'
            data = sealed.get(name, b'')
            if size and (len(data) < size or hashlib.sha256(data[:size]).hexdigest() != old['shard_ledger_sha256'][name]):
                raise ValueError(f'{path}: not an append-only extension of the ledger recorded by the previous merge')
    seen = {}
    for j, bs in pc.running_seeds(ledgers, count).items():
        if len(bs) > 1:
            raise ValueError(f'seed {j} planned in two running batches {bs}')
    pc.check_seed_history(rows)
    for r in rows:
        if r.get('type') == 'batch_planned':
            r['batch_dir'] = str((shard_dir(run_root, pc.owner(r['batch'], count)) / 'batches' / f"b{r['batch']:03d}").resolve())
            for s in r['slots']:
                key = (r['batch'], s['split'], s['seed'])
                if key in seen:
                    raise ValueError(f'duplicate slot {key}')
                seen[key] = True
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / 'ledger.jsonl.tmp'
    tmp.write_text(''.join(json.dumps(r, sort_keys=True, allow_nan=False) + '\n' for r in rows))
    tmp.replace(out / 'ledger.jsonl')
    st = pc.replay(prereg, rows)
    rep = pc.report(prereg, st, prereg_sha=prereg_sha, prereg_core=prereg_core)
    rep['sharding'] = dict(count=count, **info)
    write(out / 'report.json', rep)
    shards = {n: (hashlib.sha256(b).hexdigest() if paths[n].exists() else None) for n, b in sealed.items()}
    sizes = {n: len(b) for n, b in sealed.items()}
    meta = dict(count=count, ledger_seal='committed_prefix_v1', shard_ledger_sha256=shards, shard_ledger_bytes=sizes,
                merged_ledger_sha256=pc.file_sha256(out / 'ledger.jsonl'), **info)
    write(out / 'merge.json', meta)
    return rep, meta


def merged_meta(run_root, *, require_finished):
    """v4 (Codex H2/H3): a sharded run is read only through its merged root; convert-input needs it finished.

    Returns merge.json of a merged root (None for a serial run root).  Refuses a sharded run root itself,
    a merged ledger that differs from the one merge.json recorded and, with ``require_finished``, an
    unfinished merge (run_end missing or batches still running).
    """
    run_root = Path(run_root)
    if (run_root / 'shards').is_dir():
        raise ValueError(f'{run_root} is a sharded run root: run merge and use --run-root {run_root / "merged"}')
    path = run_root / 'merge.json'
    if not path.exists():
        return None
    meta = json.loads(path.read_text())
    if pc.file_sha256(run_root / 'ledger.jsonl') != meta.get('merged_ledger_sha256'):
        raise ValueError(f'{run_root}/ledger.jsonl differs from merge.json: rerun merge')
    if require_finished and (not meta.get('finished') or meta.get('running')):
        raise ValueError(f'{run_root}: merge not finished (finished={meta.get("finished")}, running={meta.get("running")}); '
                         'every shard must reach run_end with every planned batch done')
    return meta


def tree_dirty():
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True)
    return bool(dirty.strip())


def frozen_gate(a, prereg, sha, *, stage, episode=None, recording_dir=None, need_clean=True, shard=None):
    """Stage 'core' / 'final' manifest gate (B1/B2/B3) -> (core_sha256, manifest_sha256)."""
    if a.run_manifest is None:
        raise SystemExit(f'{a.command}: --run-manifest required at {stage} stage')
    if need_clean and tree_dirty():
        raise SystemExit('frozen stages need a clean collector checkout (tracked files)')
    raw = a.run_manifest.read_bytes()
    core = pc.check_run_manifest(json.loads(raw), stage=stage, prereg=prereg, batch_size=a.batch_size,
                                 episode=episode, repo=ROOT, recording_dir=recording_dir,
                                 verify_assets=not a.no_verify_assets, shard=shard)
    return core, hashlib.sha256(raw).hexdigest()


def collect_env(mode, prereg_path, prereg_sha, recording_check=None, probe=False, prereg_core=None):
    """Env read by the teacher candidate pairact_p3_collect; measurement mode clears it.

    v3 interface (teacher -c3 harness/grasp_act_admission.py): PAIRACT_P3_COLLECT_PREREG_CORE_SHA256
    is the prereg content sha256 (status excluded); the probe accepts FROZEN_CORE or FROZEN, data
    recording needs FROZEN and the file sha256.
    """
    env = {k: v for k, v in os.environ.items() if k not in pc.COLLECT_ENV}
    if mode == 'training':
        if recording_check is None and not probe:
            raise ValueError('training mode needs --recording-check (paired 640x480 recording-mode check)')
        env.update(PAIRACT_P3_COLLECT_PREREG=str(Path(prereg_path).resolve()),
                   PAIRACT_P3_COLLECT_PREREG_SHA256=prereg_sha, PAIRACT_P3_RECORDING_PROBE='1' if probe else '0')
        if prereg_core is not None:
            env['PAIRACT_P3_COLLECT_PREREG_CORE_SHA256'] = prereg_core
        if recording_check is not None:
            env['PAIRACT_P3_RECORDING_CHECK'] = str(Path(recording_check).resolve())
    return env


def shell_episode(template, env=None):
    def go(cases, indices, out):
        cmd = template.format(cases=shlex.quote(str(cases)), indices=','.join(map(str, indices)),
                              out=shlex.quote(str(out)))
        return subprocess.call(cmd, shell=True, env=env)
    return go


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('command', choices=('collect', 'report', 'convert-input', 'probe-cases', 'probe-episode',
                                       'check-rows', 'merge'))
    p.add_argument('--prereg', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--mode', choices=pc.MODES, default='measurement')
    p.add_argument('--noise', choices=pc.NOISE_MODES, default='off')
    p.add_argument('--batch-size', type=int, default=20)
    p.add_argument('--max-batches', type=int, default=1)
    p.add_argument('--deadline-utc', help='do not start a new batch at or after this ISO time (e.g. 2026-10-22T00:00Z)')
    p.add_argument('--episode-cmd', help='shell template with {cases} {indices} {out}; needs --rejection-table ABS and --cap-s')
    p.add_argument('--run-manifest', type=Path,
                   help='RUN_MANIFEST.json: FROZEN_CORE for the probe source / probe-cases / probe / check-rows, '
                        'FROZEN for training and convert-input')
    p.add_argument('--no-verify-assets', action='store_true',
                   help='skip re-hashing the episode assets (only off the collection VM; never for training)')
    p.add_argument('--validation-after-host-fix', action='store_true',
                   help='after STOP_HOST: run validation once DeepSeek has reported the host fix')
    p.add_argument('--dependency-root', type=Path)
    p.add_argument('--frozen-root', type=Path)
    p.add_argument('--adapter-root', type=Path, help='pinned adapter checkout (runtime placement filter family)')
    p.add_argument('--candidate', help='default: pairact_p2_r13 (measurement) / pairact_p3_collect (training)')
    p.add_argument('--recording-check', type=Path,
                   help='training: RUNC/recording-check.json (probe-cases.json and check-rows.json beside it)')
    p.add_argument('--baseline-raws', nargs='*', default=[], help='check-rows: recording-off world raw dirs')
    p.add_argument('--probe-raws', nargs='*', default=[], help='check-rows: recording-probe world raw dirs')
    p.add_argument('--shard', help='i/K: run shard i of K (prereg sharding; batch k belongs to shard k %% K)')
    p.add_argument('--vm', help='sharded runs: VM name of this process (RUN_MANIFEST sharding.assignment key)')
    p.add_argument('--shards', type=int, help='merge: shard count K')
    p.add_argument('--poll-s', type=float, default=30., help='sharded runs: seconds between view checks while waiting')
    p.add_argument('--max-wait-s', type=float, help='sharded runs: give up (WAITING) after this many seconds of waiting')
    p.add_argument('--teacher-sha')
    p.add_argument('--out', type=Path)
    a = p.parse_args()
    # report/probe/check read any status; convert-input and training collection need FROZEN
    load_mode = 'training' if a.command == 'convert-input' or (a.command == 'collect' and a.mode == 'training') \
        else 'measurement'
    prereg, sha = pc.load_prereg(a.prereg, mode=load_mode)
    prereg_core = pc.prereg_core_sha256(prereg)
    stage = prereg['status']
    if a.command in ('report', 'convert-input', 'probe-cases'):
        merged_meta(a.run_root, require_finished=False)     # v4: a sharded run root is read through merged/ only
        st = pc.replay(prereg, pc.read_ledger(a.run_root / 'ledger.jsonl'))
        pc.require_header_sha(st, sha, prereg_core)     # audit 2: never relabel a ledger under another prereg
    if a.command == 'merge':
        if not a.shards:
            p.error('merge needs --shards K')
        rep, meta = merge(a.run_root, prereg, sha, a.shards, prereg_core=prereg_core)
        print(json.dumps(dict(state=rep['run_state'], finished=meta['finished'], running=meta['running'],
                              merged=str(a.run_root / 'merged'), text=(rep.get('A') or rep.get('pilot'))['text']),
                         ensure_ascii=False))
        return
    if a.command == 'report':
        rep = pc.report(prereg, st, prereg_sha=sha, prereg_core=prereg_core)
        meta = merged_meta(a.run_root, require_finished=False)
        if meta is not None:
            rep['sharding'] = {k: v for k, v in meta.items() if k != 'shard_ledger_bytes'}
        write(a.run_root / 'report.json', rep)
        print(json.dumps(dict(state=rep['run_state'], text=(rep.get('A') or rep.get('pilot'))['text']), ensure_ascii=False))
        return
    if a.command == 'convert-input':
        if not a.teacher_sha or not a.out:
            p.error('--teacher-sha and --out required')
        if a.recording_check is None:
            p.error('convert-input needs --recording-check RUNC/recording-check.json (stage final gate)')
        core, _ = frozen_gate(a, prereg, sha, stage='final', recording_dir=a.recording_check.parent, need_clean=False)
        merged_meta(a.run_root, require_finished=True)
        print(json.dumps(pc.convert_input(prereg, st, a.out, prereg_sha=sha, teacher_sha=a.teacher_sha, core=core)))
        return
    if stage not in pc.FREEZE_STAGES and a.command in ('probe-cases', 'probe-episode', 'check-rows'):
        p.error(f'{a.command} needs a FROZEN_CORE (or FROZEN) prereg, got {stage}')
    if a.command == 'probe-cases':
        # starts for the recording probe: first 3 admitted successes of the FROZEN_CORE probe source run
        if not a.out:
            p.error('--out required')
        if a.out.exists():
            p.error('refusing to overwrite')
        core, _ = frozen_gate(a, prereg, sha, stage='core')
        pc.require_probe_source(st, core)
        cases = []
        for r in pc.probe_slots(st):
            bdir = st['batches'][r['batch']].get('batch_dir') or a.run_root / 'batches' / f"b{r['batch']:03d}"
            batch = json.loads((Path(bdir) / 'cases.json').read_text())
            case = batch[r['slot']]
            if case['plan']['seed'] != r['seed']:
                raise ValueError('ledger/cases mismatch')
            cases.append(dict(case, candidate=pc.CANDIDATE_BY_MODE['training']))
        write(a.out, cases)
        print(json.dumps(dict(out=str(a.out), core_sha256=core, seeds=[c['plan']['seed'] for c in cases],
                              baseline_raws=[r['raw'] for r in pc.probe_slots(st)])))
        return
    if a.command == 'probe-episode':
        # recording probe on probe-cases.json (data_admitted false, no check needed): FROZEN_CORE env
        if not a.out or a.out.exists():
            p.error('--out (new directory) required')
        try:
            episode = pc.episode_cmd_audit(a.episode_cmd)
        except ValueError as error:
            p.error(str(error))
        core, _ = frozen_gate(a, prereg, sha, stage='core', episode=episode)
        cases_path = a.run_root / 'probe-cases.json'
        n = len(json.loads(cases_path.read_text()))
        env = collect_env('training', a.prereg, sha, probe=True, prereg_core=prereg_core)
        code = shell_episode(a.episode_cmd, env)(cases_path, list(range(n)), a.out)
        print(json.dumps(dict(out=str(a.out), exit=code, core_sha256=core)))
        sys.exit(code)
    if a.command == 'check-rows':
        # inputs for the teacher's unchanged recording_mode_equivalence(baseline rows, probe rows)
        if not a.out or not a.baseline_raws or len(a.baseline_raws) != len(a.probe_raws):
            p.error('--out and equal-length --baseline-raws/--probe-raws required')
        core, _ = frozen_gate(a, prereg, sha, stage='core')
        rows = dict(core_sha256=core)
        for name, raws in (('baseline', a.baseline_raws), ('recorded', a.probe_raws)):
            rows[name] = []
            for raw in raws:
                res = raw_result(raw)
                seed = json.loads((Path(raw) / 'plan.json').read_text())['seed'] if (Path(raw) / 'plan.json').exists() \
                    else res.get('seed')
                rows[name].append(pc.check_row(res, seed, search15_keys=[k for k in res if k.startswith(('search', 'peer_reobserve', 'obstacle_reobserve', 'pregrasp_sampling'))]))
        write(a.out, rows)
        print(json.dumps(dict(out=str(a.out), baseline=[r['index'] for r in rows['baseline']],
                              recorded=[r['index'] for r in rows['recorded']])))
        return
    candidate = a.candidate or pc.CANDIDATE_BY_MODE[a.mode]
    if candidate != pc.CANDIDATE_BY_MODE[a.mode]:
        p.error(f'{a.mode} mode uses candidate {pc.CANDIDATE_BY_MODE[a.mode]}')
    try:
        episode = pc.episode_cmd_audit(a.episode_cmd)
    except ValueError as error:
        p.error(str(error))
    manifest_sha, freeze = None, None
    shard = pc.parse_shard(a.shard) if a.shard else None
    if shard is not None and not a.vm:
        p.error('--shard needs --vm (RUN_MANIFEST sharding.assignment key)')
    if shard is not None and shard[1] > pc.MAX_SHARDS:
        p.error(f'--shard K must be <= {pc.MAX_SHARDS} (prereg sharding.K_max, owner decision D-v4-1)')
    if a.mode == 'training':
        if a.recording_check is None or a.recording_check.name != pc.RECORDING_FILES['recording_check_sha256']:
            p.error('training needs --recording-check RUNC/recording-check.json')
        if a.no_verify_assets:
            p.error('training never skips the asset re-hash')
        core, manifest_sha = frozen_gate(a, prereg, sha, stage='final', episode=episode,
                                         recording_dir=a.recording_check.parent,
                                         shard=(shard[0], shard[1], a.vm) if shard else (0, 1, None))
        freeze = dict(stage='FROZEN', purpose=pc.PURPOSE_TRAINING, prereg_core_sha256=prereg_core, core_sha256=core)
    elif stage in pc.FREEZE_STAGES:
        core, manifest_sha = frozen_gate(a, prereg, sha, stage='core', episode=episode)
        freeze = dict(stage=stage, purpose=pc.PURPOSE_PROBE_SOURCE, prereg_core_sha256=prereg_core, core_sha256=core)
    else:
        # pre-freeze pilot: yield only, never a probe source or training input (B2)
        if a.run_manifest is not None:
            raw = a.run_manifest.read_bytes()
            if json.loads(raw).get('schema') != pc.MANIFEST_SCHEMA:
                p.error(f'run manifest schema {pc.MANIFEST_SCHEMA} required')
            manifest_sha = hashlib.sha256(raw).hexdigest()
        freeze = dict(stage=stage, purpose=pc.PURPOSE_PILOT, prereg_core_sha256=prereg_core, core_sha256=None)
    if stage in pc.FREEZE_STAGES:
        # v4 (Codex H4): generator and episodes use the RUN_MANIFEST -c pins, not just any consistent stack
        pc.check_stack_heads(json.loads(a.run_manifest.read_bytes()),
                             dict(teacher=a.dependency_root, adapter=a.adapter_root, root=a.frozen_root))
    env = collect_env(a.mode, a.prereg, sha, a.recording_check, prereg_core=prereg_core)
    sys.path.insert(0, str(ROOT / 'experiments/2026-10-21-pairact-r1'))
    import collect_cases
    geo = collect_cases.Geometry(a.dependency_root, a.frozen_root, setup_validity=True, adapter_root=a.adapter_root)
    deadline = dt.datetime.fromisoformat(a.deadline_utc.replace('Z', '+00:00')) if a.deadline_utc else None
    common = dict(mode=a.mode, noise=a.noise, batch_size=a.batch_size, max_batches=a.max_batches, deadline=deadline,
                  episode=episode, run_manifest_sha256=manifest_sha, validation_after_host_fix=a.validation_after_host_fix,
                  freeze=freeze, run_episode=shell_episode(a.episode_cmd, env),
                  make_cases=lambda slots: collect_cases.make_cases(geo, prereg, slots, candidate=candidate,
                                                                    prereg_path=a.prereg))
    if shard is not None:
        waited = [0.]

        def wait():
            if a.max_wait_s is not None and waited[0] >= a.max_wait_s:
                return False
            time.sleep(a.poll_s)
            waited[0] += a.poll_s
            return True
        state = run_shard(a.run_root, prereg, sha, shard=shard[0], count=shard[1], vm=a.vm, wait=wait, **common)
        print(json.dumps(dict(state=state, shard=a.shard, vm=a.vm,
                              merge=f'run_pairact_collect.py merge --run-root {a.run_root} --shards {shard[1]}')))
        return
    state = run(a.run_root, prereg, sha, **common)
    rep = json.loads((a.run_root / 'report.json').read_text())
    print(json.dumps(dict(state=state, text=(rep.get('A') or rep.get('pilot'))['text']), ensure_ascii=False))


if __name__ == '__main__':
    main()
