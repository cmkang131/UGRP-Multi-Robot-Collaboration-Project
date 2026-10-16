"""Legacy hook serialization and host clock v2 seconds; no world or renderer."""
import json
from types import SimpleNamespace as NS

import pytest

from harness import pair_llm_clock as clock
from harness import zone_pair_highpose_refix as hooks
from harness.pair_llm_stop_adapter import StopAdapter, window_violations
from harness.zone_study_contract import ContractViolation
from tests.pair_llm_fakes import offline_only  # noqa: F401


@pytest.mark.parametrize('kind', ['carry_stop_reached', 'relook_result'])
@pytest.mark.parametrize('origin', [0., 1.30025, 2.612345678, 7.00075])
@pytest.mark.parametrize('phase', [0., .00025, .00075, .04975])
@pytest.mark.parametrize('clock_kind', ['float_v1', 'host_v2'])
def test_real_hook_accepts_window_at_arbitrary_origin_and_substep_phase(kind, origin, phase, clock_kind):
    start = origin + 55.2 + phase
    if clock_kind == 'float_v1':
        # Deliberately accumulate float substeps, as the old clock did.
        start = origin + phase + sum(.00025 for _ in range(220800))
    else:
        start = round(1104 * .05, 9) + origin + phase
    ctl = NS(seg=1, rid='r1', log=lambda *a, **kw: None, carry_decision=lambda *a: None)
    end = round(start+10, 6)
    detail = ({'decide_at_s': end, 'latch_until_s': round(end-.2, 6)}
              if kind == 'carry_stop_reached' else {'window_until_s': end})
    hooks.SigmaRefix._hook_emit(ctl, kind, start, **detail)
    raw = json.dumps(ctl.refix_hook_events, sort_keys=True)
    adapter = StopAdapter(NS(robot_id='r1', _pair=NS(controller=ctl)), condition='no_comm', origin_s=origin)
    event, = adapter.poll()
    assert adapter.window.on_event(event, origin_s=origin)
    opened = adapter.window.current['opened_at_sim_s']
    deadline = clock.relative(end, origin)
    assert adapter.window.current['decide_at_sim_s'] == deadline
    assert abs(opened-clock.relative(start, origin)) <= .000050501
    assert not window_violations(adapter.window.snapshot(opened), opened)
    assert adapter.window.is_open(clock.seconds(clock.ticks(deadline)-1))
    assert not adapter.window.is_open(deadline)
    assert json.dumps(ctl.refix_hook_events, sort_keys=True) == raw  # original evidence preserved


def test_quantization_decode_does_not_extend_deadlines_or_admit_long_windows():
    for start in (55.2, 55.20025):
        row = {'sim_s': start, 'decide_at_s': start+10.001, 'latch_until_s': start+9.8}
        sim_s, detail = clock.hook_times(row)
        from harness.pair_llm_decisions import DecisionWindow
        with pytest.raises(ContractViolation, match='invalid decision window'):
            DecisionWindow().on_event({'event': 'pair_progress', 'sim_s': sim_s,
                                      'detail': {'kind': 'carry_stop_reached', **detail}}, origin_s=0.)


def test_actual_postlook_opener_accepts_review_timestamp():
    class Probe(hooks.SigmaRefix):
        rid, seg = 'r1', 1
        def log(self, *a, **kw): pass
        def _align_fix_checks(self, now): return {'fresh': True}
    ctl = Probe()
    ctl.refix_phase = 'looking'
    ctl.refix_look = {'window': None, 'stop': 1, 'decisions': []}
    ctl.port = NS(own=NS(last_report=NS(std_xy_m=.025, std_yaw_rad=.01)))
    ctl._align_relook_return(55.20025, True)
    a = StopAdapter(NS(robot_id='r1', _pair=NS(controller=ctl)), condition='peer_nl', origin_s=1.30025)
    event, = a.poll()
    assert a.window.on_event(event, origin_s=a.origin_s)
    assert a.window.current['opened_at_sim_s'] == 53.9
    assert a.window.current['decide_at_sim_s'] == 63.9


@pytest.mark.parametrize('origin', [1.30025, 2.612345678, 7.00075])
def test_frame_and_window_use_same_origin_precision(origin):
    import base64
    import hashlib
    from harness.pair_llm_dispatch import PairLink
    own = NS(robot_id='r1')
    link = PairLink(NS(actors={'r1': own}), 'r1', origin_s=origin)
    absolute = origin + 55.20025
    image = b'fake own frame bytes; never decoded'
    link.observe({'robot_id': 'r1', 'camera': 'robot_cam', 'frame_id': 1, 'sim_time': absolute,
                  'image': base64.b64encode(image).decode(), 'sha256': hashlib.sha256(image).hexdigest()})
    frame = link.frame_at(link.clock())
    assert frame is not None and frame.t == link.clock() == 55.20025
