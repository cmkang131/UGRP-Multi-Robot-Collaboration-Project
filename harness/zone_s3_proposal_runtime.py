"""S3 option composition; historical entry points and defaults stay unchanged."""
import copy
from harness.zone_s3_recovery_runtime import Runtime as Previous
from harness import pf_sensor_proposal as pf
from harness.zone_s3_alignment_entry import attach_endpoint


class Runtime(Previous):
    def __init__(self, static, *args, config, **kwargs):
        plain = copy.deepcopy(config)
        sensor = plain['options'].pop('sensor_proposal', 'off')
        count = plain['options'].pop('tracking_particles', None)
        entry = plain['options'].pop('alignment_entry', 'off')
        super().__init__(static, *args, config=plain, **kwargs)
        for own in self.localizers.values():
            pf.attach_s3(own, sensor_proposal=sensor, tracking_particles=count, static=static)
        if entry != 'off':
            pair = self.pair.producer
            submit = self.links['r1'].submit
            def submitted(*a, **kw):
                result = submit(*a, **kw)
                for session in pair.team.sessions:
                    for ep in session['endpoints'].values():
                        if not hasattr(ep.controller, 's3_alignment_entry'):
                            attach_endpoint(ep, alignment_entry=entry)
                return result
            for rid in ('r1', 'r2'): self.links[rid].submit = submitted
            record = pair.record
            pair.record = lambda: {**record(), 'alignment_entry': {ep.own.robot_id:
                copy.deepcopy(ep.controller.s3_alignment_entry)
                for session in pair.team.sessions for ep in session['endpoints'].values()}}
