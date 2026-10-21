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
import shlex
import subprocess

PREREG_SCHEMA = 'ugrp.pairact_r1.collect_prereg.v2'
LEDGER_SCHEMA = 'ugrp.pairact_r1.collect_ledger.v2'
REPORT_SCHEMA = 'ugrp.pairact_r1.collect_report.v2'
MODES = ('measurement', 'training')
# measurement = recording-off pilot yield/bin run on seeds.pilot (A is an admission candidate,
# 'yield measurement, not demonstrations'); training = recording on through the -c candidate
CANDIDATE_BY_MODE = {'measurement': 'pairact_p2_r13', 'training': 'pairact_p3_collect'}
SPLITS_BY_MODE = {'measurement': ('pilot',), 'training': ('train', 'validation')}
COLLECT_ENV = ('PAIRACT_P3_COLLECT_PREREG', 'PAIRACT_P3_COLLECT_PREREG_SHA256', 'PAIRACT_P3_RECORDING_CHECK',
               'PAIRACT_P3_RECORDING_PROBE')
NOISE_MODES = ('off', 'on')
VM_FILL = '[VM 기입]'
ROBOTS = ('r1', 'r2')

# Frozen status table (COLLECT_PREREG status_table; test_pairact_collect checks the two agree).
WORLD_STATUS = {'complete': 'behavior', 'HOST_ERROR': 'environment', 'interrupted': 'environment',
                'running': 'environment'}
REQUIRED_BOOL = ('grasp_physical_success', 'search_handoff', 'approach_handoff', 'data_admitted')
TRAIN_STOPS_WITH_VALIDATION = ('STOP_TARGET', 'STOP_CAP', 'STOP_SEEDS', 'STOP_ALL_BINS_LIMITED', 'STOP_HOST')
TRAINABLE = ('TRAIN', 'TRAIN_DATA_RANGE_LIMITED', 'TRAIN_SMALL_DATA')


# ------------------------------------------------------------------ prereg

def load_prereg(path, *, mode='measurement'):
    raw = Path(path).read_bytes()
    prereg = json.loads(raw)
    if prereg.get('schema') != PREREG_SCHEMA:
        raise ValueError(f'collect prereg schema {PREREG_SCHEMA} required')
    if mode not in MODES:
        raise ValueError('unknown collection mode')
    allowed = ('FROZEN',) if mode == 'training' else ('READY_FOR_REVIEW', 'FROZEN')
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

def read_ledger(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                break      # torn last line after a crash: ignore it, it is re-derived
    return rows


def repair_ledger(path):
    """Drop a torn last line (crash mid-write) so later appends stay readable; returns bytes dropped."""
    path = Path(path)
    if not path.exists():
        return 0
    raw = path.read_bytes()
    if not raw or raw.endswith(b'\n'):
        return 0
    keep = raw[:raw.rfind(b'\n') + 1]
    with open(path, 'r+b') as f:
        f.truncate(len(keep))
        os.fsync(f.fileno())
    return len(raw) - len(keep)


def append(path, row):
    with open(path, 'a') as f:
        f.write(json.dumps(row, sort_keys=True, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def episode_cmd_audit(template):
    """The episode command is part of the frozen run: rejection table must be absolute, cap explicit."""
    if not template or any(k not in template for k in ('{cases}', '{indices}', '{out}')):
        raise ValueError('--episode-cmd with {cases} {indices} {out} required')
    tokens = shlex.split(template)

    def value(flag):
        if tokens.count(flag) != 1 or tokens.index(flag) + 1 >= len(tokens):
            raise ValueError(f'episode command needs exactly one {flag} <value>')
        return tokens[tokens.index(flag) + 1]
    table = value('--rejection-table')
    if not os.path.isabs(table):
        raise ValueError(f'--rejection-table must be an absolute path, got {table!r}')
    return dict(template_sha256=hashlib.sha256(template.encode()).hexdigest(), rejection_table_input=table,
                cap_s=float(value('--cap-s')))


def header(prereg_sha, *, mode, noise, batch_size, episode=None, run_manifest_sha256=None):
    if noise not in NOISE_MODES:
        raise ValueError('unknown noise mode')
    if mode not in MODES:
        raise ValueError('unknown collection mode')
    return dict(type='header', schema=LEDGER_SCHEMA, prereg_sha256=prereg_sha, mode=mode, noise=noise,
                batch_size=int(batch_size), episode=episode, run_manifest_sha256=run_manifest_sha256)


def require_header_sha(st, prereg_sha):
    """audit 2: report / convert-input never relabel a ledger under a different pre-registration."""
    h = st['header']
    if h is None:
        raise ValueError('ledger has no header')
    if h.get('schema') != LEDGER_SCHEMA:
        raise ValueError(f'ledger schema {h.get("schema")!r} is not {LEDGER_SCHEMA}')
    if h.get('prereg_sha256') != prereg_sha:
        raise ValueError(f'ledger header prereg sha256 {h.get("prereg_sha256")} != current prereg {prereg_sha}')
    return h


def replay(prereg, rows):
    ids = bin_ids(prereg)
    st = dict(header=None, attempt_rows=[], setup_rows=[], batches={}, consumed={}, requeue=[],
              last_rr=-1, limited={}, open_batch=None)
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
        rate = c['successes'] / c['attempts']
        if rate < rule['max_success_rate']:
            out.append(dict(type='bin_limited', bin=b, attempts=c['attempts'], successes=c['successes'],
                            admitted=c['admitted'], success_rate=rate, rule=rule['id']))
    return out


def open_bins(prereg, st):
    return [b for b in bin_ids(prereg) if b not in st['limited']]


def admitted_starts(st, split='train'):
    return [v['distance_m'] for r in split_rows(st, split) if r['admitted'] for v in (r.get('start') or {}).values()]


def distance_gate(prereg, st):
    g = prereg['distance_gate']['edges']
    dist = admitted_starts(st)
    top = g['first_m'] + g['width_m'] * g['n']
    hist = Counter(min(g['n'] - 1, int((d - g['first_m']) // g['width_m'])) for d in dist
                   if g['first_m'] <= d <= top + 1e-9)
    share = (sum(d > g['over_m'] for d in dist) / len(dist)) if dist else None
    occupied = all(hist[i] >= 1 for i in range(g['n']))
    return dict(robot_starts=len(dist), hist_0p1m={f'{g["first_m"] + g["width_m"] * i:.1f}': hist[i] for i in range(g['n'])},
                all_bins_occupied=occupied, share_over_0p8=share,
                passed=bool(dist) and occupied and share >= g['min_share_over'])


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


def train_stop(prereg, st):
    """First true stop rule (prereg stop_rules.list order), or None."""
    tg, ids = prereg['targets'], bin_ids(prereg)
    if any(r['category'] == 'record_error' for r in st['attempt_rows']):
        return 'STOP_RECORD'
    if consecutive_unclean_batches(st) >= 2:
        return 'STOP_HOST'
    t, per = totals(st), bin_counts(prereg, st)
    if t['admitted'] >= tg['admitted_minimum_pairs'] and not distance_gate(prereg, st)['passed']:
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
    stop = train_stop(prereg, st)
    out = dict(train_stop=stop, decision='COLLECTING', limited_bins=[], validation=None, labels=[])
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


def plan_batch(prereg, st, batch_size, *, validation_after_host_fix=False):
    """Next batch of slots; [] when the run root is finished (see run_state)."""
    mode = (st['header'] or {}).get('mode')
    if mode == 'measurement':
        slots = _fixed_bin_slots(prereg, st, 'pilot', batch_size)
    elif mode == 'training':
        stop = train_stop(prereg, st)
        if stop is None:
            room = prereg['targets']['attempt_cap'] - totals(st)['attempts']
            n = min(batch_size, room)
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
    return dict(out, category='record_error', outcome='record_error', failure_stage='record', reason=reason)


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


def batch_is_clean(summary, exit_code):
    """status table batch.clean (audit 1)."""
    table = summary.get('rejection_table')
    return (summary.get('status') == 'complete' and summary.get('HOST_ERROR') == 0 and exit_code == 0
            and isinstance(table, str) and os.path.isabs(table))


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


def report(prereg, st, *, prereg_sha):
    h = require_header_sha(st, prereg_sha)
    mode = h['mode']
    out = dict(schema=REPORT_SCHEMA, prereg_sha256=h['prereg_sha256'], mode=mode, noise=h['noise'],
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


# ------------------------------------------------------- convert hand-off

def convert_input(prereg, st, out_dir, *, prereg_sha, teacher_sha, run_pattern='seed-{seed}'):
    """Symlink admitted train/validation episodes into the grasp_act_data.convert layout (originals untouched).

    Only a finished training ledger with decision TRAIN / TRAIN_DATA_RANGE_LIMITED under the same
    prereg sha is accepted.  seed-<seed>/{SOURCE_SHA, EXIT, raw -> <batch>/try-N/world-XXX/raw}.
    """
    h = require_header_sha(st, prereg_sha)
    if h['mode'] != 'training':
        raise ValueError('convert input needs a training-mode ledger (measurement runs have no tensors)')
    d = decision(prereg, st)
    if d['decision'] not in TRAINABLE or d['validation'] in (None, 'pending'):
        raise ValueError(f'convert input refused: decision {d["decision"]}, validation {d["validation"]}')
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
                    teacher_sha=teacher_sha, prereg_sha256=prereg_sha, decision=d['decision'],
                    data_range_limited=bool(d['limited_bins']), small_data=d['decision'] == 'TRAIN_SMALL_DATA',
                    result_labels=d['labels'], limited_bins=d['limited_bins'],
                    admission='pairact_r1 success_only_v2 (COLLECT_PREREG v2)')
    (out_dir / 'protocol.json').write_text(json.dumps(protocol, indent=1) + '\n')
    return protocol


# --------------------------------------------------------- run manifest

def manifest_unfilled(value, path=''):
    """Paths of every '[VM 기입]' left in RUN_MANIFEST.json."""
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in manifest_unfilled(v, f'{path}.{k}' if path else k)]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in manifest_unfilled(v, f'{path}[{i}]')]
    return [path] if isinstance(value, str) and VM_FILL in value else []


def check_run_manifest(manifest, *, mode, prereg_sha, collector_sha=None, episode=None, batch_size=None):
    """Training needs a fully filled manifest bound to this prereg, collector checkout and command."""
    if manifest.get('schema') != 'ugrp.pairact_r1.run_manifest.v1':
        raise ValueError('run manifest schema ugrp.pairact_r1.run_manifest.v1 required')
    if mode != 'training':
        return []
    problems = [f'unfilled {p}' for p in manifest_unfilled(manifest)]
    if manifest.get('status') != 'FROZEN':
        problems.append('run manifest status must be FROZEN')
    if manifest.get('prereg', {}).get('sha256') != prereg_sha:
        problems.append('run manifest prereg sha256 differs')
    if collector_sha is not None and manifest.get('collector', {}).get('source_sha') != collector_sha:
        problems.append('run manifest collector sha differs from this checkout')
    if episode is not None and manifest.get('command', {}).get('episode_template_sha256') != episode['template_sha256']:
        problems.append('run manifest episode template sha256 differs')
    if batch_size is not None and manifest.get('command', {}).get('batch_size') != batch_size:
        problems.append('run manifest batch size differs')
    if problems:
        raise ValueError('run manifest not usable for training: ' + '; '.join(problems))
    return problems
