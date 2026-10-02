"""Scoped f476e61f re-review; run with 352b in the candidate archive.

No physics, rendering, model calls, shared outputs or real host locks.
"""
import json
import re
import shlex
import sys

import pytest

pytest.importorskip('harness.zone_final_pair_heldout')
from tests import test_review_352b as previous
from tests.test_zone_final_pair_v3 import offline_only
from sim import workflow_manager as wm

HEAD = 'f476e61ff0bbfc264533aa01248314601a705118'
MAPS = ('zone_wide_corridor_final_v3', 'zone_wide_door_geometry_v3')


@pytest.mark.parametrize('map_id', MAPS)
def test_original_documentation_counterexample_now_passes(tmp_path, capsys, monkeypatch, map_id):
    # Call the original body directly: the old strict-xfail mark is not applied.
    monkeypatch.setattr(previous, 'HEAD', HEAD)
    previous.test_documented_direct_preview_actually_accepts_both_maps(tmp_path, capsys, map_id)
    assert not (tmp_path / 'unused').exists()


def documented_flags(map_id, output):
    text = (previous.c.ROOT / 'PHYSICS_HANDOFF.md').read_text()
    block = re.search(r'```bash\n(.*?)\n```', text, re.S).group(1)
    lines = [shlex.split(line) for line in block.replace('\\\n', ' ').splitlines()
             if ' -m scripts.sim_cli workflow run ' in line and map_id in line]
    assert len(lines) == 1
    words = lines[0]
    i = words.index('scripts.sim_cli')
    assert words[i + 1:i + 5] == ['workflow', 'run', 'zone-final-pair-heldout-v90', '--']
    flags = [HEAD if word == '$FINAL_SHA' else word for word in words[i + 5:]]
    assert flags[flags.index('--output') + 1] == '$RUN_ROOT/' + map_id
    flags[flags.index('--output') + 1] = str(output)
    return flags


@pytest.mark.parametrize('map_id', MAPS)
@pytest.mark.parametrize('check', ('calibration-fine', 'calibration-loaded'))
@pytest.mark.parametrize('execute', (False, True))
def test_documented_workflow_refuses_fine_loaded_before_host_or_output(
        tmp_path, monkeypatch, map_id, check, execute):
    output = tmp_path / 'must-not-exist'
    flags = documented_flags(map_id, output)
    flags[flags.index('--check') + 1] = check
    if not execute:
        flags.remove('--execute')
    monkeypatch.setitem(sys.modules, 'sim.final_pair_heldout', None)
    monkeypatch.setattr(previous.run, 'check_source',
                        lambda _: pytest.fail('host admission must not be reached'))
    plan = wm.plan(previous.c.ROOT, 'zone-final-pair-heldout-v90', flags)
    assert plan['command'][1:3] == ['-m', 'scripts.run_final_pair_heldout']
    with pytest.raises(ValueError, match='v90 requires unloaded collection'):
        previous.run.main(plan['command'][3:])
    assert not output.exists()


@pytest.mark.parametrize('map_id', MAPS)
def test_documented_workflow_refuses_reused_output(tmp_path, map_id):
    output = tmp_path / 'existing'
    output.mkdir()
    sentinel = output / 'preserve.json'
    sentinel.write_text(json.dumps({'original': True}))
    with pytest.raises(FileExistsError, match='workflow output already exists'):
        wm.plan(previous.c.ROOT, 'zone-final-pair-heldout-v90', documented_flags(map_id, output))
    assert json.loads(sentinel.read_text()) == {'original': True}
