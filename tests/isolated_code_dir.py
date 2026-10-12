"""Load experiment `code/` scripts whose helper modules (common.py, replay.py, ...) share names across
experiment folders. Pytest imports every test module of a shard at collection time, so another
experiment's same-named modules and sys.path entries may already be present. While loading, every
module whose file lives under experiments/ and every experiments/ sys.path entry is set aside (a fresh
interpreter's view), then sys.path and sys.modules are restored exactly (no cross-test leakage)."""
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys

EXPERIMENTS = (Path(__file__).resolve().parents[1] / 'experiments').resolve()


def _under_experiments(location):
    try:
        return Path(location).resolve().is_relative_to(EXPERIMENTS)
    except (TypeError, ValueError, OSError):
        return False


@contextmanager
def code_dir(path):
    path = Path(path).resolve()
    saved_path = list(sys.path)
    saved = {name: module for name, module in sys.modules.items()
             if _under_experiments(getattr(module, '__file__', None) or '')}
    for name in saved:
        del sys.modules[name]
    sys.path[:] = [str(path)] + [p for p in saved_path if not (p and _under_experiments(p))]
    try:
        yield
    finally:
        for name, module in list(sys.modules.items()):
            if _under_experiments(getattr(module, '__file__', None) or ''):
                del sys.modules[name]
        sys.modules.update(saved)
        sys.path[:] = saved_path


def load(path, module_name, file_name):
    path = Path(path)
    with code_dir(path):
        spec = importlib.util.spec_from_file_location(module_name, path / file_name)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module
