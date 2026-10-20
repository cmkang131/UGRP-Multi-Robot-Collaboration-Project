"""pairact-r1 P3 success-filtered teacher collection: pure controller logic.

COLLECT_PREREG_DRAFT.json is the contract.  This module never runs physics:
it replays an append-only jsonl ledger into counts, plans the next batch
(bins, seeds, cap), judges one finished episode from its result.json and
builds the convert input / bias report.  Same ledger -> same next batch.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
from collections import Counter
from pathlib import Path

LEDGER_SCHEMA = 'ugrp.pairact_r1.collect_ledger.v1'
REPORT_SCHEMA = 'ugrp.pairact_r1.collect_report.v1'
MODES = ('measurement', 'training')
# measurement = recording-off yield/bin run (A only, 'yield measurement, not demonstrations');
# training = recording on through the opt-in teacher/adapter candidate below (-c stack)
CANDIDATE_BY_MODE = {'measurement': 'pairact_p2_r13', 'training': 'pairact_p3_collect'}
COLLECT_ENV = ('PAIRACT_P3_COLLECT_PREREG', 'PAIRACT_P3_COLLECT_PREREG_SHA256', 'PAIRACT_P3_RECORDING_CHECK',
               'PAIRACT_P3_RECORDING_PROBE')
NOISE_MODES = ('off', 'on')
WARMUP_ATTEMPTS = 4
P_FLOOR = .05


# ------------------------------------------------------------------ prereg

def load_prereg(path, *, mode='measurement'):
    raw = Path(path).read_bytes()
    prereg = json.loads(raw)
    if prereg.get('schema') != 'ugrp.pairact_r1.collect_prereg.v1':
        raise ValueError('collect prereg schema required')
    if mode not in MODES:
        raise ValueError('unknown collection mode')
    allowed = ('FROZEN',) if mode == 'training' else ('READY_FOR_REVIEW', 'FROZEN')
    if prereg.get('status') not in allowed:
        raise ValueError(f'prereg status {prereg.get("status")!r} not allowed for {mode}')
    check_seed_ranges(prereg)
    return prereg, hashlib.sha256(raw).hexdigest()


def bins(prereg):
    return [dict(b, index=i) for i, b in enumerate(prereg['bins']['list'])]


def _span(r):
    return set(range(r['first'], r['last'] + 1))


def train_pool(prereg):
    s = prereg['seeds']
    return list(range(s['train_primary']['first'], s['train_primary']['last'] + 1)) + \
        list(range(s['train_extension']['first'], s['train_extension']['last'] + 1))


def validation_pool(prereg):
    v = prereg['seeds']['validation']
    return list(range(v['first'], v['last'] + 1))


def check_seed_ranges(prereg, known_ranges=()):
    s = prereg['seeds']
    train = _span(s['train_primary']) | _span(s['train_extension'])
    if s['train_extension']['first'] != s['train_primary']['last'] + 1:
        raise ValueError('train extension must continue the primary range')
    for name in ('validation', 'heldout'):
        if train & _span(s[name]):
            raise ValueError(f'train seeds overlap {name}')
    if _span(s['validation']) & _span(s['heldout']):
        raise ValueError('validation overlaps heldout')
    for r in known_ranges:
        if (train | _span(s['validation']) | _span(s['heldout'])) & _span(r):
            raise ValueError(f'seed range overlaps known range {r}')
    if len(train) < prereg['targets']['attempt_cap']:
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


def header(prereg_sha, *, mode, noise, batch_size):
    if noise not in NOISE_MODES:
        raise ValueError('unknown noise mode')
    return dict(type='header', schema=LEDGER_SCHEMA, prereg_sha256=prereg_sha, mode=mode,
                noise=noise, batch_size=int(batch_size))


def replay(prereg, rows):
    ids = [b['id'] for b in bins(prereg)]
    st = dict(header=None, attempts=Counter(), successes=Counter(), eligible=Counter(),
              host_errors=Counter(), consumed=set(), requeue=[], last_rr=-1, batches={},
              attempt_rows=[], validation_done=False, host_error_batches=[], open_batch=None)
    requeued = Counter()
    for r in rows:
        kind = r.get('type')
        if kind == 'header':
            if st['header'] is not None and r != st['header']:
                raise ValueError('ledger header changed between invocations')
            st['header'] = r
        elif kind == 'batch_planned':
            st['batches'][r['batch']] = dict(r, done=False, ingested=set())
            st['open_batch'] = r['batch']
            for s in r['slots']:
                if s['split'] == 'train':
                    st['consumed'].add(s['seed'])
                    if not s.get('requeue'):
                        st['last_rr'] = ids.index(s['bin'])
                    else:
                        requeued[s['seed']] += 1
                        st['requeue'] = [q for q in st['requeue'] if q['seed'] != s['seed']]
        elif kind == 'attempt':
            b = st['batches'][r['batch']]
            b['ingested'].add(r['slot'])
            st['attempt_rows'].append(r)
            if r['split'] != 'train':
                continue
            if r['outcome'] == 'host_error':
                st['host_errors'][r['bin']] += 1
                if requeued[r['seed']] == 0:
                    st['requeue'].append(dict(seed=r['seed'], bin=r['bin']))
                continue
            st['attempts'][r['bin']] += 1
            st['successes'][r['bin']] += bool(r['success'])
            st['eligible'][r['bin']] += bool(r['eligible'])
        elif kind == 'batch_done':
            st['batches'][r['batch']]['done'] = True
            st['open_batch'] = None
            if r.get('status') == 'HOST_ERROR':
                st['host_error_batches'].append(r['batch'])
            if r.get('split') == 'validation':
                st['validation_done'] = True
    return st


def totals(st):
    return dict(attempts=sum(st['attempts'].values()), successes=sum(st['successes'].values()),
                eligible=sum(st['eligible'].values()), host_errors=sum(st['host_errors'].values()))


def consecutive_host_error_batches(st):
    n = 0
    for k in sorted(st['batches'], reverse=True):
        b = st['batches'][k]
        if not b['done']:
            continue
        if k in st['host_error_batches']:
            n += 1
        else:
            break
    return n


def stop_reason(prereg, st):
    t, tg = totals(st), prereg['targets']
    min_bin = prereg['bins']['min_success_per_bin']
    if t['eligible'] >= tg['success_target_pairs'] and all(
            st['eligible'][b['id']] >= min_bin for b in bins(prereg)):
        return 'STOP_TARGET'
    if t['attempts'] >= tg['attempt_cap']:
        return 'STOP_CAP'
    if consecutive_host_error_batches(st) >= 2:
        return 'STOP_HOST'
    if not st['requeue'] and not [s for s in train_pool(prereg) if s not in st['consumed']]:
        return 'STOP_SEEDS'
    return None


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


def allocate(prereg, st, n):
    """Bin id per new slot (interleaved), deficit_weighted_v1."""
    ids = [b['id'] for b in bins(prereg)]
    min_bin = prereg['bins']['min_success_per_bin']
    if any(st['attempts'][b] < WARMUP_ATTEMPTS for b in ids) or \
            all(max(0, min_bin - st['eligible'][b]) == 0 for b in ids):
        return [ids[(st['last_rr'] + 1 + k) % len(ids)] for k in range(n)]
    weights = []
    for b in ids:
        need = max(0, min_bin - st['eligible'][b])
        p = (st['eligible'][b] + 1) / (st['attempts'][b] + 2)
        weights.append(need / max(p, P_FLOOR))
    counts = largest_remainder(weights, n)
    slots = []
    while len(slots) < n:
        for i, b in enumerate(ids):
            if counts[i]:
                slots.append(b)
                counts[i] -= 1
    return slots


def plan_batch(prereg, st, batch_size):
    """Next batch of slots; [] when a stop rule holds. Validation goes first, once."""
    if not st['validation_done']:
        ids = [b['id'] for b in bins(prereg)]
        return [dict(slot=i, seed=s, bin=ids[i % len(ids)], split='validation', requeue=False)
                for i, s in enumerate(validation_pool(prereg))]
    if stop_reason(prereg, st):
        return []
    room = prereg['targets']['attempt_cap'] - totals(st)['attempts']
    n = min(batch_size, room)
    slots = [dict(seed=q['seed'], bin=q['bin'], split='train', requeue=True) for q in st['requeue'][:n]]
    free = [s for s in train_pool(prereg) if s not in st['consumed']]
    new = allocate(prereg, st, min(n - len(slots), len(free)))
    slots += [dict(seed=free[k], bin=b, split='train', requeue=False) for k, b in enumerate(new)]
    return [dict(s, slot=i) for i, s in enumerate(slots)]


# ----------------------------------------------------------------- judging

def judge(result, *, mode):
    """Prereg success / filter from one raw result.json (None = world missing)."""
    out = dict(success=False, eligible=False, failure_stage=None, reason=None, handoff=False)
    if result is None or result.get('status') != 'complete' or result.get('HOST_ERROR'):
        return dict(out, outcome='host_error', failure_stage='host',
                    reason=(result or {}).get('error_type') or 'missing_result')
    carry, ev = result.get('carry') or {}, result.get('carry_eval')
    grasp = result.get('grasp_physical_success', result.get('physical_success')) is True
    handoff = bool(result.get('search_handoff') or result.get('approach_handoff'))
    out['handoff'] = handoff
    if not grasp:
        return dict(out, outcome='failure', failure_stage='grasp',
                    reason=carry.get('reason') or result.get('end_reason') or 'grasp_failed')
    if not ev:
        return dict(out, outcome='failure', failure_stage='carry_not_started',
                    reason=carry.get('reason') or 'no_carry_eval')
    success = (ev.get('success') is True and not ev.get('drop_events')
               and int(ev.get('robot_robot_contact_ticks') or 0) == 0)
    if not success:
        funnel = ev.get('funnel') or {}
        reached = [k for k, v in funnel.items() if v]
        return dict(out, outcome='failure', failure_stage='carry', reason=ev.get('failure') or 'carry_failed',
                    funnel_last=reached[-1] if reached else None)
    eligible = not handoff and (mode != 'training' or result.get('data_admitted') is True)
    tag = None if eligible else ('success_not_admitted_handoff' if handoff else 'success_not_admitted_recording')
    return dict(out, outcome='success', success=True, eligible=eligible, reason=tag)


def start_from_case(case):
    """Robot-level start distance / yaw offset from the immutable case plan."""
    layers = case['plan'].get('start_layers') or {}
    return {rid: dict(distance_m=float(v['target_distance_m']), yaw_offset_rad=float(v['yaw_bin']['offset_rad']))
            for rid, v in layers.items()}


def perturbed_ratio(raw_dir):
    """perturbed / rows per robot from teacher-<rid>.jsonl (noise bookkeeping)."""
    out = {}
    for path in sorted(Path(raw_dir).glob('teacher-*.jsonl')):
        n = p = 0
        for line in path.read_text().splitlines():
            if line.strip():
                n += 1
                p += bool(json.loads(line).get('perturbed'))
        out[path.stem.split('-', 1)[1]] = dict(rows=n, perturbed=p, ratio=p / n if n else None)
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


def report(prereg, st, *, prereg_sha):
    t = totals(st)
    min_bin = prereg['bins']['min_success_per_bin']
    table = []
    for b in bins(prereg):
        k = b['id']
        table.append(dict(bin=k, distance_m=b['distance_m'], yaw=b['yaw'], attempts=st['attempts'][k],
                          successes=st['successes'][k], eligible=st['eligible'][k],
                          rate=st['successes'][k] / st['attempts'][k] if st['attempts'][k] else None,
                          need=max(0, min_bin - st['eligible'][k]), host_errors=st['host_errors'][k]))
    train = [r for r in st['attempt_rows'] if r['split'] == 'train' and r['outcome'] != 'host_error']
    def starts(rows, key):
        return [v[key] for r in rows for v in (r.get('start') or {}).values()]
    ok = [r for r in train if r['eligible']]
    bad = [r for r in train if not r['success']]
    dist = starts(ok, 'distance_m')
    hist = Counter(min(8, int((d - .3) // .1)) for d in dist if .3 <= d <= 1.2)
    val = [r for r in st['attempt_rows'] if r['split'] == 'validation']
    mode = (st['header'] or {}).get('mode')
    return dict(
        schema=REPORT_SCHEMA, prereg_sha256=prereg_sha, mode=mode, noise=(st['header'] or {}).get('noise'),
        stop=stop_reason(prereg, st),
        A=dict(label='교사 시연 수집: 성공 n / 시도 N (데이터 필터용, 학습 결과 아님)',
               text=f"교사 시연 수집: 성공 {t['successes']} / 시도 {t['attempts']} (데이터 필터용, 학습 결과 아님); "
                    f"학습 채택 {t['eligible']}" + (' [수율 측정, 시연 아님: 녹화 없음, 텐서 없음]' if mode == 'measurement' else ''),
               **t, bins=table),
        validation=dict(attempts=sum(r['outcome'] != 'host_error' for r in val),
                        successes=sum(r['success'] for r in val), eligible=sum(r['eligible'] for r in val)),
        ks=dict(scope='admitted successes vs failures, robot-level starts; informational, not a gate',
                distance=ks_2samp(dist, starts(bad, 'distance_m')),
                abs_yaw_offset=ks_2samp([abs(wrap(x)) for x in starts(ok, 'yaw_offset_rad')],
                                        [abs(wrap(x)) for x in starts(bad, 'yaw_offset_rad')])),
        distance_gate=dict(hist_0p1m={f'{.3 + .1 * i:.1f}': hist[i] for i in range(9)},
                           all_bins_occupied=all(hist[i] >= 1 for i in range(9)),
                           share_over_0p8=(sum(d > .8 for d in dist) / len(dist)) if dist else None,
                           passed=bool(dist) and all(hist[i] >= 1 for i in range(9))
                           and sum(d > .8 for d in dist) / len(dist) >= .25),
        data_range_limited=any(r['need'] > 0 for r in table),
        failures=dict(Counter(f"{r['failure_stage']}:{r['reason']}" for r in bad)),
        not_pooled_with=['B teacher gate n/40', 'C student n/20', 'P2 smoke', 'r13 gate', 'CPU results'])


# ------------------------------------------------ recording-mode check inputs

CHECK_ROW_KEYS = ('status', 'physical_success', 'execution_host', 'source_sha', 'teacher_profile', 'action_contract',
                  'self_pose_source', 'episode_plan_sha256', 'observation_sampling', 'teacher_stability',
                  'teacher_search', 'approach_goal_set', 'nominal_blocked_handoff', 'approach_progress',
                  'approach_recovery', 'approach_coordination', 'handoff_observation')


def probe_slots(st, n=3):
    """First n admitted train successes (ledger order): the starts re-run with recording probe."""
    rows = [r for r in st['attempt_rows'] if r['split'] == 'train' and r['eligible']][:n]
    if len(rows) < n:
        raise ValueError(f'need {n} measured successes for the recording-mode check, have {len(rows)}')
    return rows


def check_row(result, seed, search15_keys=()):
    """One row for teacher harness.grasp_act_admission.recording_mode_equivalence (index = seed)."""
    row = {k: result.get(k) for k in CHECK_ROW_KEYS if k in result}
    row.update({k: result[k] for k in search15_keys if k in result})
    row.update(index=int(seed), exit=0 if result.get('status') == 'complete' else 1)
    return row


# ------------------------------------------------------- convert hand-off

def convert_input(st, out_dir, *, teacher_sha, run_pattern='seed-{seed}'):
    """Symlink admitted successes into the grasp_act_data.convert layout (originals untouched).

    seed-<seed>/{SOURCE_SHA, EXIT, raw -> <batch>/world-XXX/raw}; returns the protocol dict.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    train, val = [], []
    for r in st['attempt_rows']:
        if not r['eligible']:
            continue
        d = out_dir / run_pattern.format(seed=r['seed'])
        d.mkdir()
        (d / 'SOURCE_SHA').write_text(teacher_sha + '\n')
        (d / 'EXIT').write_text('0\n')
        (d / 'raw').symlink_to(Path(r['raw']).resolve(), target_is_directory=True)
        (train if r['split'] == 'train' else val).append(r['seed'])
    protocol = dict(train_seeds=sorted(train), validation_seeds=sorted(val), run_pattern=run_pattern,
                    teacher_sha=teacher_sha, admission='pairact_r1 success_only_v1 (COLLECT_PREREG)')
    (out_dir / 'protocol.json').write_text(json.dumps(protocol, indent=1) + '\n')
    return protocol
