"""Small executable spec: event times -> calls, wire spend, refunds and stop reason.

No harness imports, inheritance, monkeypatching, or production accounting/queue
helpers. Integer microseconds implement the published six-decimal event clock;
raw horizon comparison deliberately retains nanosecond boundaries. Pending
transport replies resolve at the last clock before the minimum completion time,
just like the frozen v64 synchronous transport contract (not wall-clock time).
"""
from collections import Counter
from dataclasses import dataclass
import math
import random

U = 1_000_000
ACTORS = ('r1', 'r2', 'r3')
PRIORITY = {'start': 70, 'failure': 60, 'timeout': 40, 'report': 30, 'retry': 25, 'idle': 20, 'timer': 10}


def stamp(seconds):
    return int(round(round(seconds, 6) * U))


@dataclass(frozen=True)
class Scenario:
    seed: int
    events: tuple
    horizon: float
    interval: int
    total: int
    per_actor: int
    calls: int
    retries: int
    reask: int

    def response(self, actor, at):
        # Exogenous; unaffected by condition, lane, call ID or oracle state.
        rng = random.Random(self.seed * 1_000_003 + at * 17 + ACTORS.index(actor))
        outcome = rng.choice(('ok', 'ok', 'error', 'timeout', 'snapshot', 'refund'))
        return outcome, rng.randrange(3), rng.choice((False, True))


def generated_case(seed):
    rng = random.Random(2456000 + seed)
    anchor = rng.choice((.5, 1., 2., 3.))
    points = [0., anchor, anchor - 1e-9, anchor + 1e-9,
              anchor - 1e-6, anchor + 1e-6, anchor + .1, anchor + .4,
              anchor + .5, anchor + 2., anchor + 4.]
    events = [(0., 'common', a) for a in ACTORS]
    # Force a tie and near-ties in every stream, then scatter all event kinds.
    events += [(t, 'message', 'r1') for t in points[1:6]]
    events += [(anchor, 'common', 'r1'), (anchor + .4, 'boundary', 'r1')]
    events += [(rng.choice(points + [rng.randrange(1, 101) / 10]),
                rng.choice(('common', 'message', 'busy', 'boundary')), rng.choice(ACTORS))
               for _ in range(16)]
    return Scenario(seed, tuple(events), rng.choice(points[1:] + [8., 12., 14.]),
                    rng.choice((0, 200_000, 500_000, 2 * U)),
                    rng.choice((3, 4, 5, 12, 90)), rng.choice((1, 2, 4, 30)),
                    rng.choice((1, 2, 4, 30)), rng.randrange(3), rng.choice((2, 10)) * U)


def reference(spec, *, messages=True):
    """Finite transition system, represented by facts and a sorted agenda."""
    now, seq = 0, 0
    agenda, calls, sources, sends, refunds, snapshots = [], [], [], [], [], []
    last, waits, retry_counts, reasks = {}, {}, Counter(), {}
    inbox = {a: [] for a in ACTORS}
    busy = dict.fromkeys(ACTORS, False)
    refused = []

    def put(at, kind, actor, data=None, lane=''):
        nonlocal seq
        seq += 1
        rank = {'message': 0, 'done': 1, 'timer': 2, 'tick': 3, 'busy': 3, 'boundary': 3, 'start': 4}[kind]
        agenda.append((at, rank, bool(lane), ACTORS.index(actor), seq, kind, actor, data))

    def request(at, actor, lane='', root=0, inputs=(), trigger='timer', merged=()):
        put(at, 'start', actor, (lane, root, tuple(inputs), trigger, merged), lane)

    def running(actor, lane):
        return any(c['actor'] == actor and c['lane'] == lane
                   and c['status'] in ('pending', 'thinking') for c in calls)

    def logical(actor, confirmed=False):
        return sum(c['actor'] == actor and c['status'] != 'not_sent'
                   and (c['sent'] if confirmed else c['admitted']) for c in calls)

    def balance(actor=None, confirmed=False):
        def count(c):
            return c['sent'] if confirmed or c['status'] not in ('pending', 'thinking') else c['reserved']
        total = spec.total - sum(count(c) for c in calls)
        own = spec.per_actor - sum(count(c) for c in calls if c['actor'] == actor)
        return min(total, own) if actor else total

    def exhausted(actor):
        return balance(actor, True) == 0 or logical(actor, True) >= spec.calls

    def hold(actor, lane, root, inputs, trigger, merged, budget=False):
        prior = waits.get((actor, lane), (0, (), trigger, (), False))
        labels = set(merged) | {trigger, prior[2]} | set(prior[3])
        best = max(labels, key=lambda t: (PRIORITY[t], t))
        waits[actor, lane] = ((root or prior[0]) if lane else 0,
                             tuple(dict.fromkeys(prior[1] + tuple(inputs))), best,
                             tuple(sorted(labels - {best})), budget or prior[4])

    def resume(actor):
        for (a, lane), (root, inputs, trigger, merged, budget) in list(waits.items()):
            if a != actor and not budget:
                continue
            inputs = tuple(i for i in inputs if sources[i]['active'])
            if lane and not inputs:
                del waits[a, lane]
                continue
            if running(a, lane) or (lane and running(a, '')):
                continue
            at = max((sources[i]['available'] for i in inputs), default=now)
            if math.isfinite(at):
                del waits[a, lane]
                request(max(now, at), a, lane, root, inputs, trigger, merged)

    def refund(c):
        c['status'], c['end'] = 'not_sent', now
        refunds.append((c['id'], now, c['reserved']))
        for i in c['inputs']:
            e = sources[i]
            if e['claimed'] == c['id']:
                e['active'] = True
                backoff = ((c['at'] + max(spec.interval, 100_000) + 99_999) // 100_000) * 100_000
                e['available'] = max(e['available'], backoff)
                hold(c['actor'], 'message', e['root'], (i,), 'report', ())
        resume(c['actor'])

    def resolve(c):
        if c['outcome'] == 'refund':
            refund(c)
        else:
            if not c['sent']:
                c['sent'] = 1
                sends.append((c['id'], now))
            c['status'] = 'thinking'
            put(c['at'] + (U if c['outcome'] == 'ok' else U // 2), 'done', c['actor'], c['id'])

    for index, (at, kind, actor) in enumerate(spec.events):
        if kind == 'message' and messages:
            put(stamp(at), 'message', actor, f'm{index}')
        elif kind == 'common':
            put(stamp(at), 'timer', actor, False)
        elif kind in ('busy', 'boundary'):
            put(stamp(at), kind, actor)
    # A single observation clock permits refunds while other calls remain live.
    put(100_000, 'tick', 'r1')
    while agenda:
        next_event = min(agenda)
        due = [c for c in calls if c['status'] == 'pending' and c['at'] + U // 2 <= next_event[0]]
        if due:
            for c in sorted(due, key=lambda c: (c['at'], c['actor'], c['id'])):
                resolve(c)
            continue
        if next_event[0] / U > spec.horizon:
            now = stamp(spec.horizon)
            break
        agenda.remove(next_event)
        now, _, _, _, _, kind, actor, data = next_event
        if kind == 'tick':
            put(now + 100_000, 'tick', actor)
        elif kind == 'busy':
            busy[actor] = True
        elif kind == 'boundary':
            busy[actor] = False
            for e in sources:
                if e['actor'] == actor and math.isinf(e['available']) and (e['active'] or any(
                        c['id'] == e['claimed'] and c['status'] == 'pending' for c in calls)):
                    e['available'] = now
            resume(actor)
        elif kind == 'message':
            inbox[actor].append(data)
            i = len(sources)
            sources.append(dict(actor=actor, tag=data, available=math.inf if busy[actor] else now,
                                active=True, claimed=0, root=0))
            request(now, actor, 'message', inputs=(i,), trigger='report')
        elif kind == 'timer':
            if data:
                reasks.pop(actor, None)
            request(now, actor, trigger=data or 'timer')
        elif kind == 'done':
            c = calls[data - 1]
            c['status'], c['end'] = ('done' if c['outcome'] == 'ok' else 'failed'), now
            if c['outcome'] != 'ok':
                groups = dict.fromkeys(c['roots'] if c['lane'] else (c['root'] or c['id'],))
                allowed = [root for root in groups if retry_counts[c['lane'] or 'common', root] < spec.retries]
                if allowed:
                    for root in allowed:
                        retry_counts[c['lane'] or 'common', root] += 1
                    inputs = []
                    for i, root in zip(c['inputs'], c['roots']):
                        if c['lane'] and root in allowed and sources[i]['claimed'] == c['id']:
                            sources[i]['active'], sources[i]['root'] = True, root
                            inputs.append(i)
                    request(now, actor, c['lane'], allowed[0], inputs if c['lane'] else c['inputs'],
                            'timeout' if c['outcome'] == 'timeout' else 'retry')
            elif not c['lane'] and logical(actor, True) < spec.calls and actor not in reasks:
                at = now + spec.reask
                if at / U <= spec.horizon:
                    reasks[actor] = at
                    put(at, 'timer', actor, 'timer' if busy[actor] else 'idle')
            resume(actor)
        elif kind == 'start':
            lane, root, inputs, trigger, merged = data
            inputs = tuple(i for i in inputs if sources[i]['active'])
            if lane and not inputs:
                continue
            if inputs:
                inputs = tuple(i for i, e in enumerate(sources) if e['active'] and e['actor'] == actor) if lane else ()
                root = next((sources[i]['root'] for i in inputs if sources[i]['root']), 0)
                available = max([math.inf if busy[actor] else now] + [sources[i]['available'] for i in inputs])
                for i in inputs:
                    sources[i]['available'] = available
                if available > now:
                    if math.isfinite(available):
                        request(available, actor, lane, root, inputs, trigger, merged)
                    else:
                        hold(actor, lane, root, inputs, trigger, merged)
                    continue
            if running(actor, lane) or (lane and running(actor, '')):
                hold(actor, lane, root, inputs, trigger, merged)
                continue
            previous = max([last.get((actor, lane), -10**12)] + ([last.get((actor, ''), -10**12)] if lane else []))
            earliest = ((previous + spec.interval + 99_999) // 100_000) * 100_000
            if earliest > now:
                request(earliest, actor, lane, root, inputs, trigger, merged)
                continue
            if balance(actor) < 1 or logical(actor) >= spec.calls:
                # v64 labels a trial from the existence of an admission denial,
                # even if a later refund restores capacity. Record that event
                # independently; do not infer the label from final balances.
                refused.append((now, actor))
                if inputs:
                    if exhausted(actor):
                        for i in inputs:
                            sources[i]['active'] = False
                    else:
                        hold(actor, lane, root, inputs, trigger, merged, True)
                continue
            inputs = tuple(i for i, e in enumerate(sources) if e['active'] and e['actor'] == actor)
            outcome, extra, immediate = spec.response(actor, now)
            c = dict(id=len(calls) + 1, actor=actor, at=now, lane=lane, root=root, trigger=trigger,
                     inputs=inputs, outcome=outcome, reserved=1, sent=0, admitted=False,
                     status='pending', end=None,
                     roots=tuple(sources[i]['root'] or len(calls) + 1 for i in inputs) if lane else ())
            calls.append(c)
            snapshots.append((c['id'], actor, now, tuple(inbox[actor])))
            for i in inputs:
                sources[i]['active'], sources[i]['claimed'] = False, c['id']
            if outcome == 'snapshot':
                refund(c)
                continue
            if extra and balance(actor) >= extra:
                c['reserved'] += extra
            if immediate and outcome != 'refund':
                c['sent'] = 1
                sends.append((c['id'], now))
            c['admitted'] = True
            last[actor, lane] = now

    # Horizon fetches/charges in-flight sends, but releases no actions/retries.
    for c in sorted(calls, key=lambda c: (c['at'], c['actor'], c['id'])):
        if c['status'] == 'pending':
            resolve(c)
        if c['status'] == 'thinking':
            c['status'], c['end'] = 'censored', now
    fields = ('id', 'actor', 'at', 'lane', 'root', 'trigger', 'status', 'end', 'sent', 'reserved')
    return dict(calls=[tuple(c[k] for k in fields) for c in calls], sends=sends, refunds=refunds,
                snapshots=snapshots, retries=sorted((a, r, n) for (a, r), n in retry_counts.items()),
                inputs=[(e['tag'], e['active'], e['claimed'], e['root'], e['available']) for e in sources],
                end_reason='budget_exhausted' if refused else 'sim_horizon',
                end_state={
                    'quiescent': all(exhausted(a) for a in ACTORS) and not any(busy.values())
                                 and not any(c['status'] == 'censored' for c in calls),
                    'pending_work_count': sum(busy.values()),
                    'in_flight_calls': sum(c['status'] == 'censored' for c in calls),
                    'censored_calls': sum(c['status'] == 'censored' for c in calls),
                    'committed_sends': len(sends), 'reserved': 0,
                    'remaining_budget': {
                        'http_total': balance(),
                        'http_per_actor': {a: balance(a) for a in ACTORS},
                        'calls_per_actor': {a: max(0, spec.calls - logical(a, True)) for a in ACTORS},
                        'calls_total': max(0, spec.total - sum(logical(a, True) for a in ACTORS)),
                    },
                    'horizon_hit': True,
                })
