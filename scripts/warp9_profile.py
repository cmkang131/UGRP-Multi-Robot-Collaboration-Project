"""Opt-in, intrusive phase accounting; never a production speed measurement.

CUDA events delimit device phases, and their completion wait is reported
separately. Compilation/setup samples are reset before measured rollout.
Basis: MJWarp testspeed/_src.cli.unroll and Warp 1.15 event timing APIs.
"""
from contextlib import contextmanager, nullcontext
import ast
import hashlib
import inspect
import textwrap
import time


class Profile:
    def __init__(self, wp):
        self.wp = wp
        self.rows = []

    @contextmanager
    def phase(self, name, *, device=False, nbytes=0, implicit_syncs=0, explicit_syncs=0):
        start = time.perf_counter()
        if device:
            first, last = self.wp.Event(enable_timing=True), self.wp.Event(enable_timing=True)
            self.wp.record_event(first)
        row = dict(phase=name, bytes=int(nbytes), implicit_syncs=implicit_syncs,
                   explicit_syncs=int(device)+explicit_syncs, device_s=None, wait_s=0., status='COMPLETE')
        try:
            yield row
        except BaseException:
            row['status'] = 'HOST_ERROR'
            raise
        finally:
            submitted = time.perf_counter()
            if device:
                self.wp.record_event(last)
                self.wp.synchronize_event(last)
                row['device_s'] = self.wp.get_event_elapsed_time(first, last) / 1000.
            row.update(submit_s=submitted-start, wall_s=time.perf_counter()-start,
                       wait_s=time.perf_counter()-submitted)
            self.rows.append(row)

    def numpy(self, array, *, name='host_readback'):
        with self.phase(name, implicit_syncs=1) as row:
            result = array.numpy()
            row['bytes'] = result.nbytes
            return result

    def summary(self):
        result = {}
        for row in self.rows:
            out = result.setdefault(row['phase'], dict(calls=0, wall_s=0., device_s=0.,
                submit_s=0., wait_s=0., bytes=0, implicit_syncs=0, explicit_syncs=0, errors=0))
            out['calls'] += 1
            out['errors'] += row['status'] != 'COMPLETE'
            for key in ('wall_s', 'device_s', 'submit_s', 'wait_s', 'bytes', 'implicit_syncs', 'explicit_syncs'):
                out[key] += row[key] or 0
        return dict(phases=result, rows=self.rows,
            scope='intrusive phase accounting; synchronization changes overlap; use separate uninstrumented throughput',
            device_time='CUDA event interval, not sum of kernel busy durations')


def phase(owner, name, **kwargs):
    profile = getattr(owner, 'warp9_profile', None)
    return profile.phase(name, **kwargs) if profile else nullcontext()


def exporter(function, readback):
    """Private copy of upstream exporter, replacing only .numpy() calls.

    No installed modules are edited. Each call's CPU reads remain genuine GPU
    arrays. No fields, contact ordering, factorization or evaluation are omitted.
    """
    source = textwrap.dedent(inspect.getsource(function))
    tree = ast.parse(source)
    count = 0

    class Rewrite(ast.NodeTransformer):
        def visit_Call(self, node):
            nonlocal count
            node = self.generic_visit(node)
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'numpy':
                if node.args or node.keywords:
                    raise ValueError('unsupported exporter numpy arguments')
                count += 1
                return ast.copy_location(ast.Call(func=ast.Name(id='__warp9_readback__', ctx=ast.Load()),
                    args=[node.func.value], keywords=[]), node)
            return node

    tree = ast.fix_missing_locations(Rewrite().visit(tree))
    if not count:
        raise ValueError('exporter has no direct device reads')
    namespace = dict(function.__globals__, __warp9_readback__=readback)
    exec(compile(tree, '<warp9-export-accounting>', 'exec'), namespace)
    return namespace[function.__name__], dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        ast_sha256=hashlib.sha256(ast.dump(tree).encode()).hexdigest(), replaced_reads=count)
