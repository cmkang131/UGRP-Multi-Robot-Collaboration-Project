"""E0 clock audit: frozen metric definitions, default-off gate, recount safety."""
from pathlib import Path
import gzip
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import act18_clock_audit as audit

PREREG = ROOT / 'experiments/2026-10-17-act18/E0_CLOCK_AUDIT_PREREG.json'
BASE = {'1': 1000, '3': 1500, '4': 1500, '5': 1500, '6': 1500}


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')


def observation(t, pwm, pe, skill):
    issued = dict(t=t, wheels=[0.] * 4, duration_s=[0.] * 4, pwm=dict(pwm))
    return dict(world=0, observation=dict(t=t, issued=[issued] * 16,
                                          pwm_elapsed_s=pe, skill_elapsed_s=skill))


def action(t, pwm, wheels, done=False):
    return dict(actions=[dict(command=dict(t=t, wheels=list(wheels),
                                           duration_s=[0.] * 4, pwm=dict(pwm)), done=done)],
                skills=['grasp'])


def open_row(seed, t, skill, phase, done_prob, teacher_done, wheels):
    return dict(seed=seed, sample_id=f'{seed}:grasp', t=t, skill=skill, stage='grasp',
                teacher_phase=phase,
                teacher=[0.] * 13 + [float(teacher_done)],
                prediction=[0.] * 13 + [float(done_prob)],
                projected=list(wheels) + [0.] * 10)


def episode(seed, probabilities, reverse=False, done_probability=0.9):
    rows = []
    for index, (phase, value) in enumerate(zip(
            ('approach', 'align', 'close', 'lift', 'hold', 'hold', 'hold'), probabilities)):
        rows.append(open_row(seed, index * .1, 'grasp', phase, value, 0, [0.] * 4))
    rows[6]['teacher'][13] = 1.
    rows[6]['prediction'][13] = done_probability
    lookback_t = len(rows) * .1
    for index in range(-3, 4):
        wheels = [-.35] * 4 if reverse and index == 0 else [0.] * 4
        phase = 'lookback' if index == 0 else ('lookback_pose' if index < 0 else 'lookback_settle')
        rows.append(open_row(seed, lookback_t + index * .1, 'grasp', phase, .01, 0, wheels))
    return rows


def test_default_off(tmp_path):
    with pytest.raises(SystemExit):
        audit.main(['--prereg', str(PREREG), '--open-frames', str(tmp_path / 'f.gz'),
                    '--dataset-columns', str(tmp_path / 'd.jsonl'), '--out', str(tmp_path / 'o')])


def test_world_audit_clock_and_path():
    rows = []
    pwm = dict(BASE)
    for index in range(20):
        t = round(1.7 + index * .1, 3)
        if index == 5:
            pwm['3'] = 700
        if index == 10:
            pwm['5'] = 1600
        pe = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}.get(index)
        if pe is None:
            pe = [0., .1, .2, .3, .4, 0., .1, .2, .3, .4, .5, .6, .7, .8,
                  .9][index - 5]
        rows.append(observation(t, pwm, pe, index * .1))
    actions = []
    command_pwm = dict(BASE)
    for index in range(20):
        if index == 12:
            command_pwm = dict(command_pwm, **{'1': 1500})
        wheels = [.35] * 4 if index < 4 else [0.] * 4
        actions.append(action(round(1.7 + index * .1, 3), command_pwm, wheels))
    events = [dict(world=0, t=round(1.7 + index * .1, 3), speed=0., min_z=.2,
                   finger_forces=[0., 0.], lift_success=False) for index in range(20)]
    events[14]['finger_forces'] = [3.1, 0.]
    events[15]['lift_success'] = True
    prereg = audit.read_json(PREREG)
    report = audit.audit_world('orig', Path('/tmp/run'), 0, rows, actions, events, prereg)
    clock = report['m01_clock']
    assert clock['eligible'] and clock['start_index'] == 5 and clock['start_pwm3'] == 700
    assert clock['max_pwm_elapsed_s'] == .9
    assert clock['resets'] == 1
    assert clock['resets_per_10s'] == round(1 / (15 * .1 / 10), 3)
    assert clock['reset_delta_by_servo']['5']['max'] == 100
    assert report['m02_skill_elapsed']['min'] == 0 and report['m02_skill_elapsed']['max'] == 1.9
    assert report['m03']['base_last_move_index'] == 3
    assert report['m03']['physical_lift'] and report['m03']['lift_first_t'] == 3.2
    assert report['m06']['close_index'] == 12
    assert report['m06']['unilateral_first_t'] == 3.1


def test_open_frames_done_and_lookback(tmp_path):
    rows = []
    for index, seed in enumerate(audit.TRAIN4_SEEDS):
        rows.extend(episode(seed, [.2, .01, .01, .01, .2, .3, .9],
                            reverse=index < 3, done_probability=.9 if index < 3 else .01))
    path = tmp_path / 'frames.jsonl.gz'
    with gzip.open(path, 'wt') as handle:
        for row in rows:
            handle.write(json.dumps(row) + '\n')
    prereg = audit.read_json(PREREG)
    report = audit.audit_open_frames(path, prereg)
    assert report['rows'] == len(rows)
    first = report['episodes'][0]
    assert first['grasp_rows'] == 14 and first['hold_rows'] == 3
    assert first['done_probability'] == .9 and first['rank'] == 1
    assert first['lookback_onset_t'] == .7
    assert first['m05_reverse'] is True and first['m05_window'][3]['offset'] == 0
    assert report['episodes'][3]['m05_reverse'] is False and report['episodes'][1]['m05_reverse'] is True
    worlds = [dict(label='orig', world=0, seed=88600, m01_clock=dict(eligible=True, max_pwm_elapsed_s=3.0),
                   m03=dict(physical_lift=True), m06=dict(close_index=5))]
    worlds += [dict(label='orig', world=index + 1, seed=audit.TRAIN4_SEEDS[index + 1],
                    m01_clock=dict(eligible=True, max_pwm_elapsed_s=3.0),
                    m03=dict(physical_lift=True), m06=dict(close_index=5)) for index in range(3)]
    dataset = dict(changed_ratio=.0005, exact_recount_valid=True, changed_rows=1)
    verdict = audit.judge(prereg, worlds, report, dataset)
    assert verdict['H1']['verdict'] == 'support'
    assert verdict['done_head'] == 'normal'
    assert verdict['M0_5']['verdict'] == 'transition_possible'
    assert verdict['R1a']['verdict'] == 'pass'


def test_dataset_clock_deadband_changes_only_jitter(tmp_path):
    rows = []
    sequence = [(BASE, 0.), (dict(BASE, **{'1': 1001}), 0.), (dict(BASE, **{'1': 1002}), 0.),
                (dict(BASE, **{'1': 1003}), 0.), (dict(BASE, **{'1': 1500}), 0.)]
    for index, (pwm, pe) in enumerate(sequence):
        rows.append(dict(seed=88600, split='train', t=round(index * .1, 3), skill='grasp',
                         teacher_phase='hold', pwm_elapsed_s=pe, issued_pwm=dict(pwm),
                         teacher_pwm=dict(pwm)))
    path = tmp_path / 'dataset-columns.jsonl'
    write_jsonl(path, rows)
    prereg = audit.read_json(PREREG)
    report = audit.audit_dataset_columns(path, prereg)
    assert report['exact_recount_valid'] is True
    # +1 at tick 1 accumulates to +2 at tick 2 (still below the reset threshold 3),
    # then tick 3 resets to 0 again.  Rows 1 and 2 differ from the exact clock.
    assert report['changed_rows'] == 2
    assert report['changed_ratio'] == pytest.approx(.4)


def test_dataset_clock_guard_flags_broken_reconstruction(tmp_path):
    rows = [dict(seed=88600, split='train', t=0., skill='grasp', teacher_phase='hold',
                 pwm_elapsed_s=5., issued_pwm=dict(BASE), teacher_pwm=dict(BASE))]
    path = tmp_path / 'broken-dataset.jsonl'
    write_jsonl(path, rows)
    report = audit.audit_dataset_columns(path, audit.read_json(PREREG))
    assert report['exact_recount_valid'] is False


def test_main_integration(tmp_path):
    open_rows = []
    for index, seed in enumerate(audit.TRAIN4_SEEDS):
        open_rows.extend(episode(seed, [.2, .01, .01, .01, .2, .3, .9],
                                 reverse=index < 3, done_probability=.9))
    open_path = tmp_path / 'frames.jsonl.gz'
    with gzip.open(open_path, 'wt') as handle:
        for row in open_rows:
            handle.write(json.dumps(row) + '\n')
    dataset_rows = []
    for index in range(10):
        dataset_rows.append(dict(seed=88600, split='train', t=round(index * .1, 3), skill='grasp',
                                 teacher_phase='hold', pwm_elapsed_s=round(index * .1, 3),
                                 issued_pwm=dict(BASE), teacher_pwm=dict(BASE)))
    dataset_path = tmp_path / 'dataset-columns.jsonl'
    write_jsonl(dataset_path, dataset_rows)
    specs = []
    for run_index, (label, seeds) in enumerate((('orig', (88600, 88601)),
                                                ('repro', (88602, 88603)))):
        run = tmp_path / label
        inputs, actions, events = [], [], []
        states = [dict(pwm=dict(BASE), command=dict(BASE)) for _ in seeds]
        for index in range(40):
            t = round(1.7 + index * .1, 3)
            if index == 8:
                for state in states:
                    state['pwm']['3'] = 700
                    state['command']['3'] = 700
            row_actions = []
            for world, state in enumerate(states):
                inputs.append(dict(world=world, observation=dict(
                    t=t, issued=[dict(t=t, wheels=[0.] * 4, duration_s=[0.] * 4,
                                      pwm=dict(state['pwm']))] * 16,
                    pwm_elapsed_s=round(index * .1, 3), skill_elapsed_s=index * .1)))
                row_actions.append(dict(command=dict(
                    t=t, wheels=[.35] * 4 if index < 3 else [0.] * 4,
                    duration_s=[0.] * 4, pwm=dict(state['command'])), done=False))
                events.append(dict(world=world, t=t, speed=.0, min_z=.2,
                                   finger_forces=[0., 0.], lift_success=index > 20))
            actions.append(dict(actions=row_actions, skills=['grasp'] * len(seeds)))
        write_jsonl(run / 'actor-inputs.jsonl', inputs)
        write_jsonl(run / 'actor-actions.jsonl', actions)
        write_jsonl(run / 'owner/evaluation-only.jsonl', events)
        (run / 'initial-plans.json').write_text(json.dumps(dict(
            episodes=[dict(seed=seed) for seed in seeds])))
        specs.extend(['--run', f'{label}={run}'])
    out = tmp_path / 'out'
    summary = audit.main(['--enabled', '--prereg', str(PREREG), *specs,
                          '--open-frames', str(open_path),
                          '--dataset-columns', str(dataset_path), '--out', str(out)])
    assert out.joinpath('summary.json').exists() and out.joinpath('manifest.json').exists()
    assert len(summary['runs']) == 2 and len(summary['runs'][0]['worlds']) == 2
    assert summary['verdict']['H1']['verdict'] in ('support', 'refute', 'ambiguous')
    assert summary['r1a_dataset']['changed_ratio'] == 0.
    assert summary['m04_done']['episodes'][0]['seed'] == 88600
