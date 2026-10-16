"""Opt-in native10Hz recording wrapper around the UNCHANGED qualified teacher.

The capture hook writes the exact JPEG returned to that controller. It reads
only named task tokens and previous issued commands at the pinned call site;
it supplies no input or action. Labels are paired after the controller exits.
Pilot/cap/error recordings are never automatically admitted as training data.
"""
import argparse
import hashlib
import inspect
import json
from pathlib import Path
import runpy
import subprocess
import sys

from warp_act_api import admit, QUALIFIED


def read_jsonl(path):
    raw = path.read_bytes() if path.exists() else subprocess.check_output(['zstd', '-dc', str(path)+'.zst'])
    return [json.loads(x) for x in raw.splitlines() if x.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    for key in ('qualified-source', 'teacher-source', 'qualification', 'runner-args-json', 'out'):
        p.add_argument('--'+key, type=Path, required=True)
    p.add_argument('--stage', choices=['pilot', 'batch'], default='pilot')
    p.add_argument('--recording-approval', type=Path)
    a = p.parse_args()
    if not a.enabled: p.error('recording is default OFF')
    gate = admit(a.qualification, a.qualified_source, a.teacher_source)
    args = json.loads(a.runner_args_json.read_text())
    if not isinstance(args, list) or not all(type(x) is str for x in args):
        p.error('runner args must be a string array')
    required = ('--scene-v5-v1', '--numpy-teacher-v1', '--batch-sleep-v1', '--native-sleep-policy-compat-v1')
    if not all(x in args for x in required) or any(x in args for x in ('--float32-solver-default-v1', '--sap-segmented-v1', '--teacher-gate-queue')):
        p.error('exact qualified numeric/scene profile, separate fresh recording cohort required')
    if args[args.index('--physics-backend')+1] != 'mjwarp_batch_v1': p.error('MJWarp recording only')
    if Path(args[args.index('--teacher-source')+1]).resolve() != a.teacher_source.resolve(): p.error('teacher source mismatch')
    sys.path.insert(0, str(a.qualified_source/'scripts')); sys.path.insert(0, str(a.teacher_source))
    import sim
    sim.__path__.append(str(a.qualified_source/'sim'))
    from harness.grasp_act_solo_recording import SoloRecorder, validate_recording, validate_approval
    validate_approval(a.recording_approval, stage=a.stage, sha=QUALIFIED, host=gate['cohort']['host'])
    import warp_act_backend
    original = warp_act_backend.WarpTransport.capture
    a.out.mkdir(parents=True, exist_ok=False)
    rows, plans = {}, {}

    def capture(hooks, index, world):
        jpeg = original(hooks, index, world)
        caller = inspect.currentframe().f_back
        if Path(caller.f_code.co_filename).resolve() != (a.qualified_source/'scripts/warp_act_episode.py').resolve():
            raise RuntimeError('unrecognized recording call site')
        local = caller.f_locals
        plan, teacher = local['plan'], local['teacher']
        if index not in rows:
            validate_recording(plan, training_rgb=True, truth_free_v1=True, negative=False,
                               stability='align_relook_v1', reach='pad_window_v2',
                               lift='solo_lift_lookback_v1', margin=True)
            plans[index] = plan; rows[index] = []
        folder = a.out/f'world-{index:03d}'/'capture'; folder.mkdir(parents=True, exist_ok=True)
        path = folder/f'{len(rows[index]):06d}.jpg'; path.write_bytes(jpeg)
        rows[index].append(dict(t=local['now'], skill=teacher.skill, phase=teacher.phase,
            previous=local['previous'], path=str(path), sha256=hashlib.sha256(jpeg).hexdigest()))
        return jpeg

    warp_act_backend.WarpTransport.capture = capture
    error = None
    try:
        sys.argv = [str(a.qualified_source/'scripts/run_warp_act_teacher.py'), *args]
        runpy.run_path(sys.argv[0], run_name='__main__')
    except BaseException as exc:
        error = repr(exc)
    finally:
        warp_act_backend.WarpTransport.capture = original
    import cv2
    import numpy as np
    controller_out = Path(args[args.index('--out')+1])
    results = []
    for i, frames in rows.items():
        folder = a.out/f'world-{i:03d}'
        (folder/'capture-context.json').write_text(json.dumps(frames, indent=2)+'\n')
        commands = read_jsonl(controller_out/f'world-{i:03d}'/'teacher-commands.jsonl')
        if len(commands) != len(frames): raise RuntimeError('unpaired capture/command trace')
        recorder = SoloRecorder(folder, plans[i], frames[0]['previous'])
        try:
            for frame, command in zip(frames, commands):
                jpeg = Path(frame['path']).read_bytes()
                if hashlib.sha256(jpeg).hexdigest() != frame['sha256'] or frame['t'] != command['t']:
                    raise RuntimeError('capture bytes/command clock changed')
                bgr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                recorder.observe(frame['t'], jpeg, bgr, skill=frame['skill'], phase=frame['phase'], previous=frame['previous'])
                context = command['student_context']
                recorder.target(command['command'], skill_after=context['skill'], phase_after=command['phase'], complete=command['phase']=='complete')
            results.append(dict(world=i, seed=plans[i]['seed'], **recorder.record()))
        finally:
            recorder.close()
    summary = dict(status='HOST_ERROR' if error else 'recording_complete', error=error,
        controller_source=QUALIFIED, adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        raw_controller=str(controller_out), stage=a.stage, gate_n=gate['n'], gate_N=gate['N'],
        exact_controller_jpeg=True, training_include=False, data_admitted=False,
        reason='pilot/raw recording requires separate inspected dataset admission', worlds=results,
        sha256={str(x.relative_to(a.out)): hashlib.sha256(x.read_bytes()).hexdigest() for x in a.out.rglob('*') if x.is_file()})
    (a.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    if error: raise RuntimeError(error)


if __name__ == '__main__': main()
