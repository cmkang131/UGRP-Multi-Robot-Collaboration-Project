"""Opt-in pytest guard for the PR #240 nonphysical contract suite (-p ...)."""
import socket

COUNTS = dict(physical_step_attempts=0, real_vision_worker_attempts=0, network_attempts=0)


def pytest_sessionstart(session):
    import mujoco
    from harness.vision_loc_client import VisionWorkerClient

    def forbidden_step(*args, **kwargs):
        COUNTS['physical_step_attempts'] += 1
        raise AssertionError('This suite forbids MuJoCo physical stepping')

    for name in ('mj_step', 'mj_step1', 'mj_step2'):
        setattr(mujoco, name, forbidden_step)
    original = VisionWorkerClient.__init__

    def fake_worker_only(self, cfg, *args, **kwargs):
        if kwargs.get('argv') is None:
            COUNTS['real_vision_worker_attempts'] += 1
            raise AssertionError('This suite forbids a real vision model worker')
        return original(self, cfg, *args, **kwargs)

    VisionWorkerClient.__init__ = fake_worker_only

    def forbidden_network(*args, **kwargs):
        COUNTS['network_attempts'] += 1
        raise AssertionError('This suite forbids network calls')

    socket.socket.connect = socket.socket.connect_ex = forbidden_network


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line('Nonphysical suite guard: ' + repr(COUNTS))
