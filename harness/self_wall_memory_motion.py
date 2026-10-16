"""Additive motion-model selection for the existing private RBPF wall memory."""
from harness.self_wall_memory import SelfWallMemory as Previous
from harness.self_pulse_odom import OPTION, PulseOdometry, MODEL_SHA256
from harness.self_pulse_rotation import OPTION as ROTATION, RotationPulseOdometry, CALIBRATION_SHA256


class SelfWallMemory(Previous):
    def __init__(self, *args, motion_model='off', **kwargs):
        if motion_model not in ('off',OPTION,ROTATION):
            raise ValueError('UNKNOWN_MOTION_MODEL')
        if motion_model != 'off' and kwargs.get('pose_correction') != 'own_map_rbpf_v1':
            raise ValueError('PULSE_MEMORY_REQUIRES_RBPF')
        super().__init__(*args, **kwargs)
        self.motion_model = motion_model
        if motion_model != 'off':
            grid = self.self_map
            driver = (RotationPulseOdometry if motion_model == ROTATION else PulseOdometry)(grid.odom.t)
            driver.step_callback = grid.propagate
            grid.odom.driver = driver

    def snapshot(self):
        result = super().snapshot()
        if self.motion_model != 'off':
            result['self_map_motion_model'] = dict(option=self.motion_model,sha256=MODEL_SHA256)
            if self.motion_model == ROTATION:
                result['self_map_motion_model']['rotation_calibration_sha256'] = CALIBRATION_SHA256
        return result
