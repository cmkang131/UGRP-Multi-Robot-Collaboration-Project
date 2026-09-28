"""Which camera frames a runner writes to disk (2026-09-27 user decision, docs/disk_management.md section 5).

Profiles are versioned and never change meaning once published:

``all_v1``
    Write every frame. This is the behaviour of every runner before 2026-09-27, of every test cohort and of
    every past pre-registration. It is the default.
``dev_1hz_decisions_v1``
    Development and diagnostic runs only. Per stream (one robot camera, or the TOP camera), write a
    periodic frame when at least 1.0 SIM s has passed since the last periodic frame written, and always
    write a decision frame (a capture the controller asked for, the capture after a macro, or a frame
    during which the controller emitted an event or changed phase). Decision frames do not move the
    periodic clock.

The policy only decides whether the JPEG *file* is written. The caller still records every frame's
SIM time and sha256 in its frame log, so a skipped frame is known by hash. Model-request images (LLM, ACT,
trained students) are not camera frames in this sense and are always kept byte for byte (AGENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

PERIOD_EPS_S = 1e-6


@dataclass(frozen=True)
class FrameProfile:
    name: str
    period_s: float | None  # None: write every frame
    reduced: bool
    description: str


PROFILES: dict[str, FrameProfile] = {
    "all_v1": FrameProfile("all_v1", None, False, "every frame (pre-2026-09-27 behaviour; test cohorts)"),
    "dev_1hz_decisions_v1": FrameProfile(
        "dev_1hz_decisions_v1", 1.0, True,
        "dev/diagnostic only: 1 periodic frame per SIM s per stream + every decision frame"),
}
DEFAULT_PROFILE = "all_v1"
REDUCED_SPLITS = ("dev", "diag")


@dataclass
class FrameStoragePolicy:
    """Per-run policy; one instance per episode. ``split`` must be given for a reduced profile."""

    profile: str = DEFAULT_PROFILE
    split: str | None = None
    _last_periodic: dict[str, float] = field(default_factory=dict)
    _counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise ValueError(f"unknown frame profile {self.profile!r}; known: {sorted(PROFILES)}")
        if PROFILES[self.profile].reduced and self.split not in REDUCED_SPLITS:
            raise ValueError(f"frame profile {self.profile!r} is for splits {REDUCED_SPLITS}, not {self.split!r};"
                             " test cohorts and pre-registered runs keep every frame (all_v1)")

    def decide(self, stream: str, t: float, *, decision: bool = False, reason: str | None = None) -> dict:
        """Return ``{'saved': bool, 'why': str}`` for one frame of ``stream`` at SIM time ``t``."""
        spec = PROFILES[self.profile]
        counts = self._counts.setdefault(stream, {"frames": 0, "saved": 0, "decision": 0, "periodic": 0})
        counts["frames"] += 1
        if spec.period_s is None:
            why = "all"
        elif decision:
            why = f"decision:{reason}" if reason else "decision"
            counts["decision"] += 1
        else:
            last = self._last_periodic.get(stream)
            if last is None or t - last >= spec.period_s - PERIOD_EPS_S:
                self._last_periodic[stream] = float(t)
                why = "periodic"
                counts["periodic"] += 1
            else:
                return {"saved": False, "why": "skipped"}
        counts["saved"] += 1
        return {"saved": True, "why": why}

    def record(self) -> dict:
        """Manifest block: profile, its meaning and per-stream counts (frames seen / files written)."""
        spec = PROFILES[self.profile]
        return {"schema": "ugrp.frame-storage.v1", "profile": spec.name, "split": self.split,
                "period_s": spec.period_s, "description": spec.description,
                "streams": {k: dict(v) for k, v in sorted(self._counts.items())}}
