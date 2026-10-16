import signal

import pytest

from scripts.sim_cli import blocked_cleanup_signals


def test_cleanup_without_posix_signal_mask(monkeypatch):
    monkeypatch.delattr(signal, 'pthread_sigmask', raising=False)
    with blocked_cleanup_signals({signal.SIGINT, signal.SIGTERM}):
        pass


def test_cleanup_restores_posix_mask_after_exception(monkeypatch):
    calls = []
    monkeypatch.setattr(signal, 'SIG_BLOCK', 0, raising=False)
    monkeypatch.setattr(signal, 'SIG_SETMASK', 2, raising=False)

    def mask(how, signals):
        calls.append((how, signals))
        return {'previous'}

    monkeypatch.setattr(signal, 'pthread_sigmask', mask, raising=False)
    with pytest.raises(RuntimeError):
        with blocked_cleanup_signals({'requested'}):
            raise RuntimeError('test')
    assert calls == [(0, {'requested'}), (2, {'previous'})]
