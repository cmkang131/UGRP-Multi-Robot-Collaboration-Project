from types import SimpleNamespace
from harness.reloc11_timing import Timings


def test_wrapper_preserves_result_exception_and_can_be_restored():
    import pytest
    class Source:
        def step(self, value):
            if value < 0:
                raise ValueError('negative')
            return {'value': value}
    source = Source()
    original = source.step
    timing = Timings()
    restore = timing.wrap(source, 'step', 'pf')
    assert source.step(3) == {'value': 3}
    with pytest.raises(ValueError, match='negative'):
        source.step(-1)
    restore()
    assert source.step == original
    result = timing.snapshot(SimpleNamespace(registration=SimpleNamespace(pf=SimpleNamespace(n=2000))))
    assert result['calls'] == {'pf': 2}
    assert result['seconds']['pf'] >= 0 and result['pf_particles'] == 2000


def test_timing_bundle_is_default_off_and_does_not_change_control_options():
    from scripts.run_self_map_diagnostic import bundle
    old = bundle('a'*40, 93571, 90)
    assert old == bundle('a'*40, 93571, 90, reloc11_timing_v1=False)
    timed = bundle('a'*40, 93571, 90, reloc11_timing_v1=True)
    assert timed['options'].pop('reloc11_timing_v1') is True
    assert timed == old


def test_half_rate_keeps_every_selected_frame_and_terminal_time(tmp_path):
    from scripts.run_self_map_diagnostic import bundle, acquire
    from test_self_map_executor import RecordingPlant, controller_factory
    old = bundle('a'*40, 93571, 1.)
    assert old == bundle('a'*40, 93571, 1., reloc11_half_rate_v1=False)
    b = bundle('a'*40, 93571, 1., reloc11_half_rate_v1=True)
    assert b['capture_s'] == .2 and b['recording']['own_rgb_hz'] == 5
    result = acquire(tmp_path/'5hz', b, RecordingPlant, controller_factory=controller_factory)
    assert result['status'] == 'RECORDED' and result['stop_reason'] == 'sim_time_cap'
    assert result['frames'] == result['input_audit']['own_rgb_frames'] == 6
    assert result['rgb_ledger_verified'] and RecordingPlant.instances[-1].now == 2.3
    assert result['invisible_measurements'] == result['held_world_reads'] == 0
