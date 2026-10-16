"""Unchanged S3 supported-lowering supervisor plus the existing cyan stop guard."""
from sim.s3_setdown import PhysicsBackend as Previous
from sim.s3_stage_safety import check_cyan


class PhysicsBackend(Previous):
    def eval_sample(self):
        super().eval_sample()
        if self.bundle['case']!='cyan':check_cyan(self,self.stage_cyan_guard)
