"""Exact JSONL buffering and diagnostic host timers; no control feedback."""
import json
import time
from contextlib import contextmanager
from sim.zone_s3_no_prior import PhysicsBackend as Previous
from scripts.run_final_environment_checks import write

OPTION = 'buffered_jsonl_v1'


class PhysicsBackend(Previous):
    def __init__(self, bundle, out, **kwargs):
        self.io_mode = bundle.get('options', {}).get('s3_io', 'off')
        if self.io_mode not in ('off', OPTION):
            raise ValueError('unknown S3 I/O option')
        self.host_timing = {}
        super().__init__(bundle, out, **kwargs)
        if self.io_mode == 'off':
            return
        render = self.world.render_rgb
        def timed_render(*args, **kwargs):
            with self.measure('render_rgb'):
                return render(*args, **kwargs)
        self.world.render_rgb = timed_render

    @contextmanager
    def measure(self, key):
        start = time.perf_counter()
        try:
            yield
        finally:
            row = self.host_timing.setdefault(key, dict(calls=0, wall_s=0.))
            row['calls'] += 1
            row['wall_s'] += time.perf_counter()-start

    def _append(self, relative, value):
        if self.io_mode == 'off':
            return super()._append(relative, value)
        with self.measure('jsonl_append'):
            if relative not in self.streams:
                path = self.out/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                self.streams[relative] = path.open('x', buffering=65536)
            self.streams[relative].write(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')

    def flush(self):
        for stream in self.streams.values():
            if not stream.closed:
                stream.flush()

    def capture(self):
        if self.io_mode == 'off':
            return super().capture()
        with self.measure('capture_including_render_io'):
            return super().capture()

    def advance_to(self, t):
        if self.io_mode == 'off':
            return super().advance_to(t)
        with self.measure('physics_advance'):
            return super().advance_to(t)

    def eval_sample(self):
        if self.io_mode == 'off':
            return super().eval_sample()
        with self.measure('eval_sample_including_io'):
            return super().eval_sample()

    def evaluate(self, *args, **kwargs):
        if self.io_mode == 'off':
            return super().evaluate(*args, **kwargs)
        self.flush()  # referee is a post-loop reader of these same streams
        return super().evaluate(*args, **kwargs)

    def close(self):
        if self.io_mode == 'off':
            return super().close()
        try:
            self.flush()
            super().close()
        finally:
            if hasattr(self, 'out') and self.out.exists():
                write(self.out/'host-timing.json', dict(option=self.io_mode,
                    timers=self.host_timing, nested_timers_not_additive=True,
                    controller_feedback=False, cprofile=False))
