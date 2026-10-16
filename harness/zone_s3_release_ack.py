"""Default-off OPEN lifecycle: queued -> host-issued receipt -> released.

Uses own issued-command acknowledgements only, never joint/contact telemetry.
The existing GO barrier, queued trajectory and physical guards are unchanged.
"""
OPTION = 'issued_open_v1'


def attach(ep, option='off'):
    if option == 'off':
        return ep
    if option != OPTION:
        raise ValueError('unknown release acknowledgement option')
    ctl = ep.controller
    original_set, original_wait = ctl.set, ctl._wait_open
    original_command = getattr(ctl, 'on_issued_command', None)
    pending = {}
    audit = []
    ctl.s3_release_ack = dict(option=option, runtime_gt=False, audit=audit,
        scope='host accepted own OPEN command; not measured finger position')

    def set_state(state, now, **detail):
        if ctl.state == 'wait_open' and state in ('released', 'cp_open'):
            if pending:
                raise RuntimeError('duplicate pending release')
            pending.update(target=state, requested_t=now, detail=detail, acknowledged_t=None)
            audit.append(dict(event='open_queued', t=now, target=state,
                issued_pwm=ctl._issued().get(1)))
            return
        # A failure/cancellation must never be overwritten by a late receipt.
        if pending and state != 'wait_open':
            pending.clear()
        return original_set(state, now, **detail)

    def on_command(row):
        if original_command is not None:
            original_command(row)
        if (pending and row.get('kind') == 'arm' and row.get('servo_id') == 1
                and row.get('pulse') == 2000 and row['t'] >= pending['requested_t']
                and pending['acknowledged_t'] is None):
            pending['acknowledged_t'] = row['t']
            audit.append(dict(event='open_host_issued', t=row['t'], pulse=row['pulse']))

    def wait_open(now, arm_idle):
        if not pending:
            return original_wait(now, arm_idle)
        # ArmSequence.commanded is a FUTURE target. Only on_command is called
        # after host.issue succeeds; stale OPEN from a previous epoch is ignored.
        if (not ctl.failure and pending['acknowledged_t'] is not None
                and ctl._issued().get(1) == 2000):
            saved = dict(pending)
            pending.clear()
            audit.append(dict(event='release_state_after_ack', t=now,
                acknowledged_t=saved['acknowledged_t'], target=saved['target']))
            return original_set(saved['target'], now, **saved['detail'])

    ctl.set, ctl._wait_open, ctl.on_issued_command = set_state, wait_open, on_command
    return ep
