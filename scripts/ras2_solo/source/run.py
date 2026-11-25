"""Connect the published Solo pipeline to one Raspberry Pi over owned SSH children."""
import argparse
import base64
from collections import deque
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tarfile
import threading
import time

ROOT = Path(os.environ.get('UGRP_SOLO_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'runtime' / 'solo_pipeline'))
from harness import grasp_act_contract as contract
from harness.approach_survey_v1 import FAR_POSTURE, SurveyApproach
from harness.grasp_act_policy import GraspActor
from harness.grasp_act_rollout import GraspTransitionRule, OwnHistory


def board_command(value, minimum):
    """Explicit experimental speed projection and inverse SIM-to-board permutation."""
    value = contract.command(value)
    wheels = [0. if not w else (1 if w > 0 else -1) * max(minimum, round(100 * abs(w))) / 100
              for w in value['wheels']]
    indices, signs = (1, 3, 0, 2), (-1, 1, 1, -1)
    return {'op': 'command', 'motors': [round(sign * wheels[i] * 100) for i, sign in zip(indices, signs)],
            'duration_s': [value['duration_s'][i] for i in indices], 'pwm': value['pwm']}, wheels


class Link:
    def __init__(self, host, user, output, execute, seconds, expected_host='ras2'):
        if expected_host not in ('ras2', 'ugrp1'):
            raise ValueError('Unsupported expected robot hostname')
        self.process = None
        self.stderr = (output / 'ssh-stderr.log').open('w', encoding='utf-8')
        self.ssh = ['ssh', '-T', '-o', 'ConnectTimeout=8', '-o', 'StrictHostKeyChecking=accept-new',
                    '-o', 'NumberOfPasswordPrompts=1', '-o', 'ServerAliveInterval=2',
                    '-o', 'ServerAliveCountMax=2', f'{user}@{host}']
        package = io.BytesIO()
        control_archive = ROOT.parent / 'ugrp-masterpi-179dd3a20fb8.tar.gz'
        if hashlib.sha256(control_archive.read_bytes()).hexdigest() != '996904acbb137bf3d7e48d5a5723517cb163da0602145c2b2da1cfefad978a4f':
            raise ValueError('Existing hardware driver archive checksum mismatch')
        with tarfile.open(control_archive) as archived:
            driver = archived.extractfile('masterpi_control.py').read()
        files = {'masterpi_control.py': driver, 'pi_bridge.py': Path(__file__).with_name('pi_bridge.py').read_bytes()}
        signature = hashlib.sha256(b''.join(files.values())).hexdigest()
        with tarfile.open(fileobj=package, mode='w:gz') as bundle:
            manifest = ''.join(f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name, data in files.items())
            for name, data in {**files, 'SHA256SUMS': manifest.encode()}.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                bundle.addfile(entry, io.BytesIO(data))
        remote = f'"$HOME/MasterPi/tools/ras2-solo-{signature[:16]}"'
        upload = f'mkdir -p {remote} && tar -xzf - -C {remote} && cd {remote} && sha256sum --strict --quiet -c SHA256SUMS'
        try:
            subprocess.run([*self.ssh, upload], input=package.getvalue(), stdout=subprocess.PIPE,
                           stderr=self.stderr, timeout=30, check=True)
        except BaseException:
            self.stderr.close()
            raise
        command = f'cd {remote} && exec python3 -u pi_bridge.py --control masterpi_control.py --seconds {seconds + 30} --expected-host {expected_host}'
        if execute:
            command += ' --execute'
        self.process = subprocess.Popen([*self.ssh, command], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.stderr, text=True, encoding='utf-8', bufsize=1)
        self.responses = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.ready = self.receive(10.)
            if self.ready.get('ready') is not True:
                raise RuntimeError('Pi bridge did not become ready')
        except BaseException:
            self.close()
            raise

    def _read(self):
        for line in self.process.stdout:
            self.responses.put(line)
        self.responses.put(None)

    def receive(self, timeout=5.):
        try:
            line = self.responses.get(timeout=timeout)
        except queue.Empty as error:
            raise TimeoutError('Pi response timed out; see ssh-stderr.log') from error
        if line is None:
            raise RuntimeError('SSH bridge closed; see ssh-stderr.log')
        result = json.loads(line)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    def request(self, payload):
        self.process.stdin.write(json.dumps(payload, allow_nan=False) + '\n')
        self.process.stdin.flush()
        return self.receive()

    def close(self):
        if self.process is not None:
            try:
                if self.process.poll() is None:
                    self.request({'op': 'stop'})
            except (Exception, KeyboardInterrupt):
                pass
            finally:
                self.process.stdin.close()
                try:
                    self.process.wait(timeout=10.)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3.)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                self.reader.join(timeout=1.)
        self.stderr.close()


def select_target(entries, target):
    choices = [i for i, entry in enumerate(entries) if entry['kind'] == target]
    return min(choices, key=lambda i: entries[i]['distance_m']) if choices else -1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='192.168.137.11')
    parser.add_argument('--user', required=True)
    parser.add_argument('--expected-host', choices=('ras2', 'ugrp1'), default='ras2')
    parser.add_argument('--target', choices=('red', 'cyan'), default='red')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--seconds', type=float, default=240.)
    parser.add_argument('--wheel-floor', type=int, choices=(35,), default=35)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', args.user):
        parser.error('Invalid SSH user')
    if not 1 <= args.seconds <= 600:
        parser.error('seconds must be between 1 and 600')
    import torch
    torch.set_num_threads(4)
    output = ROOT / 'runs' / time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True, exist_ok=False)
    report = {'mode': 'execute' if args.execute else 'check', 'target': args.target,
              'expected_host': args.expected_host, 'address': args.host,
              'model': 'solo-act-model-gseg-step4000', 'image_frontend': 'seg5_v1',
              'camera_geometry': 'published SIM reference; ras2 calibration pending',
              'wheel_projection': 'experimental nonzero floor 35, original pulse widths, inverse motor permutation',
              'timing': '10 Hz target; motors expire locally; inference pauses logged, no time compression',
              'physical_grasp_success': None, 'status': 'starting'}
    link = None
    began = time.monotonic()
    try:
        print('Loading published seg5_v1 step4000 ACT model...', flush=True)
        actor = GraspActor.load(ROOT / 'runtime/actor', device='cpu')
        if actor.image_frontend != 'seg5_v1':
            raise ValueError('Wrong actor preprocessing')
        link = Link(args.host, args.user, output, args.execute, args.seconds, args.expected_host)
        frame = link.request({'op': 'observe'})
        jpeg = base64.b64decode(frame['jpeg'], validate=True)
        from harness.grasp_act_data import image_array
        image_array(jpeg)  # enforce the trained 640x480 camera input
        (output / 'first-frame.jpg').write_bytes(jpeg)
        report['hardware'] = link.ready
        print(f"{link.ready['host']} connected, camera 640x480, battery {link.ready['probe'].get('battery_mv')} mV", flush=True)
        initial = {'t': frame['t'], 'wheels': [0.] * 4, 'duration_s': [0.] * 4,
                   'pwm': {str(k): v for k, v in FAR_POSTURE.items()}}
        if not args.execute:
            history = OwnHistory('r1', 'ras2-check', initial)
            obs, pixels, _ = history.observe(frame['t'], jpeg, skill='grasp', object_kind=args.target, role='west')
            started = time.monotonic()
            chunk = actor.predict(obs, pixels)
            report.update(status='check_passed', inference_s=time.monotonic()-started,
                          chunk_shape=[len(chunk), len(chunk[0])], motion_commands_sent=0,
                          history='check-only stationary initialization; published FAR_POSTURE, not measured joints')
            print('CHECK PASSED: model, camera, board. Hardware motion commands sent: 0', flush=True)
            return
        hardware, _ = board_command(initial, args.wheel_floor)
        accepted = link.request(hardware)
        initial['t'] = accepted['accepted_at']
        history = OwnHistory('r1', 'ras2-live', initial)
        approach = SurveyApproach(contract, lambda entries: select_target(entries, args.target))
        rule = GraspTransitionRule()
        pending = deque()
        phase = None
        (output / 'rgb/r1').mkdir(parents=True)
        run_start = time.monotonic()
        with (output / 'events.jsonl').open('w', encoding='utf-8') as events:
            while time.monotonic() - run_start < args.seconds:
                tick_start = time.monotonic()
                frame = link.request({'op': 'observe'})
                now = frame['t']
                jpeg = base64.b64decode(frame['jpeg'], validate=True)
                obs, pixels, relative = history.observe(now, jpeg, skill='grasp', object_kind=args.target, role='west')
                (output / relative).write_bytes(jpeg)
                inference_s = 0.
                if not approach.arrived:
                    stage = approach.stage
                    requested = approach.step(jpeg, now)
                    if approach.arrived:
                        record = approach.record()
                        (output / 'approach.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
                        if not (approach.align_reason or '').startswith('aligned_'):
                            raise RuntimeError(f'Approach/alignment failed: {approach.reason}, {approach.align_reason}')
                        clock = contract.IssuedClock()
                        clock.skill = ('grasp', args.target, 'west', 'none')
                        clock.started = now + contract.PERIOD_S - approach.approach_seconds()
                        history.clock = clock
                else:
                    stage = 'ACT grasp'
                    if not pending:
                        # Wheel pulse deadlines continue running on the Pi during inference.
                        started = time.monotonic()
                        chunk = actor.predict(obs, pixels)
                        inference_s = time.monotonic() - started
                        if inference_s > 1.5:
                            raise TimeoutError('Inference exceeded 1.5s; Pi heartbeat deadline is 2.5s')
                        pending.extend(contract.decode_action(row) for row in chunk)
                    action = pending.popleft()
                    requested = {'t': now, **{key: action[key] for key in ('wheels', 'duration_s', 'pwm')}}
                if stage != phase:
                    print(f'STAGE {stage}', flush=True)
                    phase = stage
                hardware, applied_wheels = board_command(requested, args.wheel_floor)
                accepted = link.request(hardware)
                issued = dict(requested, t=accepted['accepted_at'], wheels=applied_wheels,
                              pwm={key: accepted['pwm'][key] for key in requested['pwm']})
                history.issue(issued)
                events.write(json.dumps({'stage': stage, 'observation': obs, 'requested': requested,
                                         'issued': issued, 'board': hardware, 'inference_s': inference_s}) + '\n')
                events.flush()
                if stage == 'ACT grasp' and rule.observe(issued['t'], issued):
                    report.update(status='grasp_command_sequence_complete',
                                  note='Own-command rule fired; physical lift requires observation')
                    print('GRASP COMMAND SEQUENCE COMPLETE. Verify the actual object lift.', flush=True)
                    break
                time.sleep(max(0., contract.PERIOD_S - (time.monotonic() - tick_start)))
            else:
                raise TimeoutError('Trial time budget reached')
    except BaseException as error:
        report.update(status='interrupted' if isinstance(error, KeyboardInterrupt) else 'failed', error=str(error))
        raise
    finally:
        if link:
            link.close()
        report['wall_s'] = time.monotonic() - began
        (output / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'Log directory: {output}', flush=True)


if __name__ == '__main__':
    main()
