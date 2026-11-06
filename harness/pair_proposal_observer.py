"""Optional observer for the existing pair audit sink; never alters control.

Snapshot is after controller.propose and before issue clears proposals. It
captures a command candidate, not an entire ACT chunk or environment effect.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sys


def _copy(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


class AtomicStatus:
    """Publish only after a complete flush/fsync/close; never expose a torn update."""
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('x', encoding='utf-8') as stream:
            json.dump({'finished': False, 'complete': False, 'reason': 'not finalized'}, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def publish(self, value):
        fd, name = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, sort_keys=True, allow_nan=False)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            # A flush OR close failure skips replacement and retains prior state.
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)  # our exclusive temporary file only

    def close(self):
        pass  # no persistent file descriptor


class ProposalObserver:
    def __init__(self, controller, *, enabled=False, source_controller=None,
                 sink=None, expected_source_sha256=None, status_stream=None):
        if type(enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        self._controller = controller
        self._source = source_controller
        self._sink = sink
        self.enabled = enabled
        self.capture_attempts = 0
        self.captured_ticks = 0
        self.expected_robot_candidates = 0
        self.captured_robot_candidates = 0
        self.status_write_failures = 0
        self._status_stream = status_stream
        self._finished = False
        self.capture_failures = 0
        self.last_capture_error = None
        self.source_sha256 = None
        if enabled:
            if source_controller is None or sink is None or not expected_source_sha256:
                raise ValueError('explicit source controller, existing sink and source pin required')
            if controller is not source_controller and getattr(controller, '_controller', None) is not source_controller:
                raise ValueError('observer/source controller association mismatch')
            module = sys.modules[type(source_controller).__module__]
            path = Path(module.__file__).resolve()
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected_source_sha256:
                raise ValueError('controller source pin mismatch')
            if not isinstance(source_controller.proposals, dict):
                raise ValueError('controller proposal mapping required')
            self.source_sha256 = actual

    def __getattr__(self, name):
        return getattr(self._controller, name)

    def propose(self, now, robots):
        result = self._controller.propose(now, robots)
        if self.enabled:
            self.capture_attempts += 1
            self.expected_robot_candidates += len(result)
            try:
                # Build the complete independent record before writing once.
                if set(result) != set(self._source.proposals):
                    raise ValueError('proposal/result robot sets differ')
                snapshots = {}
                for rid, (proposal, done, previous) in self._source.proposals.items():
                    obs = result[rid]['observation']
                    if obs['robot_id'] != rid or obs['t'] != now or type(done) is not bool:
                        raise ValueError('proposal observation identity/time/type mismatch')
                    barrier = self._source.barriers[rid]
                    if type(barrier.blocked) is not bool:
                        raise ValueError('blocked must be boolean')
                    snapshots[rid] = {'sample_id': obs['sample_id'],
                        'episode_id': self._source.inputs[rid].episode_id, 'observation_digest': _digest(obs),
                        'proposal': _copy(proposal), 'proposal_digest': _digest(proposal),
                        'done': done, 'previous': _copy(previous),
                        'previous_digest': _digest(previous),
                        'blocked': barrier.blocked, 'stage': result[rid]['stage']}
                self._sink.write({'kind': 'raw_proposal_snapshot', 't': now,
                    'controller_source_sha256': self.source_sha256,
                    'semantics': 'candidate before issue; not issued/applied/acknowledged',
                    'robots': snapshots})
                self.captured_ticks += 1
                self.captured_robot_candidates += len(snapshots)
            except Exception as exc:
                # Observation failure never changes the result or control flow.
                # Counter is out-of-band; caller must not claim complete capture.
                self.capture_failures += 1
                self.last_capture_error = type(exc).__name__
            self._persist_status()
        return result

    def capture_status(self):
        return {'kind': 'proposal_capture_summary', 'run_id': getattr(self._sink, 'run_id', None),
                'controller_source_sha256': self.source_sha256, 'finished': self._finished,
                'attempted_ticks': self.capture_attempts, 'captured_ticks': self.captured_ticks,
                'failed_ticks': self.capture_failures,
                'expected_robot_candidates': self.expected_robot_candidates,
                'captured_robot_candidates': self.captured_robot_candidates,
                'last_capture_error': self.last_capture_error,
                'status_write_failures': self.status_write_failures,
                'complete': self._finished and self.capture_attempts > 0 and self.capture_failures == 0
                            and self.status_write_failures == 0
                            and self.capture_attempts == self.captured_ticks}

    def _persist_status(self):
        if self._status_stream is not None:
            try:
                stream = self._status_stream
                if hasattr(stream, 'publish'):
                    stream.publish(self.capture_status())
                    return
                text = json.dumps(self.capture_status(), sort_keys=True, allow_nan=False) + '\n'
                stream.seek(0)
                stream.write(text)
                stream.truncate()
                stream.flush()
            except Exception:
                self.status_write_failures += 1

    def finish(self):
        if not self.enabled or self._finished:
            return
        self._finished = True
        self._persist_status()
        try:
            summary = self.capture_status()
            summary.pop('run_id', None)  # supplied by the existing sink envelope
            self._sink.write(summary)
        except Exception:
            # The independent status artifact remains the authority on missing
            # snapshot rows when the shared sink cannot accept a summary.
            pass
