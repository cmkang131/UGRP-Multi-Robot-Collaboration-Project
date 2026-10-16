"""Import-only MuJoCo placeholder for source/XML audits; every API use fails."""
import types


def forbidden(*args, **kwargs):
    raise AssertionError('MuJoCo API use is forbidden in this static audit')


def unavailable(name):
    if name.startswith('__'):
        raise AttributeError(name)
    return forbidden


def module():
    value = types.ModuleType('mujoco')
    value.__file__ = '<offline-mujoco>'
    value.__getattr__ = unavailable
    return value
