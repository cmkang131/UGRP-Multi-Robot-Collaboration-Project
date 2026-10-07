"""Exact observation time boundary; no environment episode or B threshold tuning."""
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'experiments/2026-10-07-mapfree-collision-monitor/code/integer_episode.py'
spec=importlib.util.spec_from_file_location('integer_episode',path)
clock=importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)


def test_clock_has_exact_three_second_gap_for_entire_budget():
    ts=[clock.observation_time(i) for i in range(300)]
    assert ts[0]==2. and ts[-1]==899.
    assert all(b-a==3. for a,b in zip(ts,ts[1:]))
    assert all(clock.control_end_time(i,9)+2==clock.observation_time(i+1) for i in range(299))
    # Original unrounded +=.1 causes the observed strict-gap break.
    old=2.;gaps=[]
    for _ in range(299):
        prior=old
        for _ in range(10):old+=.1
        old+=2.
        gaps.append(old-prior)
    assert any(g>3. for g in gaps)
    # A genuinely late frame remains late; no 3s threshold widening/epsilon.
    assert clock.observation_time(86)+.1-clock.observation_time(85)>3.
