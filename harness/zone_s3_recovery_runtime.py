"""Versioned opt-in S3 lease/own-RGB/PF diversity composition."""
import copy
from harness.zone_s3_consistent_runtime import Runtime as Previous
from harness import pf_resampling_diversity as pf
from harness import zone_s3_door_lease as door
from harness import zone_s3_visual_alignment as alignment


class Runtime(Previous):
    def __init__(self, static, *args, config, **kwargs):
        plain = copy.deepcopy(config)
        diversity = plain['options'].pop('resampling_diversity', 'off')
        lease = plain['options'].pop('door_lease', 'off')
        visual = plain['options'].pop('visual_alignment', 'off')
        super().__init__(static, *args, config=plain, **kwargs)
        for own in self.localizers.values(): pf.attach_s3(own, resampling_diversity=diversity)
        pair = self.pair.producer
        alignment.attach(pair, visual_alignment=visual, submit=self.links['r1'].submit)
        if visual != 'off':
            for rid in ('r1', 'r2'): self.links[rid].submit = pair.s3_visual_submit
        door.attach(self, static=static, door_lease=lease,
            dev_light=plain['options'].get('s3_dev_light')=='continue_estimate_v1')
