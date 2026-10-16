"""Default-off full-control-period CUDA graph; identical physics work.

Basis: MJWarp official Graph capture guidance and testspeed's unroll. The
exclusive gcp4 baseline submits 25 copies of a 16-step graph each 0.1 SIM s;
the host launch loop occupies 5.65 s of the 6.17 s event interval for
0.3 SIM s (overlap is unknown). Reducing launch count is a hypothesis.
Capture the existing 400 commands/steps once, without changing dt, solver,
NoSlip, command tape, or the frequency of controller/render/evaluation calls.
"""
import hashlib
import inspect


def capture_period(transport):
    wp, mjw = transport.wp, transport.mjw
    steps = transport.control_steps
    previous = dict(chunk=transport.graph_chunk, repeats=transport.graph_repeats)
    if steps != previous['chunk'] * previous['repeats']:
        raise ValueError('physics work must equal the full control period')
    with wp.ScopedCapture() as capture:
        for _ in range(steps):
            wp.launch(transport.command_kernel, dim=(transport.n, transport.m.nu),
                      inputs=[transport.tape, transport.graph_tick, transport.wd.ctrl])
            mjw.step(transport.wm, transport.wd)
            wp.launch(transport.advance_kernel, dim=1, inputs=[transport.graph_tick])
    transport.graph = capture.graph
    transport.graph_chunk, transport.graph_repeats = steps, 1
    transport.capacities.update(graph_chunk=steps, graph_repeats=1)
    return dict(profile='warp9_full_period_graph_v1', previous=previous,
                control_steps=steps, launches_per_period=1,
                basis='official CUDA graph capture; same integer control_steps, no physics setting changes')


def capture_trace(transport):
    """Pinned official EventTracer in capture only; no state advance.

    CUDA events in a repeated graph are overwritten on each replay. Report the
    last chunk only, never multiply it into a purported whole-period profile.
    The pinned tracer resets its module stack on exit; retain that event tree
    by reference and read completed events without changing module globals.
    """
    from mujoco_warp._src import warp_util
    wp, mjw = transport.wp, transport.mjw
    with warp_util.EventTracer():
        with wp.ScopedCapture() as capture:
            for _ in range(transport.graph_chunk):
                wp.launch(transport.command_kernel, dim=(transport.n, transport.m.nu),
                          inputs=[transport.tape, transport.graph_tick, transport.wd.ctrl])
                mjw.step(transport.wm, transport.wd)
                wp.launch(transport.advance_kernel, dim=1, inputs=[transport.graph_tick])
        transport._warp9_trace_events = warp_util._STACK
    transport.graph = capture.graph
    return dict(profile='warp9_physics_event_trace_v1',recorded_steps=transport.graph_chunk,
                scope='last replayed graph chunk; intrusive CUDA event intervals, nested rows overlap',
                upstream_tracer_sha256=hashlib.sha256(inspect.getsource(warp_util.EventTracer).encode()).hexdigest())


def trace_summary(transport):
    rows=[]
    def visit(tree,path):
        for name,(events,children) in tree.items():
            key=path+'/'+name
            elapsed=[transport.wp.get_event_elapsed_time(a,b)/1000 for a,b in events]
            rows.append(dict(path=key,calls=len(elapsed),device_event_s=sum(elapsed)))
            visit(children,key)
    visit(transport._warp9_trace_events,'')
    return dict(audit=transport.warp9_trace_audit,rows=rows)
