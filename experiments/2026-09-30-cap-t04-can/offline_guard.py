"""T04 local regression guard: no physics, renderer, model or network calls."""
import importlib.abc
import sys


COUNTS = dict(forbidden_imports=0, network_attempts=0)


class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'glfw', 'torch', 'openai', 'anthropic'}:
            COUNTS['forbidden_imports'] += 1
            raise RuntimeError('T04 offline guard forbids import: ' + fullname)


def offline_audit(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        COUNTS['network_attempts'] += 1
        raise RuntimeError('T04 offline guard forbids network')


sys.meta_path.insert(0, OfflineOnly())
sys.addaudithook(offline_audit)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line('T04 offline guard: ' + repr(COUNTS))
