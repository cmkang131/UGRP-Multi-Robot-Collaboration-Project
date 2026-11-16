#!/usr/bin/env python3
"""Pack directories of JPEG frames into one mp4 + a per-frame sha256 list (docs/disk_management.md section 5).

For every directory under PATH that holds ``*.jpg`` files (sorted by name) this writes, next to the directory,
``<name>.mp4`` (H.264, the original JPEG bytes piped to ffmpeg) and ``<name>.sha256.jsonl``
(``{index, file, sha256, bytes}`` per frame, so every original JPEG stays identifiable by hash).

Default is a dry run that prints the plan and the sizes. ``--execute`` writes the mp4 and the list and verifies
both (list rows == files, ffprobe decoded frame count == files).

``--trash-originals`` (needs ``--execute`` and ``--reason``) then MOVES the JPEGs of a verified directory to the
macOS Trash (never deletes) and writes a record to ``outputs/cleanup-records/`` (AGENTS.md "보존"). Image bytes
are kept for active work and open PRs, the last 3 days, version representative videos and pre-registered study
cohorts, so the tool refuses a directory with a JPEG newer than ``--min-age-days`` (default 3) and the caller
states in ``--reason`` why the directory is outside the other keep categories. Never use it on frames a sealed or
pre-registered cohort still keeps: that cohort's inventory (sha256/size/mtime) stays as written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

CRF = 28
EXIT_REFUSED = 2
DEFAULT_MIN_AGE_DAYS = 3.0
DEFAULT_RECORD_DIR = Path("/Users/changmin/projects/ugrp/outputs/cleanup-records")


def frame_dirs(root: Path) -> list[Path]:
    found = []
    for directory in sorted({p.parent for p in root.rglob("*.jpg")}):
        found.append(directory)
    return found


def hash_rows(files: list[Path]) -> list[dict]:
    rows = []
    for index, path in enumerate(files):
        data = path.read_bytes()
        rows.append({"index": index, "file": path.name, "sha256": hashlib.sha256(data).hexdigest(),
                     "bytes": len(data)})
    return rows


def encode(files: list[Path], dest: Path, fps: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg not found on PATH")
    proc = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", f"{fps:g}", "-c:v", "mjpeg",
         "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(CRF), "-pix_fmt", "yuv420p",
         "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-movflags", "+faststart", str(dest)], stdin=subprocess.PIPE)
    try:
        for path in files:
            proc.stdin.write(path.read_bytes())
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {dest}")


def decoded_frames(mp4: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=nb_read_frames", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


def too_recent(files: list[Path], min_age_days: float) -> list[Path]:
    cutoff = time.time() - min_age_days * 86400
    return [f for f in files if f.stat().st_mtime > cutoff]


def move_to_trash(files: list[Path], trash_dir: Path) -> list[dict]:
    """Move (not delete) files into trash_dir, keeping the original absolute path below it. Returns the moves."""
    moved = []
    for f in files:
        src = f.resolve()
        dest = trash_dir / str(src).lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = src.stat().st_size
        shutil.move(str(src), str(dest))
        moved.append({"path": str(src), "trash": str(dest), "bytes": size})
    return moved


def git_tracked(files: list[Path]) -> list[Path]:
    """JPEGs tracked by git (test fixtures, committed evidence) are in the 'tests use them' keep category."""
    if not files:
        return []
    out = subprocess.run(["git", "-C", str(files[0].parent), "ls-files", "--", *[str(f) for f in files]],
                         capture_output=True, text=True)
    return files if out.returncode == 0 and out.stdout.strip() else []


def pack(directory: Path, fps: float, *, trash: bool = False, reason: str = "", min_age_days: float = DEFAULT_MIN_AGE_DAYS,
         trash_root: Path | None = None, record_dir: Path = DEFAULT_RECORD_DIR) -> dict:
    files = sorted(directory.glob("*.jpg"))
    mp4 = directory.parent / f"{directory.name}.mp4"
    lst = directory.parent / f"{directory.name}.sha256.jsonl"
    before = sum(f.stat().st_size for f in files)
    refusal = None
    reuse = False   # an earlier --execute already wrote and may be re-verified for the trash step
    if mp4.exists() or lst.exists():
        if trash and mp4.exists() and lst.exists():
            now_rows = hash_rows(files)
            listed = [json.loads(x) for x in lst.read_text().splitlines()]
            if listed == now_rows and decoded_frames(mp4) == len(files):
                reuse = True
            else:
                refusal = f"existing {mp4.name}/{lst.name} do not match the current JPEGs (never overwritten)"
        else:
            refusal = f"{mp4.name} or {lst.name} already exists (an earlier pack; never overwritten)"
    if refusal is None and trash:
        recent = too_recent(files, min_age_days)
        if recent:
            refusal = f"{len(recent)} JPEG(s) newer than {min_age_days:g} days (AGENTS.md 보존: last 3 days)"
        elif git_tracked(files):
            refusal = "JPEGs tracked by git (tests/evidence use them: AGENTS.md 보존)"
        else:
            try:
                record_dir.mkdir(parents=True, exist_ok=True)
                probe = record_dir / f".write-probe-{uuid.uuid4().hex}"
                probe.write_text("")
                probe.unlink()
            except OSError as exc:
                refusal = f"cleanup record dir {record_dir} not writable: {exc}"
    if refusal:   # refuse before writing anything
        return {"dir": str(directory), "frames": len(files), "jpeg_bytes": before, "mp4_bytes": 0, "mp4": None,
                "hash_list": None, "verified": False, "originals_moved_to_trash": False, "refused": refusal}
    rows = hash_rows(files)
    if not reuse:
        encode(files, mp4, fps)
        lst.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
    verified = (len(lst.read_text().splitlines()) == len(files) and decoded_frames(mp4) == len(files))
    moved = False
    if trash and verified:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        tag = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:8]
        trash_dir = (trash_root or Path.home() / ".Trash") / f"ugrp-pack-frames-{stamp}-{tag}"
        record = {"schema": "ugrp.pack_frames_cleanup.v1", "date": stamp, "dir": str(directory.resolve()),
                  "reason": reason, "rule": "AGENTS.md 보존 (2026-10-04): hash list and mp4 kept, JPEGs moved to Trash",
                  "hash_list": str(lst.resolve()), "mp4": str(mp4.resolve()), "trash_dir": str(trash_dir),
                  "min_age_days": min_age_days, "status": "planned",
                  "planned_files": [{"path": str(f.resolve()), "bytes": f.stat().st_size,
                                     "sha256": rows[i]["sha256"]} for i, f in enumerate(files)],
                  "restore": "move each file under trash_dir/<original absolute path> back to its path"}
        record_path = record_dir / f"pack-frames-{stamp}-{tag}-{directory.name}.json"
        with open(record_path, "x") as handle:       # the plan is on disk BEFORE anything moves
            handle.write(json.dumps(record, indent=1))
        move_to_trash(files, trash_dir)
        record["status"] = "done"
        tmp = record_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=1))
        os.replace(tmp, record_path)
        moved = True
    return {"dir": str(directory), "frames": len(files), "jpeg_bytes": before, "mp4_bytes": mp4.stat().st_size,
            "mp4": str(mp4), "hash_list": str(lst), "verified": verified, "originals_moved_to_trash": moved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--execute", action="store_true", help="write mp4 + hash list (default: dry run)")
    parser.add_argument("--trash-originals", action="store_true",
                        help="after verification MOVE the JPEGs of that directory to the Trash and write a record "
                             "(needs --execute and --reason)")
    parser.add_argument("--reason", default="", help="why these frames are outside the AGENTS.md keep categories")
    parser.add_argument("--min-age-days", type=float, default=DEFAULT_MIN_AGE_DAYS,
                        help="refuse to trash a directory holding a JPEG newer than this (default 3)")
    parser.add_argument("--record-dir", type=Path, default=DEFAULT_RECORD_DIR)
    parser.add_argument("--trash-root", type=Path, default=None, help="default ~/.Trash")
    args = parser.parse_args(argv)
    if args.trash_originals and not args.execute:
        parser.error("--trash-originals needs --execute")
    if args.trash_originals and not args.reason.strip():
        parser.error("--trash-originals needs --reason")
    if args.trash_originals and args.trash_root is None and sys.platform != "darwin":
        parser.error("--trash-originals without --trash-root needs macOS (~/.Trash is a real Trash only there)")
    dirs = frame_dirs(args.path)
    if not dirs:
        print(f"no *.jpg under {args.path}")
        return 0
    results = []
    refused_any = False
    for d in dirs:
        if not args.execute:
            n = len(list(d.glob("*.jpg")))
            size = sum(f.stat().st_size for f in d.glob("*.jpg"))
            print(f"plan {d}: {n} frames, {size / 2**20:.2f} MiB")
            continue
        results.append(pack(d, args.fps, trash=args.trash_originals, reason=args.reason,
                            min_age_days=args.min_age_days, trash_root=args.trash_root, record_dir=args.record_dir))
        r = results[-1]
        if r.get("refused"):
            print(f"refused {r['dir']}: {r['refused']}")
            refused_any = True
            continue
        print(f"packed {r['dir']}: {r['frames']} frames {r['jpeg_bytes'] / 2**20:.2f} -> {r['mp4_bytes'] / 2**20:.2f} MiB "
              f"verified={r['verified']} trashed={r['originals_moved_to_trash']}")
    if results:
        print(json.dumps({"jpeg_bytes": sum(r["jpeg_bytes"] for r in results),
                          "mp4_bytes": sum(r["mp4_bytes"] for r in results),
                          "all_verified": all(r["verified"] for r in results if not r.get("refused")),
                          "refused": sum(1 for r in results if r.get("refused"))}))
        if not all(r["verified"] for r in results if not r.get("refused")):
            return 1
        return EXIT_REFUSED if refused_any else 0     # nothing moved for a refused directory: not a clean success
    return 0


if __name__ == "__main__":
    sys.exit(main())
