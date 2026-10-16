"""Inherited tripwire: block genuine MuJoCo steps in pytest and Python children."""
import builtins
import os
import sys
_original_import = builtins.__import__
def _step_forbidden(*args, **kwargs):
    with open(os.environ['V6_STEP_AUDIT'], 'a') as stream:
        stream.write('blocked MuJoCo physical step\n')
    raise AssertionError('MuJoCo physical stepping forbidden by v6 regression scope')
def _guarded_import(name, *args, **kwargs):
    result = _original_import(name, *args, **kwargs)
    module = sys.modules.get('mujoco')
    if name == 'mujoco' and module is not None and not getattr(module, '_v6_step_guard_installed', False):
        for method in ('mj_step', 'mj_step1', 'mj_step2'):
            if hasattr(module, method):
                setattr(module, method, _step_forbidden)
        module._v6_step_guard_installed = True
    return result
builtins.__import__ = _guarded_import
