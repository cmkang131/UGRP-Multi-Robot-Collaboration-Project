"""Offline synthetic own-camera evidence; no physics, joint reads or contacts."""
import numpy as np
import pytest
from sim.crate_rgb_lift import confirm, confirm_v2, LiftObserver


def frame(end='blue', *, shift=0, loss=False, floor=False):
    f = np.zeros((100, 120, 3), np.uint8)
    f[:] = (140, 140, 140) if floor else (255, 150, 180)
    f[40:100, max(0, shift):min(120, 120+shift)] = (0, 20, 255) if end == 'blue' else (0, 255, 120)
    if loss:
        f[:] = (140, 140, 140)
    return f


def command(t, arm=1200, *, pan=1500, grip=1500, wheels=None):
    return {'t': t, 'pwm': {'1': grip, '3': arm, '4': 2100, '5': 2400, '6': pan},
            'wheels': wheels or [0.]*4, 'duration_s': [0.]*4}


def history():
    return [command(0), command(1.7, 750), command(4.7, 750)]


@pytest.mark.parametrize('end', ['blue', 'teal'])
def test_close_rigid_view_confirms_without_any_background(end):
    before = frame(end)
    assert confirm(before, before, end)['verdict'] == 'undetermined'
    out = confirm_v2(before, before, end, commands=history(), settled=before)
    assert out['verdict'] == 'confirmed'
    assert len(out['comparisons']) == 2


def test_missing_wrong_or_lost_assigned_lug_and_post_hold_drop_block_release():
    b = frame()
    assert confirm_v2(frame('teal'), b, 'blue', commands=history(), settled=b)['verdict'] == 'undetermined'
    assert confirm_v2(b, frame(loss=True), 'blue', commands=history(), settled=b)['verdict'] == 'not_confirmed'
    assert confirm_v2(b, b, 'blue', commands=history(), settled=frame(loss=True))['verdict'] == 'not_confirmed'
    # Same held area with a shifted part must not be treated as persistence.
    assert confirm_v2(b, np.roll(b, 25, axis=0), 'blue', commands=history(), settled=b)['verdict'] == 'undetermined'
    assert confirm_v2(b, b, 'blue', commands=history())['verdict'] == 'undetermined'
    assert confirm_v2(b, np.full_like(b, (255, 150, 180)), 'blue', commands=history(), settled=b)['verdict'] == 'not_confirmed'


@pytest.mark.parametrize('commands', [[], [command(0), command(5)],
    [command(0), command(1.7, 750, grip=2000)],
    [command(0), command(1.7, 750, pan=1540)],
    [command(0), command(1.7, 750, wheels=[.35]*4)],
    [command(0), command(.5, 750)]])
def test_pixels_alone_cannot_authorize_without_compatible_issued_lift(commands):
    b = frame()
    assert confirm_v2(b, b, 'blue', commands=commands, settled=b)['verdict'] == 'undetermined'


def test_runner_observer_waits_for_own_permit_completion_and_three_second_hold():
    o = LiftObserver('blue')
    captured = []
    def capture(tag):
        captured.append(tag)
        return frame()
    assert o.observe(permit=False, complete=False, command=command(-1), capture=capture) is None
    assert not captured
    assert o.observe(permit=True, complete=False, command=command(0), capture=capture) is None
    assert o.observe(permit=False, complete=True, command=command(1.7, 750), capture=capture) is None
    assert o.observe(permit=False, complete=True, command=command(4.6, 750), capture=capture) is None
    out = o.observe(permit=False, complete=True, command=command(4.7, 750), capture=capture)
    assert out['verdict'] == 'confirmed'
    assert captured == ['before_lift', 'lift_complete', 'settled_hold']
    # Both robots are still required by the actual release authorization helper.
    from scripts.run_crate_teacher import release_ready
    assert not release_ready({'r1': True, 'r2': True}, 3, {'r1': out, 'r2': {'verdict': 'undetermined'}})


@pytest.mark.parametrize('end', ['blue', 'teal'])
def test_v3_retains_lug_but_allows_body_outline_rotation(end):
    from sim.crate_rgb_lift import confirm_v3
    b = np.zeros((100, 120, 3), np.uint8) + 140
    b[5:50, 30:90] = (255, 150, 180)
    b[55:90, 20:100] = (0, 20, 255) if end == 'blue' else (0, 255, 120)
    a = b.copy()
    a[20:35, 10:110] = (255, 150, 180)  # body outline wider; grasped lug unchanged
    assert confirm_v2(b, a, end, commands=history(), settled=a)['verdict'] == 'undetermined'
    assert confirm_v3(b, a, end, commands=history(), settled=a)['verdict'] == 'confirmed'
    # Neither one colour alone, a vanished body, nor body sliding down is accepted.
    missing = a.copy(); missing[:55] = 140
    assert confirm_v3(b, missing, end, commands=history(), settled=missing)['verdict'] == 'not_confirmed'
    down = b.copy(); down[:55] = 140; down[22:52, 30:90] = (255, 150, 180)
    assert confirm_v3(b, down, end, commands=history(), settled=down)['verdict'] == 'not_confirmed'
    assert confirm_v3(b, a, end, commands=history())['verdict'] == 'undetermined'
    assert confirm_v3(b, a, end, commands=[], settled=a)['verdict'] == 'undetermined'
    assert confirm_v3(b, a, end, commands=history(), settled=frame(loss=True))['verdict'] == 'not_confirmed'


def test_v3_opt_in_observer_does_not_change_v2_or_solo_core():
    from sim.crate_rgb_lift import confirm_v3
    assert LiftObserver('teal').confirm is confirm_v2
    assert LiftObserver('teal', mode='crate_rgb_lift_v3').confirm is confirm_v3
    with pytest.raises(ValueError):
        LiftObserver('teal', mode='unknown')


@pytest.mark.parametrize('end', ['blue', 'teal'])
@pytest.mark.parametrize('stale_sample', ['lift_complete', 'settled_hold', 'both'])
def test_v3_repeated_pre_lift_image_cannot_authorize_release(end, stale_sample):
    from sim.crate_rgb_lift import confirm_v3
    from scripts.run_crate_teacher import release_ready
    before = frame(end)
    changed = before.copy()
    changed[0, 0] = (250, 150, 180)
    after = before.copy() if stale_sample in ('lift_complete', 'both') else changed
    settled = before.copy() if stale_sample in ('settled_hold', 'both') else changed
    out = confirm_v3(before, after, end, commands=history(), settled=settled)
    assert out['verdict'] == 'undetermined'
    assert 'identical to pre-lift' in out['reason']
    assert not release_ready({'r1': True, 'r2': True}, 3,
                             {'r1': out, 'r2': {'verdict': 'confirmed'}})
    # The legacy opt-in retains its old semantics.
    assert confirm_v2(before, before, end, commands=history(), settled=before)['verdict'] == 'confirmed'
