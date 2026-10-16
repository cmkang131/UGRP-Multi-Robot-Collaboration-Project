"""Active adapter for the frozen M2 door student's delayed relocalization."""
from scripts.run_m2_pair import M2DoorStudent, PREGRASP_PANS_V2
from harness.owncam_drive import LOOK_P20, WIDE_LOOK_PANS


class ProviderM2DoorStudent(M2DoorStudent):
    def _queue_grasp(self, now):
        if self.pregrasp_done:
            return super()._queue_grasp(now)
        provider = self.driver._shared_pose
        if provider is None:
            raise ValueError('M2 adapter requires the owning pose provider')
        self.vo_pose = None
        provider.begin_relocalization(now, self.driver.servo)
        self.pregrasp_sweeps += 1
        self.pg_pans = list(PREGRASP_PANS_V2 if self.version in ('v2', 'v3') else WIDE_LOOK_PANS)
        self.arm.queue({**LOOK_P20, 6: self.pg_pans.pop(0)}, now, duration=.8, settle=.6)
        self.set('pregrasp_look', now, sweep=self.pregrasp_sweeps)
