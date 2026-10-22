"""pairact-r1 P3 success-filtered teacher collection: pure controller logic.

COLLECT_PREREG_DRAFT.json (schema v2) is the contract.  This module never runs
physics: it replays an append-only jsonl ledger into counts, plans the next
batch (bins, seeds, cap), judges one finished pair episode from its
result.json + the batch status, and builds the convert input / bias report.
Same ledger -> same next batch.

Counts are in pair episodes: N behavior attempts, S physical successes,
A admitted, E environment failures (not in N).
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import stat
import subprocess
import xml.etree.ElementTree as ET

PREREG_SCHEMA = 'ugrp.pairact_r1.collect_prereg.v2'
LEDGER_SCHEMA = 'ugrp.pairact_r1.collect_ledger.v3'
REPORT_SCHEMA = 'ugrp.pairact_r1.collect_report.v2'
MODES = ('measurement', 'training')
# measurement = recording-off pilot yield/bin run on seeds.pilot (A is an admission candidate,
# 'yield measurement, not demonstrations'); training = recording on through the -c candidate
CANDIDATE_BY_MODE = {'measurement': 'pairact_p2_r13', 'training': 'pairact_p3_collect'}
SPLITS_BY_MODE = {'measurement': ('pilot',), 'training': ('train', 'validation')}
COLLECT_ENV = ('PAIRACT_P3_COLLECT_PREREG', 'PAIRACT_P3_COLLECT_PREREG_SHA256', 'PAIRACT_P3_RECORDING_CHECK',
               'PAIRACT_P3_RECORDING_PROBE', 'PAIRACT_P3_COLLECT_PREREG_CORE_SHA256')
NOISE_MODES = ('off', 'on')
VM_FILL = '[VM 기입]'
ROBOTS = ('r1', 'r2')

# Frozen status table (COLLECT_PREREG status_table; test_pairact_collect checks the two agree).
WORLD_STATUS = {'complete': 'behavior', 'HOST_ERROR': 'environment', 'interrupted': 'environment',
                'running': 'environment'}
REQUIRED_BOOL = ('grasp_physical_success', 'search_handoff', 'approach_handoff', 'data_admitted')
TRAIN_STOPS_WITH_VALIDATION = ('STOP_TARGET', 'STOP_CAP', 'STOP_SEEDS', 'STOP_ALL_BINS_LIMITED', 'STOP_HOST')
TRAINABLE = ('TRAIN', 'TRAIN_DATA_RANGE_LIMITED', 'TRAIN_SMALL_DATA')


# Two-stage freeze (v3, Codex v2 B1/B2): FROZEN_CORE fixes everything except the three
# recording_check hashes (core_sha256); FROZEN adds them.  Probe / probe-cases accept
# FROZEN_CORE, training recording needs FROZEN.  Pre-freeze pilot ledgers are yield only.
FREEZE_STAGES = ('FROZEN_CORE', 'FROZEN')
PURPOSE_PILOT = 'pilot_yield_only'          # READY_FOR_REVIEW measurement: never probe / training input
PURPOSE_PROBE_SOURCE = 'probe_source'       # FROZEN_CORE measurement bound to core_sha256
PURPOSE_TRAINING = 'training'
RECORDING_FIELDS = ('probe_cases_sha256', 'check_rows_sha256', 'recording_check_sha256')
RECORDING_FILES = {'probe_cases_sha256': 'probe-cases.json', 'check_rows_sha256': 'check-rows.json',
                   'recording_check_sha256': 'recording-check.json'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def prereg_core_sha256(prereg):
    """Content identity of the prereg across READY -> FROZEN_CORE -> FROZEN (status excluded)."""
    return hashlib.sha256(canonical({k: v for k, v in prereg.items() if k != 'status'})).hexdigest()


def manifest_core(manifest):
    """RUN_MANIFEST without status, the three recording_check hashes and the per-VM recording checks
    of a sharded run (sharding.vm_recording_check, filled at FROZEN like recording_check)."""
    core = json.loads(json.dumps({k: v for k, v in manifest.items() if k != 'status'}))
    for k in RECORDING_FIELDS:
        core.get('recording_check', {}).pop(k, None)
    if isinstance(core.get('sharding'), dict):
        core['sharding'].pop('vm_recording_check', None)
    return core


def core_sha256(prereg, manifest):
    """core_sha256 = sha256(canonical {prereg minus status, manifest_core}); never stored in either file."""
    return hashlib.sha256(canonical(dict(prereg={k: v for k, v in prereg.items() if k != 'status'},
                                         manifest=manifest_core(manifest)))).hexdigest()


# ------------------------------------------------------------------ prereg

def load_prereg(path, *, mode='measurement'):
    raw = Path(path).read_bytes()
    prereg = json.loads(raw)
    if prereg.get('schema') != PREREG_SCHEMA:
        raise ValueError(f'collect prereg schema {PREREG_SCHEMA} required')
    if mode not in MODES:
        raise ValueError('unknown collection mode')
    allowed = ('FROZEN',) if mode == 'training' else ('READY_FOR_REVIEW',) + FREEZE_STAGES
    if prereg.get('status') not in allowed:
        raise ValueError(f'prereg status {prereg.get("status")!r} not allowed for {mode}')
    check_seed_ranges(prereg)
    return prereg, hashlib.sha256(raw).hexdigest()


def bins(prereg):
    return [dict(b, index=i) for i, b in enumerate(prereg['bins']['list'])]


def bin_ids(prereg):
    return [b['id'] for b in prereg['bins']['list']]


def _span(r):
    return set(range(r['first'], r['last'] + 1))


def pool(prereg, split):
    s = prereg['seeds']
    if split == 'train':
        return list(range(s['train_primary']['first'], s['train_primary']['last'] + 1)) + \
            list(range(s['train_extension']['first'], s['train_extension']['last'] + 1))
    if split not in ('pilot', 'validation'):
        raise ValueError(f'split {split!r} is never collected')
    return list(range(s[split]['first'], s[split]['last'] + 1))


def seed_phase(prereg, seed):
    """primary / extension for train seeds (reported separately: before/after the extension)."""
    return 'primary' if seed <= prereg['seeds']['train_primary']['last'] else 'extension'


def check_seed_ranges(prereg, known_ranges=()):
    s = prereg['seeds']
    if s['train_extension']['first'] != s['train_primary']['last'] + 1:
        raise ValueError('train extension must continue the primary range')
    named = dict(train=_span(s['train_primary']) | _span(s['train_extension']), pilot=_span(s['pilot']),
                 validation=_span(s['validation']), heldout=_span(s['heldout']))
    names = sorted(named)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if named[a] & named[b]:
                raise ValueError(f'{a} seeds overlap {b}')
    every = set().union(*named.values())
    for r in known_ranges:
        if every & _span(r):
            raise ValueError(f'seed range overlaps known range {r}')
    if len(named['train']) < prereg['targets']['attempt_cap']:
        raise ValueError('train seed pool smaller than the attempt cap')


# ------------------------------------------------------------- start draws

def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def yaw_class(offset):
    """facing: heading within 90 deg of pointing back at the assigned end."""
    return 'facing' if abs(wrap(offset - math.pi)) <= math.pi / 2 + 1e-12 else 'away'


def bin_of(prereg, distance, offset):
    edges = prereg['bins']['distance_edges_m']
    if not edges[0] <= distance <= edges[-1]:
        return None
    for b in bins(prereg):
        lo, hi = b['distance_m']
        if lo <= distance <= hi and yaw_class(offset) == b['yaw']:
            return b['id']
    return None


def draw_start(prereg, seed, bin_id, robot_index):
    """Setup-only draw: distance uniform in the bin, yaw offset uniform in its half circle."""
    b = next(b for b in bins(prereg) if b['id'] == bin_id)
    rng = random.Random(f'pairact_r1_collect_v1:{seed}:{bin_id}:{robot_index}')  # str seed: sha512, process independent
    lo, hi = b['distance_m']
    distance = rng.uniform(lo, hi)
    u = rng.uniform(-math.pi / 2, math.pi / 2)
    offset = (math.pi + u if b['yaw'] == 'facing' else u) % (2 * math.pi)
    return distance, offset


# ------------------------------------------------------------------ ledger

def committed_bytes(path):
    """v5: the ledger bytes up to and including the last newline -- the only part reader, repair and the merge
    append-only seal share.  A tail without a newline (crash mid-append, partial sync) is uncommitted, even when
    it happens to be valid JSON: invisible to read_ledger, dropped by repair_ledger, outside the merge seal."""
    path = Path(path)
    if not path.exists():
        return b''
    raw = path.read_bytes()
    return raw[:raw.rfind(b'\n') + 1]


def read_ledger(path):
    return parse_ledger(committed_bytes(path))


def parse_ledger(data):
    """Rows of committed ledger bytes (see committed_bytes)."""
    rows = []
    for line in data.decode().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                break      # malformed committed line: stop there (never skip over it)
    return rows


def repair_ledger(path):
    """Drop the uncommitted tail (crash mid-write) so later appends stay readable; returns bytes dropped."""
    path = Path(path)
    if not path.exists():
        return 0
    raw = path.read_bytes()
    keep = committed_bytes(path)
    if len(keep) == len(raw):
        return 0
    with open(path, 'r+b') as f:
        f.truncate(len(keep))
        os.fsync(f.fileno())
    return len(raw) - len(keep)


def append(path, row):
    with open(path, 'a') as f:
        f.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


# v6 (Codex v5 re-review 3): options the gates read from the episode command.  argparse keeps the *last* of a
# repeated option, accepts ``--flag=value`` and unique prefixes, so a first-match reader could check one path
# while the wrapper runs another.  Every gate reads them through episode_option(), which refuses all of that.
EPISODE_VALUE_FLAGS = ('--teacher-source', '--adapter-source', '--canonical-xml', '--per-world-model-references-v1',
                       '--rejection-table', '--cap-s')


def episode_option(tokens, flag):
    """The single value of ``flag`` in the episode command tokens (``flag v`` or ``flag=v``), None if absent.
    Raises ValueError when the option is given more than once, abbreviated, or lacks a value."""
    hits = []
    for i, t in enumerate(tokens):
        name, eq, val = t.partition('=')
        if name == flag:
            if not eq and i + 1 >= len(tokens):
                raise ValueError(f'episode command {flag} has no value')
            hits.append(val if eq else tokens[i + 1])
        elif len(name) > 2 and name.startswith('--') and flag.startswith(name):
            raise ValueError(f'episode command abbreviates {flag} as {name}; spell it out')
    if len(hits) > 1:
        raise ValueError(f'episode command names {flag} {len(hits)} times; give it once')
    return hits[0] if hits else None


def episode_option_problems(template):
    """v6: every gated option of the episode command is unambiguous (once, unabbreviated), and so is the root."""
    tokens, out = shlex.split(template), []
    for flag in EPISODE_VALUE_FLAGS:
        try:
            episode_option(tokens, flag)
        except ValueError as error:
            out.append(str(error))
    if sum(t.startswith('WARP_SOURCE_ROOT=') for t in tokens) > 1:
        out.append('episode command sets WARP_SOURCE_ROOT more than once; give it once')
    if sum(t.endswith('.py') for t in tokens) > 1:
        out.append('episode command names more than one .py; the wrapper must be unambiguous')
    return out


def episode_cmd_audit(template):
    """The episode command is part of the frozen run: rejection table must be absolute, cap explicit."""
    if not template or any(k not in template for k in ('{cases}', '{indices}', '{out}')):
        raise ValueError('--episode-cmd with {cases} {indices} {out} required')
    episode_command_form(template)      # v7 risk 2: one wrapper argv, no shell syntax
    problems = episode_command_problems(template)
    if problems:
        raise ValueError(problems[0])
    tokens = shlex.split(template)

    def value(flag):
        got = episode_option(tokens, flag)
        if got is None:
            raise ValueError(f'episode command needs exactly one {flag} <value>')
        return got
    table = value('--rejection-table')
    if not os.path.isabs(table):
        raise ValueError(f'--rejection-table must be an absolute path, got {table!r}')
    return dict(template_sha256=hashlib.sha256(template.encode()).hexdigest(), rejection_table_input=table,
                cap_s=float(value('--cap-s')))


def header(prereg_sha, *, mode, noise, batch_size, episode=None, run_manifest_sha256=None, freeze=None, shard=None):
    """Ledger header.  ``freeze``: dict(stage, purpose, prereg_core_sha256, core_sha256) from the runner.

    ``shard`` (v3s sharded runs only): dict(index, count, vm); a serial header has no ``shard`` key.
    """
    if noise not in NOISE_MODES:
        raise ValueError('unknown noise mode')
    if mode not in MODES:
        raise ValueError('unknown collection mode')
    freeze = dict(dict(stage=None, purpose=PURPOSE_TRAINING if mode == 'training' else PURPOSE_PILOT,
                       prereg_core_sha256=None, core_sha256=None), **(freeze or {}))
    if freeze['purpose'] not in (PURPOSE_PILOT, PURPOSE_PROBE_SOURCE, PURPOSE_TRAINING) or \
            (freeze['purpose'] == PURPOSE_TRAINING) != (mode == 'training'):
        raise ValueError(f'ledger purpose {freeze["purpose"]!r} does not fit mode {mode}')
    out = dict(type='header', schema=LEDGER_SCHEMA, prereg_sha256=prereg_sha, mode=mode, noise=noise,
               batch_size=int(batch_size), episode=episode, run_manifest_sha256=run_manifest_sha256,
               freeze_stage=freeze['stage'], purpose=freeze['purpose'],
               prereg_core_sha256=freeze['prereg_core_sha256'], core_sha256=freeze['core_sha256'])
    if shard is not None:
        out['shard'] = dict(shard)
    return out


def require_header_sha(st, prereg_sha, prereg_core=None):
    """audit 2: report / convert-input never relabel a ledger under a different pre-registration.

    Same file sha256, or (v3) the same prereg content (status excluded) when the header recorded it:
    a pilot ledger stays reportable after the status moves READY -> FROZEN_CORE -> FROZEN.
    """
    h = st['header']
    if h is None:
        raise ValueError('ledger has no header')
    if h.get('schema') != LEDGER_SCHEMA:
        raise ValueError(f'ledger schema {h.get("schema")!r} is not {LEDGER_SCHEMA}')
    same_core = prereg_core is not None and h.get('prereg_core_sha256') == prereg_core
    if h.get('prereg_sha256') != prereg_sha and not same_core:
        raise ValueError(f'ledger header prereg sha256 {h.get("prereg_sha256")} != current prereg {prereg_sha}')
    return h


def require_probe_source(st, core):
    """probe-cases: only a FROZEN_CORE measurement ledger bound to the current core_sha256 (B2)."""
    h = st['header']
    if h is None or h.get('schema') != LEDGER_SCHEMA:
        raise ValueError(f'ledger schema {LEDGER_SCHEMA} required')
    if h.get('purpose') == PURPOSE_PILOT:
        raise ValueError('pilot_yield_only ledger (pre-freeze pilot) is never a recording probe source')
    if h.get('purpose') != PURPOSE_PROBE_SOURCE or h.get('mode') != 'measurement':
        raise ValueError(f'probe source needs a {PURPOSE_PROBE_SOURCE} measurement ledger, got {h.get("purpose")!r}')
    if h.get('core_sha256') != core:
        raise ValueError(f'ledger core_sha256 {h.get("core_sha256")} != current core {core}')
    return h


def replay(prereg, rows):
    ids = bin_ids(prereg)
    st = dict(header=None, attempt_rows=[], setup_rows=[], batches={}, consumed={}, requeue=[],
              last_rr=-1, limited={}, open_batch=None, barrier=None)
    requeued = Counter()
    for r in rows:
        kind = r.get('type')
        if kind == 'header':
            if st['header'] is not None and r != st['header']:
                raise ValueError('ledger header changed between invocations')
            st['header'] = r
        elif kind == 'setup_rejected':
            st['consumed'].setdefault(r['split'], set()).add(r['seed'])
            st['setup_rows'].append(r)
            if r.get('requeue'):
                # Codex v2 B5: a re-queued slot rejected by the generator leaves the queue (never re-queued)
                requeued[(r['split'], r['seed'])] += 1
                st['requeue'] = [q for q in st['requeue'] if (q['split'], q['seed']) != (r['split'], r['seed'])]
        elif kind == 'bin_limited':
            st['limited'][r['bin']] = r
        elif kind == 'train_closed':
            st.setdefault('train_closed', r)        # sharded runs only: the stop fixed on the drained view
            st['barrier'] = None                     # the close resolves a held barrier
        elif kind == 'train_barrier':
            # sharded runs only (v4 stop barrier): 'hold' stops new train planning until every in-flight
            # batch is done; 'release' lifts it when the drained view has no stop
            st['barrier'] = r if r.get('action') == 'hold' else None
        elif kind == 'batch_planned':
            st['batches'][r['batch']] = dict(r, done=False, clean=None, ingested=set())
            st['open_batch'] = r['batch']
            for s in r['slots']:
                st['consumed'].setdefault(s['split'], set()).add(s['seed'])
                if s.get('requeue'):
                    requeued[(s['split'], s['seed'])] += 1
                    st['requeue'] = [q for q in st['requeue'] if (q['split'], q['seed']) != (s['split'], s['seed'])]
                elif s['split'] == 'train':
                    st['last_rr'] = ids.index(s['bin'])
        elif kind == 'attempt':
            st['batches'][r['batch']]['ingested'].add(r['slot'])
            st['attempt_rows'].append(r)
            if r.get('requeue_eligible') and requeued[(r['split'], r['seed'])] == 0:
                st['requeue'].append(dict(seed=r['seed'], bin=r['bin'], split=r['split']))
        elif kind == 'batch_done':
            b = st['batches'][r['batch']]
            b.update(done=True, clean=bool(r.get('clean')), status=r.get('status'))
            st['open_batch'] = None
    return st


# ------------------------------------------------------------------ counts

def tally(rows):
    """N/S/A/E for a list of attempt rows (pair episodes)."""
    beh = [r for r in rows if r['category'] == 'behavior']
    env = [r for r in rows if r['category'] == 'environment']
    return dict(attempts=len(beh), successes=sum(r['success'] for r in beh),
                admitted=sum(r['admitted'] for r in beh), env_failures=len(env),
                env_by_kind=dict(Counter(r['outcome'] for r in env)),
                record_errors=sum(r['category'] == 'record_error' for r in rows))


def split_rows(st, split):
    return [r for r in st['attempt_rows'] if r['split'] == split]


def bin_counts(prereg, st, split='train'):
    rows = split_rows(st, split)
    return {b: tally([r for r in rows if r['bin'] == b]) for b in bin_ids(prereg)}


def totals(st, split='train'):
    return tally(split_rows(st, split))


def pending_bin_limits(prereg, st):
    """bin_limited rows to append at this batch boundary (bin_limit_v1, train only)."""
    rule = prereg['bins']['bin_limit']
    out = []
    for b, c in bin_counts(prereg, st).items():
        if b in st['limited'] or c['attempts'] < rule['min_attempts']:
            continue
        rate = c['admitted'] / c['attempts']        # v4 (xreview R1): the allocation quantity A_b, not S_b
        if rate < rule['max_admitted_rate']:
            out.append(dict(type='bin_limited', bin=b, attempts=c['attempts'], successes=c['successes'],
                            admitted=c['admitted'], admitted_rate=rate,
                            success_rate=c['successes'] / c['attempts'], rule=rule['id']))
    return out


def open_bins(prereg, st):
    return [b for b in bin_ids(prereg) if b not in st['limited']]


def admitted_starts(st, split='train'):
    return [v['distance_m'] for r in split_rows(st, split) if r['admitted'] for v in (r.get('start') or {}).values()]


def excluded_bands(prereg, st):
    """Distance bands [lo, hi] whose every start bin is bin_limited (distance gate v3, xreview R2)."""
    by_band = {}
    for b in prereg['bins']['list']:
        by_band.setdefault(tuple(b['distance_m']), []).append(b['id'])
    return [list(band) for band, ids in sorted(by_band.items()) if all(i in st['limited'] for i in ids)]


def _overlap(lo, hi, a, b):
    return max(0., min(hi, b) - max(lo, a))


def distance_gate(prereg, st):
    """start_distance_gate_v3: the v2 gate on the distance range of the bands that are not fully bin_limited.

    A band (both yaw bins of one distance range) that is entirely bin_limited leaves the gate: its
    admitted robot starts leave the denominator, its 0.1 m cells leave the occupancy check and the
    required share above over_m is scaled by the uniform share of the remaining range
    (min_share_over x u_open / u_full; 25 % when nothing is excluded).  Reported as range_excluded.
    """
    g = prereg['distance_gate']['edges']
    top = g['first_m'] + g['width_m'] * g['n']
    excluded = excluded_bands(prereg, st)
    band_of = {b['id']: tuple(b['distance_m']) for b in prereg['bins']['list']}
    dist = [v['distance_m'] for r in split_rows(st, 'train') if r['admitted']
            and list(band_of.get(r['bin'], ())) not in excluded for v in (r.get('start') or {}).values()]
    cells = [i for i in range(g['n'])
             if not any(lo - 1e-9 <= g['first_m'] + g['width_m'] * (i + .5) <= hi + 1e-9 for lo, hi in excluded)]
    hist = Counter(min(g['n'] - 1, int((d - g['first_m']) // g['width_m'])) for d in dist
                   if g['first_m'] <= d <= top + 1e-9)
    share = (sum(d > g['over_m'] for d in dist) / len(dist)) if dist else None
    occupied = all(hist[i] >= 1 for i in cells)
    required = g['min_share_over']
    if excluded:
        full = top - g['first_m']
        open_len = full - sum(_overlap(lo, hi, g['first_m'], top) for lo, hi in excluded)
        over = lambda lo, hi: _overlap(lo, hi, g['over_m'], top)
        u_full = over(g['first_m'], top) / full
        u_open = (over(g['first_m'], top) - sum(over(lo, hi) for lo, hi in excluded)) / open_len if open_len > 0 else 0.
        required = g['min_share_over'] * u_open / u_full
    label = None
    if excluded:
        label = '거리 관문 축소(제한 구간 제외: ' + ', '.join(f'{lo:.1f}-{hi:.1f} m' for lo, hi in excluded) + \
                f', 요구 비율 {required:.3f})'
    return dict(robot_starts=len(dist), hist_0p1m={f'{g["first_m"] + g["width_m"] * i:.1f}': hist[i] for i in range(g['n'])},
                cells_required=[f'{g["first_m"] + g["width_m"] * i:.1f}' for i in cells],
                all_bins_occupied=occupied, share_over_0p8=share, min_share_required=required,
                range_excluded=excluded, label=label,
                passed=bool(dist) and occupied and share >= required - 1e-12)


def consecutive_unclean_batches(st, split='train'):
    n = 0
    for k in sorted(st['batches'], reverse=True):
        b = st['batches'][k]
        if not b['done'] or b['split'] != split:
            continue
        if b['clean']:
            break
        n += 1
    return n


def shard_count(st):
    return int(((st['header'] or {}).get('shard') or {}).get('count') or 1)


def _train_flags(st, owner=None, count=1, split='train'):
    """clean flags of the finished train batches in batch order (optionally of one shard k % count == owner)."""
    return [st['batches'][k]['clean'] for k in sorted(st['batches'])
            if st['batches'][k]['done'] and st['batches'][k]['split'] == split and (owner is None or k % count == owner)]


def _unclean_run(flags, n):
    run = 0
    for c in flags:
        run = 0 if c else run + 1
        if run >= n:
            return True
    return False


def host_unclean_pair(st):
    """STOP_HOST global part (v4): two consecutive finished train batches (batch order) are both unclean.
    In a serial run this is 'the last two' at the boundary where it first holds; as a property of the
    ordered results it is not undone by later clean batches (Codex H1)."""
    return _unclean_run(_train_flags(st), 2)


def shard_host(prereg, st, split='train'):
    """Per-shard host health (v4, xreview R3): shards whose finished train batches (owner k % K, batch order)
    contain ``consecutive`` unclean batches in a row, or a prefix of >= ``min_batches`` batches with an unclean
    share >= ``max_share``.  Prefix properties of the ordered results, so a serial run stops where it first
    holds and later batches cannot undo it.  K = 1 (serial) is one shard."""
    rule = prereg['stop_rules']['shard_host']
    count, out = shard_count(st), []
    for i in range(count):
        fin = _train_flags(st, i, count, split)
        bad = [sum(not c for c in fin[:m]) for m in range(len(fin) + 1)]
        ratio = [m for m in range(rule['min_batches'], len(fin) + 1) if bad[m] / m >= rule['max_share']]
        if _unclean_run(fin, rule['consecutive']) or ratio:
            out.append(dict(shard=i, finished=len(fin), unclean=bad[-1],
                            ratio_prefix=ratio[0] if ratio else None))
    return out


def far_bins(prereg):
    """Bins of the farthest distance band (B4, B5)."""
    top = max(b['distance_m'][1] for b in prereg['bins']['list'])
    return [b['id'] for b in prereg['bins']['list'] if b['distance_m'][1] == top]


def far_bins_settled(prereg, st, per=None):
    """Owner decision D-v4-1 (2026-10-21, before freeze): STOP_DISTANCE is evaluated only once every far bin
    has A_b >= min_admitted_per_bin or is bin_limited; before that the distance gate is not a stop reason."""
    per = per or bin_counts(prereg, st)
    need = prereg['bins']['min_admitted_per_bin']
    return all(per[b]['admitted'] >= need or b in st['limited'] for b in far_bins(prereg))


def train_stop(prereg, st):
    """First true stop rule (prereg stop_rules.list order), or None.  A pure function of the train/validation
    results: the same function for every K (v4: train_closed is never read here)."""
    tg, ids = prereg['targets'], bin_ids(prereg)
    if any(r['category'] == 'record_error' for r in st['attempt_rows']):
        return 'STOP_RECORD'
    if host_unclean_pair(st) or shard_host(prereg, st):
        return 'STOP_HOST'
    t, per = totals(st), bin_counts(prereg, st)
    if t['admitted'] >= tg['admitted_minimum_pairs'] and far_bins_settled(prereg, st, per) and \
            not distance_gate(prereg, st)['passed']:
        return 'STOP_DISTANCE'
    min_bin = prereg['bins']['min_admitted_per_bin']
    if t['admitted'] >= tg['admitted_target_pairs'] and all(
            per[b]['admitted'] >= min_bin or b in st['limited'] for b in ids):
        return 'STOP_TARGET'
    if not open_bins(prereg, st):
        return 'STOP_ALL_BINS_LIMITED'
    if t['attempts'] >= tg['attempt_cap']:
        return 'STOP_CAP'
    if not [q for q in st['requeue'] if q['split'] == 'train'] and \
            not [s for s in pool(prereg, 'train') if s not in st['consumed'].get('train', set())]:
        return 'STOP_SEEDS'
    return None


def check_train_closed(prereg, st):
    """A sharded ledger's train_closed must equal the stop of its own data (v4 barrier: it is written on the
    drained view, after which no train result arrives).  STOP_RECORD of a later validation row may override."""
    closed = st.get('train_closed')
    if closed is None:
        return
    stop = train_stop(prereg, st)
    if stop not in (closed['stop'], 'STOP_RECORD'):
        raise ValueError(f"train_closed {closed['stop']} at boundary {closed.get('planning_batch')} disagrees with "
                         f'the stop of the ledger data ({stop})')


def validation_done(prereg, st):
    free = [s for s in pool(prereg, 'validation') if s not in st['consumed'].get('validation', set())]
    return not free and not [q for q in st['requeue'] if q['split'] == 'validation'] and \
        all(b['done'] for b in st['batches'].values() if b['split'] == 'validation')


def validation_gate(prereg, st):
    g = prereg['validation_gate']
    rows = [r for r in split_rows(st, 'validation') if r['admitted']]
    stages = sorted({s for r in rows for v in (r.get('sidecar') or {}).get('stages', {}).values() for s in v})
    missing = [s for s in g['required_stages'] if s not in stages]
    return dict(admitted=len(rows), min_admitted=g['min_admitted'], stages=stages, missing_stages=missing,
                passed=len(rows) >= g['min_admitted'] and not missing)


def decision(prereg, st):
    """training_decision tiers (owner 2026-10-21); the validation gate applies once validation is done.

    A >= 150 and all bins >= 20 -> TRAIN; A >= 150, some bin < 20 -> TRAIN_DATA_RANGE_LIMITED;
    80 <= A < 150 -> TRAIN_SMALL_DATA (funnel-centred interpretation); A < 80 -> NO_TRAIN_BELOW_FLOOR.
    """
    check_train_closed(prereg, st)
    stop = train_stop(prereg, st)
    out = dict(train_stop=stop, decision='COLLECTING', limited_bins=[], validation=None, labels=[])
    if stop == 'STOP_HOST':
        out['host_stop'] = dict(unclean_pair=host_unclean_pair(st), last_unclean=consecutive_unclean_batches(st),
                                shards=shard_host(prereg, st))
    if stop is None:
        return out
    t, per = totals(st), bin_counts(prereg, st)
    min_bin = prereg['bins']['min_admitted_per_bin']
    out['limited_bins'] = [dict(bin=b, admitted=per[b]['admitted'], attempts=per[b]['attempts'],
                                cause='bin_limited' if b in st['limited'] else stop)
                           for b in bin_ids(prereg) if per[b]['admitted'] < min_bin]
    if stop == 'STOP_RECORD':
        out['decision'] = 'NO_TRAIN_RECORD_ERROR'
    elif t['admitted'] < prereg['targets']['admitted_floor_pairs']:
        out['decision'] = 'NO_TRAIN_BELOW_FLOOR'
    elif not distance_gate(prereg, st)['passed']:
        out['decision'] = 'NO_TRAIN_DISTANCE_GATE'
    elif t['admitted'] < prereg['targets']['admitted_minimum_pairs']:
        out['decision'] = 'TRAIN_SMALL_DATA'
    else:
        out['decision'] = 'TRAIN_DATA_RANGE_LIMITED' if out['limited_bins'] else 'TRAIN'
    if out['decision'] == 'TRAIN_SMALL_DATA':
        out['labels'].append('소량 데이터(A<150): 결과 해석은 단계 퍼널 중심으로 제한')
    if out['decision'] in TRAINABLE and out['limited_bins']:
        out['labels'].append('데이터 범위 제한(구간 부족: ' + ', '.join(x['bin'] for x in out['limited_bins']) + ')')
    gate_label = distance_gate(prereg, st)['label']
    if out['decision'] in TRAINABLE + ('NO_TRAIN_DISTANCE_GATE',) and gate_label:
        out['labels'].append(gate_label)
    if out['decision'] in TRAINABLE and stop in TRAIN_STOPS_WITH_VALIDATION:
        if validation_done(prereg, st):
            out['validation'] = validation_gate(prereg, st)
            if not out['validation']['passed']:
                out['decision'] = 'NO_TRAIN_VALIDATION_INSUFFICIENT'
        else:
            out['validation'] = 'pending'
    return out


# -------------------------------------------------------------- allocation

def largest_remainder(weights, n):
    total = sum(weights)
    if n <= 0 or total <= 0:
        return [0] * len(weights)
    exact = [w * n / total for w in weights]
    out = [math.floor(x) for x in exact]
    order = sorted(range(len(weights)), key=lambda i: (-(exact[i] - out[i]), i))
    for i in order[:n - sum(out)]:
        out[i] += 1
    return out


def _round_robin(ids, opened, last_rr, n):
    order = [ids[(last_rr + 1 + k) % len(ids)] for k in range(len(ids))]
    order = [b for b in order if b in opened]
    return [order[k % len(order)] for k in range(n)] if order else []


def allocate(prereg, st, n):
    """Bin id per new train slot (interleaved), deficit_weighted_v2; success_b == A_b everywhere."""
    ids, opened = bin_ids(prereg), open_bins(prereg, st)
    a = prereg['allocation']['params']
    min_bin = prereg['bins']['min_admitted_per_bin']
    per = bin_counts(prereg, st)
    need = {b: max(0, min_bin - per[b]['admitted']) for b in ids}
    if any(per[b]['attempts'] < a['warmup_attempts'] for b in opened) or all(need[b] == 0 for b in opened):
        return _round_robin(ids, opened, st['last_rr'], n)
    weights = []
    for b in ids:
        p = (per[b]['admitted'] + 1) / (per[b]['attempts'] + 2)
        weights.append(need[b] / max(p, a['p_floor']) if b in opened else 0.)
    counts = largest_remainder(weights, n)
    slots = []
    while len(slots) < n:
        for i, b in enumerate(ids):
            if counts[i]:
                slots.append(b)
                counts[i] -= 1
    return slots


def _fixed_bin_slots(prereg, st, split, n):
    ids, first = bin_ids(prereg), pool(prereg, split)[0]
    slots = [dict(seed=q['seed'], bin=q['bin'], split=split, requeue=True)
             for q in st['requeue'] if q['split'] == split][:n]
    free = [s for s in pool(prereg, split) if s not in st['consumed'].get(split, set())]
    slots += [dict(seed=s, bin=ids[(s - first) % len(ids)], split=split, requeue=False) for s in free[:n - len(slots)]]
    return slots


def plan_batch(prereg, st, batch_size, *, validation_after_host_fix=False, reserved=0):
    """Next batch of slots; [] when the run root is finished (see run_state).

    ``reserved`` (sharded runs, v3s): train slots planned in batches whose results are not yet in
    ``st`` (in flight); they count against the attempt cap so N never exceeds it.  0 for serial runs.
    """
    mode = (st['header'] or {}).get('mode')
    if mode == 'measurement':
        slots = _fixed_bin_slots(prereg, st, 'pilot', batch_size)
    elif mode == 'training':
        stop = train_stop(prereg, st)
        if stop is None:
            room = prereg['targets']['attempt_cap'] - totals(st)['attempts'] - reserved
            n = max(0, min(batch_size, room))
            slots = [dict(seed=q['seed'], bin=q['bin'], split='train', requeue=True)
                     for q in st['requeue'] if q['split'] == 'train'][:n]
            free = [s for s in pool(prereg, 'train') if s not in st['consumed'].get('train', set())]
            new = allocate(prereg, st, min(n - len(slots), len(free)))
            slots += [dict(seed=free[k], bin=b, split='train', requeue=False) for k, b in enumerate(new)]
        elif decision(prereg, st)['validation'] == 'pending' and (stop != 'STOP_HOST' or validation_after_host_fix):
            slots = _fixed_bin_slots(prereg, st, 'validation', batch_size)
        else:
            slots = []
    else:
        raise ValueError('ledger header with a known mode required')
    return [dict(s, slot=i) for i, s in enumerate(slots)]


def run_state(prereg, st):
    """Why a run root has nothing left to plan (for the runner's return value and report)."""
    mode = (st['header'] or {}).get('mode')
    if mode == 'measurement':
        return 'PILOT_DONE'
    d = decision(prereg, st)
    if d['train_stop'] == 'STOP_HOST' and d['validation'] == 'pending':
        return 'STOP_HOST'
    return d['decision'] if d['validation'] != 'pending' else d['train_stop']


# ----------------------------------------------------------------- judging

def _last_fail(carry):
    for e in reversed(carry.get('events') or []):
        if isinstance(e, dict) and e.get('event') == 'fail':
            detail = e.get('detail')
            return dict(code=e.get('code'), phase=e.get('phase'),
                        detail=None if detail is None else str(detail)[:300])
    return None


def _record_error(out, reason):
    # v5: also when applied to a judged success (runner carry_success check): never S or A
    return dict(out, category='record_error', outcome='record_error', failure_stage='record', reason=reason,
                success=False, admitted=False)


def judge(result, *, mode, batch_clean, sidecar=None):
    """One pair episode -> status-table category, S, A and failure sub-reasons. Never defaults a field."""
    out = dict(category=None, outcome=None, success=False, admitted=False, failure_stage=None, reason=None,
               handoff=None, requeue_eligible=False, end_reason=None, cap_end=None, eval_failure=None,
               carry_outcome=None, carry_fail=None, funnel_last=None, carried_max_m=None, drop_kinds=None)
    if result is None:
        return dict(out, category='environment', outcome='host_error', failure_stage='host',
                    reason='missing_result', requeue_eligible=True)
    status = result.get('status')
    if status not in WORLD_STATUS:
        return _record_error(out, f'unregistered_status:{status}')
    if WORLD_STATUS[status] == 'environment':
        return dict(out, category='environment', outcome='host_error', failure_stage='host',
                    reason=result.get('error_type') or status, requeue_eligible=True)
    bad = [k for k in REQUIRED_BOOL if not isinstance(result.get(k), bool)]
    if bad or 'end_reason' not in result:
        return _record_error(out, 'missing_fields:' + ','.join(bad + ([] if 'end_reason' in result else ['end_reason'])))
    handoff = result['search_handoff'] or result['approach_handoff']
    out.update(category='behavior', handoff=handoff, end_reason=result['end_reason'], cap_end=result.get('cap_end'))
    if not result['grasp_physical_success']:
        return dict(out, outcome='failure', failure_stage='grasp', reason=result['end_reason'])
    carry, ev = result.get('carry'), result.get('carry_eval')
    if not isinstance(carry, dict) or 'outcome' not in carry or not isinstance(carry.get('events'), list):
        return _record_error(out, 'missing_fields:carry.outcome/events')
    if not isinstance(ev, dict) or not isinstance(ev.get('success'), bool) or 'failure' not in ev \
            or not isinstance(ev.get('drop_events'), list) or type(ev.get('robot_robot_contact_ticks')) is not int:
        return _record_error(out, 'missing_fields:carry_eval.success/failure/drop_events/robot_robot_contact_ticks')
    funnel = ev.get('funnel') or {}
    reached = [k for k, v in funnel.items() if v]
    out.update(eval_failure=ev['failure'], carry_outcome=carry['outcome'], carry_fail=_last_fail(carry),
               funnel_last=reached[-1] if reached else None, carried_max_m=ev.get('carried_max_m'),
               drop_kinds=[d.get('kind') for d in ev['drop_events'] if isinstance(d, dict)])
    if not (ev['success'] and not ev['drop_events'] and ev['robot_robot_contact_ticks'] == 0):
        return dict(out, outcome='failure', failure_stage='carry', reason=ev['failure'] or 'carry_failed')
    why = []
    if handoff:
        why.append('handoff')
    if not batch_clean:
        why.append('batch_not_clean')
    if mode == 'training':
        if result['data_admitted'] is not True:
            why.append('recording_not_admitted')
        if not sidecar or not sidecar.get('passed'):
            why.append('sidecar_failed')
    return dict(out, outcome='success', success=True, admitted=not why,
                reason=None if not why else 'success_not_admitted:' + '+'.join(why))


def validation_unclean(j, *, split, requeue, batch_clean):
    """v4 (xreview B3): a judged world of an unclean *validation* batch is re-queued once with the same seed,
    like an environment failure (category environment, not in N).  The re-queued run is judged as usual;
    if its batch is unclean again the seed stays not admitted (success_not_admitted:batch_not_clean)."""
    if split != 'validation' or batch_clean or requeue or j['category'] != 'behavior':
        return j
    return dict(j, category='environment', outcome='unclean_batch_requeue', failure_stage='host',
                reason=f"validation_batch_not_clean:{j['outcome']}", success=False, admitted=False,
                requeue_eligible=True, judged_outcome=j['outcome'], judged_success=j['success'])


def batch_is_clean(summary, exit_code):
    """status table batch.clean (audit 1); the rejection table must be an existing absolute file (v3 N2)."""
    table = summary.get('rejection_table')
    return (summary.get('status') == 'complete' and summary.get('HOST_ERROR') == 0 and exit_code == 0
            and isinstance(table, str) and os.path.isabs(table) and os.path.isfile(table))


# ---------------------------------------------------------------- sidecar

def read_jsonl(path):
    path = Path(path)
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return [json.loads(line) for line in raw.decode().splitlines() if line.strip()]


def _stream(raw_dir, name):
    for p in (Path(raw_dir) / f'{name}.jsonl', Path(raw_dir) / f'{name}.jsonl.zst'):
        if p.exists():
            return p
    return None


def sidecar_check(raw_dir, robots=ROBOTS, read_rows=read_jsonl, phase_table=None):
    """filter.sidecar_check: both robot streams must label every row before an episode is eligible."""
    if phase_table is None:
        from harness.pairact_r1 import TEACHER_PHASE_TO_STAGE as phase_table
    stages, rows, recover = {}, {}, 0
    for rid in robots:
        teacher, student = _stream(raw_dir, f'teacher-{rid}'), _stream(raw_dir, f'student-{rid}')
        if teacher is None or student is None:
            return dict(passed=False, reason=f'{rid}: teacher/student stream missing')
        trows, srows = read_rows(teacher), read_rows(student)
        if not trows:
            return dict(passed=False, reason=f'{rid}: empty teacher stream')
        seen = set()
        for row in trows:
            if 'sample_id' not in row or row.get('teacher_phase') not in phase_table:
                return dict(passed=False, reason=f'{rid}: row without sample_id or with unmapped teacher_phase '
                                                 f'{row.get("teacher_phase")!r}')
            seen.add(row['sample_id'])
        if seen != {r.get('sample_id') for r in srows}:
            return dict(passed=False, reason=f'{rid}: teacher/student sample_id sets differ')
        got = [phase_table[r['teacher_phase']] for r in trows]
        stages[rid], rows[rid] = sorted(set(got)), len(trows)
        recover += got.count('recover')
    return dict(passed=True, reason=None, stages=stages, rows=rows, recover_rows=recover)


def start_from_case(case):
    """Robot-level start distance / yaw offset from the immutable case plan."""
    layers = case['plan'].get('start_layers') or {}
    return {rid: dict(distance_m=float(v['target_distance_m']), yaw_offset_rad=float(v['yaw_bin']['offset_rad']))
            for rid, v in layers.items()}


def perturbed_ratio(raw_dir, read_rows=read_jsonl):
    """perturbed / rows per robot from teacher-<rid>.jsonl(.zst) (noise bookkeeping)."""
    out = {}
    for rid in ROBOTS:
        path = _stream(raw_dir, f'teacher-{rid}')
        if path is None:
            continue
        rows = read_rows(path)
        p = sum(bool(r.get('perturbed')) for r in rows)
        out[rid] = dict(rows=len(rows), perturbed=p, ratio=p / len(rows) if rows else None)
    return out


# ------------------------------------------------------------------ report

def ks_2samp(a, b):
    """Two-sample KS statistic and asymptotic two-sided p (Kolmogorov series)."""
    a, b = sorted(a), sorted(b)
    if not a or not b:
        return dict(n1=len(a), n2=len(b), D=None, p=None)
    i = j = 0
    d = 0.
    while i < len(a) and j < len(b):
        x = min(a[i], b[j])
        while i < len(a) and a[i] <= x:
            i += 1
        while j < len(b) and b[j] <= x:
            j += 1
        d = max(d, abs(i / len(a) - j / len(b)))
    ne = len(a) * len(b) / (len(a) + len(b))
    lam = (math.sqrt(ne) + .12 + .11 / math.sqrt(ne)) * d
    p = 0. if lam > 0 else 1.
    if lam > 0:
        p = 2 * sum((-1) ** (k - 1) * math.exp(-2 * k * k * lam * lam) for k in range(1, 101))
    return dict(n1=len(a), n2=len(b), D=d, p=min(1., max(0., p)))


def pair_values(row):
    """One value per pair episode (both robots share the bin, so robots are not independent samples)."""
    s = list((row.get('start') or {}).values())
    if not s:
        return None
    return dict(distance_m=sum(v['distance_m'] for v in s) / len(s),
                abs_yaw_offset_rad=sum(abs(wrap(v['yaw_offset_rad'])) for v in s) / len(s))


def ks_groups(rows):
    groups = dict(physical_failure=[r for r in rows if r['category'] == 'behavior' and not r['success']],
                  success_not_admitted=[r for r in rows if r['success'] and not r['admitted']],
                  admitted=[r for r in rows if r['admitted']])
    vals = {g: [v for v in map(pair_values, rs) if v] for g, rs in groups.items()}
    names = list(groups)
    out = dict(scope='pair-level (mean of the two robots); three groups; informational, not a gate; '
                     'conditional on the adaptive bin allocation',
               n={g: len(v) for g, v in vals.items()}, comparisons={})
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            out['comparisons'][f'{a}__vs__{b}'] = {
                k: ks_2samp([v[k] for v in vals[a]], [v[k] for v in vals[b]])
                for k in ('distance_m', 'abs_yaw_offset_rad')}
    return out


def _bin_table(prereg, st, rows, split):
    min_bin = prereg['bins']['min_admitted_per_bin']
    table = []
    for b in bins(prereg):
        k = b['id']
        rs = [r for r in rows if r['bin'] == k]
        c = tally(rs)
        fails = Counter(f"{r['failure_stage']}:{r['eval_failure']}:{r['carry_outcome']}"
                        for r in rs if r['category'] == 'behavior' and not r['success'])
        table.append(dict(bin=k, distance_m=b['distance_m'], yaw=b['yaw'], **c,
                          success_rate=c['successes'] / c['attempts'] if c['attempts'] else None,
                          admitted_rate=c['admitted'] / c['attempts'] if c['attempts'] else None,
                          need=max(0, min_bin - c['admitted']), bin_limited=k in st['limited'],
                          setup_rejections=sum(s['bin'] == k and s['split'] == split for s in st['setup_rows']),
                          failure_subreasons=dict(fails)))
    return table


def report(prereg, st, *, prereg_sha, prereg_core=None):
    h = require_header_sha(st, prereg_sha, prereg_core)
    mode = h['mode']
    out = dict(schema=REPORT_SCHEMA, prereg_sha256=h['prereg_sha256'], mode=mode, noise=h['noise'],
               purpose=h.get('purpose'), freeze_stage=h.get('freeze_stage'), core_sha256=h.get('core_sha256'),
               unit='pair episode (N attempts, S physical successes, A admitted, E environment failures not in N)',
               run_state=run_state(prereg, st),
               setup_rejections=dict(n=len(st['setup_rows']),
                                     by_bin=dict(Counter(f"{s['split']}:{s['bin']}" for s in st['setup_rows']))),
               not_pooled_with=['B teacher gate n/40', 'C student n/20', 'P2 smoke', 'r13 gate', 'CPU results',
                                'pilot vs training run'])
    if mode == 'measurement':
        rows = split_rows(st, 'pilot')
        t = tally(rows)
        out['pilot'] = dict(
            text=f"pilot 수율 측정: 물리 성공 {t['successes']} / 시도 {t['attempts']}, 채택 후보 {t['admitted']} / "
                 f"시도 {t['attempts']} (수율 측정, 시연 아님: 녹화 없음, 텐서 없음); 환경 실패 {t['env_failures']} 별도",
            **t, bins=_bin_table(prereg, st, rows, 'pilot'))
        out['ks'] = ks_groups(rows)
        return out
    rows = split_rows(st, 'train')
    t = tally(rows)
    out['A'] = dict(
        text=f"교사 시연 수집(적응형 구간 배정, pair episode): 물리 성공 {t['successes']} / 시도 {t['attempts']}, "
             f"최종 채택 {t['admitted']} / 시도 {t['attempts']} (데이터 필터용, 학습 결과 아님; 채택 목표 200은 분모가 아님); "
             f"환경 실패 {t['env_failures']} 별도",
        **t, bins=_bin_table(prereg, st, rows, 'train'),
        by_seed_phase={ph: dict(**tally([r for r in rows if seed_phase(prereg, r['seed']) == ph]),
                                bins=_bin_table(prereg, st, [r for r in rows if seed_phase(prereg, r['seed']) == ph], 'train'))
                       for ph in ('primary', 'extension')},
        bin_limited=list(st['limited'].values()))
    val = split_rows(st, 'validation')
    v = tally(val)
    n_val = len(pool(prereg, 'validation'))
    out['validation'] = dict(text=f"validation: 물리 성공 {v['successes']} / {n_val}, 채택 {v['admitted']} / {n_val} "
                                  f"(환경 실패 {v['env_failures']} 별도)", **v)
    out['ks'] = ks_groups(rows)
    out['distance_gate'] = distance_gate(prereg, st)
    out['decision'] = decision(prereg, st)
    out['data_range_limited'] = bool(out['decision']['limited_bins']) and out['decision']['decision'] in TRAINABLE
    out['result_labels'] = out['decision']['labels']
    out['recover_rows_admitted'] = sum((r.get('sidecar') or {}).get('recover_rows', 0) for r in rows if r['admitted'])
    return out


# ------------------------------------------------ recording-mode check inputs

CHECK_ROW_KEYS = ('status', 'physical_success', 'execution_host', 'source_sha', 'teacher_profile', 'action_contract',
                  'self_pose_source', 'episode_plan_sha256', 'observation_sampling', 'teacher_stability',
                  'teacher_search', 'approach_goal_set', 'nominal_blocked_handoff', 'approach_progress',
                  'approach_recovery', 'approach_coordination', 'handoff_observation')


def probe_slots(st, n=3):
    """First n admitted pilot successes (ledger order): the starts re-run with recording probe."""
    rows = [r for r in st['attempt_rows'] if r['split'] == 'pilot' and r['admitted']][:n]
    if len(rows) < n:
        raise ValueError(f'need {n} admitted pilot successes for the recording-mode check, have {len(rows)}')
    return rows


def check_row(result, seed, search15_keys=()):
    """One row for teacher harness.grasp_act_admission.recording_mode_equivalence (index = seed)."""
    row = {k: result.get(k) for k in CHECK_ROW_KEYS if k in result}
    row.update({k: result[k] for k in search15_keys if k in result})
    row.update(index=int(seed), exit=0 if result.get('status') == 'complete' else 1)
    return row


def _index_list(rows):
    return [r.get('index') if isinstance(r, dict) else None for r in rows] if isinstance(rows, list) else None


def _case_seeds(cases):
    return [_dig(c, ('plan', 'seed')) for c in cases] if isinstance(cases, list) else None


def check_rows_binding(st, core, probe_cases_path, baseline, recorded):
    """v5 (Codex v4 re-review 1): what check-rows.json records so the final gate can tie the recording check to
    the current core: the FROZEN_CORE probe source ledger (purpose, core, first admitted seeds), the sha256 of
    the probe-cases.json those seeds became, and the same seeds in baseline / recorded order."""
    h = require_probe_source(st, core)
    seeds = [r['seed'] for r in probe_slots(st)]
    if _case_seeds(json.loads(Path(probe_cases_path).read_text())) != seeds:
        raise ValueError(f'probe-cases.json seeds differ from the probe source ledger seeds {seeds}')
    if _index_list(baseline) != seeds or _index_list(recorded) != seeds:
        raise ValueError(f'check rows baseline / recorded seeds differ from the probe source seeds {seeds}')
    return dict(core_sha256=core, probe_cases_sha256=file_sha256(probe_cases_path),
                probe_source=dict(purpose=h['purpose'], core_sha256=h['core_sha256'], seeds=seeds))


def recording_binding_problems(recording_dir, core):
    """v5 (Codex v4 re-review 1): the final gate ties the three recording files to the current core.

    check-rows.json core_sha256 and its probe_source (a probe_source ledger of this core) == ``core``;
    probe_cases_sha256 hashes the probe-cases.json beside it (training candidate cases); probe source seeds ==
    probe-cases seeds == baseline / recorded indices (same order); recording-check.json indices / N == those
    seeds.  Evidence produced under another core (a revised manifest / prereg) is refused."""
    d = Path(recording_dir)
    try:
        cases, rows, check = (json.loads((d / RECORDING_FILES[k]).read_text()) for k in RECORDING_FIELDS)
    except (OSError, ValueError) as error:
        return [f'recording evidence in {d} unreadable: {error}']
    if not (isinstance(cases, list) and isinstance(rows, dict) and isinstance(check, dict)):
        return [f'recording evidence in {d}: probe-cases list, check-rows / recording-check objects required']
    out = []
    if rows.get('core_sha256') != core:
        out.append(f'check-rows.json core_sha256 {rows.get("core_sha256")} != current core {core} '
                   '(recording evidence of another core)')
    src = rows.get('probe_source') if isinstance(rows.get('probe_source'), dict) else {}
    if src.get('purpose') != PURPOSE_PROBE_SOURCE or src.get('core_sha256') != core:
        out.append(f'check-rows.json probe_source {src.get("purpose")!r}/{src.get("core_sha256")} is not a '
                   f'{PURPOSE_PROBE_SOURCE} ledger of the current core')
    if rows.get('probe_cases_sha256') != file_sha256(d / RECORDING_FILES['probe_cases_sha256']):
        out.append('check-rows.json probe_cases_sha256 does not hash the probe-cases.json beside it')
    if any(not isinstance(c, dict) or c.get('candidate') != CANDIDATE_BY_MODE['training'] for c in cases):
        out.append(f'probe-cases.json: every case needs candidate {CANDIDATE_BY_MODE["training"]}')
    seeds = _case_seeds(cases)
    if not seeds or not (seeds == src.get('seeds') == _index_list(rows.get('baseline')) ==
                         _index_list(rows.get('recorded'))):
        out.append('probe source / probe-cases / check-rows baseline / recorded seeds differ')
    if not seeds or sorted(check.get('indices') or []) != sorted(seeds) or check.get('N') != len(seeds):
        out.append('recording-check.json indices / N do not match probe-cases.json')
    return out


# ------------------------------------------------------- convert hand-off

def convert_input(prereg, st, out_dir, *, prereg_sha, teacher_sha, run_pattern='seed-{seed}', core=None):
    """Symlink admitted train/validation episodes into the grasp_act_data.convert layout (originals untouched).

    Only a finished training ledger with decision TRAIN / TRAIN_DATA_RANGE_LIMITED under the same
    prereg sha is accepted.  seed-<seed>/{SOURCE_SHA, EXIT, raw -> <batch>/try-N/world-XXX/raw}.
    """
    h = require_header_sha(st, prereg_sha)
    if h.get('purpose') == PURPOSE_PILOT:
        raise ValueError('pilot_yield_only ledger is never a training input')
    if h['mode'] != 'training':
        raise ValueError('convert input needs a training-mode ledger (measurement runs have no tensors)')
    if core is not None and (h.get('freeze_stage') != 'FROZEN' or h.get('core_sha256') != core):
        raise ValueError('convert input needs a FROZEN training ledger bound to the current core_sha256')
    check_attempt_identity(st)
    d = decision(prereg, st)
    if d['decision'] not in TRAINABLE or d['validation'] in (None, 'pending'):
        raise ValueError(f'convert input refused: decision {d["decision"]}, validation {d["validation"]}')
    missing = [r['raw'] for r in st['attempt_rows'] if r['admitted'] and r['split'] in ('train', 'validation')
               and not (r.get('raw') and Path(r['raw']).is_dir())]
    if missing:
        raise ValueError(f'convert input refused: {len(missing)} admitted world raw directories missing '
                         f'(copy them to this host first), e.g. {missing[0]}')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    train, val = [], []
    for r in st['attempt_rows']:
        if not r['admitted'] or r['split'] not in ('train', 'validation'):
            continue
        p = out_dir / run_pattern.format(seed=r['seed'])
        p.mkdir()
        (p / 'SOURCE_SHA').write_text(teacher_sha + '\n')
        (p / 'EXIT').write_text('0\n')
        (p / 'raw').symlink_to(Path(r['raw']).resolve(), target_is_directory=True)
        (train if r['split'] == 'train' else val).append(r['seed'])
    protocol = dict(train_seeds=sorted(train), validation_seeds=sorted(val), run_pattern=run_pattern,
                    teacher_sha=teacher_sha, prereg_sha256=prereg_sha, core_sha256=h.get('core_sha256'),
                    decision=d['decision'],
                    data_range_limited=bool(d['limited_bins']), small_data=d['decision'] == 'TRAIN_SMALL_DATA',
                    result_labels=d['labels'], limited_bins=d['limited_bins'],
                    admission='pairact_r1 success_only_v2 (COLLECT_PREREG v2)')
    (out_dir / 'protocol.json').write_text(json.dumps(protocol, indent=1) + '\n')
    return protocol




# --------------------------------------------------------- run manifest (v3, Codex v2 B1/B2/B3)

MANIFEST_SCHEMA = 'ugrp.pairact_r1.run_manifest.v2'
# Collector files fixed by the freeze (B1): runner code, its direct setup-geometry imports and inputs.
# They must be identical between collector.source_sha (commit X) and the checkout HEAD.
COLLECTOR_FILES = (
    'harness/pairact_collect.py', 'harness/pairact_r1.py', 'scripts/run_pairact_collect.py',
    'scripts/pairact_r1_freeze.py', 'scripts/check_pairact_r1_seeds.py',
    'experiments/2026-10-21-pairact-r1/seeds.json',
    'harness/static_keepouts.py', 'harness/zone_final_environment.py', 'sim/zone_cargo.py', 'sim/zone_arena.py',
    'experiments/2026-10-17-beamact5/teacher/wide_start.py', 'experiments/2026-10-15-beampair1/scenario-v7.json')
GENERATOR_FILE = 'experiments/2026-10-21-pairact-r1/collect_cases.py'
PLACEHOLDER_PATTERNS = (VM_FILL, '[확인 필요]', '[-c3 SHA 기입]', '기입]')
_ANGLE = __import__('re').compile(r'<[^<>\s]{1,60}>')
_HEX = __import__('re').compile(r'[0-9a-f]+')


def _sha64(v):
    return isinstance(v, str) and len(v) == 64 and bool(_HEX.fullmatch(v))


def _git40(v):
    return isinstance(v, str) and len(v) == 40 and bool(_HEX.fullmatch(v))


def _text(v):
    return isinstance(v, str) and bool(v.strip())


def _int(v):
    return type(v) is int


def _num(v):
    return type(v) in (int, float)


def _sha_map(v):
    return isinstance(v, dict) and bool(v) and all(_text(k) and _sha64(x) for k, x in v.items())


def _abs_sha_map(v):
    return _sha_map(v) and all(os.path.isabs(k) for k in v)


def _smoke_worlds(v):
    return isinstance(v, dict) and set(v) == {'world-000', 'world-001', 'world-002'} and all(map(_sha64, v.values()))


def _text_list(v):
    return isinstance(v, list) and bool(v) and all(map(_text, v))


def _assignment(v):
    return isinstance(v, dict) and bool(v) and all(_text(k) and isinstance(x, list) and bool(x) and all(map(_int, x))
                                                   for k, x in v.items())


def _vm_recording(v):
    return isinstance(v, dict) and all(_text(k) and isinstance(x, dict) and set(x) == set(RECORDING_FIELDS)
                                       and all(map(_sha64, x.values())) for k, x in v.items())


def _stack_entry():
    return dict(branch=_text, sha=_git40, note=_text)


# Fixed schema: every key, nothing extra (B3).  VM-fill fields (23, v7) are marked with VM_FIELDS below.
MANIFEST_SPEC = dict(
    schema=_text, status=_text, freeze_rule=_text,
    prereg=dict(path=_text, schema=_text, core_sha256=_sha64),
    stack=dict(teacher=_stack_entry(), adapter=_stack_entry(), root=_stack_entry(), pin_rule=_text),
    collector=dict(branch=_text, source_sha=_git40, files_rule=_text, file_sha256=_sha_map),
    generator=dict(file=_text, file_sha256=_sha64, base_generator=_text, scenario=_text, scene_profile=_text,
                   proposal_budget=_int, placement_filter=_text),
    command=dict(batch_size=_int, max_batches_per_night=_text, episode_template_draft=_text,
                 episode_template=_text, episode_template_sha256=_sha64),
    limits=dict(grasp_cap_sim_s=_num, carry_cap_sim_s=_num, episode_cap_sim_s=_num, planning_wall_safety_cap=_text,
                speed_gate=_text, attempt_cap=_int, pilot_seeds=_int, validation_seeds=_int,
                max_tries_per_batch=_int, host_error_requeue=_int),
    assets=dict(canonical_xml_sha256=_sha64, per_world_model_references_sha256=_sha64,
                per_world_reference_files_sha256=_sha64,
                rejection_table_input_sha256=_sha64, mesh_assets_sha256=_abs_sha_map, wrapper_sha256=_sha64),
    host=dict(machine=_text, gpu=_text, cuda_warp_mujoco=_text, python=_text, warp_kernel_cache=_text),
    smoke=dict(run=_text, summary_sha256=_sha64, carry_eval_sha256=_smoke_worlds, artifact_manifest_sha256=_sha64,
               world1_raw_result_sha256=_sha64, report_file=_text, report_file_sha256=_sha64,
               video_sha256=_sha_map),
    recording_check=dict(function=_text, probe_cases_sha256=_sha64, check_rows_sha256=_sha64,
                         recording_check_sha256=_sha64, scope=_text),
    seed_check=dict(local_2026_10_21=_text, vm_seed_check_sha256=_sha64),
    sharding=dict(rule=_text, count=_int, lag_batches=_int, assignment=_assignment, primary_vm=_text,
                  vm_recording_check=_vm_recording),
    fill_commands=_text_list)
VM_FIELDS = ('prereg.core_sha256', 'collector.source_sha', 'command.episode_template',
             'command.episode_template_sha256', 'assets.canonical_xml_sha256',
             'assets.per_world_model_references_sha256', 'assets.per_world_reference_files_sha256',
             'assets.rejection_table_input_sha256',
             'assets.mesh_assets_sha256', 'assets.wrapper_sha256', 'host.machine', 'host.gpu',
             'host.cuda_warp_mujoco', 'host.python', 'host.warp_kernel_cache', 'smoke.summary_sha256',
             'smoke.carry_eval_sha256', 'smoke.artifact_manifest_sha256', 'smoke.world1_raw_result_sha256',
             'recording_check.probe_cases_sha256', 'recording_check.check_rows_sha256',
             'recording_check.recording_check_sha256', 'seed_check.vm_seed_check_sha256')
RECORDING_PATHS = tuple(f'recording_check.{k}' for k in RECORDING_FIELDS) + ('sharding.vm_recording_check',)


def manifest_unfilled(value, path=''):
    """Paths of every '[VM 기입]' left in RUN_MANIFEST.json."""
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in manifest_unfilled(v, f'{path}.{k}' if path else k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in manifest_unfilled(v, f'{path}[{i}]')]
    return [path] if isinstance(value, str) and VM_FILL in value else []


def manifest_placeholders(value, path=''):
    """Paths of any placeholder string ([VM 기입], [확인 필요], [-c3 SHA 기입], <...>)."""
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in manifest_placeholders(v, f'{path}.{k}' if path else k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in manifest_placeholders(v, f'{path}[{i}]')]
    if isinstance(value, str) and (any(m in value for m in PLACEHOLDER_PATTERNS) or _ANGLE.search(value)):
        return [path]
    return []


def _bracket_placeholders(value, path=''):
    """[VM 기입] / [확인 필요] / [... 기입] in the prereg (its <rid>/<seed> notation is not a placeholder)."""
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _bracket_placeholders(v, f'{path}.{k}' if path else k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _bracket_placeholders(v, f'{path}[{i}]')]
    return [path] if isinstance(value, str) and any(m in value for m in PLACEHOLDER_PATTERNS) else []


def _schema_problems(value, spec, path, skip):
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            return [f'{path or "manifest"}: object required']
        out = [f'missing {path + "." if path else ""}{k}' for k in spec if k not in value]
        out += [f'unexpected {path + "." if path else ""}{k}' for k in value if k not in spec]
        for k, sub in spec.items():
            if k in value:
                out += _schema_problems(value[k], sub, f'{path}.{k}' if path else k, skip)
        return out
    if path in skip:
        return []
    return [] if spec(value) else [f'invalid {path}: {spec.__name__.strip("_")} required, got {value!r:.80}']


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collector_provenance(repo, source_sha, files):
    """B1: source_sha (commit X) is an ancestor of HEAD and no fixed collector file changed X..HEAD or is dirty."""
    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True)
    problems = []
    if not _git40(source_sha):
        return [f'collector.source_sha {source_sha!r:.60} is not a 40-hex commit']
    if git('cat-file', '-e', f'{source_sha}^{{commit}}').returncode:
        return [f'collector.source_sha {source_sha} not in this repository']
    if git('merge-base', '--is-ancestor', source_sha, 'HEAD').returncode:
        problems.append(f'collector.source_sha {source_sha} is not an ancestor of HEAD')
    changed = git('diff', '--name-only', source_sha, 'HEAD', '--', *files)
    if changed.returncode or changed.stdout.strip():
        problems.append('collector files changed since collector.source_sha: ' + changed.stdout.strip().replace('\n', ','))
    dirty = git('status', '--porcelain', '--untracked-files=no', '--', *files)
    if dirty.stdout.strip():
        problems.append('collector files dirty in the checkout: ' + dirty.stdout.strip().replace('\n', ','))
    return problems


def episode_assets(template):
    """Asset paths named by the expanded episode command (wrapper, canonical xml, references, rejection table)."""
    tokens = shlex.split(template)

    def flag(name):
        return episode_option(tokens, name)
    wrapper = next((t for t in tokens if t.endswith('.py')), None)
    return dict(wrapper_sha256=wrapper, canonical_xml_sha256=flag('--canonical-xml'),
                per_world_model_references_sha256=flag('--per-world-model-references-v1'),
                rejection_table_input_sha256=flag('--rejection-table'))


# v5 (Codex v4 re-review 2): MuJoCo XML file references.  mesh / skin / hfield resolve under compiler meshdir,
# texture (incl. the six cube faces) under texturedir; assetdir sets both when the specific one is unset;
# strippath keeps the file name only; include and <model file> resolve against the main model directory.
XML_FILE_ATTRS = {'mesh': ('file',), 'skin': ('file',), 'hfield': ('file',),
                  'texture': ('file', 'fileright', 'fileleft', 'fileup', 'filedown', 'filefront', 'fileback')}
XML_MESHDIR_TAGS = ('mesh', 'skin', 'hfield', 'flexcomp')
XML_FILE_ATTRS['flexcomp'] = ('file',)     # v7: flexcomp file (mesh / gmsh) resolves under meshdir like <mesh>


def xml_dependencies(xml_path, base=None):
    """Every file a MuJoCo XML pulls in (includes recursively, assets, sub-models): sorted absolute paths.
    Raises ET.ParseError / OSError on an unreadable file and ValueError on an include cycle.

    v7: ``base`` is the directory relative names resolve against -- the XML's directory for
    ``from_xml_path`` (default), the compiling process's cwd for ``from_xml_string`` (the teacher reads
    --canonical-xml as text; see episode_xml_problems)."""
    main = Path(os.path.realpath(xml_path))
    base, deps, elements = (main.parent if base is None else Path(os.path.realpath(base))), set(), []

    def at(directory, name):
        return os.path.realpath(name if os.path.isabs(name) else base / (directory or '') / name)

    def expand(path, chain):
        for el in ET.parse(path).getroot().iter():
            if el.tag == 'include' and el.get('file'):
                inc = at(None, el.get('file'))
                if inc in chain:
                    raise ValueError(f'include cycle at {inc}')
                deps.add(inc)
                expand(inc, chain | {inc})
            else:
                elements.append(el)
    expand(main, {str(main)})
    comp = {}
    for el in elements:
        if el.tag == 'compiler':
            comp.update(el.attrib)
    strip = comp.get('strippath', 'false').lower() == 'true'
    dirs = dict(mesh=comp.get('meshdir', comp.get('assetdir')), texture=comp.get('texturedir', comp.get('assetdir')))
    for el in elements:
        for attr in XML_FILE_ATTRS.get(el.tag, ()):
            name = el.get(attr)
            if name:
                name = os.path.basename(name) if strip else name
                deps.add(at(dirs['mesh' if el.tag in XML_MESHDIR_TAGS else 'texture'], name))
        if el.tag == 'model' and el.get('file'):
            sub = at(None, el.get('file'))
            deps.add(sub)
            deps.update(xml_dependencies(sub))
    return sorted(deps)


def xml_asset_problems(xml_path, registered):
    """v5: assets.mesh_assets_sha256 must list exactly the files the canonical XML references (no omission, no
    unrelated decoy); their hashes are compared separately."""
    try:
        deps = set(xml_dependencies(xml_path))
    except (ET.ParseError, OSError, ValueError) as error:
        return [f'canonical XML dependencies unreadable: {error}']
    reg = {os.path.realpath(k) for k in registered}
    out = []
    if deps - reg:
        out.append('assets.mesh_assets_sha256 misses files the canonical XML references: ' + ', '.join(sorted(deps - reg)))
    if reg - deps:
        out.append('assets.mesh_assets_sha256 lists files the canonical XML does not reference: '
                   + ', '.join(sorted(reg - deps)))
    return out


# v7 (Codex v6 re-review 2b): the per-world model references JSON is only a pointer file.  The wrapper reads it as
# {scene-xml sha256: {actuator, geometry}} and opens Path(actuator), Path(geometry) and the geometry sidecar
# str(geometry) + '.json' (simalt_compiled_compat.apply_reference / apply_geometry) -- relative paths against its
# own cwd, not the JSON's directory.  Hashing the JSON alone left those model inputs free under one core, so the
# manifest binds a transitive digest of every file it names.  Root = the directory of the references JSON.
PER_WORLD_REF_KEYS = ('actuator', 'geometry')
GEOMETRY_SIDECAR_SUFFIX = '.json'


def _no_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError('per-world references JSON repeats a key (json.loads would keep the last one)')
    return dict(pairs)


def per_world_reference_files(refs_path):
    """The single reading of the per-world references JSON: sorted (path relative to the JSON's directory,
    absolute path) of every model-input file it makes the wrapper open (actuator, geometry, geometry sidecar).
    Raises ValueError for a format the wrapper could resolve differently or a path that leaves the root:
    a relative JSON path, duplicate keys, other keys, relative or '..' paths, a path outside the JSON's directory, a symlink at the
    JSON or on any component below the root.  Missing files are reported by per_world_reference_digest."""
    if not os.path.isabs(refs_path):
        raise ValueError(f'--per-world-model-references-v1 must be an absolute path, got {str(refs_path)!r}')
    refs_path = os.path.normpath(refs_path)
    root = os.path.dirname(refs_path)
    if os.path.islink(refs_path):
        raise ValueError(f'per-world references JSON is a symlink: {refs_path}')
    refs = json.loads(Path(refs_path).read_bytes(), object_pairs_hook=_no_duplicate_keys)
    if not isinstance(refs, dict):
        raise ValueError('per-world references JSON must be an object {xml_sha256: {actuator, geometry}}')
    files = set()
    for key, entry in refs.items():
        if not _sha64(key):
            raise ValueError(f'per-world references key {key!r:.80} is not a scene XML sha256')
        if not isinstance(entry, dict) or set(entry) != set(PER_WORLD_REF_KEYS):
            raise ValueError(f'per-world references[{key[:12]}] must have exactly {PER_WORLD_REF_KEYS}')
        for role in PER_WORLD_REF_KEYS:
            path = entry[role]
            if not isinstance(path, str) or not path:
                raise ValueError(f'per-world references[{key[:12]}].{role} must be a path string')
            if not os.path.isabs(path) or '..' in Path(path).parts or os.path.normpath(path) != path:
                raise ValueError(f'per-world references[{key[:12]}].{role} must be a normalized absolute path '
                                 f'(the wrapper resolves it against its cwd): {path!r}')
            names = [path] + ([path + GEOMETRY_SIDECAR_SUFFIX] if role == 'geometry' else [])
            for name in names:
                if os.path.commonpath([root, name]) != root:
                    raise ValueError(f'per-world reference outside {root}: {name}')
                walk = root
                for part in Path(os.path.relpath(name, root)).parts:
                    walk = os.path.join(walk, part)
                    if os.path.islink(walk):
                        raise ValueError(f'per-world reference goes through a symlink: {walk}')
                if os.path.commonpath([os.path.realpath(root), os.path.realpath(name)]) != os.path.realpath(root):
                    raise ValueError(f'per-world reference resolves outside {root}: {name}')
                files.add((os.path.relpath(name, root), name))
    return sorted(files)


def per_world_reference_digest(refs_path):
    """assets.per_world_reference_files_sha256: sha256 of the canonical sorted [[relative path, sha256], ...] of
    per_world_reference_files.  Raises ValueError on a refused reference or a missing / non-regular file."""
    rows = []
    for rel, path in per_world_reference_files(refs_path):
        if not os.path.isfile(path):
            raise ValueError(f'per-world reference file missing: {path}')
        rows.append([rel, file_sha256(path)])
    return hashlib.sha256(canonical(rows)).hexdigest()


def sharding_problems(manifest, *, stage, shard=None):
    """v3s: shard count / VM assignment of the run (core) and, at final, one recording check per extra VM.

    ``shard`` = (index, count, vm) of a training collection process (serial: (0, 1, None)).
    """
    sh = manifest.get('sharding')
    if not isinstance(sh, dict) or not _int(sh.get('count')) or not _assignment(sh.get('assignment')):
        return []                     # schema problems are reported by _schema_problems
    out, count, assign = [], sh['count'], sh['assignment']
    if count > MAX_SHARDS:
        out.append(f'sharding.count {count} > {MAX_SHARDS} (owner decision D-v4-1: K <= {MAX_SHARDS})')
    flat = [i for v in assign.values() for i in v]
    if sorted(flat) != list(range(count)):
        out.append(f'sharding.assignment must cover shards 0..{count - 1} exactly once, got {sorted(flat)}')
    if sh.get('lag_batches') != count:
        out.append('sharding.lag_batches must equal sharding.count')
    if sh.get('primary_vm') not in assign:
        out.append('sharding.primary_vm must be a key of sharding.assignment (the VM of host.* / recording_check)')
    if stage == 'final' and isinstance(sh.get('vm_recording_check'), dict) and \
            set(sh['vm_recording_check']) != set(assign) - {sh.get('primary_vm')}:
        out.append('sharding.vm_recording_check needs exactly the non-primary VMs of sharding.assignment')
    if shard is not None:
        index, n, vm = shard
        if n != count:
            out.append(f'shard count {n} != sharding.count {count}')
        if vm is not None and vm not in assign:
            out.append(f'vm {vm!r} not in sharding.assignment')
        elif index not in assign.get(vm if vm is not None else sh.get('primary_vm'), []):
            out.append(f'shard {index} is not assigned to vm {vm if vm is not None else sh.get("primary_vm")!r}')
    return out


def recording_hashes_for(manifest, vm=None):
    """The recording_check hashes that bind recording on ``vm`` (None / primary: recording_check)."""
    sh = manifest.get('sharding') or {}
    if vm is None or vm == sh.get('primary_vm'):
        return manifest.get('recording_check') or {}
    return (sh.get('vm_recording_check') or {}).get(vm) or {}


def check_run_manifest(manifest, *, stage, prereg, batch_size=None, episode=None, repo=None,
                       recording_dir=None, verify_assets=False, shard=None, episode_cwd=None):
    """Freeze gate (B3).  stage 'core' (probe source / probe / check rows) or 'final' (training / convert).

    Fixed schema with types for every field, no placeholder anywhere, prereg / manifest status
    agree, prereg core sha256, command / batch / limits bound to this run, collector provenance
    (B1, when ``repo`` is given), asset files re-hashed (``verify_assets``), and for 'final' the
    three recording_check files in ``recording_dir`` hash to the manifest values.  Returns core_sha256.
    """
    if manifest.get('schema') != MANIFEST_SCHEMA:
        raise ValueError(f'run manifest schema {MANIFEST_SCHEMA} required')
    if stage not in ('core', 'final'):
        raise ValueError('stage core or final')
    skip = RECORDING_PATHS if stage == 'core' else ()
    problems = _schema_problems(manifest, MANIFEST_SPEC, '', skip)
    problems += [f'placeholder {p}' for p in manifest_placeholders(manifest)
                 if not (stage == 'core' and p in RECORDING_PATHS)]
    problems += [f'placeholder in prereg {p}' for p in _bracket_placeholders(prereg)]
    problems += sharding_problems(manifest, stage=stage, shard=shard)
    allowed = FREEZE_STAGES if stage == 'core' else ('FROZEN',)
    if manifest.get('status') not in allowed:
        problems.append(f'run manifest status {manifest.get("status")!r} not in {allowed}')
    if prereg.get('status') != manifest.get('status'):
        problems.append(f'prereg status {prereg.get("status")!r} != manifest status {manifest.get("status")!r}')
    m = lambda *keys: _dig(manifest, keys)
    if m('prereg', 'schema') != prereg.get('schema'):
        problems.append('run manifest prereg schema differs')
    if m('prereg', 'core_sha256') != prereg_core_sha256(prereg):
        problems.append('run manifest prereg core sha256 differs')
    if isinstance(m('collector', 'file_sha256'), dict) and set(m('collector', 'file_sha256')) != set(COLLECTOR_FILES):
        problems.append('run manifest collector.file_sha256 must list exactly COLLECTOR_FILES')
    if m('generator', 'file') != GENERATOR_FILE:
        problems.append(f'run manifest generator.file must be {GENERATOR_FILE}')
    template = m('command', 'episode_template')
    if isinstance(template, str):
        if hashlib.sha256(template.encode()).hexdigest() != m('command', 'episode_template_sha256'):
            problems.append('command.episode_template_sha256 is not sha256(command.episode_template)')
        if '$' in template:
            problems.append('command.episode_template has an unexpanded shell variable')
        problems += episode_option_problems(template)
        problems += episode_command_problems(template, strict=True)   # v7 risk 2 + b: form + wrapper parser
        problems += episode_allowlist_problems(template)    # v7 a: only options whose value the core binds
    if episode is not None and m('command', 'episode_template_sha256') != episode['template_sha256']:
        problems.append('run manifest episode template sha256 differs')
    if episode is not None and m('limits', 'grasp_cap_sim_s') != episode['cap_s']:
        problems.append('limits.grasp_cap_sim_s differs from the episode --cap-s')
    if batch_size is not None and m('command', 'batch_size') != batch_size:
        problems.append('run manifest batch size differs')
    s = prereg.get('seeds', {})
    for key, want in (('attempt_cap', _dig(prereg, ('targets', 'attempt_cap'))),
                      ('pilot_seeds', _span_len(s.get('pilot'))), ('validation_seeds', _span_len(s.get('validation')))):
        if m('limits', key) != want:
            problems.append(f'limits.{key} {m("limits", key)!r} != prereg {want!r}')
    if repo is not None:
        files = list(COLLECTOR_FILES) + [GENERATOR_FILE]
        problems += collector_provenance(repo, m('collector', 'source_sha'), files)
        for rel, want in dict(m('collector', 'file_sha256') or {}, **{GENERATOR_FILE: m('generator', 'file_sha256')}).items():
            path = Path(repo) / rel
            if not path.is_file() or file_sha256(path) != want:
                problems.append(f'file sha256 differs from the manifest: {rel}')
    if verify_assets and isinstance(template, str) and not episode_option_problems(template):
        for key, path in episode_assets(template).items():
            if key == 'wrapper_sha256':         # v8: the absolute symlink-free file the runner pins and runs
                try:
                    got = resolve_episode_wrapper(template)[0]['sha256']
                except ValueError as error:
                    problems.append(f'asset for assets.wrapper_sha256 refused: {error}')
                else:
                    if got != m('assets', key):
                        problems.append(f'assets.wrapper_sha256 differs from {path}')
                continue
            if path is None or not os.path.isfile(path):
                problems.append(f'asset for assets.{key} missing: {path}')
            elif file_sha256(path) != m('assets', key):
                problems.append(f'assets.{key} differs from {path}')
        for path, want in (m('assets', 'mesh_assets_sha256') or {}).items():
            if not os.path.isfile(path) or file_sha256(path) != want:
                problems.append(f'assets.mesh_assets_sha256 differs or missing: {path}')
        problems += episode_source_problems(manifest, template)
        refs = episode_assets(template)['per_world_model_references_sha256']
        if refs is not None:                    # v7 2b: every file the references JSON makes the wrapper open
            try:
                got = per_world_reference_digest(refs)
            except (OSError, ValueError) as error:
                problems.append(f'per-world reference files refused: {error}')
            else:
                if got != m('assets', 'per_world_reference_files_sha256'):
                    problems.append(f'assets.per_world_reference_files_sha256 differs from the files {refs} references')
        xml = episode_assets(template)['canonical_xml_sha256']
        if xml is not None and os.path.isfile(xml) and isinstance(m('assets', 'mesh_assets_sha256'), dict):
            problems += (xml_asset_problems(xml, m('assets', 'mesh_assets_sha256')) if episode_cwd is None else
                         episode_xml_problems(xml, m('assets', 'mesh_assets_sha256'), episode_cwd))
    if stage == 'final':
        if recording_dir is None:
            problems.append('final stage needs the recording check directory')
        else:
            want = recording_hashes_for(manifest, shard[2] if shard else None)
            for key, name in RECORDING_FILES.items():
                path = Path(recording_dir) / name
                if not path.is_file():
                    problems.append(f'recording_check file missing: {path}')
                elif file_sha256(path) != want.get(key):
                    problems.append(f'recording_check.{key} differs from {path}')
            check = Path(recording_dir) / RECORDING_FILES['recording_check_sha256']
            if check.is_file() and json.loads(check.read_text()).get('qualified') is not True:
                problems.append('recording-check.json is not qualified')
            if all((Path(recording_dir) / name).is_file() for name in RECORDING_FILES.values()):
                problems += recording_binding_problems(recording_dir, core_sha256(prereg, manifest))
    if problems:
        raise ValueError(f'run manifest not usable at stage {stage}: ' + '; '.join(problems))
    return core_sha256(prereg, manifest)


def _dig(value, keys):
    for k in keys:
        value = value.get(k) if isinstance(value, dict) else None
    return value


def _span_len(r):
    return r['last'] - r['first'] + 1 if isinstance(r, dict) and 'first' in r else None


# ------------------------------------------------------------- sharding (v3s)
#
# Execution-only change (prereg ``sharding``): K shard processes, batch k owned by shard k % K.
# Batch k is planned with the unchanged plan_batch / allocate / stop rules on a *view*: the plans
# of every batch < k and the results of every batch <= k - K, in the serial ledger order
# (results of batch j - K, then the plan rows of batch j).  K = 1 is the serial ledger row for
# row.  The view only depends on immutable rows, so the plan of batch k is the same whatever the
# wall-clock order of the shards; a shard waits until the view is complete.

# Owner decision D-v4-1 (2026-10-21, before freeze): K <= 3.  With the distance stop deferred until the far
# bins are settled, K = 2 and 3 reproduced the serial decision class on the cross-review fakes, K = 4 did not
# (X7: lagged bin_limit closed B2 / B4 on a seed-periodic fake) -> prereg sharding.K_max.
MAX_SHARDS = 3

SHARD_PLAN_ROWS = ('bin_limited', 'train_barrier', 'train_closed', 'setup_rejected', 'batch_planned', 'batch_skipped',
                   'run_end')
PLAN_DONE_ROWS = ('batch_planned', 'batch_skipped', 'run_end')
RESULT_ROWS = ('attempt', 'batch_done')


def parse_shard(text):
    """'i/K' -> (i, K) with 0 <= i < K."""
    try:
        i, k = (int(x) for x in str(text).split('/'))
    except ValueError:
        raise ValueError(f'--shard i/K required, got {text!r}') from None
    if not (k >= 1 and 0 <= i < k):
        raise ValueError(f'shard {text!r}: need 0 <= i < K')
    return i, k


def owner(batch, count):
    return batch % count


def row_batch(r):
    """Batch index a shard ledger row belongs to (plan rows: the planning boundary)."""
    if r.get('type') in ('setup_rejected', 'bin_limited', 'train_barrier', 'train_closed'):
        return r.get('planning_batch')
    return r.get('batch')


def shard_index(rows):
    """One shard ledger -> plan rows / results per batch, plan-complete and done batch sets."""
    out = dict(header=None, plan={}, results={}, complete={}, done=set(), ingested={}, ended=None)
    for r in rows:
        kind = r.get('type')
        if kind == 'header':
            out['header'] = r
            continue
        j = row_batch(r)
        if kind in SHARD_PLAN_ROWS:
            out['plan'].setdefault(j, []).append(r)
            if kind in PLAN_DONE_ROWS:
                out['complete'][j] = r
                if kind != 'batch_planned':
                    out['done'].add(j)          # a skipped / end boundary has no results to wait for
            if kind == 'run_end':
                out['ended'] = j
        elif kind in RESULT_ROWS:
            out['results'].setdefault(j, []).append(r)
            if kind == 'attempt':
                out['ingested'].setdefault(j, set()).add(r['slot'])
            else:
                out['done'].add(j)
    return out


def check_shard_headers(ledgers, count):
    """Every shard header equal except shard.index / shard.vm; returns the merged-view header."""
    heads = {i: shard_index(rows)['header'] for i, rows in ledgers.items() if rows}
    if not heads:
        return None
    base = None
    for i, h in sorted(heads.items()):
        s = h.get('shard') or {}
        if s.get('index') != i or s.get('count') != count:
            raise ValueError(f'shard {i} ledger header has shard {s}, expected index {i} of {count}')
        common = {k: v for k, v in h.items() if k != 'shard'}
        if base is None:
            base = common
        elif common != base:
            raise ValueError(f'shard {i} ledger header differs from the other shards')
    return dict(base, shard=dict(count=count, lag_batches=count, merged=True))


def _index_all(ledgers, count):
    idx = {i: shard_index(rows) for i, rows in ledgers.items()}
    for i, x in idx.items():
        for j in list(x['plan']) + list(x['results']):
            if j is None or owner(j, count) != i:
                raise ValueError(f'shard {i} ledger has a row of batch {j} (owner {None if j is None else owner(j, count)})')
    return idx


def shard_view(ledgers, count, k=None):
    """Virtual serial ledger (header first) from the shard ledgers.

    ``k`` given: the view that plans batch k -> (rows, inflight) or None while incomplete (a plan of
    some batch < k or a result of some batch <= k - count is not visible yet).  The partial plan
    rows of batch k itself (crash mid-planning) are included, as in a serial ledger.
    ``k`` None: the merged ledger -> (rows, info) with every visible plan and finished result.
    """
    hdr = check_shard_headers(ledgers, count)
    if hdr is None:
        return None
    idx = _index_all(ledgers, count)
    plan = lambda j: idx.get(owner(j, count), {}).get('plan', {}).get(j, [])
    complete = lambda j: j in idx.get(owner(j, count), {}).get('complete', {})
    done = lambda j: j in idx.get(owner(j, count), {}).get('done', set())
    results = lambda j: idx.get(owner(j, count), {}).get('results', {}).get(j, [])
    rows = [hdr]
    if k is not None:
        if any(not complete(j) for j in range(k)) or any(not done(j) for j in range(max(0, k - count + 1))):
            return None
        for j in range(k + 1):
            if j - count >= 0:
                rows += results(j - count)
            rows += plan(j)
        inflight = [j for j in range(max(0, k - count + 1), k)
                    if idx[owner(j, count)]['complete'][j]['type'] == 'batch_planned']
        return rows, inflight
    last = -1
    while complete(last + 1):
        last += 1
    shown = set()
    for j in range(last + 1):
        if j - count >= 0 and done(j - count):
            rows += results(j - count)
            shown.add(j - count)
        rows += plan(j)
    tail = [j for j in range(last + 1) if j not in shown and done(j)]
    for j in tail:
        rows += results(j)
    planned = [j for j in range(last + 1) if idx[owner(j, count)]['complete'][j]['type'] == 'batch_planned']
    ended = next((j for j in range(last + 1) if idx[owner(j, count)]['complete'][j]['type'] == 'run_end'), None)
    return rows, dict(last_planned=last, planned=planned, done=[j for j in planned if done(j)],
                      running=[j for j in planned if not done(j)], ended=ended,
                      finished=ended is not None and all(done(j) for j in planned))


def running_seeds(ledgers, count):
    """(split, seed) -> batches that are planned but not done: the test invariant is <= 1 each."""
    idx = _index_all(ledgers, count)
    out = {}
    for i, x in idx.items():
        for j, r in x['complete'].items():
            if r['type'] == 'batch_planned' and j not in x['done']:
                for s in r['slots']:
                    out.setdefault((s['split'], s['seed']), []).append(j)
    return out


def inflight_train_slots(rows, inflight):
    planned = {r['batch']: r for r in rows if r.get('type') == 'batch_planned'}
    return sum(s['split'] == 'train' for j in inflight for s in planned[j]['slots'])


def boundary_rows(prereg, st, k):
    """Rows the planner appends at planning boundary k before planning (bin_limit_v1, train close)."""
    mode = (st['header'] or {}).get('mode')
    out = []
    if mode == 'training' and not any(b['split'] == 'validation' for b in st['batches'].values()):
        out += [dict(r, planning_batch=k) for r in pending_bin_limits(prereg, st)]
    return out


def stop_control(prereg, st, k, inflight):
    """v4 stop barrier (owner 2026-10-21, xreview B1/B2): the row the planner appends at boundary k, or None.

    The first stop seen on the lagged view (in-flight batches present) writes train_barrier 'hold': no new
    batch is planned until every in-flight batch is done.  On the drained view (no batch in flight, every
    result present) the unchanged train_stop decides once: a stop -> train_closed (fixed; no train result
    can arrive after it), no stop -> train_barrier 'release' and planning resumes exactly as a serial run
    on the same ledger would.  K = 1 never has batches in flight, so a stop is closed at once.
    """
    if (st['header'] or {}).get('mode') != 'training' or st.get('train_closed'):
        return None
    stop = train_stop(prereg, st)
    t = totals(st)
    if inflight:
        if stop is not None and st.get('barrier') is None:
            return dict(type='train_barrier', planning_batch=k, action='hold', stop=stop, inflight=list(inflight),
                        attempts=t['attempts'], admitted=t['admitted'])
        return None
    if stop is not None:
        return dict(type='train_closed', planning_batch=k, stop=stop, attempts=t['attempts'], admitted=t['admitted'],
                    barrier=None if st.get('barrier') is None else st['barrier']['planning_batch'])
    if st.get('barrier') is not None:
        return dict(type='train_barrier', planning_batch=k, action='release', stop=None,
                    held_at=st['barrier']['planning_batch'], held_stop=st['barrier']['stop'],
                    attempts=t['attempts'], admitted=t['admitted'])
    return None


def check_seed_history(rows):
    """Merged ledger audit (v4, xreview R7 / Codex H5): per split a seed is planned fresh at most once
    (batch slot or setup rejection) and re-queued at most once, only after an environment failure of the
    same seed that is visible earlier in the serial-order ledger."""
    fresh, requeued, env = Counter(), Counter(), set()
    for r in rows:
        kind = r.get('type')
        if kind == 'attempt' and r.get('category') == 'environment':
            env.add((r['split'], r['seed']))
        plans = r['slots'] if kind == 'batch_planned' else [r] if kind == 'setup_rejected' else []
        for s in plans:
            key = (s['split'], s['seed'])
            if s.get('requeue'):
                if key not in env:
                    raise ValueError(f'seed {key} re-queued without an earlier environment failure')
                requeued[key] += 1
                if requeued[key] > 1 and kind == 'batch_planned':
                    raise ValueError(f'seed {key} re-queued twice')
            else:
                fresh[key] += 1
                if fresh[key] > 1:
                    raise ValueError(f'seed {key} planned fresh twice')
    return dict(fresh=sum(fresh.values()), requeued=sum(requeued.values()))


def check_attempt_identity(st):
    """v5 (Codex v4 re-review 5): every completed attempt is one planned slot, judged once.

    (batch, slot) appears at most once and names a planned slot with the same seed / split / requeue flag
    and -- v6 (Codex v5 re-review, bin binding) -- the same bin, since bin_counts() and the distance stop trust
    attempt.bin;
    (split, seed, requeue) appears at most once (a seed is judged fresh once and re-queued at most once).
    A duplicated append (ledger damage, double sync) would otherwise count twice in N / S / A.
    Returns the number of attempt rows."""
    slots, ids = set(), set()
    for r in st['attempt_rows']:
        b = st['batches'].get(r.get('batch'))
        planned = next((s for s in (b or {}).get('slots', []) if s.get('slot') == r.get('slot')), None)
        if planned is None or (planned['seed'], planned['split'], bool(planned.get('requeue')), planned.get('bin')) != \
                (r.get('seed'), r.get('split'), bool(r.get('requeue')), r.get('bin')):
            raise ValueError(f'attempt batch {r.get("batch")} slot {r.get("slot")} seed {r.get("seed")} '
                             f'is not that planned slot')
        key, ident = (r['batch'], r['slot']), (r['split'], r['seed'], bool(r.get('requeue')))
        if key in slots or ident in ids:
            raise ValueError(f'duplicate attempt: batch {key[0]} slot {key[1]} / {ident} judged twice')
        slots.add(key)
        ids.add(ident)
    return len(st['attempt_rows'])


STACK_ROLES = ('teacher', 'adapter', 'root')
EPISODE_SOURCE_FLAGS = dict(teacher='--teacher-source', adapter='--adapter-source')


def episode_sources(template, env=None):
    """v5 (Codex v4 re-review 3): the source checkouts the episode command runs: --teacher-source,
    --adapter-source and the root (the wrapper's WARP_SOURCE_ROOT: a ``WARP_SOURCE_ROOT=...`` token of the
    template, else ``env``).  None where the command does not name one."""
    problems = episode_option_problems(template)
    if problems:
        raise ValueError(problems[0])
    tokens = shlex.split(template)

    def flag(name):
        return episode_option(tokens, name)
    root = next((x.split('=', 1)[1] for x in tokens if x.startswith('WARP_SOURCE_ROOT=')), None)
    if root is None and env is not None:
        root = env.get('WARP_SOURCE_ROOT')
    return dict(teacher=flag(EPISODE_SOURCE_FLAGS['teacher']), adapter=flag(EPISODE_SOURCE_FLAGS['adapter']),
                root=root)


def _git_head(path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(path), *args], text=True, stderr=subprocess.DEVNULL).strip()
    return git('rev-parse', 'HEAD'), bool(git('status', '--porcelain', '--untracked-files=no'))


def stack_pin_problems(manifest, role, path, rev_parse=None):
    """The checkout at ``path`` is at RUN_MANIFEST stack.<role>.sha with no tracked change."""
    try:
        head, dirty = (rev_parse or _git_head)(path)
    except (OSError, subprocess.CalledProcessError) as error:
        return [f'stack {role} checkout {path} is not a git checkout: {error}']
    want = _dig(manifest, ('stack', role, 'sha'))
    if head != want:
        return [f'stack {role} checkout {path} is at {head}, RUN_MANIFEST pins {want}']
    return [f'stack {role} checkout {path} has tracked changes'] if dirty else []


def episode_source_problems(manifest, template, rev_parse=None):
    """v5 manifest gate (verify_assets, on the VM): the teacher / adapter (and a template WARP_SOURCE_ROOT) the
    episode command names exist and are at the stack pins."""
    src, out = episode_sources(template), []
    for role in STACK_ROLES:
        path = src[role]
        name = EPISODE_SOURCE_FLAGS.get(role, 'WARP_SOURCE_ROOT')
        if path is None:
            if role != 'root':
                out.append(f'episode template needs {name}')
        elif not os.path.isdir(path):
            out.append(f'episode {name} {path} does not exist')
        else:
            out += stack_pin_problems(manifest, role, path, rev_parse)
    return out


def check_stack_heads(manifest, roots, *, rev_parse=None, env=None):
    """v4 (Codex H4): the teacher / adapter / root checkouts the generator and episodes use must be at
    RUN_MANIFEST stack.<role>.sha with no tracked change.  ``roots`` maps role -> checkout path.

    v5 (Codex v4 re-review 3): they must also *be* the episode sources -- --teacher-source / --adapter-source of
    command.episode_template and the root WARP_SOURCE_ROOT (template token, else ``env``, default os.environ),
    existing and the same realpath; the root may instead hold the wrapper .py itself."""
    template = _dig(manifest, ('command', 'episode_template'))
    if not isinstance(template, str):
        raise ValueError('stack check: RUN_MANIFEST command.episode_template required')
    env = os.environ if env is None else env
    src = episode_sources(template, env)
    src['root'] = resolve_episode_root(template, env)     # v8: token vs env disagreement refused, realpath
    try:                                                    # v8: the pinned wrapper path, never cwd-relative
        wrapper = resolve_episode_wrapper(template)[0]['path']
    except ValueError:
        wrapper = None
    out = {}
    for role in STACK_ROLES:
        path = roots.get(role)
        if path is None:
            raise ValueError(f'stack check: {role} checkout path required')
        ep, name = src[role], EPISODE_SOURCE_FLAGS.get(role, 'WARP_SOURCE_ROOT')
        if ep is None:
            inside = wrapper is not None and wrapper.startswith(os.path.realpath(path) + os.sep)
            if role != 'root' or not inside:
                raise ValueError(f'stack check: the episode command does not name its {role} source ({name})')
        elif not os.path.isdir(ep):
            raise ValueError(f'stack check: episode {role} source {ep} ({name}) does not exist')
        elif os.path.realpath(ep) != os.path.realpath(path):
            raise ValueError(f'stack check: episode {role} source {ep} ({name}) is not the checked {role} checkout {path}')
        problems = stack_pin_problems(manifest, role, path, rev_parse)
        if problems:
            raise ValueError(problems[0])
        out[role] = manifest['stack'][role]['sha']
    return out


# ------------------------------------------------------------- v7 (Codex v6 re-review: risk 2, 1b, XML base)

# Risk 2: the gates read tokens of the template while the runner used to hand the string to a shell.  The
# episode command now has one explicit form, ``[WARP_SOURCE_ROOT=/abs] python[3[.N]] /path/wrapper.py --opt ...``,
# and runs as that argv (no shell): no operators, no env/cd prefix, no standalone ``--``, no short options.
EPISODE_PYTHON = re.compile(r'(?:.*/)?python(?:3(?:\.\d+)?)?')
EPISODE_ASSIGNMENTS = ('WARP_SOURCE_ROOT',)
EPISODE_PLACEHOLDERS = dict(cases='/pairact-placeholder/cases.json', indices='0', out='/pairact-placeholder/out')
REPO_WRAPPER = Path(__file__).resolve().parents[1] / 'experiments/2026-10-17-beamact5/teacher/run_warp_flow_teacher_gcp6.py'


def episode_command_form(template):
    """v7: (assignments, python, wrapper, args) of the one accepted episode command shape; ValueError otherwise."""
    if not isinstance(template, str) or '\n' in template or '`' in template or '$' in template:
        raise ValueError('episode command must be one line without $ / backtick substitutions')
    lex = shlex.shlex(template, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    tokens = list(lex)
    ops = [t for t in tokens if t and set(t) <= set(lex.punctuation_chars)]
    if ops:
        raise ValueError(f'episode command has shell operators {ops}; one wrapper argv only')
    if tokens != shlex.split(template):
        raise ValueError('episode command tokenizes differently with shell operators; quote nothing special')
    assign, i = {}, 0
    while i < len(tokens) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*', tokens[i]):
        name, _, val = tokens[i].partition('=')
        if name not in EPISODE_ASSIGNMENTS or name in assign:
            raise ValueError(f'episode command may only set {EPISODE_ASSIGNMENTS} once, got {name}')
        if not os.path.isabs(val):
            raise ValueError(f'episode command {name} must be absolute, got {val!r}')
        assign[name], i = val, i + 1
    if i >= len(tokens) or not EPISODE_PYTHON.fullmatch(tokens[i]):
        raise ValueError(f'episode command must start with python (no env/cd/sh/exec prefix), got '
                         f'{tokens[i] if i < len(tokens) else None!r}')
    python, rest = tokens[i], tokens[i + 1:]
    if not rest or not rest[0].endswith('.py') or rest[0].startswith('-'):
        raise ValueError('episode command must be python <wrapper.py> (no interpreter options, -c or -m)')
    wrapper, args = rest[0], rest[1:]
    if '--' in args:
        raise ValueError('episode command has a standalone --; argparse would stop reading options there')
    short = [t for t in args if t.startswith('-') and not t.startswith('--') and len(t) > 1
             and not re.fullmatch(r'-\d+(\.\d*)?(e-?\d+)?', t)]
    if short:
        raise ValueError(f'episode command has short options {short}; long options only')
    return assign, python, wrapper, args


class EpisodeParseError(ValueError):
    pass


def wrapper_parser(path, source=None):
    """v7: the wrapper's own ``parser()`` (taken from its source without importing the module, which needs
    WARP_SOURCE_ROOT and the simulator); argparse errors raise EpisodeParseError instead of exiting.
    v8: ``source`` = the bytes already hashed for the pin (read the file only when not given)."""
    import argparse as _argparse
    import ast

    class Parser(_argparse.ArgumentParser):
        def error(self, message):
            raise EpisodeParseError(message)

        def exit(self, status=0, message=None):
            raise EpisodeParseError(message or f'exit {status}')
    src = Path(path).read_text() if source is None else source.decode()
    tree = ast.parse(src)
    node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parser'), None)
    if node is None:
        raise ValueError(f'wrapper {path} has no parser() to read the episode command with')
    shim = type('argparse_shim', (), dict(vars(_argparse)))
    shim.ArgumentParser = Parser
    ns = dict(argparse=shim, Path=Path, __doc__=ast.get_docstring(tree))
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), ns)
    return ns['parser']()


def episode_parse_problems(template, parser):
    """v7: read the command with the wrapper's real parser (placeholders filled) before running it: every
    option is spelled exactly, nothing is left over, and each gated value is the one argparse will run."""
    try:
        _, _, _, args = episode_command_form(template)
    except ValueError as error:
        return [str(error)]
    args = [_fill(t, EPISODE_PLACEHOLDERS) for t in args]
    known = parser._option_string_actions
    out = [f'episode command option {t.partition("=")[0]} is not a wrapper option (exact spelling required)'
           for t in args if t.startswith('--') and t.partition('=')[0] not in known]
    try:
        ns, extra = parser.parse_known_args(args)
    except EpisodeParseError as error:
        return out + [f'wrapper parser refuses the episode command: {error}']
    if extra:
        out.append(f'wrapper parser leaves arguments unread: {extra}')
    for flag in EPISODE_VALUE_FLAGS:
        action = known.get(flag)
        if action is None:
            continue
        try:
            mine = episode_option(args, flag)
        except ValueError as error:
            out.append(str(error))
            continue
        got = getattr(ns, action.dest)
        want = None if mine is None else (action.type(mine) if action.type else mine)
        if got != want:
            out.append(f'episode command {flag}: gate reads {want!r}, wrapper parser runs {got!r}')
    return out


def _fill(token, values):
    for k, v in values.items():
        token = token.replace('{' + k + '}', str(v))
    return token


def episode_command_problems(template, *, wrapper=None, strict=False):
    """v7 static + parser check of the episode command.  ``wrapper``: the wrapper file whose parser reads it
    (the template's own .py when it exists, else the repository copy when the template names the gcp6 wrapper).
    ``strict`` (core / final manifest gates, v7 b): a wrapper whose parser() cannot be read is refused instead of
    falling back to the form check only."""
    try:
        _, python, named, _ = episode_command_form(template)
    except ValueError as error:
        return [str(error)]
    if strict and wrapper is None:
        # v8: core / final read the parser of the named file itself -- absolute, symlink-free, the bytes hashed
        # (no REPO_WRAPPER stand-in: that copy is not what runs) -- and python by absolute path (no PATH lookup)
        out = [] if os.path.isabs(python) else [
            f'episode python {python!r} must be an absolute path at core / final (bare names resolve via PATH)']
        try:
            pin, source = resolve_episode_wrapper(template)
            parser = wrapper_parser(pin['path'], source)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as error:
            msg = str(error)
            return out + [msg if isinstance(error, EpisodePinError) else f'episode wrapper parser unreadable: {msg}']
        return out + episode_parse_problems(template, parser)
    if wrapper is None:
        if os.path.isfile(named):
            wrapper = named
        elif os.path.basename(named) == REPO_WRAPPER.name:
            wrapper = REPO_WRAPPER
    if wrapper is None:
        return [f'episode wrapper {named} not found; its parser() must read the command'] if strict else []
    try:
        parser = wrapper_parser(wrapper)
    except (OSError, SyntaxError, ValueError) as error:
        if not strict and os.path.basename(str(wrapper)) != REPO_WRAPPER.name:
            return []       # pilot only: another wrapper without parser(), form check (assets.wrapper_sha256)
        return [f'episode wrapper parser unreadable: {error}']
    return episode_parse_problems(template, parser)


# v7 a: the wrapper parser accepts options that change the model input (--compiled-reference-v1,
# --compiled-geometry-312-v1, --physics-backend, ...; the act teacher also takes --damping-ablation-v1).  The
# core binds the template text, but a path option binds only its *name*, so an option outside the assets the
# manifest hashes would feed an unhashed file.  The core / final gates accept only the options below, each
# with what binds its value; anything else is refused even when the wrapper parser knows it.
EPISODE_OPTION_ALLOWLIST = {
    '--flow': 'value in command.episode_template_sha256',
    '--cap-s': 'value in command.episode_template_sha256 and limits.grasp_cap_sim_s',
    '--vm-hourly-usd': 'value in command.episode_template_sha256 (cost recording only)',
    '--teacher-source': 'stack.teacher.sha (git HEAD of the checkout)',
    '--adapter-source': 'stack.adapter.sha (git HEAD of the checkout)',
    '--canonical-xml': 'assets.canonical_xml_sha256 + assets.mesh_assets_sha256',
    '--per-world-model-references-v1': 'assets.per_world_model_references_sha256 + per_world_reference_files_sha256',
    '--rejection-table': 'assets.rejection_table_input_sha256',
    '--cases': 'runner placeholder {cases}', '--indices': 'runner placeholder {indices}',
    '--out': 'runner placeholder {out}',
    **{flag: 'switch in command.episode_template_sha256' for flag in (
        '--gcp6-isolated-v1', '--placement-graspable-filter-v1', '--world-model-parameters-v1',
        '--native-sleep-policy-compat-v1', '--full-active-dof-workspace-v1', '--warp-native-contact-v1',
        '--batch-per-world-speed-v1')}}
EPISODE_PLACEHOLDER_OPTIONS = {'--cases': '{cases}', '--indices': '{indices}', '--out': '{out}'}


def episode_allowlist_problems(template):
    """v7 a: every option of the episode command is on EPISODE_OPTION_ALLOWLIST (exact spelling, ``=`` form
    included) and the runner options carry exactly their placeholder."""
    try:
        _, _, _, args = episode_command_form(template)
    except ValueError as error:
        return [str(error)]
    out = [f'episode command option {t.partition("=")[0]} is not on the v7 allowlist (its input is not bound '
           f'to the core)' for t in args if t.startswith('--') and t.partition('=')[0] not in EPISODE_OPTION_ALLOWLIST]
    for flag, want in EPISODE_PLACEHOLDER_OPTIONS.items():
        try:
            got = episode_option(args, flag)
        except ValueError as error:
            out.append(str(error))
            continue
        if got != want:
            out.append(f'episode command {flag} must be exactly {want}, got {got!r}')
    return out


def episode_argv(template, cases, indices, out):
    """v7: (env assignments, argv) the runner executes -- the checked form, placeholders filled per token."""
    assign, python, wrapper, args = episode_command_form(template)
    values = dict(cases=cases, indices=','.join(map(str, indices)), out=out)
    return assign, [python, _fill(wrapper, values)] + [_fill(t, values) for t in args]


# XML base: the teacher reads --canonical-xml as text and compiles it from a string, so relative include /
# compiler dirs / file names resolve against the episode process's cwd, not the XML's directory.
def episode_xml_problems(xml_path, registered, cwd):
    """v7: assets.mesh_assets_sha256 == the dependency set at the episode cwd (string compile), and the scene
    must not depend on that choice silently: a set that differs from the file-relative one is reported."""
    try:
        at_cwd = set(xml_dependencies(xml_path, base=cwd))
    except (ET.ParseError, OSError, ValueError) as error:
        return [f'canonical XML dependencies unreadable at episode cwd {cwd}: {error}']
    reg = {os.path.realpath(k) for k in registered}
    out = []
    if at_cwd - reg:
        out.append(f'assets.mesh_assets_sha256 misses files the canonical XML references from cwd {cwd}: '
                   + ', '.join(sorted(at_cwd - reg)))
    if reg - at_cwd:
        out.append(f'assets.mesh_assets_sha256 lists files the canonical XML does not reference from cwd {cwd}: '
                   + ', '.join(sorted(reg - at_cwd)))
    missing = sorted(p for p in at_cwd if not os.path.isfile(p))
    if missing:
        out.append('canonical XML dependencies missing at the episode cwd: ' + ', '.join(missing))
    return out


# 1b: the frozen teacher / wrapper cannot be edited (stack pins, assets.wrapper_sha256), so a process that
# sets the PAIRACT_P3_* env by hand still runs.  What it cannot get is a launch binding: the runner writes
# ``<out>.pairact-binding.json`` (core, manifest, template, argv, cwd) only after the manifest gate passed,
# and every consumer of teacher output (check-rows probe raws, convert-input training raws) requires it.
LAUNCH_BINDING_SCHEMA = 'ugrp.pairact_r1.launch_binding.v1'
LAUNCH_BINDING_SUFFIX = '.pairact-binding.json'


def launch_binding_path(out):
    out = Path(out)
    return out.parent / (out.name + LAUNCH_BINDING_SUFFIX)


def launch_binding(*, stage, core, manifest_sha256, template, argv, cwd, out, pin=None):
    """v8: ``pin`` = the episode pin checked immediately before the launch; the runner adds ``pin_post`` (the
    pin re-resolved after the process exited) and consumers refuse the output unless both are present and equal."""
    if stage not in ('core', 'final'):
        raise ValueError(f'launch binding stage {stage!r}')
    if not (isinstance(core, str) and len(core) == 64):
        raise ValueError('launch binding needs the manifest-gate core sha256')
    return dict(schema=LAUNCH_BINDING_SCHEMA, stage=stage, core_sha256=core, run_manifest_sha256=manifest_sha256,
                episode_template_sha256=hashlib.sha256(template.encode()).hexdigest(),
                argv_sha256=hashlib.sha256(json.dumps(argv).encode()).hexdigest(), cwd=str(cwd),
                out=os.path.realpath(out), pin=pin, pin_post=None)


def launch_binding_problems(raw, core, stages):
    """v7 1b: ``raw`` lies under a launch ``out`` whose binding carries this ``core`` at one of ``stages``."""
    raw = Path(os.path.realpath(raw))
    for d in (raw, *raw.parents):
        b = launch_binding_path(d)
        if b.is_file():
            try:
                rec = json.loads(b.read_text())
            except json.JSONDecodeError:
                return [f'launch binding unreadable: {b}']
            if rec.get('schema') != LAUNCH_BINDING_SCHEMA or rec.get('out') != str(d):
                return [f'launch binding {b} is not for {d}']
            if rec.get('stage') not in stages:
                return [f'launch binding {b} stage {rec.get("stage")!r} not in {stages}']
            if rec.get('core_sha256') != core:
                return [f'launch binding {b} core {rec.get("core_sha256")} != {core}']
            pin, post = rec.get('pin'), rec.get('pin_post')     # v8: the wrapper / python / root that ran
            if not isinstance(pin, dict) or not pin.get('strict') or not pin.get('wrapper_sha256'):
                return [f'launch binding {b} has no strict episode pin (launched before v8 or outside the runner)']
            if not isinstance(post, dict):
                return [f'launch binding {b} has no post-run pin (the episode did not finish under the runner)']
            diff = [k for k in PIN_KEYS if pin.get(k) != post.get(k)]
            if diff:
                return [f'launch binding {b}: episode {",".join(diff)} changed while the teacher ran']
            return []
    return [f'{raw} has no launch binding (teacher output not launched behind the manifest gate)']


# ------------------------------------------------------------- v8 (Codex v7 4th review: checked != executed)

# The gates read the wrapper .py token relative to their own cwd (or a repository copy when the named file was
# missing), python came from PATH at exec time and WARP_SOURCE_ROOT from token-or-env -- so a file other than the
# one parsed / hashed could run.  v8 resolves each of them once into a *pin* (absolute path + sha256) that the
# gate checks and the runner re-checks immediately before and after subprocess.call.
class EpisodePinError(ValueError):
    pass


def _own_realpath(path, what):
    """``path`` is absolute, placeholder-free and its own realpath (no symlink, ``..`` or ``//`` in any component)."""
    if not isinstance(path, str) or not os.path.isabs(path):
        raise EpisodePinError(f'{what} must be an absolute path, got {path!r}')
    if '{' in path or '}' in path:
        raise EpisodePinError(f'{what} {path} carries a runner placeholder; the checked path must be the run path')
    real = os.path.realpath(path)
    if real != path:
        raise EpisodePinError(f'{what} {path} is not its own realpath ({real}): no symlink / .. in any component')
    return path


def resolve_episode_wrapper(template):
    """v8: (dict(path, sha256), source bytes) of the wrapper the episode command runs.  The token must be an
    absolute, symlink-free path to a regular file; the bytes hashed are the bytes the parser reads."""
    _, _, named, _ = episode_command_form(template)
    _own_realpath(named, 'episode wrapper')
    try:
        fd = os.open(named, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        raise EpisodePinError(f'episode wrapper {named} not found; its parser() must read the command') from None
    except OSError as error:
        raise EpisodePinError(f'episode wrapper {named} unreadable: {error}') from None
    with os.fdopen(fd, 'rb') as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise EpisodePinError(f'episode wrapper {named} is not a regular file')
        data = f.read()
    _own_realpath(named, 'episode wrapper')                 # a component swapped to a symlink while opening
    return dict(path=named, sha256=hashlib.sha256(data).hexdigest()), data


def resolve_episode_python(template, env=None, *, strict=True):
    """v8: the interpreter.  Core / final (``strict``): the template names it by absolute path, so the core binds
    the path and PATH plays no part.  Pilot: a bare name is resolved once with the exec env's PATH and the runner
    executes that absolute path.  The realpath + sha256 of the binary are pinned (a venv python is a symlink to
    the base interpreter; argv[0] keeps the venv path so the venv still applies)."""
    _, python, _, _ = episode_command_form(template)
    if os.path.isabs(python):
        path = python
    elif strict:
        raise EpisodePinError(f'episode python {python!r} must be an absolute path at core / final '
                              '(a bare name resolves through the exec PATH, not the checked interpreter)')
    else:
        path = shutil.which(python, path=(os.environ if env is None else env).get('PATH', os.defpath))
        if path is None:
            raise EpisodePinError(f'episode python {python!r} not found on the exec PATH')
        path = os.path.abspath(path)
    real = os.path.realpath(path)
    if not os.path.isfile(real):
        raise EpisodePinError(f'episode python {path} is not a file')
    return dict(python=path, python_realpath=real, python_sha256=file_sha256(real))


def resolve_episode_root(template, env=None):
    """v8: the WARP_SOURCE_ROOT the episode runs with: the template token, else the env value; both present and
    different (realpath) is refused.  None when neither names one (the runner then removes it from the env)."""
    assign, _, _, _ = episode_command_form(template)
    tok = assign.get('WARP_SOURCE_ROOT')
    ev = (os.environ if env is None else env).get('WARP_SOURCE_ROOT')
    if tok is not None and ev is not None and os.path.realpath(tok) != os.path.realpath(ev):
        raise EpisodePinError(f'WARP_SOURCE_ROOT token {tok} != env WARP_SOURCE_ROOT {ev}; give one root')
    root = tok if tok is not None else ev
    return None if root is None else os.path.realpath(root)


PIN_KEYS = ('wrapper', 'wrapper_sha256', 'python', 'python_realpath', 'python_sha256', 'root', 'cwd', 'strict')


def episode_pin(template, *, cwd, env=None, strict=True):
    """v8: the one value the gate checks and the runner executes: wrapper (path, sha256), python (path,
    realpath, sha256), WARP_SOURCE_ROOT realpath and cwd.  ``strict`` = core / final rules."""
    if strict:
        w, _ = resolve_episode_wrapper(template)
    else:                       # pilot: relative wrapper allowed, resolved at the pinned cwd and hashed
        _, _, named, _ = episode_command_form(template)
        path = os.path.realpath(os.path.join(cwd, named))
        w = dict(path=path, sha256=file_sha256(path) if os.path.isfile(path) else None)
    py = resolve_episode_python(template, env, strict=strict)
    return dict(wrapper=w['path'], wrapper_sha256=w['sha256'], **py, root=resolve_episode_root(template, env),
                cwd=os.path.realpath(cwd), strict=strict)


def episode_pin_problems(pin, template, *, cwd, env=None):
    """v8: re-resolve the episode command now and list every difference from ``pin``."""
    try:
        now = episode_pin(template, cwd=cwd, env=env, strict=pin.get('strict', True))
    except (OSError, ValueError) as error:
        return [f'episode pin no longer resolves: {error}']
    return [f'episode pin {k}: pinned {pin.get(k)!r}, now {now.get(k)!r}' for k in PIN_KEYS if pin.get(k) != now.get(k)]


def pinned_exec(pin, argv, env, assign):
    """v8: (argv, env) actually executed: argv[0] the pinned python, WARP_SOURCE_ROOT the pinned root or absent."""
    env = dict(env, **assign)
    env.pop('WARP_SOURCE_ROOT', None)
    if pin['root'] is not None:
        env['WARP_SOURCE_ROOT'] = pin['root']
    return [pin['python']] + list(argv[1:]), env
