"""FrameSink (per-run write cap, hash list), pack_frames and write_cap_guard (2026-10-01 disk policy)."""

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from harness.frame_storage import DEFAULT_WRITE_CAP_MIB, FrameSink, FrameWriteCapExceeded

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = shutil.which("ffmpeg") is not None


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jpeg(seed, size=(64, 48)):
    import cv2
    rng = np.random.default_rng(seed)
    image = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
    ok, enc = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return enc.tobytes()


def rows(out):
    return [json.loads(line) for line in (Path(out) / FrameSink.HASH_LIST).read_text().splitlines()]


def test_default_stores_no_bytes_but_logs_every_hash(tmp_path):
    frames = [jpeg(i) for i in range(6)]
    with FrameSink(tmp_path, "none_v1", split="dev") as sink:
        for i, data in enumerate(frames):
            assert sink.add("r1", i * 0.2, data)["stored"] is None
    assert not list(tmp_path.rglob("*.jpg")) and not list(tmp_path.glob("*.mp4"))
    assert [r["sha256"] for r in rows(tmp_path)] == [hashlib.sha256(d).hexdigest() for d in frames]
    rec = sink.record()
    assert rec["profile"] == "none_v1" and rec["bytes_written"] == 0
    assert rec["write_cap_mib"] == DEFAULT_WRITE_CAP_MIB and rec["cap_exceeded"] is False


def test_jpeg_profile_is_capped_and_stops_the_run(tmp_path):
    data = [jpeg(i) for i in range(4)]
    sink = FrameSink(tmp_path, "all_v1", split="dev", cap_mib=(sum(len(b) for b in data[:3]) + 1) / 2**20)
    for i in range(3):
        assert sink.add("r1", i, data[i])["stored"] == "jpeg"
    with pytest.raises(FrameWriteCapExceeded) as err:
        sink.add("r1", 3, data[3])
    assert err.value.errno is None and isinstance(err.value, OSError)
    with pytest.raises(FrameWriteCapExceeded):      # latched: nothing more is written even if the caller swallowed it
        sink.add("r1", 4, data[0])
    sink.close()
    assert sink.record()["cap_exceeded"] is True
    assert len(rows(tmp_path)) == 4                      # the crossing frame is still listed by hash
    with pytest.raises(FileExistsError):                 # a second sink never appends to / overwrites this run
        FrameSink(tmp_path, "all_v1", split="dev")


def test_only_smoke_runs_may_omit_the_profile_and_cohorts_must_state_a_cap(tmp_path):
    for split in (None, "dev", "diag", "test", "cohort"):
        with pytest.raises(ValueError):
            FrameSink(tmp_path / str(split), split=split)
    assert FrameSink(tmp_path / "smoke", split="smoke").record()["profile"] == "none_v1"
    for profile in ("none_v1", "mp4_v1"):                              # no original JPEG: not for cohorts
        with pytest.raises(ValueError):
            FrameSink(tmp_path / f"c-{profile}", profile, split="test", cap_mib=500)
    with pytest.raises(ValueError, match="cap_mib"):
        FrameSink(tmp_path / "nocap", "all_v1", split="test")
    sink = FrameSink(tmp_path / "ok", "all_v1", split="test", cap_mib=500)   # explicit choice keeps the JPEGs
    assert sink.add("r1", 0.0, jpeg(1))["stored"] == "jpeg"
    sink.close()


def test_no_unlimited_mode(tmp_path):
    for bad in (0, -1):
        with pytest.raises(ValueError):
            FrameSink(tmp_path, "none_v1", split="dev", cap_mib=bad)


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_mp4_profile_packs_a_stream_and_keeps_the_hash_list(tmp_path):
    frames = [jpeg(i) for i in range(10)]
    with FrameSink(tmp_path, "mp4_v1", split="dev", cap_mib=5) as sink:
        for i, data in enumerate(frames):
            assert sink.add("r1", i * 0.2, data)["stored"] == "mp4"
    assert (tmp_path / "r1.mp4").stat().st_size > 0 and not list(tmp_path.rglob("*.jpg"))
    assert [r["sha256"] for r in rows(tmp_path)] == [hashlib.sha256(d).hexdigest() for d in frames]
    pack = load("pack_frames")
    assert pack.decoded_frames(tmp_path / "r1.mp4") == 10


def _frames_dir(tmp_path, n=8, age_days=10.0):
    import os
    import time
    d = tmp_path / "frames"
    d.mkdir()
    data = [jpeg(i) for i in range(n)]
    for i, b in enumerate(data):
        f = d / f"{i:05d}.jpg"
        f.write_bytes(b)
        old = time.time() - age_days * 86400
        os.utime(f, (old, old))
    return d, data


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_pack_frames_dry_run_then_verified_pack_then_trash_with_record(tmp_path):
    pack = load("pack_frames")
    d, data = _frames_dir(tmp_path)
    assert pack.main([str(tmp_path)]) == 0
    assert not (tmp_path / "frames.mp4").exists() and len(list(d.glob("*.jpg"))) == 8
    assert pack.main([str(tmp_path), "--execute"]) == 0
    assert len(list(d.glob("*.jpg"))) == 8
    listed = [json.loads(x) for x in (tmp_path / "frames.sha256.jsonl").read_text().splitlines()]
    assert [r["sha256"] for r in listed] == [hashlib.sha256(b).hexdigest() for b in data]
    trash, records = tmp_path / "trash", tmp_path / "records"
    assert pack.main([str(tmp_path), "--execute", "--trash-originals", "--reason", "past dev run, no keep category",
                      "--trash-root", str(trash), "--record-dir", str(records)]) == 0
    assert not list(d.glob("*.jpg"))
    # moved, not deleted: every original is in the Trash with identical bytes, and a record says where
    record = json.loads(next(records.glob("pack-frames-*.json")).read_text())
    assert record["reason"] == "past dev run, no keep category" and len(record["planned_files"]) == 8
    assert record["status"] == "done"
    trashed = [Path(record["trash_dir"]) / m["path"].lstrip("/") for m in record["planned_files"]]
    assert sorted(hashlib.sha256(t.read_bytes()).hexdigest() for t in trashed) == \
        sorted(hashlib.sha256(b).hexdigest() for b in data)
    # packing again without trashing is refused (earlier mp4 / hash list never overwritten), and a changed
    # directory no longer matches the earlier list so the trash step refuses it too
    (d / "00000.jpg").write_bytes(data[0])
    assert pack.main([str(tmp_path), "--execute"]) == pack.EXIT_REFUSED
    (d / "00000.jpg").write_bytes(data[1])
    assert pack.main([str(tmp_path), "--execute", "--trash-originals", "--reason", "x",
                      "--trash-root", str(trash), "--record-dir", str(records)]) == pack.EXIT_REFUSED


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
def test_pack_frames_refuses_to_trash_frames_from_the_last_three_days(tmp_path):
    pack = load("pack_frames")
    d, _ = _frames_dir(tmp_path, age_days=1.0)
    assert pack.main([str(tmp_path), "--execute", "--trash-originals", "--reason", "x",
                      "--trash-root", str(tmp_path / "trash"), "--record-dir", str(tmp_path / "records")]) \
        == pack.EXIT_REFUSED
    assert len(list(d.glob("*.jpg"))) == 8 and not (tmp_path / "records").exists()
    assert not (tmp_path / "frames.mp4").exists()


def test_pack_frames_trash_needs_execute_and_a_reason(tmp_path):
    pack = load("pack_frames")
    with pytest.raises(SystemExit):
        pack.main([str(tmp_path), "--trash-originals", "--reason", "x"])
    with pytest.raises(SystemExit):
        pack.main([str(tmp_path), "--execute", "--trash-originals"])


def test_write_cap_guard_stops_a_growing_run_and_writes_a_receipt(tmp_path):
    guard = load("write_cap_guard")
    out = tmp_path / "run"
    code = ("import pathlib,time;p=pathlib.Path(%r);p.mkdir(exist_ok=True)\n"
            "for i in range(600):\n (p/f'{i}.bin').write_bytes(b'x'*(256*1024));time.sleep(0.01)" % str(out))
    rc = guard.main(["--watch", str(out), "--max-mib", "2", "--poll-s", "0.05", "--", sys.executable, "-c", code])
    assert rc == guard.EXIT_CAP
    receipt = json.loads((out / "write-cap.json").read_text())
    assert receipt["cap_exceeded"] is True and receipt["growth_bytes"] > 2 * 2**20
    assert len(list(out.glob("*.bin"))) < 600


def test_write_cap_guard_passes_through_a_normal_exit(tmp_path):
    guard = load("write_cap_guard")
    assert guard.main(["--watch", str(tmp_path / "run"), "--max-mib", "5", "--", sys.executable, "-c",
                       "raise SystemExit(7)"]) == 7
    assert not (tmp_path / "run" / "write-cap.json").exists()


class _Writer:
    def __init__(self):
        self.images = []

    def text(self, *a):
        pass

    def image(self, tag, data, step):
        self.images.append((tag, step))


class _Src:
    def __init__(self, files):
        self.files = files

    def image(self, ref):
        return b"jpeg"


def _record(sha):
    return {"record_complete": False, "calls": [],
            "request_archive": [{"request_id": "q1", "image_refs": [{"label": "own", "bytes_sha256": sha}]}]}


def test_tensorboard_zone_study_hash_only_request_images_needs_the_explicit_flag(monkeypatch):
    from scripts.tensorboard_tools import zone_study
    from scripts.tensorboard_tools.zone_study import request_images
    sha = "a" * 64
    with pytest.raises(ValueError, match="Missing"):                        # default: a missing image is rejected
        request_images(_Src({}), _record(sha), _Writer(), 4)
    monkeypatch.setattr(zone_study, "ALLOW_REMOVED_REQUEST_IMAGES", True)
    writer = _Writer()
    assert request_images(_Src({}), _record(sha), writer, 4) == (1, 1)        # removed by the retention rule: hash only
    assert writer.images == []
    stored = {f"study/request_images/{sha}.jpg": {"sha256": sha}}
    writer = _Writer()
    assert request_images(_Src(stored), _record(sha), writer, 4) == (1, 0)
    assert writer.images
    with pytest.raises(ValueError, match="Hash-mismatched"):
        request_images(_Src({f"study/request_images/{sha}.jpg": {"sha256": "b" * 64}}), _record(sha), _Writer(), 4)
    with pytest.raises(ValueError, match="no bytes_sha256"):
        request_images(_Src({}), _record(None), _Writer(), 4)
