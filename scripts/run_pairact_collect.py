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
    python scripts/run_pairact_collect.py convert-input --prereg P --run-root R --teacher-sha SHA --out DIR

Batch status, required fields and the sidecar check follow COLLECT_PREREG v2 status_table / filter:
an unclean batch (HOST_ERROR, exit != 0 or unknown) admits nothing; a missing field is a record
error (STOP_RECORD), never a default.  Generator budget exhaustion is a setup_rejected ledger row.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
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
    if j['category'] == 'behavior' and j['failure_stage'] != 'grasp' and \
            w.get('carry_success') != (result.get('carry_eval') or {}).get('success'):
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
        bdir.mkdir(parents=True, exist_ok=True)
        slots = st['batches'][k]['slots']
        cases = batch_cases(bdir, st['batches'][k], slots, make_cases)
        done = st['batches'][k]['ingested']
        tries = sorted(int(p.name.split('-')[1]) for p in bdir.glob('try-*') if p.is_dir())
        last = tries[-1] if tries else 0
        summary = final_summary(bdir / f'try-{last}') if last else None
        if summary is None:
            if last >= MAX_TRIES:
                # interrupted twice: remaining slots become host errors, batch closed as unclean
                ingest(ledger, k, last, slots, cases, dict(status='HOST_ERROR', HOST_ERROR=1,
                       error_type='interrupted_twice', worlds=[]), None, mode=mode, noise=noise, done_slots=done,
                       read_rows=read_rows)
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
        ingest(ledger, k, last, slots, cases, summary, exit_code(bdir, last), mode=mode, noise=noise,
               done_slots=done, read_rows=read_rows)


def tree_dirty():
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT, text=True)
    return bool(dirty.strip())


def frozen_gate(a, prereg, sha, *, stage, episode=None, recording_dir=None, need_clean=True):
    """Stage 'core' / 'final' manifest gate (B1/B2/B3) -> (core_sha256, manifest_sha256)."""
    if a.run_manifest is None:
        raise SystemExit(f'{a.command}: --run-manifest required at {stage} stage')
    if need_clean and tree_dirty():
        raise SystemExit('frozen stages need a clean collector checkout (tracked files)')
    raw = a.run_manifest.read_bytes()
    core = pc.check_run_manifest(json.loads(raw), stage=stage, prereg=prereg, batch_size=a.batch_size,
                                 episode=episode, repo=ROOT, recording_dir=recording_dir,
                                 verify_assets=not a.no_verify_assets)
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
                                       'check-rows'))
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
        st = pc.replay(prereg, pc.read_ledger(a.run_root / 'ledger.jsonl'))
        pc.require_header_sha(st, sha, prereg_core)     # audit 2: never relabel a ledger under another prereg
    if a.command == 'report':
        rep = pc.report(prereg, st, prereg_sha=sha, prereg_core=prereg_core)
        write(a.run_root / 'report.json', rep)
        print(json.dumps(dict(state=rep['run_state'], text=(rep.get('A') or rep.get('pilot'))['text']), ensure_ascii=False))
        return
    if a.command == 'convert-input':
        if not a.teacher_sha or not a.out:
            p.error('--teacher-sha and --out required')
        core, _ = frozen_gate(a, prereg, sha, stage='final', need_clean=False)
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
            batch = json.loads((a.run_root / 'batches' / f"b{r['batch']:03d}" / 'cases.json').read_text())
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
    if a.mode == 'training':
        if a.recording_check is None or a.recording_check.name != pc.RECORDING_FILES['recording_check_sha256']:
            p.error('training needs --recording-check RUNC/recording-check.json')
        if a.no_verify_assets:
            p.error('training never skips the asset re-hash')
        core, manifest_sha = frozen_gate(a, prereg, sha, stage='final', episode=episode,
                                         recording_dir=a.recording_check.parent)
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
    env = collect_env(a.mode, a.prereg, sha, a.recording_check, prereg_core=prereg_core)
    sys.path.insert(0, str(ROOT / 'experiments/2026-10-21-pairact-r1'))
    import collect_cases
    geo = collect_cases.Geometry(a.dependency_root, a.frozen_root, setup_validity=True, adapter_root=a.adapter_root)
    deadline = dt.datetime.fromisoformat(a.deadline_utc.replace('Z', '+00:00')) if a.deadline_utc else None
    state = run(a.run_root, prereg, sha, mode=a.mode, noise=a.noise, batch_size=a.batch_size,
                max_batches=a.max_batches, deadline=deadline, episode=episode, run_manifest_sha256=manifest_sha,
                validation_after_host_fix=a.validation_after_host_fix, freeze=freeze,
                make_cases=lambda slots: collect_cases.make_cases(geo, prereg, slots, candidate=candidate,
                                                                  prereg_path=a.prereg),
                run_episode=shell_episode(a.episode_cmd, env))
    rep = json.loads((a.run_root / 'report.json').read_text())
    print(json.dumps(dict(state=state, text=(rep.get('A') or rep.get('pilot'))['text']), ensure_ascii=False))


if __name__ == '__main__':
    main()
