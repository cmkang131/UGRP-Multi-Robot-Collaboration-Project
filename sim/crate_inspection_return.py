"""One bounded return to the just-used pickup pose to inspect the floor.

UNKNOWN is never converted into destination INSIDE. If the bases have not
been commanded to move since closing, reverse the checked constant-XY lift,
open, back off, and obtain a new own-camera floor scan. No arm/camera pan is
issued while gripping. Command reversibility is not physical success.
"""
from sim.crate_cartesian_lift import plan_lift, DT_S, DURATION_S

MODE = 'crate_inspection_return_v1'


def reverse_lift(closed_pwm, current_pwm, issued_since_close):
    """Return per-robot (offset, PWM) events, or None; own commands only."""
    if not issued_since_close or any(any(c['wheels']) for c in issued_since_close):
        return None
    closed = {int(k): int(v) for k, v in closed_pwm.items()}
    current = {int(k): int(v) for k, v in current_pwm.items()}
    if closed.get(1) != current.get(1) or current.get(1, 2000) >= 1900:
        return None
    plan, _ = plan_lift(closed)
    if plan is None or any(current.get(s) != plan['issued_pwm'][s] for s in (3, 4, 5, 6)):
        return None
    # Rebuild the very same accepted PWM samples, then reverse them.
    samples = [dict(closed)]
    for i in range(1, round(DURATION_S/DT_S)+1):
        sample = dict(samples[-1])
        for at, servo, pwm in plan['events']:
            if abs(at-i*DT_S) < 1e-8:
                sample[servo] = pwm
        samples.append(sample)
    # Ensure the recorded path actually followed this family: no unrelated
    # arm command can be hidden by a matching endpoint.
    allowed = {tuple(p[s] for s in (1, 3, 4, 5, 6)) for p in samples}
    for command in issued_since_close:
        p = {int(k): int(v) for k, v in command['pwm'].items()}
        if tuple(p[s] for s in (1, 3, 4, 5, 6)) not in allowed:
            return None
    return [(i*DT_S, {s: p[s] for s in (3, 4, 5, 6)})
            for i, p in enumerate(reversed(samples[:-1]), 1)]


def inspection_choice(choice, paths, *, used, after_visible):
    """Finite signal decision + locally certified return paths, no margins."""
    if (choice['action'] == 'observe' and not used and not after_visible
            and paths and all(path is not None for path in paths.values())):
        return 'return_to_pickup_for_observation'
    return 'insufficient'
