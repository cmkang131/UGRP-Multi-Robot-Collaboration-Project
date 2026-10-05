"""v98 same-tick final veto: a terminal pair endpoint never dispatches a non-hold.

``zone_final_pair_runtime.Runtime.step`` asks the actors in sequence, so motion that actor A
returned *before* actor B aborted in the same tick is still in the list it hands to the runner, even
though ``team.poll`` has by then marked A terminal (PARTNER_ABORT). ``arm_step`` has the same shape
and no poll at all. This module is the last stage between the runtime and the backend: after every
actor's state has been propagated it replaces the non-hold commands of an endpoint that is terminal
with one ``hold`` in that same tick and records what it removed.

Information boundary: the veto reads only each endpoint's own ``terminal`` flag (set by its own
``check``/``abort``, including the partner-status ENUM path it already uses). It never looks at
partner controller state, poses, or evaluation data, and it does not make one endpoint terminal
because the other one is.
"""
import copy

PROFILE = 'v98_same_tick_final_veto_v1'
HOLD = {'kind': 'hold'}


def endpoint(team, rid):
    """Current pair endpoint of ``rid`` (latest session that contains it), or None."""
    for session in reversed(team.sessions):
        ep = session['endpoints'].get(rid)
        if ep is not None:
            return ep
    return None


def terminal_robots(team, rids):
    return {rid for rid in rids if getattr(endpoint(team, rid), 'terminal', False)}


def abort_reason(ep):
    """Reason text of the endpoint owner's latest ``job_failed`` event (log only), else None."""
    for event in reversed(getattr(getattr(ep, 'own', None), 'events', None) or []):
        if event.get('event') == 'job_failed':
            return (event.get('detail') or {}).get('reason')
    return None


def log_of(runtime):
    # StagedRuntime bypasses Runtime.__init__, so the log is created lazily.
    return runtime.__dict__.setdefault('final_veto_log', [])


def final_veto(issued, now, phase, before, after, team, log):
    """Return the dispatch list with every terminal endpoint reduced to a single hold.

    ``before``/``after`` are the sets of terminal robots when the runtime call started and after all
    propagation. A robot that became terminal during the call and has no hold in the list gets one,
    so the stop reaches the backend in the same tick even if the endpoint had nothing queued.
    """
    vetoed = {rid: [c for r, c in issued if r == rid and c.get('kind') != 'hold'] for rid in after}
    out, placed = [], set()
    for rid, cmd in issued:
        if vetoed.get(rid):
            if rid not in placed:
                out.append((rid, copy.deepcopy(HOLD)))
                placed.add(rid)
            continue
        out.append((rid, cmd))
    for rid in sorted(after - before):
        if rid not in placed and not any(r == rid and c.get('kind') == 'hold' for r, c in out):
            out.append((rid, copy.deepcopy(HOLD)))
            placed.add(rid)
            log.append({'sim_s': now, 'phase': phase, 'robot_id': rid, 'vetoed': [],
                        'hold_added': True, 'newly_terminal': True,
                        'terminal_after': sorted(after)})
    for rid in sorted(vetoed):
        if vetoed[rid]:
            ep = endpoint(team, rid)
            log.append({'sim_s': now, 'phase': phase, 'robot_id': rid,
                        'vetoed': copy.deepcopy(vetoed[rid]), 'hold_added': False,
                        'newly_terminal': rid in after - before,
                        'reason': abort_reason(ep),
                        'terminal_after': sorted(after)})
    return out


def record(runtime):
    log = log_of(runtime)
    return {'profile': PROFILE, 'count': len(log), 'vetoes': copy.deepcopy(log)}
