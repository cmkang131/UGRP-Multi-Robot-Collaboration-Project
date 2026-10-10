"""Inject a static route at the real, captured OwnLink submission boundary.

S3 replaces team.start with a claim dispatcher after capturing the executable
submit callback. Keep recovery/DEV/heading/vision wrappers and their closures;
replace only make_plan in the endpoint factory's already-private namespace.
"""
import inspect
import sys


def planner_functions(callback, seen=None):
    seen = set() if seen is None else seen
    fn = callback.__func__ if inspect.ismethod(callback) else callback
    if not inspect.isfunction(fn) or id(fn) in seen:
        return []
    seen.add(id(fn))
    if 'make_plan' in fn.__code__.co_names and 'make_plan' in fn.__globals__:
        if fn.__globals__ is vars(sys.modules[fn.__module__]):
            raise ValueError('route injection requires an instance-private planner namespace')
        return [fn]
    closure = inspect.getclosurevars(fn).nonlocals
    return [leaf for name in ('start', 'inner', 'submit') if name in closure
            for leaf in planner_functions(closure[name], seen)]


def configure(runtime, route, transform, *, e2e_own_inputs_v1='off'):
    from harness.e2e_own_inputs import enabled
    if enabled(e2e_own_inputs_v1):
        raise ValueError('E2E_STATIC_ROUTE_OVERLAY_FORBIDDEN: use s3_inputs for planner/guard/provider')
    leaves = []
    for rid in ('r1', 'r2'):
        found = planner_functions(runtime.links[rid].submit)
        if len(found) != 1:
            raise ValueError('own submit must contain exactly one private pair planner')
        if found[0] not in leaves:
            leaves.append(found[0])
    # Resolve both chains before modifying anything; no partial injection.
    for fn in leaves:
        old = fn.__globals__['make_plan']
        def planner(static, *args, old=old, **kwargs):
            return transform(old(static, *args, **kwargs), static, route)
        fn.__globals__['make_plan'] = planner
    return runtime
