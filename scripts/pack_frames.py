#!/usr/bin/env python3
"""Pack directories of JPEG frames into one mp4 + a per-frame sha256 list (docs/disk_management.md section 5).

For every directory under PATH that holds ``*.jpg`` files (sorted by name) this writes, next to the directory,
``<name>.mp4`` (H.264, the original JPEG bytes piped to ffmpeg) and ``<name>.sha256.jsonl``
(``{index, file, sha256, bytes}`` per frame, so every original JPEG stays identifiable by hash).

Default is a dry run that prints the plan and the sizes. ``--execute`` writes the mp4 and the list and verifies
both (list rows == files, ffprobe decoded frame count == files). ``--remove-originals`` (needs ``--execute``) then
deletes the JPEGs of a verified directory only. Never use it on a past sealed cohort whose pinned inventory
(sha256/size/mtime) lists those files: that inventory is evidence of the past run and stays as written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

CRF = 28


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


def pack(directory: Path, fps: float, *, remove: bool) -> dict:
    files = sorted(directory.glob("*.jpg"))
    mp4 = directory.parent / f"{directory.name}.mp4"
    lst = directory.parent / f"{directory.name}.sha256.jsonl"
    before = sum(f.stat().st_size for f in files)
    rows = hash_rows(files)
    encode(files, mp4, fps)
    lst.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
    verified = (len(lst.read_text().splitlines()) == len(files) and decoded_frames(mp4) == len(files))
    removed = False
    if remove and verified:
        for f in files:
            f.unlink()
        removed = True
    return {"dir": str(directory), "frames": len(files), "jpeg_bytes": before, "mp4_bytes": mp4.stat().st_size,
            "mp4": str(mp4), "hash_list": str(lst), "verified": verified, "originals_removed": removed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--execute", action="store_true", help="write mp4 + hash list (default: dry run)")
    parser.add_argument("--remove-originals", action="store_true",
                        help="after verification delete the JPEGs of that directory (needs --execute)")
    args = parser.parse_args(argv)
    if args.remove_originals and not args.execute:
        parser.error("--remove-originals needs --execute")
    dirs = frame_dirs(args.path)
    if not dirs:
        print(f"no *.jpg under {args.path}")
        return 0
    results = []
    for d in dirs:
        if not args.execute:
            n = len(list(d.glob("*.jpg")))
            size = sum(f.stat().st_size for f in d.glob("*.jpg"))
            print(f"plan {d}: {n} frames, {size / 2**20:.2f} MiB")
            continue
        results.append(pack(d, args.fps, remove=args.remove_originals))
        r = results[-1]
        print(f"packed {r['dir']}: {r['frames']} frames {r['jpeg_bytes'] / 2**20:.2f} -> {r['mp4_bytes'] / 2**20:.2f} MiB "
              f"verified={r['verified']} removed={r['originals_removed']}")
    if results:
        print(json.dumps({"jpeg_bytes": sum(r["jpeg_bytes"] for r in results),
                          "mp4_bytes": sum(r["mp4_bytes"] for r in results),
                          "all_verified": all(r["verified"] for r in results)}))
        return 0 if all(r["verified"] for r in results) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
