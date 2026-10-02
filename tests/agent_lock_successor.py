"""Compare v91's default lock API with the frozen historical implementation.

Only the explicitly requested SIM-slot tool is a new source successor. Its
historical hash stays in old receipts; production bundles carry the actual hash.
"""
import os
from types import ModuleType
from unittest.mock import patch

from scripts import agent_lock


def assert_default_lock_compatibility(original, tmp_path):
    historical = ModuleType('historical_agent_lock')
    exec(compile(original, '<frozen agent_lock>', 'exec'), historical.__dict__)
    records = []
    with patch('time.time', return_value=12345.), patch('os.getloadavg', return_value=(1., 2., 3.)):
        for index, module in enumerate((historical, agent_lock)):
            root = tmp_path/str(index)
            kwargs = dict(owner='codex', branch='codex/default', purpose='compatibility',
                          pid=os.getpid(), expected_minutes=2)
            acquired = module.acquire(root, **kwargs)
            held = module.status(root)
            errors = []
            for operation in (lambda: module.acquire(root, **kwargs),
                              lambda: module.release(root, owner='claude')):
                try:
                    operation()
                except RuntimeError as exc:
                    errors.append(str(exc))
            assert len(errors) == 2
            released = module.release(root, owner='codex')
            records.append((acquired, held, errors, released,
                            (root/'released.jsonl').read_bytes(), module.status(root)))
    assert records[0] == records[1]
