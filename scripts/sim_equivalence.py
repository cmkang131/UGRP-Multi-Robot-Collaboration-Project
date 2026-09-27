"""Compare two M1 run directories (or sim_profile directories) for exact equivalence (dev tool).

Checks, in order: trajectory checkpoints (qpos/qvel/act SHA-256 every N mj_step,
from ``scripts/sim_profile.py``), issued commands, control-input frame rows and
the saved JPEG bytes, original command/event/evaluation log bytes and
``result.json`` bytes. Full comparison validates the complete M1 v3 log
inventory, counts, sampling coverage and grasp-through-final-look phases.
Sampling coverage starts at ``manifest.recording_start_sim_s`` or a logged
``recording_started`` event, not at simulation zero (scene setup advances SIM
time). Legacy runs use agreeing first frame/GT timestamps, with that limitation
reported explicitly. Invalid, conflicting or unequal A/B starts fail closed.
``--until-sim-s T`` compares only rows before SIM time T
(a truncated run against a full one; result.json is then skipped because the
truncated run ends with SIM_LIMIT). manifest.json differences are listed but not
judged: code SHA, wall time, load and the recorded speedup set are expected to
differ.

Missing evidence is a failure, never a pass (Codex review of PR #209): both
sides must be directories with all nine LOGS and result/manifest for full
comparison (commands/frames for a prefix), every row must parse as a JSON
object, both sides must reach the
compared window (last control frame at or after T), and the compared command,
frame, JPEG and (when both sides are sim_profile directories) checkpoint counts
must be nonzero. Exit code 0 = equivalent, 1 = different, 2 = insufficient evidence.

    python3 scripts/sim_equivalence.py A_DIR B_DIR [--until-sim-s 120] [--json out.json]

``A_DIR``/``B_DIR`` may be a run directory (with result.json) or a sim_profile
output directory (with run/ and qpos_checkpoints.jsonl).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

LOGS = ('inputs/commands.jsonl', 'inputs/frames.jsonl', 'controller_events.jsonl', 'skill_events.jsonl',
        'macros.jsonl', 'eval_only/frames_eval.jsonl', 'eval_only/gt_trajectory.jsonl', 'eval_only/contacts.jsonl',
        'eval_only/retention.jsonl')
REQUIRED_LOGS = ('inputs/commands.jsonl', 'inputs/frames.jsonl')
REQUIRED_FULL = ('result.json', 'manifest.json')
M1_SCHEMA = 'ugrp.m1_owncam_run.v3'
FULL_PHASES = ('grasp', 'to_carry_posture', 'nav_preplace', 'release', 'look_back')
CHECKPOINTS = 'qpos_checkpoints.jsonl'
# Recording-start presence can differ for legacy runs; its value is checked separately.
MANIFEST_EXPECTED = ('code', 'wall_s', 'load_average', 'speedups', 'env', 'files', 'recording_start_sim_s')
EXIT_EQUIVALENT, EXIT_DIFFERENT, EXIT_INSUFFICIENT = 0, 1, 2


class Evidence:
    """Collects evidence gaps; any gap makes the verdict ``insufficient_evidence``."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.raw: dict[Path, bytes | None] = {}

    def data(self, side: str, path: Path, *, required=True) -> bytes | None:
        if path not in self.raw:
            try:
                self.raw[path] = path.read_bytes()
            except OSError:
                self.raw[path] = None
        if self.raw[path] is None and required:
            self.errors.append(f'{side}: missing or unreadable {path}')
        return self.raw[path]

    def rows(self, side: str, path: Path, *, required: bool) -> list[dict]:
        raw = self.data(side, path, required=required)
        if raw is None:
            return []
        out = []
        for number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError):
                self.errors.append(f'{side}: {path} line {number} is not JSON')
                continue
            if not isinstance(row, dict):
                self.errors.append(f'{side}: {path} line {number} is not a JSON object')
                continue
            out.append(row)
        return out

    def document(self, side: str, path: Path) -> dict:
        raw = self.data(side, path)
        if raw is None:
            return {}
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            self.errors.append(f'{side}: {path} is not JSON')
            return {}
        if not isinstance(value, dict):
            self.errors.append(f'{side}: {path} is not a JSON object')
            return {}
        return value


def split_dirs(path: Path) -> tuple[Path, Path | None]:
    """(run_dir, profile_dir or None)."""
    if (path/'run').is_dir() or (path/CHECKPOINTS).exists() or (path/'profile.json').exists():
        return path/'run', path
    return path, (path.parent if (path.parent/CHECKPOINTS).exists() else None)


def validate_checkpoints(side: str, profile: Path, run: Path, rows: list[dict],
                         until: float | None, ev: Evidence) -> None:
    """Validate coverage independently on each side, even when both files match.

    These are sampled states, not an every-step trajectory digest. Final metadata
    binds the tail to the recorder's step count and the runner's rounded SIM time.
    Old profiles without this evidence cannot certify a full state comparison.
    """
    def fail(message):
        ev.errors.append(f'{side}: qpos checkpoints: {message}')

    def positive_integer(value):
        return type(value) is int and value > 0

    def finite(value):
        return type(value) in (int, float) and math.isfinite(value)

    def valid_row(row):
        return (isinstance(row, dict) and positive_integer(row.get('step'))
                and finite(row.get('t')) and row['t'] >= 0
                and isinstance(row.get('sha256'), str)
                and re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None)

    meta = ev.document(side, profile/'profile.json')
    every, total = meta.get('qpos_every'), meta.get('mj_steps')
    start, dt, final = meta.get('initial_sim_s'), meta.get('timestep'), meta.get('final_checkpoint')
    last_step = meta.get('last_step_checkpoint')
    if not rows or not all(valid_row(row) for row in rows):
        fail('empty or invalid step/t/sha256 schema')
        return
    if (not positive_integer(every) or not positive_integer(total)
            or not finite(start) or start < 0 or not finite(dt) or dt <= 0
            or not valid_row(final) or not valid_row(last_step) or meta.get('checkpoint_error')):
        fail('missing/invalid interval, total steps, initial time, timestep or final state')
        return
    expected_count = total // every + bool(total % every)
    if len(rows) != expected_count or any(r['step'] != min(i * every, total)
                                           for i, r in enumerate(rows, 1)):
        fail('step interval/order/total coverage mismatch')
    if type(meta.get('checkpoints')) is not int or meta['checkpoints'] != len(rows):
        fail('checkpoint count mismatch')
    # MuJoCo accumulates timestep with floating point error over millions of steps.
    if any(not math.isclose(r['t'], start + r['step'] * dt, rel_tol=1e-8, abs_tol=1e-8)
           for r in rows) or any(b['t'] <= a['t'] for a, b in zip(rows, rows[1:])):
        fail('SIM time order/timestep mismatch')
    if final != rows[-1] or last_step != rows[-1] or final['step'] != total:
        fail('final state does not match checkpoint tail/total steps')
    if until is not None:
        if rows[-1]['t'] < until:
            fail(f'end at {rows[-1]["t"]} s, before the compared window {until} s')
    else:
        result = ev.document(side, run/'result.json')
        sim_s = result.get('sim_s')
        # run_m1_owncam records result.sim_s rounded to two decimal places.
        if not finite(sim_s) or abs(sim_s - final['t']) > .00500001:
            fail('final SIM time disagrees with result.sim_s')


def row_time(row: dict):
    for key in ('t', 'sim_t'):
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            return float(value)
    return None


def cut(items: list[dict], until: float | None) -> list[dict]:
    """The log prefix written before SIM time ``until``: rows up to the first one stamped at or after it.

    A prefix, not a filter: rows are in emission order and a truncated run's log is a prefix of the full
    run's. Some rows carry a time that is not their emission time (``M1OwnCamDelivery`` logs
    ``approach_point`` with ``t=0.0`` long after start); a filter would pull such a row into any window.
    Rows without a time do not end the prefix (callers reject untimed required logs when cutting).
    """
    if until is None:
        return items
    for index, row in enumerate(items):
        t = row_time(row)
        if t is not None and t >= until:
            return items[:index]
    return items


def check_until(until) -> float | None:
    if until is None:
        return None
    if isinstance(until, bool) or not isinstance(until, (int, float)) or not math.isfinite(until) or until <= 0:
        raise ValueError(f'until must be a finite SIM time > 0 or None, got {until!r}')
    return float(until)


def compare_lists(a: list, b: list) -> dict:
    n = min(len(a), len(b))
    first = next((i for i in range(n) if a[i] != b[i]), None)
    same = first is None and len(a) == len(b)
    out = {'identical': same, 'len_a': len(a), 'len_b': len(b)}
    if not same:
        out['first_diff_index'] = first if first is not None else n
        if first is not None:
            out['a'] = json.dumps(a[first], ensure_ascii=False)[:400]
            out['b'] = json.dumps(b[first], ensure_ascii=False)[:400]
    return out


def frame_digest(side: str, run: Path, row: dict, ev: Evidence) -> str | None:
    name, recorded = row.get('file'), row.get('sha256')
    if not isinstance(name, str) or not isinstance(recorded, str):
        ev.errors.append(f'{side}: frame row {row.get("frame")!r} lacks file/sha256')
        return None
    try:
        digest = hashlib.sha256((run/name).read_bytes()).hexdigest()
    except OSError:
        ev.errors.append(f'{side}: missing frame file {run/name}')
        return None
    return digest if digest == recorded else None       # a JPEG that disagrees with its own log row never matches


def compare_bytes(a: bytes | None, b: bytes | None) -> dict:
    ha = None if a is None else hashlib.sha256(a).hexdigest()
    hb = None if b is None else hashlib.sha256(b).hexdigest()
    return {'identical': ha is not None and ha == hb, 'sha256_a': ha, 'sha256_b': hb}


def log_bytes(raw: bytes | None, selected_rows: int, until: float | None) -> bytes | None:
    """Hash original bytes, including whitespace/newlines; never reserialize JSON."""
    if raw is None or until is None:
        return raw
    kept, n = [], 0
    for line in raw.splitlines(keepends=True):
        if line.strip():
            if n == selected_rows:
                break
            n += 1
        kept.append(line)
    return b''.join(kept)


def recording_start(side: str, logs: dict, manifest: dict, ev: Evidence) -> dict:
    """Resolve the sampling origin without mistaking setup/command time for it.

    Explicit evidence is authoritative: malformed/conflicting markers must not
    silently fall back. Old M1 v3 logs have no marker, so both independently
    sampled streams must agree on a finite first time. That fallback cannot
    establish what happened before the surviving first samples.
    """
    def fail(message):
        ev.errors.append(f'{side}: recording start: {message}')

    def valid(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    first = {name: row_time(logs[name][0]) if logs[name] else None
             for name in ('inputs/frames.jsonl', 'eval_only/gt_trajectory.jsonl')}
    explicit = {}
    field = 'recording_start_sim_s'
    if field in manifest:
        explicit['manifest.json:' + field] = manifest[field]
    markers = [row for row in logs['controller_events.jsonl'] if row.get('event') == 'recording_started']
    for index, row in enumerate(markers):
        explicit[f'controller_events.jsonl:recording_started[{index}]'] = row_time(row)
    evidence = {'sim_s': None, 'inferred': not explicit, 'sources': list(explicit) or list(first),
                'first_samples_sim_s': first}
    if explicit:
        values = list(explicit.values())
        if not all(valid(t) for t in values):
            fail('invalid explicit SIM timestamp; cannot fall back to first samples')
        elif len(markers) > 1 or any(t != values[0] for t in values[1:]):
            fail('conflicting/duplicate explicit markers')
        else:
            evidence['sim_s'] = float(values[0])
    else:
        evidence['limitation'] = ('Inferred from first frame/GT samples; coverage before the first samples '
                                  'cannot be established without an explicit recording-start marker.')
        values = list(first.values())
        if not all(valid(t) for t in values):
            fail('unknown: missing/invalid first frame or GT SIM timestamp')
        elif values[0] != values[1]:
            fail('first frame and GT SIM timestamps disagree; cannot infer a common origin')
        else:
            evidence['sim_s'] = values[0]
    return evidence


def validate_full_run(side: str, run: Path, logs: dict, result: dict, manifest: dict, ev: Evidence,
                      recording_start_sim_s: float | None) -> None:
    """The fixed M1 v3 evidence contract, independent of A/B equality.

    Hashes bind irregular/untimed event logs to the completed runner's manifest.
    Counts, index continuity, sampling cadence and phase coverage independently
    reject equally truncated files even if their manifest hashes were rewritten.
    This is evidence validation, not a claim of physical task success.
    """
    def fail(message):
        ev.errors.append(f'{side}: full M1 evidence: {message}')

    def number(value, positive=False):
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)

    if result.get('schema') != M1_SCHEMA or manifest.get('schema') != M1_SCHEMA:
        fail('unsupported/missing result or manifest schema')
    end, dt, period = result.get('sim_s'), manifest.get('timestep_s'), manifest.get('frame_period_s')
    if not number(end, True) or not number(dt, True) or period != .2 or manifest.get('tick_s') != .1:
        fail('missing/invalid final time, timestep or M1 capture/control cadence')
        return
    files = manifest.get('files')
    for name in LOGS:
        raw = ev.data(side, run/name)
        if raw is not None and (not isinstance(files, dict)
                                or files.get(name) != hashlib.sha256(raw).hexdigest()):
            fail(f'{name}: missing/mismatched manifest SHA-256')

    frames, commands = logs['inputs/frames.jsonl'], logs['inputs/commands.jsonl']
    for field, rows in (('frames', frames), ('commands', commands)):
        count = result.get(field)
        if type(count) is not int or count < 1 or count != len(rows):
            fail(f'{field}: row count does not match result.{field}')
    if (any(type(r.get('frame')) is not int for r in frames)
            or [r.get('frame') for r in frames] != list(range(len(frames)))):
        fail('frame indices are not contiguous from zero')
    if len({r.get('file') for r in frames if isinstance(r.get('file'), str)}) != len(frames):
        fail('frame files are missing/duplicated')

    def timed(name, *, cadence=None, tail=None):
        rows = logs[name]
        ts = [row_time(r) for r in rows]
        if not rows or any(t is None or t < 0 or t > end + .0051 for t in ts):
            fail(f'{name}: missing/out-of-range SIM timestamps')
            return None
        if any(b < a for a, b in zip(ts, ts[1:])):
            fail(f'{name}: timestamps are not in emission order')
        if cadence is not None:
            # Logged SIM times are rounded to four decimals; the first sample
            # may be one physics step after the explicit recording origin.
            if (recording_start_sim_s is None or ts[0] < recording_start_sim_s - .00011
                    or ts[0] > recording_start_sim_s + dt + .00011):
                fail(f'{name}: missing initial sample or sample before recording start')
            if any(b - a > cadence + dt + .0002 for a, b in zip(ts, ts[1:])):
                fail(f'{name}: sampling gap')
        if tail is not None and end - ts[-1] > tail + dt + .0052:
            fail(f'{name}: does not cover the final SIM interval')
        return ts

    timed('inputs/frames.jsonl', cadence=period, tail=period)
    command_times = timed('inputs/commands.jsonl')
    if (not commands or commands[0].get('kind') != 'initial_servo_command'
            or row_time(commands[0]) != 0 or commands[-1].get('kind') != 'hold'
            or not command_times or abs(end - command_times[-1] - .5) > dt + .0052):
        fail('commands: missing initial command or terminal hold before 0.5 s settling')
    timed('eval_only/gt_trajectory.jsonl', cadence=.05, tail=.05)
    frame_eval = logs['eval_only/frames_eval.jsonl']
    alignment = ('frame', 't', 'phase', 'skill_phase')
    if len(frame_eval) != len(frames) or any(any(a.get(k) != b.get(k) for k in alignment)
                                            for a, b in zip(frames, frame_eval)):
        fail('evaluation frames do not match control frame indices/times/phases')

    phases = result.get('phase_times')
    if not isinstance(phases, dict):
        phases = {}
    phase_starts = [phases.get('skill:' + phase) for phase in FULL_PHASES]
    if (any(not number(t) or t > end for t in phase_starts)
            or any(b < a for a, b in zip(phase_starts, phase_starts[1:]))):
        fail('result.phase_times must reach grasp/lift/carry/release/look_back in order')
    else:
        for phase, start in zip(FULL_PHASES, phase_starts):
            if not any(r.get('skill_phase') == phase and row_time(r) is not None
                       and row_time(r) + .011 >= start for r in frames):
                fail(f'missing control/evaluation frame evidence for phase {phase}')
    macros = logs['macros.jsonl']
    timed('macros.jsonl')
    if not {'grasp', 'to_carry_posture'} <= {
            r['skill_phase'] for r in macros if isinstance(r.get('skill_phase'), str)}:
        fail('macro evidence must extend through grasp/lift')
    if not logs['controller_events.jsonl']:
        fail('missing controller events')
    if not {'grasp_attached', 'carry_posture_anchored'} <= {
            r['event'] for r in logs['skill_events.jsonl'] if isinstance(r.get('event'), str)}:
        fail('missing grasp/carry skill events')
    evaluation = result.get('evaluation_only')
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    contact_counts = evaluation.get('contacts')
    if not isinstance(contact_counts, dict) or any(
            type(contact_counts.get(k)) is not int or contact_counts[k] != sum(
                r.get('kind') == k for r in logs['eval_only/contacts.jsonl'])
            for k in ('wall', 'peer_robot', 'other_box')):
        fail('contact counts do not match result.evaluation_only.contacts')
    retention = logs['eval_only/retention.jsonl']
    recorded = evaluation.get('retention')
    recorded = recorded if isinstance(recorded, dict) else {}
    count = recorded.get('carry_steps')
    if (not retention or type(count) is not int or count <= 0
            or any(type(r.get('steps')) is not int or r['steps'] <= 0 for r in retention)):
        fail('missing post-grasp retention steps')
    else:
        logged = sum(r['steps'] for r in retention)
        # The runner leaves at most one partial 0.05s retention window unflushed.
        if not 0 <= count - logged <= math.ceil(.05 / dt) + 1:
            fail('retention steps do not cover result carry_steps')
        timed('eval_only/retention.jsonl')


def compare(a_path: Path, b_path: Path, until: float | None = None) -> dict:
    until = check_until(until)
    a_path, b_path = Path(a_path), Path(b_path)
    report: dict = {'a': str(a_path), 'b': str(b_path), 'until_sim_s': until, 'checks': {}, 'not_compared': []}
    checks, ev = report['checks'], Evidence()
    for side, path in (('A', a_path), ('B', b_path)):
        if not path.is_dir():
            ev.errors.append(f'{side}: {path} is not a directory')
    if ev.errors:
        return finish(report, ev)
    a_run, a_prof = split_dirs(a_path)
    b_run, b_prof = split_dirs(b_path)
    if a_prof and b_prof:
        ca = ev.rows('A', a_prof/CHECKPOINTS, required=True)
        cb = ev.rows('B', b_prof/CHECKPOINTS, required=True)
        validate_checkpoints('A', a_prof, a_run, ca, until, ev)
        validate_checkpoints('B', b_prof, b_run, cb, until, ev)
        checks['qpos_checkpoints'] = compare_lists(cut(ca, until), cut(cb, until))
        if until is None and len(ca) != len(cb):        # different lengths of full runs: compare the common prefix
            n = min(len(ca), len(cb))
            checks['qpos_checkpoints']['common_prefix_identical'] = ca[:n] == cb[:n]
        if not (cut(ca, until) and cut(cb, until)):
            ev.errors.append('qpos checkpoints: nothing to compare on at least one side')
    else:
        only = 'A' if a_prof else 'B' if b_prof else None
        report['not_compared'].append('qpos_checkpoints: ' + (f'only {only} is a sim_profile directory' if only
                                                              else 'neither side is a sim_profile directory'))
        if only:
            ev.errors.append('qpos checkpoints: missing profile evidence on one side')
    untimed, logs = [], {}
    for name in LOGS:
        required = until is None or name in REQUIRED_LOGS
        la = ev.rows('A', a_run/name, required=required)
        lb = ev.rows('B', b_run/name, required=required)
        logs[name] = (la, lb)
        if not la and not lb and not required:
            continue
        if until is not None and any(row_time(r) is None for r in la + lb):
            if required:
                ev.errors.append(f'{name}: rows without SIM time cannot be cut at {until}')
            untimed.append(name)        # e.g. skill_events (no SIM time): a truncated run cannot be cut
            continue
        selected_a, selected_b = cut(la, until), cut(lb, until)
        checks[name] = compare_lists(selected_a, selected_b)
        checks[name].update(compare_bytes(log_bytes(ev.raw.get(a_run/name), len(selected_a), until),
                                          log_bytes(ev.raw.get(b_run/name), len(selected_b), until)))
        if name in REQUIRED_LOGS and not (selected_a and selected_b):
            ev.errors.append(f'{name}: no rows to compare on at least one side')
    if untimed:
        report['not_compared_untimed_rows'] = untimed
    if until is not None:
        reach = {side: max((t for t in map(row_time, rows) if t is not None), default=None)
                 for side, rows in zip('AB', logs['inputs/frames.jsonl'])}
        report['last_frame_sim_s'] = reach
        for side, last in reach.items():
            if last is None or last < until:
                ev.errors.append(f'{side}: control frames end at {last} s, before the compared window {until} s')
    fa, fb = (cut(rows, until) for rows in logs['inputs/frames.jsonl'])
    n = min(len(fa), len(fb))
    bad = []
    for i in range(n):
        ha, hb = frame_digest('A', a_run, fa[i], ev), frame_digest('B', b_run, fb[i], ev)
        if ha is None or ha != hb:
            bad.append(i)
    checks['frame_jpeg_bytes'] = {'identical': not bad and len(fa) == len(fb), 'compared': n,
                                  'mismatched': bad[:20], 'n_mismatched': len(bad)}
    if n == 0:
        ev.errors.append('frame JPEG bytes: nothing compared')
    if until is None:
        ra, rb = (ev.document(side, run/'result.json') for side, run in (('A', a_run), ('B', b_run)))
        diff = sorted(k for k in set(ra) | set(rb) if k not in ra or k not in rb or ra[k] != rb[k])
        checks['result.json'] = {**compare_bytes(ev.raw.get(a_run/'result.json'), ev.raw.get(b_run/'result.json')),
                                 'fields': len(ra), 'differing_fields': diff}
        ma, mb = (ev.document(side, run/'manifest.json') for side, run in (('A', a_run), ('B', b_run)))
        starts = report['recording_start'] = {}
        for i, (side, run, result, manifest) in enumerate((('A', a_run, ra, ma), ('B', b_run, rb, mb))):
            side_logs = {name: rows[i] for name, rows in logs.items()}
            starts[side] = recording_start(side, side_logs, manifest, ev)
            validate_full_run(side, run, side_logs, result, manifest, ev, starts[side]['sim_s'])
        same_start = starts['A']['sim_s'] is not None and starts['A']['sim_s'] == starts['B']['sim_s']
        checks['recording_start'] = {'identical': same_start}
        if not same_start:
            ev.errors.append('recording start: A/B origins are unknown or disagree')
        mdiff = sorted(k for k in set(ma) | set(mb) if k not in ma or k not in mb or ma[k] != mb[k])
        report['manifest_differences'] = {'expected': [k for k in mdiff if k in MANIFEST_EXPECTED],
                                          'unexpected': [k for k in mdiff if k not in MANIFEST_EXPECTED]}
        report['speedups'] = {'a': ma.get('speedups', 'none (field absent)'), 'b': mb.get('speedups', 'none (field absent)')}
    return finish(report, ev)


def finish(report: dict, ev: Evidence) -> dict:
    same = all(c['identical'] for c in report['checks'].values()) and not (
        report.get('manifest_differences', {}).get('unexpected'))
    report['evidence_errors'] = ev.errors
    report['verdict'] = 'insufficient_evidence' if ev.errors else 'equivalent' if same else 'different'
    report['equivalent'] = report['verdict'] == 'equivalent'
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    p.add_argument('a', type=Path)
    p.add_argument('b', type=Path)
    p.add_argument('--until-sim-s', type=float, default=None)
    p.add_argument('--json', type=Path, default=None, help='also write the report here')
    args = p.parse_args(argv)
    try:
        report = compare(args.a, args.b, args.until_sim_s)
    except ValueError as exc:
        p.error(str(exc))
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.json:
        args.json.write_text(text + '\n')
    print(text)
    return {'equivalent': EXIT_EQUIVALENT, 'different': EXIT_DIFFERENT}.get(report['verdict'], EXIT_INSUFFICIENT)


if __name__ == '__main__':
    sys.exit(main())
