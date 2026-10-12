"""Load experiment `code/` scripts whose sibling modules (common.py, replay.py, ...) share names
across experiment folders. Cached same-named modules from another folder are evicted while the
folder is first on sys.path, then sys.path and sys.modules are restored (no cross-test leakage)."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys


@contextmanager
def code_dir(path):
    path = Path(path)
    names = {p.stem for p in path.glob('*.py')}
    saved = {n: sys.modules.pop(n) for n in list(sys.modules) if n in names}
    sys.path.insert(0, str(path))
    try:
        yield
    finally:
        sys.path.remove(str(path))
        for n in names:
            sys.modules.pop(n, None)
        sys.modules.update(saved)


def load(path, module_name, file_name):
    path = Path(path)
    with code_dir(path):
        spec = importlib.util.spec_from_file_location(module_name, path / file_name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module
