"""Which camera frames a runner writes to disk (2026-09-27 user decision, docs/disk_management.md section 5).

Profiles are versioned and never change meaning once published:

``all_v1``
    Write every frame as an original JPEG. This is the behaviour of every runner before 2026-09-27 and of every
    past pre-registration. Runs whose frames fall in the AGENTS.md keep categories (active work, the last 3 days,
    pre-registered study cohorts) must choose it explicitly.
``none_v1``
    No frame bytes, only one sha256 row per frame. The default (profile omitted) for ``smoke`` runs only.
``mp4_v1``
    One H.264 mp4 per stream plus the sha256 list. Lossy: the original JPEGs are not kept.

``none_v1`` and ``mp4_v1`` leave no original image, so they are allowed for ``dev``/``diag``/``smoke`` only. A run
whose frames fall in a keep category chooses ``all_v1`` (or a reduced dev profile) and a ``cap_mib``.
``dev_1hz_decisions_v1``
    Development and diagnostic runs only. Per stream (one robot camera, or the TOP camera), write a
    periodic frame when at least 1.0 SIM s has passed since the last periodic frame written, and always
    write a decision frame (a capture the controller asked for, the capture after a macro, or a frame
    during which the controller emitted an event or changed phase). Decision frames do not move the
    periodic clock.

The policy only decides whether the JPEG *file* is written. The caller still records every frame's
SIM time and sha256 in its frame log, so a skipped frame is known by hash. This module covers camera frames
only. Model-request images (LLM, ACT, trained students) do not go through ``FrameSink``; the runner keeps them
with the request text. Retention after writing follows
AGENTS.md "보존": text, ledgers, logs and sha256 lists are always kept; image bytes only for active work and open
PRs, the last 3 days, version representative videos and pre-registered study cohorts; anything else goes to the
Trash with a record in outputs/cleanup-records/ (scripts/pack_frames.py --trash-originals). A run whose images
fall in a keep category must say so by choosing ``all_v1`` (or ``mp4_v1``) and its cap explicitly.
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
    "all_v1": FrameProfile("all_v1", None, False, "every frame as original JPEG (explicit choice; capped)"),
    "dev_1hz_decisions_v1": FrameProfile(
        "dev_1hz_decisions_v1", 1.0, True,
        "dev/diagnostic only: 1 periodic frame per SIM s per stream + every decision frame"),
    "none_v1": FrameProfile("none_v1", None, False, "no frame bytes, per-frame sha256 list only (dev/diag default)", "none"),
    "mp4_v1": FrameProfile("mp4_v1", None, False, "one H.264 mp4 per stream + per-frame sha256 list", "mp4"),
}
DEFAULT_PROFILE = "none_v1"       # used only when the split is one of DEFAULT_SPLITS
DEFAULT_SPLITS = ("smoke",)       # throwaway smoke runs: nothing to keep. dev/diag name their profile
NO_ORIGINAL_SPLITS = ("dev", "diag", "smoke")   # none_v1 / mp4_v1 leave no original JPEG
NO_ORIGINAL_PROFILES = ("none_v1", "mp4_v1")
REDUCED_SPLITS = ("dev", "diag")


@dataclass
class FrameStoragePolicy:
    """Per-run policy; one instance per episode. ``split`` must be given for a reduced profile.

    ``profile=None`` means the default (``none_v1``) and is allowed only for ``smoke`` runs. Any other run
    (dev/diag, test or pre-registered cohort, unknown split) must name its profile, so a run whose images are in a
    keep category (active work, last 3 days, cohort) never loses them by omission. ``none_v1``/``mp4_v1`` keep no
    original JPEG and are refused outside dev/diag/smoke."""

    profile: str | None = None
    split: str | None = None
    _last_periodic: dict[str, float] = field(default_factory=dict)
    _counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.profile is None:
            if self.split not in DEFAULT_SPLITS:
                raise ValueError(f"split {self.split!r} has no default frame profile; name one explicitly "
                                 f"(all_v1 keeps the JPEGs, none_v1/mp4_v1 do not). Default only for {DEFAULT_SPLITS}")
            self.profile = DEFAULT_PROFILE
        if self.profile not in PROFILES:
            raise ValueError(f"unknown frame profile {self.profile!r}; known: {sorted(PROFILES)}")
        if self.profile in NO_ORIGINAL_PROFILES and self.split not in NO_ORIGINAL_SPLITS:
            raise ValueError(f"frame profile {self.profile!r} keeps no original JPEG; allowed splits "
                             f"{NO_ORIGINAL_SPLITS}, not {self.split!r} (cohort/test runs use all_v1)")
        if PROFILES[self.profile].reduced and self.split not in REDUCED_SPLITS:
            raise ValueError(f"frame profile {self.profile!r} is for splits {REDUCED_SPLITS}, not {self.split!r};"
                             " test cohorts and pre-registered runs name all_v1 explicitly")

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
             "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
             "-movflags", "frag_keyframe+empty_moov", str(dest)],     # playable even if the run aborts
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

    def __init__(self, out_dir, profile: str | None = None, *, split: str | None = None,
                 cap_mib: float | None = None, fps: float = 5.0):
        self.policy = FrameStoragePolicy(profile, split=split)
        if cap_mib is None:
            if self.policy.split in NO_ORIGINAL_SPLITS:
                cap_mib = DEFAULT_WRITE_CAP_MIB
            else:
                raise ValueError("a cohort/test run must state cap_mib (sized from its pre-registration); the "
                                 f"{DEFAULT_WRITE_CAP_MIB:g} MiB dev default would stop it mid-run")
        if cap_mib <= 0:
            raise ValueError("a positive per-run frame write cap (MiB) is required; there is no unlimited mode")
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        if (self.out / self.HASH_LIST).exists():
            raise FileExistsError(f"{self.out / self.HASH_LIST} exists: a FrameSink needs a fresh directory so "
                                  "earlier frames and their hash list are never overwritten")
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
        if self.cap_exceeded:   # latched: after the cap no further bytes are written, even if the caller swallowed the error
            raise FrameWriteCapExceeded(f"frame write cap of {self.cap_mib:g} MiB already exceeded")
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
