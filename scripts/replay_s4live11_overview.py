"""Oracle-only evaluation replay of S4 live11 globally ordered issued commands, with no model client."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

CONDITIONS = ('no_comm', 'peer_ko', 'leader_ko', 'structured')
ROBOTS = ('r1', 'r2', 'r3')
BASE_SHA = '4316bdd5804f37e46d7eb3866f9c7d2ae774168f'
ORIGINAL_SHA = BASE_SHA


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')


def audit_tape(raw):
    """Check global issue order against all three independent actuator logs."""
    tape = read(raw/'decision-command-links.json')
    frames = rows(raw/'robots/r1/frames.jsonl')
    start = frames[0]['sim_time']
    end = round(start+read(raw/'result.json')['check_sim_s'], 9)
    grouped = {}
    previous = start
    for row in tape:
        t = row['t']
        if t < previous-1e-8 or t > end+1e-8 or row['robot_id'] not in ROBOTS:
            raise ValueError('nonchronological or out-of-range original command')
        previous = t
        tick = round((t-start)/.05)
        if abs(start+tick*.05-t) > 1e-8:
            raise ValueError('command outside original 0.05s clock')
        grouped.setdefault(tick, []).append(row)
    for rid in ROBOTS:
        actual = rows(raw/f'robots/{rid}/commands.jsonl')
        prefix = [row for row in actual if row['t'] < start-1e-8]
        reconstructed = prefix+[
            {'t':row['t'], **row['action']} for row in tape if row['robot_id']==rid
        ]+[{'t':end, 'kind':'hold'}]
        if reconstructed != actual:
            raise ValueError('global command tape does not reproduce '+rid+' log')
    return start, end, grouped


def message_timeline(raw):
    """Use recorded acceptance times (relative to stage), never request times."""
    events = []
    for row in read(raw/'llm/actions.json'):
        if row['kind'] != 'claim_order':
            continue
        args = row['arguments']
        text = f"{row['actor']} claim {args.get('order_id')} {args.get('role')}"
        if not row['accepted']:
            text += ' [rejected]'
        events.append((row['submitted_at_sim_s'], text))
    for row in read(raw/'pair-handshake.json')['decisions']:
        action = row['action']; choice = action.get('choice')
        if choice not in ('go', 'ack_go'):
            continue
        text = f"{row['robot_id']} {'GO' if choice=='go' else 'ACK'} epoch={action.get('epoch')}"
        if choice == 'ack_go':
            text += ' -> '+str(action.get('peer_go_ref'))
        if not row['accepted']:
            text += ' [rejected]'
        events.append((row['at'], text))
    return sorted(events, key=lambda event:event[0])


def latest_message(events, relative):
    eligible = [event for event in events if event[0] <= relative+1e-8]
    if not eligible:
        return 'LLM: waiting for claim'
    t, message = eligible[-1]
    return f'LLM @{t:.2f}s: {message}'


from scripts.overview_evaluation_video import Video


def run(original, output, execution_sha, *, path_check=False):
    import numpy as np
    import mujoco
    from sim.s4_cyan_supervisor import PhysicsBackend
    from scripts.run_s3_alignment_probe import restore_scene
    from harness.zone_pair_highpose_exact_speedups import install
    original = Path(original); raw = original/'raw'
    start, end, grouped = audit_tape(raw)
    b = read(raw/'bundle.json'); condition = b['condition']
    if b['source_sha'] != ORIGINAL_SHA or condition not in CONDITIONS:
        raise ValueError('wrong S4 r3 original source/condition')
    root = Path(__file__).resolve().parents[1]
    checked = {}
    for path, expected in b['source_sha256'].items():
        if path.startswith(('sim/','harness/','scripts/','configs/')):
            checked[path] = sha(root/path)
            if checked[path] != expected:
                raise ValueError('original replay dependency changed: '+path)
    output.mkdir(parents=True, exist_ok=False)
    summary = dict(condition=condition, status='RUNNING', execution_sha=execution_sha,
        base_sha=BASE_SHA, original_source_sha=ORIGINAL_SHA, original_path=str(original),
        original_outcome=read(raw/'result.json')['status'], source_sha256=checked,
        model_calls=0, evaluation_only=True, controller_run=False, physics_correction=False,
        loadavg_start=os.getloadavg(), start_sim_s=start, end_sim_s=end,
        subtitle_time_basis='absolute SIM time from the original capture clock',
        playback_speed=8, width=1280, height=480)
    backend = video = None; issued = []; began = time.monotonic(); _, undo = install('v98-exact-v6')
    try:
        backend = PhysicsBackend(b, output, seed=b['seed'])
        eval_states={round(r['t'],9):r['states'] for r in rows(raw/'eval_only/setdown.jsonl')}
        backend.states_getter=lambda:eval_states.get(round(backend.now,9),{})
        backend.reset(b['reset_cap_s'])
        restore_scene(backend, read(raw/'eval_only/stage-setup.json'))
        if abs(backend.now-start) > 1e-8:
            raise ValueError('original stage start differs')
        spec = mujoco.mjtState.mjSTATE_INTEGRATION
        state = np.empty(mujoco.mj_stateSize(backend.world.model, spec))
        mujoco.mj_getState(backend.world.model, backend.world.data, state, spec)
        old = np.load(raw/'eval_only/stage-integration-state.npz')['state']
        summary['initial_state_exact'] = bool(np.array_equal(old, state))
        if not summary['initial_state_exact']:
            raise ValueError('initial integration state differs; no state correction applied')
        backend.set_deadline(end)
        video = Video(backend, 's4live11 '+condition+' seed '+str(b['seed']), ROBOTS)
        frame_times = {round(row['sim_time'],9) for row in rows(raw/'robots/r1/frames.jsonl')}
        steps = round((end-start)/.05)
        if path_check:
            steps = min(steps, 1)
        for i in range(steps+1):
            backend.eval_sample()
            if round(backend.now,9) in frame_times:
                own = backend.capture()  # same original 20Hz RGB/presentation calls
                video.frame(backend, own)
            for row in grouped.get(i, []):
                backend.issue(row['robot_id'], row['action'])
                issued.append(dict(t=backend.now, robot_id=row['robot_id'], action=row['action']))
            if i%20 == 0:
                write(output.parent/'health.json', dict(status='RUNNING', absolute_sim_s=backend.now,
                    relative_sim_s=round(backend.now-start,8), wall_s=time.monotonic()-began,
                    video_frames=video.frames, pid=os.getpid(), loadavg=os.getloadavg()))
            if i < steps:
                backend.advance_to(start+(i+1)*.05)
        for rid in ROBOTS:
            backend.issue(rid, {'kind':'hold'})  # original finally block, same order
        summary['status'] = 'PATH_CHECK' if path_check else 'COMPLETED'
    except Exception:
        import traceback
        summary.update(status='HOST_ERROR', error=traceback.format_exc())
    finally:
        for name, closer in [('video', video.close if video else None),
                             ('backend', backend.close if backend else None), ('speedups', undo)]:
            if closer is not None:
                try:
                    closer()
                except Exception:
                    import traceback
                    summary.update(status='HOST_ERROR')
                    summary.setdefault('cleanup_errors', {})[name] = traceback.format_exc()
        if video is not None:
            summary['video_frames'] = video.frames
            summary['terminal_still_frames']=60
        summary.update(wall_s=time.monotonic()-began, loadavg_end=os.getloadavg())
        if summary['status'] == 'COMPLETED':
            canonical = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            original_tape = [dict(t=r['t'], robot_id=r['robot_id'], action=r['action'])
                             for r in read(raw/'decision-command-links.json')]
            write(output/'replayed-command-order.json', issued)
            summary['global_command_order'] = dict(original=canonical(original_tape), replay=canonical(issued))
            summary['commands'] = {r:dict(original=sha(raw/f'robots/{r}/commands.jsonl'),
                replay=sha(output/f'robots/{r}/commands.jsonl')) for r in ROBOTS}
            summary['command_trajectory_match'] = (all(x['original']==x['replay'] for x in summary['commands'].values())
                and summary['global_command_order']['original']==summary['global_command_order']['replay'])
            summary['evaluation_trajectories'] = {r:dict(original=sha(raw/f'eval_only/{r}/trajectory.jsonl'),
                replay=sha(output/f'eval_only/{r}/trajectory.jsonl')) for r in ROBOTS}
            summary['evaluation_trajectory_match'] = all(x['original']==x['replay'] for x in summary['evaluation_trajectories'].values())
            summary['own_camera_match']=all(sha(raw/f'robots/{r}/frames.jsonl')==sha(output/f'robots/{r}/frames.jsonl') for r in ROBOTS)
            summary['beam_truth_match']=sha(raw/'eval_only/referee_truth.jsonl')==sha(output/'eval_only/referee_truth.jsonl')
            summary['video_sha256'] = sha(video.output)
            if not all(summary[k] for k in ('command_trajectory_match','evaluation_trajectory_match','own_camera_match','beam_truth_match')):summary['status']='REPLAY_MISMATCH'
        write(output.parent/'summary.json', summary)
        write(output.parent/'health.json', dict(status=summary['status'], wall_s=summary['wall_s']))
    print(json.dumps({k:summary.get(k) for k in ('condition','status','command_trajectory_match','evaluation_trajectory_match','error')}))
    return int(summary['status'] in ('HOST_ERROR','REPLAY_MISMATCH'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-source-sha', required=True)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--path-check', action='store_true')
    a = p.parse_args()
    from scripts.run_s3_x86_probe import archive_guard
    archive_guard(a.expected_source_sha, a.output)
    if os.environ.get('LP_NUM_THREADS') != '4':
        raise ValueError('original LP_NUM_THREADS=4 required')
    return run(a.original, a.output, a.expected_source_sha, path_check=a.path_check)


if __name__ == '__main__':
    raise SystemExit(main())
