"""Replay recorded camera times and commands; never connect to robot hardware."""
import argparse
import base64
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import run


def verify_failure_cleanup(rows, directory):
    """Exercise the actual execute loop with a fake transport, never SSH/I2C."""
    initial = rows[0]['observation']['issued'][-1]
    frames = [{'t': row['observation']['t'], 'jpeg': base64.b64encode(
        (directory / row['observation']['rgb'][-1]['path']).read_bytes()).decode('ascii')}
              for row in rows]
    frames += [dict(frames[-1], t=frames[-1]['t']+.1),
               dict(frames[-1], t=frames[-1]['t']-.1)]
    instances = []

    class FakeActor:
        image_frontend = 'seg5_v1'

        def predict(self, *args):
            raise AssertionError('Recorded trial never reached ACT grasp')

    class FakeLink:
        def __init__(self, *args):
            self.ready = {'host': 'ugrp1', 'probe': {'battery_mv': 7492}}
            self.frames = iter([dict(frames[0], t=initial['t']-.01), *frames])
            self.now = None
            self.closed = False
            instances.append(self)

        def request(self, payload):
            if payload['op'] == 'observe':
                frame = next(self.frames)
                self.now = frame['t']
                return frame
            assert payload['op'] == 'command'
            return {'accepted_at': self.now+.001, 'pwm': payload['pwm']}

        def close(self):
            self.closed = True

    with tempfile.TemporaryDirectory(prefix='solo-cleanup-regression-') as folder:
        root = Path(folder)
        argv = ['run.py', '--user', 'ugrp1', '--expected-host', 'ugrp1', '--execute']
        with patch.object(run, 'ROOT', root), patch.object(run, 'Link', FakeLink), \
             patch.object(run.GraspActor, 'load', return_value=FakeActor()), \
             patch.object(run.time, 'sleep'), patch.object(sys, 'argv', argv), \
             contextlib.redirect_stdout(io.StringIO()):
            try:
                run.main()
            except ValueError as error:
                assert str(error) == 'Live camera clock reversed'
            else:
                raise AssertionError('Expected the injected clock reversal')
        output = next((root / 'runs').iterdir())
        result = json.loads((output / 'result.json').read_bytes())
        assert result['error'] == 'Live camera clock reversed'
        assert result['loop_commands_acknowledged'] == len(rows)+1
        assert instances[0].closed
        assert (output / result['last_capture']['path']).is_file()
        assert json.loads((output / 'approach.json').read_bytes())['stage_ticks']['approach'] == 46
        for name in ('approach-trace.json', 'alignment-trace.json'):
            assert (output / name).is_file()
    return 'fake transport: 167 accepted ticks; reversed-clock frame saved; session close called; diagnostics saved'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.run_dir / 'events.jsonl').read_text().splitlines()]
    initial = rows[0]['observation']['issued'][-1]
    original = run.PublishedOwnHistory('r1', 'published-replay', initial)
    fixed = run.OwnHistory('r1', 'live-replay', initial)
    approach = run.SurveyApproach(run.contract, lambda entries: run.select_target(entries, 'red'))
    instruction = {'skill': 'grasp', 'object_kind': 'red', 'role': 'west'}
    ages, command_matches = [], 0
    for row in rows:
        now = row['observation']['t']
        jpeg = (args.run_dir / row['observation']['rgb'][-1]['path']).read_bytes()
        original.observe(now, jpeg, **instruction)
        obs, _, _ = fixed.observe(now, jpeg, **instruction)
        run.contract.validate_observation(obs)
        ages.append(now-obs['rgb'][0]['t'])
        requested = approach.step(jpeg, now)
        assert requested == row['requested'], 'Published approach replay differs from recorded command'
        command_matches += 1
        for history in (original, fixed):
            history.issue(row['issued'])
    # The failed capture was not saved by the old runner. Explicitly synthesize
    # its next time; the image below is a replay fixture, not a new live frame.
    now += .1
    try:
        original.observe(now, jpeg, **instruction)
    except ValueError as error:
        assert str(error) == 'future, reversed or stale image'
        old_refs = run.contract.image_history([ref for ref, _ in original.frames], now)
        reproduced = {'error': str(error), 'oldest_age_s': now-old_refs[0]['t'],
                      'synthetic_next_frame_time': now}
    else:
        raise AssertionError('Expected recorded-boundary failure was not reproduced')
    obs, _, _ = fixed.observe(now, jpeg, **instruction)
    assert max(now-ref['t'] for ref in obs['rgb']) <= run.contract.MEMORY_S + .15
    for ref, image in fixed.frames:
        assert ref['sha256'] == hashlib.sha256(image).hexdigest()
    stress = run.OwnHistory('r1', 'jitter-regression', initial)
    clock = rows[0]['observation']['t']
    for i in range(1000):
        clock += (.10, .36, .08, .63, .12)[i % 5]
        obs, _, _ = stress.observe(clock, jpeg, **instruction)
        run.contract.validate_observation(obs)
        stress.issue(dict(initial, t=clock+.001))
    try:
        stress.observe(clock-1., jpeg, **instruction)
    except ValueError as error:
        assert str(error) == 'Live camera clock reversed'
    else:
        raise AssertionError('Clock reversal was accepted')
    future = run.OwnHistory('r1', 'future-command', dict(initial, t=clock+1.))
    try:
        future.observe(clock, jpeg, **instruction)
    except ValueError as error:
        assert str(error) == 'Live camera timestamp precedes the last issued command'
    else:
        raise AssertionError('Future command was accepted')
    contract_hash = hashlib.sha256(Path(run.contract.__file__).read_bytes()).hexdigest()
    assert contract_hash == '6bc58d6f9707abd5d854c6dbbb63357ed14dab6c37bcf055ddd8d1d66d171056'
    cleanup = verify_failure_cleanup(rows, args.run_dir)
    result = {'source_run': str(args.run_dir.resolve()), 'recorded_rows_replayed': len(rows),
              'published_approach_commands_exactly_matched': command_matches,
              'original_failure_reproduced': reproduced,
              'fixed_next_observation_ages_s': fixed.last_audit['selected_image_ages_s'],
              'jitter_ticks_validated': 1000, 'clock_reversal_rejected': True,
              'future_command_rejected': True, 'unchanged_published_contract_sha256': contract_hash,
              'failure_cleanup_and_evidence': cleanup,
              'recorded_stages': sorted({row['stage'] for row in rows}),
              'physical_commands_sent_by_verification': 0,
              'calibration_and_lift_validation': 'not performed'}
    output = run.ROOT / 'diagnostics' / args.run_dir.name
    output.mkdir(parents=True, exist_ok=True)
    (output / 'replay-verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (output / 'approach-reconstructed.json').write_text(json.dumps(approach.record(), indent=2), encoding='utf-8')
    (output / 'approach-trace-reconstructed.json').write_text(json.dumps(approach.trace, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
