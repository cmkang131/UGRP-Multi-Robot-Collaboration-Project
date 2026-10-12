"""Versioned S3 wrapper for explicit PF numerical and consistency options."""
import copy
from harness.zone_s3_motion_runtime import Runtime as Previous
from harness.pf_observation_consistency import attach_s3
from harness.zone_s3_pose_validity import attach, finite_record


class Runtime(Previous):
    def __init__(self, *args, config, **kwargs):
        plain = copy.deepcopy(config)
        option = plain['options'].pop('observation_consistency', 'off')
        validity = plain['options'].pop('pose_validity', 'off')
        if validity != 'off' and plain['options'].get('s3_dev_light') != 'continue_estimate_v1':
            raise ValueError('prediction-only camera deferral requires explicit S3 dev_light')
        super().__init__(*args, config=plain, **kwargs)
        self.pose_validity = validity
        for own in self.localizers.values():
            attach_s3(own, observation_consistency=option)
            attach(own, pose_validity=validity)

    def step(self, now):
        if self.pose_validity != 'off':
            for rid, own in self.localizers.items():
                if own.pose.provider.failure:
                    raise RuntimeError('POSE_PROVIDER_FAILED '+rid+': '+str(own.pose.provider.failure))
        return super().step(now)

    def record(self):
        value = super().record()
        return finite_record(value) if self.pose_validity != 'off' else value
