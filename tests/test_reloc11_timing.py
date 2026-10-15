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
