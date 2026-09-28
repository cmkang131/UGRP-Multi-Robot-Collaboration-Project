"""Raw memory fix boundaries and explicit identity; no physics or models."""
import copy
import importlib
import json

import pytest

from harness.owncam_drive import LOOK_P20
from harness.owncam_memory import OwnCamMemory, LOOK_FIX_STALE_S
from harness.owncam_memory_time import TIME_CONTRACT, condition_label
from harness.owncam_memory_v3 import OwnCamMemoryV3
from harness.owncam_pose_guard_v3 import FIX_MAX_AGE_S
from tests.test_owncam_memory_v3 import memory, report, consistent


def observed_memory(cls, capture):
    mem = memory(cls)
    mem.provider.observe = lambda **kw: [dict(
        landmark_id='face:fixture', landmark_type='wall_face', feature_id='edge',
        range_m=1., azimuth_rad=0., elevation_rad=0.)]
    if cls is OwnCamMemoryV3:
        consistent(mem.guard, capture)
    mem.observe_frame(capture, frame_id=1, image=None, servo={**LOOK_P20, 1: 2000, 6: 1500},
                      report=report(capture), arm_settled_s=1., loaded=False)
    return mem


@pytest.mark.parametrize('cls', [OwnCamMemory, OwnCamMemoryV3])
@pytest.mark.parametrize('capture', [1.00049, 1.00051])
def test_fix_since_keeps_both_rounding_directions_and_raw_sweep_boundary(cls, capture, monkeypatch):
    mem = observed_memory(cls, capture)
    if cls is OwnCamMemoryV3:
        # Isolate the fix/sweep boundary; independent evidence is tested by the
        # pose guard suite and must not mask a rounded last_look_fix here.
        monkeypatch.setattr(mem.guard, 'consistent', lambda *args, **kwargs: True)
    assert mem.last_fix['t'] == mem.last_look_fix['t'] == capture
    assert mem.look_fix_since(capture - .00002)
    assert mem.look_fix_since(capture)
    assert not mem.look_fix_since(capture + .00001)
    snap = mem.snapshot(capture)
    assert snap['time_contract'] == snap['last_fix']['time_contract'] == TIME_CONTRACT
    assert snap['last_look_fix']['time_contract'] == TIME_CONTRACT
    # Snapshot is an output copy, not a mutable alias to live control state.
    snap['last_look_fix']['t'] = 0.
    assert mem.last_look_fix['t'] == capture


@pytest.mark.parametrize('cls,limit', [(OwnCamMemory, LOOK_FIX_STALE_S), (OwnCamMemoryV3, FIX_MAX_AGE_S)])
@pytest.mark.parametrize('capture', [1.00049, 1.00051])
@pytest.mark.parametrize('offset,expected', [(0., True), (-.00002, True), (.00002, False)])
def test_freshness_uses_raw_fix_age_at_expiry(cls, limit, capture, offset, expected):
    mem = observed_memory(cls, capture)
    now = capture + limit + offset
    if cls is OwnCamMemoryV3:
        consistent(mem.guard, now)  # current independent evidence; age is the variable
    assert bool(mem.look_fix_fresh(now, mem.last_look_fix['xy'])) is expected


@pytest.mark.parametrize('capture', [1.00049, 1.00051])
def test_v3_just_captured_fix_is_fresh_even_when_display_rounds_up(capture):
    mem = observed_memory(OwnCamMemoryV3, capture)
    assert mem.look_fix_fresh(capture, mem.last_look_fix['xy'])
    mem.last_look_fix['t'] = capture + .00002
    assert not mem.look_fix_fresh(capture, mem.last_look_fix['xy'])


@pytest.mark.parametrize('module,conditions', [
    ('scripts.run_m1_owncam_memory', ('memory_v2', 'off')),
    ('scripts.run_m1_owncam_memory_v3', ('memory_v2', 'memory_v3', 'off', 'off_legacy',
                                          'memory_provider', 'm1_provider')),
])
def test_runner_records_and_displays_contract_without_relabelling_history(tmp_path, monkeypatch, module, conditions):
    runner = importlib.import_module(module)
    from scripts import run_m1_owncam as base_runner
    seen = []
    def fake_run(spec, out, student):
        seen.append(student)
        out.mkdir()
        for name in ('result.json', 'manifest.json'):
            (out / name).write_text('{}')
        return {'controller': {}}, {'student': student}
    monkeypatch.setattr(base_runner, 'run', fake_run)
    monkeypatch.setattr(runner, 'free_gib', lambda path: 100.)
    monkeypatch.setattr(runner, 'git', lambda *args: '')
    for name in runner.THREAD_VARS:
        monkeypatch.setenv(name, '1')
    for condition in conditions:
        _, manifest, row = runner.run_episode({'episode_id': 'fake'}, tmp_path / condition, {}, condition,
                                             prereg_sha256='fake')
        has_memory = condition.startswith('memory_') or (module.endswith('_v3') and condition == 'off')
        contract = TIME_CONTRACT if has_memory else None
        assert row['time_contract'] == manifest['student']['time_contract'] == contract
        assert row['condition_label'] == condition_label(condition, contract)
        assert seen[-1]['condition_label'] == row['condition_label']
        assert json.loads((tmp_path / condition / 'memory_runner.json').read_text()) == row
    for version in ('memory_v2', 'memory_v3'):
        historical = {'condition': version, 'result_label': 'interim, tag provider'}
        original = copy.deepcopy(historical)
        assert condition_label(historical['condition'], historical.get('time_contract')) == version
        assert historical == original and 'time_contract' not in historical


def test_pair_and_integration_bundle_record_memory_time_identity():
    from scripts.zone_pair_grasp_contract import grasp_contract
    from scripts import run_zone_study_integration as runner
    from tests.test_zone_study_integration_pair import PREREG
    pre = runner.load_prereg(PREREG)
    bundle = runner.run_bundle(pre, pre['episodes'][0])[0]
    assert bundle['memory_time_contract'] == grasp_contract()['memory_time_contract'] == TIME_CONTRACT
    assert 'harness/owncam_memory_time.py' in bundle['runtime_files_sha256']
