"""Memory confidence over an injected provider, with explicit measurement evidence.

Missing consistency diagnostics never count as evidence. The unchanged v3
guard inflates uncertainty until the provider supplies independent diagnostics.
"""
from harness.owncam_pose_guard_v3 import GuardedLocalizerV3


class GuardedPoseProviderV3:
    def __init__(self, provider, guard):
        self.provider, self.guard = provider, guard
        self.loc = GuardedLocalizerV3(provider.loc, guard)
        self.frames = 0
        self.last_raw_report = None

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def on_command(self, row):
        self.guard.on_command(row, self.get_motion_params())
        self.provider.on_command(row)

    def get_motion_params(self):
        return self.provider.get_motion_params()

    def on_frame(self, now, rgb):
        self.guard.advance(now)
        self.frames += 1
        if self.guard.last_evidence_t == now:
            return self.report(now)
        raw = self.provider.on_frame(now, rgb)
        self.last_raw_report = raw
        self.guard.observe_pose(raw)
        evidence = (raw.observation_quality or {}).get('consistency', {})
        accepted = bool((raw.observation_quality or {}).get('accepted'))
        self.guard.observe_evidence(now, self.frames,
                                    nis=evidence.get('nis') if accepted else None,
                                    log_likelihood=evidence.get('log_likelihood') if accepted else None,
                                    settled=accepted and evidence.get('settled') is True)
        return self.guard.effective_report(raw, now)

    def report(self, now):
        return self.guard.effective_report(self.provider.report(now), now)
