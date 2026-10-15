"""Opt-in wall-clock accounting; no observation or control changes."""
from collections import defaultdict
from contextlib import contextmanager
from time import perf_counter


class Timings:
    def __init__(self):
        self.seconds = defaultdict(float)
        self.calls = defaultdict(int)

    @contextmanager
    def measure(self, name):
        started = perf_counter()
        try:
            yield
        finally:
            self.seconds[name] += perf_counter()-started
            self.calls[name] += 1

    def wrap(self, obj, name, category):
        original = getattr(obj, name)
        def measured(*args, **kwargs):
            with self.measure(category):
                return original(*args, **kwargs)
        setattr(obj, name, measured)
        return lambda: setattr(obj, name, original)

    def snapshot(self, mapper):
        pf = getattr(getattr(mapper, 'registration', None), 'pf', None)
        return dict(seconds=dict(self.seconds), calls=dict(self.calls),
                    pf_particles=None if pf is None else pf.n,
                    nested_categories=True,
                    note='control includes feature/PF/geometry; registration includes PF and evidence')


def install(timing, controller):
    """Process-local wrappers, restored before final artifact generation."""
    from harness import self_map_integration as integration
    from harness import selfmap4_geometry as geometry
    mapper = controller.mapper
    restores = [timing.wrap(integration, 'extract', 'feature_extract'),
                timing.wrap(mapper.slam, 'step', 'feature_tracking')]
    if mapper.registration is not None:
        restores += [timing.wrap(mapper.flow, 'step', 'plane_flow'),
                     timing.wrap(geometry, 'observe', 'structure_extract'),
                     timing.wrap(mapper.registration.pf, 'step', 'pf'),
                     timing.wrap(mapper.registration, 'step', 'registration')]
    return restores
