import json
import pytest
from scripts.replay_egomap70_overview import tape


def fixture(p,commands):
    q=p/'robots/r3';q.mkdir(parents=True)
    (q/'frames.jsonl').write_text('\n'.join(json.dumps(dict(sim_time=t)) for t in [1.3,1.5,1.7]))
    (q/'commands.jsonl').write_text('\n'.join(json.dumps(r) for r in commands))


def test_replay_boot_clock_and_duplicate_terminal_holds(tmp_path):
    fixture(tmp_path,[dict(t=1.3000000000000178,kind='initial_servo_command',pulses={'1':2000}),
        dict(t=1.3,kind='arm',servo_id=1,pulse=2000),dict(t=1.7,kind='hold'),dict(t=1.7,kind='hold')])
    start,end,boot,group=tape(tmp_path)
    assert (start,end)==(1.3,1.7)
    assert boot==[dict(kind='arm',servo_id=1,pulse=2000)]
    assert group[2]==[dict(kind='hold'),dict(kind='hold')]


def test_replay_rejects_wrong_capture_grid(tmp_path):
    fixture(tmp_path,[dict(t=1.4,kind='hold')])
    with pytest.raises(ValueError,match='5Hz'):tape(tmp_path)
