"""PR #235 review 7: arm-wait dispatch through the host, no physics or models."""
from dataclasses import replace

import pytest

from sim.camera_robot_port import CameraRobotPort
from tests.test_camera_robot_port import _WorldSpy
from tests.test_zone_pair_executor import active, ends, m2_controller, pair_obs, setup, start


@pytest.mark.parametrize('real_port', [False, True], ids=['fake-port', 'camera-port'])
def test_pregrasp_look_collision_hold_preserves_pair_and_resumes_arm_queue(real_port):
    host, exs = setup(factory=m2_controller)
    assert start(host)['accepted']
    eps = active(host)
    ep, own = eps['r1'], exs['r1']
    if real_port:
        # The production port on actuator spies: validation/hold really run,
        # but no simulator is constructed and no physics step is performed.
        world = _WorldSpy()
        world.robots['r1'].servo_command_pulses = dict(own.servo)
        host.robots['r1'].port = CameraRobotPort(world, 'r1', allow_reverse=True, allow_mecanum=True)

    ep.started = ep.control_started = True
    ctl = ep.controller
    ctl.state = 'cp_open'
    ctl.arm.events.clear()
    ctl.arm.until = 0.
    assert ep.command_guard.before_control(0.)
    ctl._cp_open(0., True)  # Real M2 checkpoint enters its stationary sweep.
    assert ctl.state == 'pregrasp_look' and len(ctl.arm.events) == 64
    original, until = list(ctl.arm.events), ctl.arm.until
    # A peer queue must survive the wait as well (no propagated PARTNER_ABORT).
    eps['r2'].controller.arm.queue({6: 1520}, 1., duration=.2, settle=.1)
    peer_queue = list(eps['r2'].controller.arm.events)

    now = 0.
    for sigma in (.12, .12, .01):
        now += .05  # Follow the host's unrounded arm clock.
        own.last_report = replace(own.last_report, t_est=now, initialized=True,
                                  x_m=1.975, y_m=.05, std_xy_m=sigma)
        own.last_obs = pair_obs('r1', own.last_obs['frame_id'] + 1, now, own.servo)
        for endpoint in eps.values():
            endpoint.status.tick('aligning', now)
        before = len(host.robots['r1'].commands)
        host._pair_arm_tick(now)
        for rid, endpoint in eps.items():
            assert not host.robots[rid].dead, host.robots[rid].exception
            assert host.robots[rid].exception is None
            assert not endpoint.terminal and not ends(exs[rid])
        assert eps['r2'].controller.arm.events == peer_queue
        issued = host.robots['r1'].commands[before:]
        if sigma == .12:
            assert issued == [{'t': now, 'kind': 'hold'}]
            assert len(ctl.arm.events) == 64
            assert [(s, p) for _, s, p in ctl.arm.events] == [(s, p) for _, s, p in original]
            assert ep.command_guard.recheck.waited_s == pytest.approx(now - .05)
            if real_port:
                assert world.robots['r1'].motor_calls[-1] == [0.] * 4
                assert not world.robots['r1'].servo_calls
            else:
                assert host.robots['r1'].port.log[-1] == (now, 'hold', {})
        else:
            assert len(issued) == 4 and all(c['kind'] in ('arm', 'look') for c in issued)
            assert len(ctl.arm.events) == 60
            assert ep.arm_wait_at is None
    assert ctl.arm.until == pytest.approx(until + .1)
