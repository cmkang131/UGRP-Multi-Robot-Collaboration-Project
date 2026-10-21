"""Tournament A ledger writer on a fake run root (no physics)."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import act18_tournament_ledger as tl  # noqa: E402

PREREG = ROOT / 'experiments/2026-10-17-act18/CARRY_TOURNAMENT_A_PREREG_DRAFT.json'


def action(pwm1, skill_t):
    return dict(command=dict(t=skill_t, wheels=[0, 0, 0, 0], pwm={'1': pwm1, '3': 1500, '4': 1500,
                                                                     '5': 1500, '6': 1500}))


def make_group(stage_dir, group, seeds, *, status='complete', scores=None, actions=None, lift=None):
    g = stage_dir / f'group-{group:03d}'
    ev = g / 'evaluation'
    (ev / 'owner').mkdir(parents=True)
    (g / 'plans.json').write_text(json.dumps(dict(episodes=[dict(seed=s) for s in seeds])))
    if status is None:
        return g
    scores = scores if scores is not None else [
        dict(seed=s, release_success=True, physical_success=True, drop_detected=False, cap_end=False,
             issued_done_times=dict(grasp=5.0, release=9.0)) for s in seeds]
    (ev / 'summary.json').write_text(json.dumps(dict(status=status, student_scores=scores)))
    rows = []
    for w in range(len(seeds)):
        for k in range(32):   # 3.2 s stable lift from t=1.0, completes before done 5.0
            t = 1.0 + .1 * k
            rows.append(dict(world=w, t=t, min_z=.02, tilt_deg=1., finger_forces=[1., 1.]))
    if lift is not None:
        rows = [r for r in rows if r['world'] != lift]
    (ev / 'owner/evaluation-only.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    actions = actions or [(['grasp'] * len(seeds), [2000] * len(seeds)), (['grasp'] * len(seeds), [1500] * len(seeds)),
                          (['release'] * len(seeds), [2000] * len(seeds))]
    (ev / 'actor-actions.jsonl').write_text(''.join(
        json.dumps(dict(skills=sk, actions=[action(p, 0.) for p in pw])) + '\n' for sk, pw in actions))
    return g


def test_world_rows_keys_and_flags(tmp_path):
    stage = tmp_path / 'A-c1-ho4-rep1' / 'R8-diag'
    make_group(stage, 0, [88668])
    # world 0 closes then re-opens in grasp (early open); world 1 never stable-lifts
    make_group(stage, 1, [88670, 88671], lift=1,
               actions=[(['grasp', 'grasp'], [2000, 2000]), (['grasp', 'grasp'], [1500, 1500]),
                        (['grasp', 'grasp'], [1950, 1500]), (['release', 'release'], [1500, 2000])])
    rows = tl.ledger_rows(PREREG, tmp_path)
    head, world = rows[0], rows[1:]
    assert head['type'] == 'header' and head['prereg_sha256'] == tl.sha256(PREREG)
    assert [(r['seed'], r['cohort'], r['arm'], r['rep']) for r in world] == [
        (88668, 'HO4', 'A-c1', 1), (88670, 'HO4', 'A-c1', 1), (88671, 'HO4', 'A-c1', 1)]
    for key in ('release_success', 'physical_success', 'drop_detected', 'G', 'early_open_grasp',
                'open_issued', 'release_done', 'cap_end'):
        assert all(key in r for r in world)
    by = {r['seed']: r for r in world}
    assert by[88668]['G'] and not by[88668]['early_open_grasp'] and by[88668]['open_issued']
    assert by[88670]['early_open_grasp'] and not by[88670]['open_issued'] and by[88670]['G']
    assert not by[88671]['G'] and by[88671]['open_issued'] and not by[88671]['early_open_grasp']
    assert all(r['status'] == 'complete' and r['release_done'] for r in world)


@pytest.mark.parametrize('status,scores', [(None, None), ('HOST_ERROR', []), ('complete', [])])
def test_unfinished_group_is_host_error_for_every_seed(tmp_path, status, scores):
    stage = tmp_path / 'A-base-train4-rep2' / 'R8-train'
    make_group(stage, 0, [88600, 88603], status=status, scores=scores)
    world = tl.ledger_rows(PREREG, tmp_path)[1:]
    assert [(r['seed'], r['status'], r['cohort'], r['arm']) for r in world] == [
        (88600, 'HOST_ERROR', 'TRAIN4', 'A-base'), (88603, 'HOST_ERROR', 'TRAIN4', 'A-base')]
    assert 'release_success' not in world[0]


def test_unknown_arm_and_missing_plans_refused(tmp_path):
    make_group(tmp_path / 'A-c9-ho4-rep1' / 'R8-diag', 0, [88668])
    with pytest.raises(ValueError, match='not in prereg arms'):
        tl.ledger_rows(PREREG, tmp_path)
    other = tmp_path / 'b'
    (other / 'A-c2-ho4-rep1' / 'R8-diag' / 'group-000').mkdir(parents=True)
    with pytest.raises(ValueError, match='plans.json'):
        tl.ledger_rows(PREREG, other)


def test_cli_refuses_existing_output(tmp_path):
    make_group(tmp_path / 'run' / 'A-c3-ho4-rep3' / 'R8-diag', 0, [88669])
    out = tmp_path / 'report' / 'tournament-ledger.jsonl'
    assert tl.main(['--prereg', str(PREREG), '--run-root', str(tmp_path / 'run'), '--out', str(out)]) == 0
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert lines[0]['type'] == 'header' and lines[1]['seed'] == 88669
    with pytest.raises(SystemExit):
        tl.main(['--prereg', str(PREREG), '--run-root', str(tmp_path / 'run'), '--out', str(out)])


def test_prereg_records_host_error_rule_and_writer():
    d = json.loads(PREREG.read_text())
    assert 'never re-run' in d['host_error']['rule']
    assert 'act18_tournament_ledger.py' in d['ledger']['writer']
