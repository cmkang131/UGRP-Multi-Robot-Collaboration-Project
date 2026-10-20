from copy import deepcopy
from pathlib import Path
import importlib.util
import pytest


def test_adoption_rejects_other_task_root_parent_and_process_group(monkeypatch):
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root/'scripts'))
    spec=importlib.util.spec_from_file_location('act16w_parallel_test',root/'scripts/act16w_record_parallel.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    row=dict(pid=20,state='R',ppid=10,pgid=20,argv=['python','/frozen/record.py','--enabled','--out','/owned/capture'])
    def validate(r):return module.identity(r,script='/frozen/record.py',flag='--out',root='/owned/capture',parent=10)
    assert validate(row)==row
    for change in [dict(ppid=11),dict(pgid=10),dict(state='Z'),dict(argv=['python','/other.py','--enabled','--out','/owned/capture']),dict(argv=['python','/frozen/record.py','--enabled','--out','/foreign/capture']),dict(argv=['python','/frozen/record.py','--enabled','--out'])]:
        with pytest.raises(ValueError):validate({**deepcopy(row),**change})
