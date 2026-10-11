"""Azure host adapter for the frozen egomap70 milestone, passive live video only."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time

SOURCE = 'f26d9322c48eadbe2b28777ac1f07684ca03e124'
CHECKPOINT = 'ckpt_00071_t00015.500.pkl.zlib'
CHECKPOINT_SHA = 'fbb1159a172daa9b4151fbd05ba74dda29d9d9f65b908ee08db8d0f041dc4824'
ORIGINAL = {
    'robots/r3/commands.jsonl': '16ef40956c9263cb14c04843d682cac7b2aaab13f2eb503e4aee6d8b0d5f6937',
    'own-controller.jsonl': '7a651c09c2b55a8da2a257748b252e7a1a8c77a057544c3dc16babd03248f69b',
    'result.json': '701f3eeeb074dd68840698d61e7f5b0e8c54ddcd2f148666d0cc1d2f3b492029',
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--prefix', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--lease', type=Path, required=True)
    a = p.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or os.environ.get('MUJOCO_GL') != 'osmesa':
        raise ValueError('Azure x86 OSMesa required')
    if a.source.name != SOURCE or len(os.sched_getaffinity(0)) != 1 or not os.sched_getaffinity(0) <= set(range(12)):
        raise ValueError('frozen source and one non-E2E core required')
    if os.getpriority(os.PRIO_PROCESS, 0) != 0:
        raise ValueError('nice zero required')
    run = a.output
    run.mkdir(exist_ok=False)
    write(run / 'RUN_META.json', dict(**{'class': 'milestone'}, pr=405, branch='codex/egomap70-overview',
        sha=SOURCE, batch=run.name, seed=63003, condition='calib_traversed_zone', host='azure'))
    (run / 'SOURCE_SHA').write_text(SOURCE + '\n')
    (run / 'COMMAND').write_text(json.dumps(sys.argv) + '\n')
    write(run / 'runtime.json', dict(host='azure', affinity=sorted(os.sched_getaffinity(0)),
        loadavg=os.getloadavg(), LP_NUM_THREADS=os.environ.get('LP_NUM_THREADS'), driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    halt = threading.Event()
    def heartbeat():
        while not halt.is_set():
            a.lease.touch()
            halt.wait(30)
    threading.Thread(target=heartbeat, daemon=True).start()
    sys.path.insert(0, str(a.source))
    from harness.active_camera import bind
    from scripts import run_own_route_turn_lateral as frozen
    from scripts.dev_pair_checkpoint import DevCheckpoint, find_checkpoint
    spec = importlib.util.spec_from_file_location('scripts.overview_evaluation_video',
        Path(__file__).with_name('overview_evaluation_video.py'))
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    from scripts.overview_evaluation_video import Video, Timeline, rows
    prefix = run / 'prefix'
    shutil.copytree(a.prefix, prefix)
    for packed in prefix.rglob('*.zst'):
        target = Path(str(packed)[:-4])
        if not target.exists():
            with target.open('xb') as stream:
                subprocess.run(['zstd', '-dc', str(packed)], stdout=stream, check=True)
    checkpoint = prefix / 'checkpoints' / CHECKPOINT
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != CHECKPOINT_SHA:
        raise ValueError('original checkpoint mismatch')
    videos = []
    began = time.monotonic()
    initial = None
    @contextlib.contextmanager
    def slot():
        if os.getloadavg()[0] >= 12.8:
            raise ValueError('Azure load admission exceeded')
        yield 'azure_one_core'
    def load(path, out):
        row = find_checkpoint(path)
        cp = DevCheckpoint(resume=dict(row=row, file=str(path), source_case_dir=str(prefix),
            labels={'egomap60': True, 'host': 'oracle-x86'}))
        out.mkdir(exist_ok=False)
        backend, c, start, tick, _ = cp.restore(out, {}, stream_aliases=True)
        # Inherited prefix frame bytes remain the original checkpoint's input.
        for image in (prefix / 'robots').glob('*/rgb/*'):
            target = out / image.relative_to(prefix)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(image, target)
        trace = Timeline(rows(out / 'own-controller.jsonl'))
        first = rows(out / 'eval_only/trajectory.jsonl')[0]
        origin = [*first['robot_xyz_m'][:2], first['robot_yaw_rad']]
        video = Video(backend, '재현 실행 · egomap70 calib_traversed_zone seed 63003', ('r3',),
            own_trace=trace, origin=origin, return_valid=False)
        videos.append(video)
        capture, append, evaluate = backend.capture, backend._append, backend.eval_sample
        own = {}
        def observed_capture():
            nonlocal own
            own = capture()
            return own
        def observed_append(relative, value):
            append(relative, value)
            if relative == 'own-controller.jsonl':
                trace.records.append(value)
                trace.times.append(value['t'])
        def observed_evaluate():
            nonlocal initial
            evaluate()
            import math
            distance = math.dist(backend.world.data.body('r3__robot').xpos[:2], origin[:2])
            video.return_valid = distance <= .2
            video.frame(backend, own)
            age = time.monotonic() - began
            if initial is None and age >= 180:
                initial = frozen.previous.early_check(out, row['sim_s'], age)
                write(run / 'initial-check.json', initial)
                if initial['anomaly']:
                    raise RuntimeError('INITIAL_CHECK_' + initial['anomaly'])
            if round(backend.now * 5) % 25 == 0:
                write(run / 'health.json', dict(sim_s=backend.now, wall_s=age, video_frames=video.frames,
                    stage=c.stage, pid=os.getpid(), actual_xy_evaluation_only=backend.world.data.body('r3__robot').xpos[:2].tolist()))
        backend.capture, backend._append, backend.eval_sample = observed_capture, observed_append, observed_evaluate
        return backend, c, start, tick, row
    # Only resource admission / archive location / passive observer are adapted.
    frozen.ref.server_slot = slot
    frozen.ref.old.checkpoint_load = load
    args = argparse.Namespace(seed=63003, condition='calib_traversed_zone', mode='stage',
        output=run / 'raw', checkpoint=checkpoint)
    status = 1
    try:
        result = frozen.run(args)
        for video in videos:
            video.close()
        scores = run / 'evaluation'
        scores.mkdir()
        frozen.score_batch([dict(seed=63003, condition='calib_traversed_zone', status=result['status'],
            output=str(run / 'raw'), early_checks=[initial] if initial else [])], scores)
        score = json.loads((scores / 'scores.json').read_text())[0]
        comparison = {name: dict(original=digest, rerun=hashlib.sha256((run / 'raw' / name).read_bytes()).hexdigest())
            for name, digest in ORIGINAL.items()}
        for value in comparison.values():
            value['match'] = value['original'] == value['rerun']
        matched = sum(v['match'] for v in comparison.values())
        if initial is None:
            initial = frozen.previous.early_check(run / 'raw', 15.5, time.monotonic() - began)
        summary = dict(status=result['status'], label='재현 실행(원본과 다름)' if matched < 3 else '원본 로그 3/3 일치',
            source_sha=SOURCE, seed=63003, condition='calib_traversed_zone', **{'class': 'milestone'}, pr=405,
            host='azure', raw=str(run / 'raw'), video=str(run / 'overview.mp4'), playback_speed=8,
            video_start_sim_s=15.5, inherited_prefix_not_filmed=True, overlay_evaluation_only=True,
            original_comparison=comparison, original_match_n=matched, initial_check=initial,
            rerun=dict(B_arrived=score.get('B_arrived'), returned=score.get('returned'),
                final_error_m=score.get('final_error_m'), final_return_distance_m=score.get('final_return_distance_m'),
                declarations=score.get('declarations'), samples=score.get('samples')),
            original=dict(B_arrived=True, returned=True, final_error_m=.02635518781456547,
                final_return_distance_m=.17177799719940554), video_frames=videos[0].frames if videos else 0,
            video_sha256=hashlib.sha256((run / 'overview.mp4').read_bytes()).hexdigest())
        write(run / 'summary.json', summary)
        status = 0 if result['status'] == 'RECORDED' and not initial['anomaly'] else 1
    finally:
        halt.set()
        (run / 'EXIT').write_text(str(status) + '\n')
    return status


if __name__ == '__main__':
    raise SystemExit(main())
