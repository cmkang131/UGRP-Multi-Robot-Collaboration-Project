import importlib.util
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location('act17_open_loop', Path(__file__).resolve().parents[1]/'scripts/act17_open_loop.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_physical_command_unit_conversions():
    a = np.zeros(14)
    a[:4], a[4:8], a[8:13] = .31, 1., .02
    e = m.action_errors(a, np.zeros(14))
    assert np.allclose(e['wheel_full_scale'], .31)
    assert np.allclose(e['pulse_ms'], 150)
    assert np.allclose(e['servo_PWM_counts'], 20)
    assert m.quantiles([0, 1, 2]) == dict(n=3, median=1., p90=1.8)


def test_phase_buckets_keep_release_separate():
    assert m.phase_group(dict(skill='grasp', teacher_phase='align')) == 'alignment'
    assert m.phase_group(dict(skill='grasp', teacher_phase='approach')) == 'approach'
    assert m.phase_group(dict(skill='grasp', teacher_phase='close')) == 'grasp'
    assert m.phase_group(dict(skill='release', teacher_phase='align')) == 'release'
