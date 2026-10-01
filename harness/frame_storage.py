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

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PERIOD_EPS_S = 1e-6
DEFAULT_WRITE_CAP_MIB = 64.0      # per run; raise it only in the run's bundle/config and record it
MP4_CRF = 28


@dataclass(frozen=True)
class FrameProfile:
    name: str
    period_s: float | None  # None: every frame (when the profile stores frames at all)
    reduced: bool
    description: str
    store: str = "jpeg"     # "jpeg": original JPEG files, "mp4": one mp4 per stream, "none": hashes only


PROFILES: dict[str, FrameProfile] = {
    "all_v1": FrameProfile("all_v1", None, False, "every frame as original JPEG (explicit opt-in; capped)"),
    "dev_1hz_decisions_v1": FrameProfile(
        "dev_1hz_decisions_v1", 1.0, True,
        "dev/diagnostic only: 1 periodic frame per SIM s per stream + every decision frame"),
    "none_v1": FrameProfile("none_v1", None, False, "default: no frame bytes, per-frame sha256 list only", "none"),
    "mp4_v1": FrameProfile("mp4_v1", None, False, "one H.264 mp4 per stream + per-frame sha256 list", "mp4"),
}
DEFAULT_PROFILE = "none_v1"
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
        if spec.store != "jpeg":
            return {"saved": False, "why": f"{spec.store}_only"}
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
                "period_s": spec.period_s, "store": spec.store, "description": spec.description,
                "streams": {k: dict(v) for k, v in sorted(self._counts.items())}}


# ---------------------------------------------------------------------------------------------------------
# Per-run write cap and the sink that applies a profile (2026-10-01).
# ---------------------------------------------------------------------------------------------------------

class FrameWriteCapExceeded(OSError):
    """A run wrote more frame bytes than its cap. An OSError so host guards treat it as infrastructure and stop
    the run (it is not a task failure and not ENOSPC; errno stays None)."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _Mp4Stream:
    """ffmpeg process fed with original JPEG bytes (image2pipe/mjpeg); one per stream."""

    def __init__(self, dest: Path, fps: float):
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("profile mp4_v1 needs ffmpeg on PATH")
        self.dest = dest
        self.proc = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", f"{fps:g}", "-c:v", "mjpeg",
             "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(MP4_CRF),
             "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-movflags", "+faststart", str(dest)],
            stdin=subprocess.PIPE)

    def write(self, jpeg: bytes) -> None:
        self.proc.stdin.write(jpeg)

    def size(self) -> int:
        try:
            return self.dest.stat().st_size
        except FileNotFoundError:
            return 0

    def close(self) -> None:
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed for {self.dest}")


class FrameSink:
    """Apply a ``FrameStoragePolicy`` to the frames of one run and enforce the per-run write cap.

    ``add`` logs every frame's sha256 to ``<out_dir>/frames.sha256.jsonl`` (flushed per frame, so an aborted run
    keeps the list) and writes JPEG/mp4 bytes only when the profile says so. ``close`` finalizes the mp4 files and
    returns the manifest block. The cap counts frame bytes written (JPEG files, finished mp4 files) and raises
    ``FrameWriteCapExceeded`` on the frame that crosses it.
    """

    HASH_LIST = "frames.sha256.jsonl"

    def __init__(self, out_dir, profile: str = DEFAULT_PROFILE, *, split: str | None = None,
                 cap_mib: float = DEFAULT_WRITE_CAP_MIB, fps: float = 5.0):
        if cap_mib is None or cap_mib <= 0:
            raise ValueError("a positive per-run frame write cap (MiB) is required; there is no unlimited mode")
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.policy = FrameStoragePolicy(profile, split=split)
        self.cap_bytes = int(cap_mib * 2**20)
        self.cap_mib, self.fps = float(cap_mib), float(fps)
        self.bytes_written = 0
        self._jpeg_bytes = 0
        self.cap_exceeded = False
        self._hash_log = (self.out / self.HASH_LIST).open("a", buffering=1)
        self._mp4: dict[str, _Mp4Stream] = {}
        self._index: dict[str, int] = {}
        self._closed = False

    def _check_cap(self) -> None:
        """Frame bytes on disk = JPEG files written + the mp4 files (their current size, ffmpeg writes as it goes)."""
        mp4_now = sum(stream.size() for stream in self._mp4.values())
        self.bytes_written = self._jpeg_bytes + mp4_now
        if self.bytes_written > self.cap_bytes:
            self.cap_exceeded = True
            raise FrameWriteCapExceeded(
                f"frame writes {self.bytes_written / 2**20:.1f} MiB exceed the {self.cap_mib:g} MiB per-run cap "
                f"(profile {self.policy.profile}); raise the cap in the run config or store fewer frames")

    def add(self, stream: str, t: float, jpeg: bytes, *, decision: bool = False, reason: str | None = None) -> dict:
        index = self._index.get(stream, 0)
        self._index[stream] = index + 1
        verdict = self.policy.decide(stream, t, decision=decision, reason=reason)
        store = PROFILES[self.policy.profile].store
        row = {"stream": stream, "index": index, "t": round(float(t), 4), "sha256": _sha256(jpeg),
               "bytes": len(jpeg), "stored": None, "why": verdict["why"]}
        if store == "jpeg" and verdict["saved"]:
            d = self.out / stream
            d.mkdir(parents=True, exist_ok=True)
            path = d / f"{index:05d}.jpg"
            path.write_bytes(jpeg)
            row.update(stored="jpeg", file=f"{stream}/{index:05d}.jpg")
        elif store == "mp4":
            if stream not in self._mp4:
                self._mp4[stream] = _Mp4Stream(self.out / f"{stream}.mp4", self.fps)
            self._mp4[stream].write(jpeg)
            row.update(stored="mp4", file=f"{stream}.mp4")
        self._hash_log.write(json.dumps(row, separators=(",", ":")) + "\n")
        if row["stored"] == "jpeg":
            self._jpeg_bytes += len(jpeg)
        if row["stored"]:
            self._check_cap()
        return row

    def close(self) -> dict:
        """Finish the mp4 files (final size is checked against the cap) and return the manifest block."""
        if self._closed:
            return self.record()
        self._closed = True
        self._hash_log.close()
        for stream in self._mp4.values():
            stream.close()
        if not self.cap_exceeded:          # already reported by add(); do not raise a second time
            self._check_cap()
        return self.record()

    def record(self) -> dict:
        rec = self.policy.record()
        rec.update(schema="ugrp.frame-storage.v2", write_cap_mib=self.cap_mib,
                   bytes_written=self.bytes_written, cap_exceeded=self.cap_exceeded,
                   hash_list=self.HASH_LIST,
                   mp4={k: str((self.out / f"{k}.mp4").name) for k in self._mp4})
        return rec

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.close()
        except FrameWriteCapExceeded:
            if exc[0] is None:
                raise
        return False
