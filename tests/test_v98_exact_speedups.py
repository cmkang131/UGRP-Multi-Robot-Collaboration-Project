"""harness.zone_pair_highpose_exact_speedups and scripts/compare_v98_runs.py (no physics run here).

Real-run equivalence (full align_to_carry, 2 baselines + 1 speedup run) is recorded in
experiments/2026-10-05-sim-walltime-monitor/README.md.
"""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from harness import zone_pair_highpose_exact_speedups as sp
from scripts import compare_v98_runs as cmp


class FakePF:
    def __init__(self):
        self.px = np.random.default_rng(0).normal(size=(50, 3))
        self.load = SimpleNamespace(loaded=False)
        self.columns = np.arange(8.)
        self.calls = 0

    def expected(self, px, pose):
        self.calls += 1
        s = float(sum(pose.values())) + (1. if self.load.loaded else 0.)
        return px[:, :1] * 2. + s, px[:, 1:2] - s


def test_memo_returns_identical_values_and_recomputes_on_any_change():
    pf = FakePF()
    ref = FakePF()
    memo = sp.ExpectedMemo(pf)
    pf.expected = memo
    pose = {1: 500, 6: 1500}
    a = pf.expected(pf.px, pose)
    b = pf.expected(pf.px, pose)
    assert memo.misses == 1 and memo.hits == 1
    for x, y, z in zip(a, b, FakePF.expected(ref, ref.px, pose)):
        assert x.tobytes() == y.tobytes() == z.tobytes()
    b[0][:] = 0.                                   # caller mutation must not reach the cache
    assert pf.expected(pf.px, pose)[0].tobytes() == a[0].tobytes()
    pf.px[3, 0] += 1e-12                           # in-place particle change -> miss
    pf.expected(pf.px, pose)
    assert memo.misses == 2
    pf.expected(pf.px, {1: 501, 6: 1500})          # pose change -> miss
    pf.load.loaded = True                          # load change -> miss
    pf.expected(pf.px, {1: 501, 6: 1500})
    assert memo.misses == 4
    other = pf.px.copy()                           # not the filter's own array -> never cached
    pf.expected(other, pose)
    pf.expected(other, pose)
    assert memo.misses == 4 and memo.hits == 2


def test_install_none_is_a_no_op_and_sets_restore():
    from harness import vision_pose_source_highpose as src
    from harness import zone_final_pair_loaded_schedule as sched
    from sim import zone_final_v3_scene as scene
    before = (src.HighPoseSource.__init__, sched.schedule_bytes, scene.build_world)
    rec, undo = sp.install('none')
    assert rec['items'] == [] and (src.HighPoseSource.__init__, sched.schedule_bytes, scene.build_world) == before
    undo()
    rec, undo = sp.install('v98-exact-v1')
    assert sched.schedule_bytes is not before[1] and scene.build_world is not before[2]
    undo()
    assert (src.HighPoseSource.__init__, sched.schedule_bytes, scene.build_world) == before
    with pytest.raises(ValueError):
        sp.install('fast-and-loose')


def _case(root, task_id, frame=b'\xff\xd8jpeg', load=1.0, command=0.1):
    (root / 'robots/r1/rgb').mkdir(parents=True)
    (root / 'robots/r1/rgb/00000.jpg').write_bytes(frame)
    (root / 'robots/r1/commands.jsonl').write_text(json.dumps({'t': 1.3, 'vx': command}) + '\n')
    (root / 'result.json').write_text(json.dumps({'loadavg_start': [load, 1, 1], 'status': 'X'}))
    (root / 'student_record.json').write_text(json.dumps({'pair': [{'status_messages': [{'task_id': task_id, 'seq': 1}]}]}))
    files = sorted(p for p in root.rglob('*') if p.is_file())
    (root / 'artifacts.sha256.json').write_text(json.dumps({str(p.relative_to(root)): cmp.sha(p) for p in files}))


def test_compare_allows_only_listed_key_paths(tmp_path):
    _case(tmp_path / 'a', 'pair-1', load=3.)
    _case(tmp_path / 'b', 'pair-2', load=9.)
    assert cmp.compare(tmp_path / 'a', tmp_path / 'b')['verdict'] == 'IDENTICAL_UP_TO_ALLOWLIST'
    _case(tmp_path / 'c', 'pair-3', frame=b'\xff\xd8jpeG')
    r = cmp.compare(tmp_path / 'a', tmp_path / 'c')
    assert r['verdict'] == 'BEHAVIOUR_DIFFERENT' and 'robots/r1/rgb/00000.jpg' in r['behaviour_differences']
    _case(tmp_path / 'd', 'pair-4', command=0.2)
    r = cmp.compare(tmp_path / 'a', tmp_path / 'd')
    assert r['behaviour_differences'] == ['artifacts.sha256.json', 'robots/r1/commands.jsonl']
