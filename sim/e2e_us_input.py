"""Own-sonar acquisition for E2E; the controller receives no world reference."""
from harness.ultrasonic_input import OwnRangeInput
from harness.ultrasonic_model import sensor_seed
from sim.ultrasonic_input import OwnUltrasonicRig


def attach(backend, robots, *, seed, out):
    """After reset: timestamps and noise ticks use the E2E episode clock."""
    origin = backend.now
    ranges = OwnRangeInput(tuple(robots), 'on_v1',
        noise_seeds={r: sensor_seed(seed, r) for r in robots}, out_dir=out,
        run_meta={'clock': 'episode_since_reset', 'raw_time_origin': origin,
                  'poll_interval_s': .05, 'effective_period_s': .10})
    try:
        rig = OwnUltrasonicRig(backend.world.model, backend.world.data, tuple(robots),
                              episode_seed=seed, range_input=ranges)
    except Exception:
        ranges.close()
        raise
    for rid, robot in robots.items():
        robot.range_provider = rig.provider(rid)
    advance, close = backend.advance_to, backend.close

    def advance_to(t):
        advance(t)
        rig.tick(round(backend.now-origin, 8))

    def closed():
        try:
            rig.close()
        finally:
            close()

    backend.advance_to, backend.close = advance_to, closed
    rig.tick(0.)
    return rig
