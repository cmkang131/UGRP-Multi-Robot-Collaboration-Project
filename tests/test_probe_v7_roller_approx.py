import math

import pytest

from scripts import probe_v7_roller_approx as probe


def forward(v, tail_min=None, peak=1., status='MEASURED_DEV'):
    return {'status': status, 'steady_velocity': [v, 0, 0, 0, 0, 0],
            'tail_forward_min_mps': v*.95 if tail_min is None else tail_min, 'peak_command_com_xy_m': peak}


def test_acceptance_limits_are_the_declared_ones():
    assert probe.ACCEPT['forward_speed_rel'] == .05
    assert probe.ACCEPT['left_yaw_diff_deg'] == .5
    assert probe.ACCEPT['speed_gain_min'] == 1.2


def test_forward_speed_within_five_percent_passes_and_outside_fails():
    assert probe.compare_forward('f050', 50, forward(.22), forward(.2299))['passed']
    assert not probe.compare_forward('f050', 50, forward(.22), forward(.2321))['passed']


def test_stationary_and_sustained_judgements_must_match():
    assert probe.compare_forward('f020', 20, forward(0, peak=2e-5), forward(0, peak=5e-4))['passed']
    assert not probe.compare_forward('f020', 20, forward(0, peak=2e-5), forward(0, peak=.0015))['passed']
    # one variant stops while the other keeps driving
    assert not probe.compare_forward('f035', 35, forward(.138), forward(.138, tail_min=5e-4))['passed']
    assert not probe.compare_forward('f035', 35, forward(.138), forward(.138, status='PHYSICS_FAILURE'))['passed']


def left(yaw_deg, vy=.1246, tail=.1198, status='MEASURED_DEV'):
    return {'status': status, 'yaw_change_rad': math.radians(yaw_deg), 'steady_velocity': [0, vy, 0, 0, 0, 0],
            'tail_lateral_min_mps': tail}


def test_left_yaw_difference_limit():
    assert probe.compare_left('left', left(-2.49), left(-2.89))['passed']
    assert not probe.compare_left('left', left(-2.49), left(-3.05))['passed']
    assert not probe.compare_left('left', left(-2.49), left(-2.49, vy=.14))['passed']


def beam(y=.0305, yaw=-3.35, progress=.0545, status='MEASURED_DEV'):
    return {'status': status, 'final': {'beam_delta_m': [0, y, 0], 'beam_yaw_change_deg': yaw,
            'progress_difference_m': progress}}


def test_beam_comparison_limits():
    assert probe.compare_beam(beam(), beam(y=.0325, yaw=-3.6, progress=.0585))['passed']
    assert not probe.compare_beam(beam(), beam(y=.0345))['passed']
    assert not probe.compare_beam(beam(), beam(yaw=-4.0))['passed']
    assert not probe.compare_beam(beam(), beam(status='PHYSICS_FAILURE'))['passed']


def test_speed_summary_gain_uses_physics_only_time():
    def run(step, sim=6., diag=1.2):
        return {'sim_s': sim, 'wall_per_sim': diag, 'profile': {'step_total_s': step}}
    summary = probe.speed_summary({'mesh': [run(3.0), run(3.3)], 'sphere6_v1': [run(2.0), run(2.2)], 'mesh_freeze': [run(2.4), run(2.4)]})
    assert summary['gain_physics_only'] == pytest.approx(1.5)
    assert summary['variants']['mesh_freeze']['gain_physics_only'] == pytest.approx(1.3125)
    assert summary['passed']
    slow = probe.speed_summary({'mesh': [run(3.0)], 'sphere6_v1': [run(2.7)]})
    assert not slow['passed']


def test_timer_delta_reports_per_call_microseconds():
    from scripts.probe_masterpi_drive_friction import timer_delta
    before = {'step': (1.0, 100), 'forward': (.5, 100)}
    after = {'step': (1.2, 300), 'forward': (.5, 100)}
    assert timer_delta(before, after) == {'step': {'calls': 200, 'total_s': pytest.approx(.2), 'mean_us': pytest.approx(1000.)}}


def test_timer_snapshot_reads_every_mujoco_stage():
    import mujoco
    from scripts.probe_masterpi_drive_friction import timer_snapshot
    model = mujoco.MjModel.from_xml_string('<mujoco><worldbody><geom type="plane" size="1 1 .1"/></worldbody></mujoco>')
    data = mujoco.MjData(model)
    before = timer_snapshot(data)
    mujoco.mj_step(model, data)
    after = timer_snapshot(data)
    assert {'step', 'forward', 'position', 'constraint', 'pos_collision', 'col_narrow'} <= set(before)
    assert after['step'][1] == before['step'][1]+1 and after['step'][0] >= before['step'][0]
