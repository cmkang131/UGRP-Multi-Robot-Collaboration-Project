"""Additive motion-model selection for the existing private RBPF wall memory."""
from harness.self_wall_memory import SelfWallMemory as Previous
from harness.self_pulse_odom import OPTION, PulseOdometry, MODEL_SHA256


class SelfWallMemory(Previous):
    def __init__(self, *args, motion_model='off', **kwargs):
        if motion_model not in ('off',OPTION):
            raise ValueError('UNKNOWN_MOTION_MODEL')
        if motion_model != 'off' and kwargs.get('pose_correction') != 'own_map_rbpf_v1':
            raise ValueError('PULSE_MEMORY_REQUIRES_RBPF')
        super().__init__(*args, **kwargs)
        self.motion_model = motion_model
        if motion_model != 'off':
            grid = self.self_map
            driver = PulseOdometry(grid.odom.t)
            driver.step_callback = grid.propagate
            grid.odom.driver = driver

    def snapshot(self):
        result = super().snapshot()
        if self.motion_model != 'off':
            result['self_map_motion_model'] = dict(option=self.motion_model,sha256=MODEL_SHA256)
        return result
