import pytest
from types import SimpleNamespace

from harness import grasp_speed_options as o


def test_default_is_off():
    assert o.parse('') == {} and o.parse(None) == {}


def test_parse_values_and_rejections():
    assert o.parse('adaptive_dt=0.001,idle_freeze,review_period=2') == {
        'adaptive_dt': .001, 'idle_freeze': True, 'review_period': 2.}
    assert o.parse('adaptive_dt')['adaptive_dt'] == .001
    for bad in ('adaptive_dt=0.002', 'adaptive_dt=0.00025', 'review_period=0.5', 'review_period=1.55',
                'nope', 'idle_freeze=1', 'idle_freeze,idle_freeze'):
        with pytest.raises(ValueError):
            o.parse(bad)


def test_adaptive_step_switches_once_from_issued_commands_only():
    world = SimpleNamespace(model=SimpleNamespace(opt=SimpleNamespace(timestep=.00025)))
    step = o.AdaptiveStep(world, .001, {'r1': {1: 2000, 5: 1320}, 'r2': {1: 2000, 5: 1320}})
    assert world.model.opt.timestep == .001
    base = {'1': 2000, '3': 740, '4': 2320, '5': 1320, '6': 1500}
    step.observe('r1', {**base, '3': 500, '4': 2500}, 1.)       # approach posing keeps the coarse step
    assert world.model.opt.timestep == .001 and not step.fine
    step.observe('r2', {**base, '5': 1344}, 2.)                 # arm leaves its setpoint
    assert world.model.opt.timestep == o.FINE_DT_S and step.fine
    step.observe('r1', {**base, '1': 1500}, 3.)
    assert len(step.events) == 1 and step.record()['switched'] is True
