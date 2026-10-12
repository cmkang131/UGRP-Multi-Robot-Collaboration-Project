"""S3-only pulse calibration selection over the unchanged S2 runtime."""
from harness.zone_solo_cyan_pulse_cal import Runtime as Previous, OPTION
from harness.pulse_rotation_odometry import selected_model
from harness.zone_final_pair_binding import bind


def runtime_class(base):
    class Runtime(base):
        def __init__(self, *args, pulse_odometry='off', **kwargs):
            if pulse_odometry != 'off':
                if kwargs.get('pulse_motion_model', 'off') != OPTION:
                    raise ValueError('pulse_odometry requires fixed pulse model')
                kwargs['pulse_calibration'] = selected_model(
                    kwargs.get('pulse_calibration'), pulse_odometry=pulse_odometry)
            super().__init__(*args, **kwargs)
    return Runtime


Runtime = runtime_class(Previous)


def runtime_factory(config):
    from scripts import run_s2_unknown_start as old
    return bind(old.runtime_factory, UnknownStart=runtime_class(old.UnknownStart))(config)
