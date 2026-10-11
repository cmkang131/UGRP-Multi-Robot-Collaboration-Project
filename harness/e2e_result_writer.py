"""Durable partial/final results, including repeated shutdown signals."""
import json
import os
from pathlib import Path
import signal
import tempfile


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Finalizer:
    def __init__(self, out, result):
        self.out, self.result = Path(out), result
        self.finalizing = False
        self.previous = {}
        result.update(finalization_complete=False, shutdown_signals=[], finalization_errors=[])
        self.checkpoint()

    def checkpoint(self):
        write(self.out / 'result.json', self.result)
        write(self.out / 'summary.json', self.result)

    def signal(self, signum, frame):
        self.result['shutdown_signals'].append(signum)
        if not self.finalizing:
            raise KeyboardInterrupt('SIGNAL_' + signal.Signals(signum).name)

    def install(self):
        for s in (signal.SIGINT, signal.SIGTERM):
            self.previous[s] = signal.signal(s, self.signal)

    def attempt(self, name, callback):
        try:
            return callback()
        except BaseException as exc:
            self.result['finalization_errors'].append(dict(step=name, type=type(exc).__name__, message=str(exc)))
            self.result.update(status='HOST_ERROR', E2E_success=False)
        finally:
            self.checkpoint()

    def finish(self):
        self.result['finalization_complete'] = True
        self.checkpoint()
        for s, previous in self.previous.items():
            signal.signal(s, previous)
