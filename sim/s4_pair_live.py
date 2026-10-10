"""S3 v165 coupled plant, with the existing independent cyan guard retained."""
from sim.s3_synchronized_carry import PhysicsBackend as Previous
from sim.s3_stage_safety import check_cyan


class PhysicsBackend(Previous):
    def eval_sample(self):
        super().eval_sample()
        if self.bundle['case'] != 'cyan':
            check_cyan(self, self.stage_cyan_guard)
