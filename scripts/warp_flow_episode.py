"""Scheduling-only adaptation of exact frozen beampair6 sources.

No teacher action, perception, threshold or success expression is rewritten.
Two AST edits replace the runner call with yield-from and its nested advance
loop with the shared transport barrier. Every lane owns its imported modules;
switching a lane never leaves its monkeypatches installed in another lane.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import sys

ADAPTER_SHA = '08f129213031255dd188e20df832bb6714dfca9a'
TEACHER_SHA = '26f84d0f0ada1c33473c83cca2d3415ce51bd247'


def owned(name):
    return name.split('.')[0] in ('harness', 'sim', 'scripts')


def replace_modules(values):
    for name in list(sys.modules):
        if owned(name):
            del sys.modules[name]
    sys.modules.update(values)


class Lane:
    def __init__(self, factory, source):
        self.factory, self.source = factory, str(source)
        self.modules, self.generator = {}, None
        self.closed = False

    def invoke(self, method):
        parent = {k: v for k, v in sys.modules.copy().items() if owned(k)}
        search = sys.path[:]
        try:
            replace_modules(self.modules)
            sys.path.insert(0, self.source)
            if self.generator is None:
                self.generator = self.factory()
            return getattr(self.generator, method)()
        finally:
            self.modules = {k: v for k, v in sys.modules.copy().items() if owned(k)}
            replace_modules(parent)
            sys.path[:] = search

    def __next__(self):
        if self.closed:
            raise StopIteration
        return self.invoke('__next__')

    def close(self):
        if self.generator is not None and not self.closed:
            try:
                self.invoke('close')
            finally:
                self.closed = True


def compile_function(text, name, namespace, *, runner=False):
    """Fail closed when the frozen function no longer has the expected shape."""
    tree = ast.parse(text)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    edits = {'advance_definition': 0, 'advance_call': 0, 'runner_call': 0}

    class Rewrite(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if runner and node is not function and node.name == 'advance':
                edits['advance_definition'] += 1
                node.body = ast.parse('yield from __warp2_bridge__.advance(world, ports, scene, target)').body
                return node
            return self.generic_visit(node)

        def visit_Call(self, node):
            self.generic_visit(node)
            if runner and isinstance(node.func, ast.Name) and node.func.id == 'advance':
                edits['advance_call'] += 1
                return ast.copy_location(ast.YieldFrom(value=node), node)
            if (not runner and isinstance(node.func, ast.Attribute) and node.func.attr == 'run'
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == 'runner'):
                edits['runner_call'] += 1
                node.func = ast.Attribute(value=ast.Name(id='__warp2_bridge__', ctx=ast.Load()),
                                          attr='execute_runner', ctx=ast.Load())
                node.args.insert(0, ast.Name(id='runner', ctx=ast.Load()))
                return ast.copy_location(ast.YieldFrom(value=node), node)
            return node

    Rewrite().visit(function)
    expected = {'advance_definition': 1, 'advance_call': 2, 'runner_call': 0} if runner else {
        'advance_definition': 0, 'advance_call': 0, 'runner_call': 1}
    if edits != expected:
        raise ValueError(f'frozen scheduling shape changed: {edits} != {expected}')
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(module, '<warp2-frozen-scheduling-only>', 'exec'), namespace)
    return namespace[name], dict(edits=edits, source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        transformed_ast_sha256=hashlib.sha256(ast.dump(module, include_attributes=False).encode()).hexdigest())


class Bridge:
    def __init__(self, hooks, index):
        self.hooks, self.index = hooks, index
        self.context = None
        self.transforms = []

    def execute_runner(self, runner, *args, **kwargs):
        # Change only how the frozen world is advanced and rendered. The original
        # factory, scene setup, camera binding and native actuator objects remain.
        from sim import masterpi_drive_friction_v7 as factory
        original = factory.build_world
        def build(*a, **kw):
            kw['render'] = self.hooks.native_render
            return original(*a, **kw)
        factory.build_world = build
        namespace = runner.__dict__.copy()
        namespace['__warp2_bridge__'] = self
        function, audit = compile_function(Path(runner.__file__).read_text(), 'run', namespace, runner=True)
        self.transforms.append(audit)
        try:
            return (yield from function(*args, **kwargs))
        finally:
            factory.build_world = original

    def advance(self, world, ports, scene, target):
        if self.context is None:
            inst = next(c for c in scene.cargo if c.item_id == 'beam_1')
            gids = [world.model.geom(inst.geom(p.name)).id for p in inst.spec().parts if p.collision]
            fingers = {world.model.geom(f'{rid}__{side}_finger').id: 2*j+k
                for j, rid in enumerate(ports) for k, side in enumerate(('left', 'right'))}
            self.context = dict(kind='setup', world=world, ports=ports, gids=gids,
                finger_ids=fingers, camera_size=(320, 240), origin=float(world.data.time))
            self.context['scene_xml_path'] = self.output/'raw/scene.xml'
            if not self.hooks.native_render:
                from scripts.cargo_formation_teacher import FormationTeacher
                def forces(holder):
                    return {rid: tuple(self.hooks.forces(self.index, world.model, world.data, set(gids),
                        {g: k % 2 for g, k in fingers.items() if k // 2 == j}))
                        for j, rid in enumerate(ports)}
                FormationTeacher.finger_forces = forces
                def jpeg(*, robot_id='r1', camera='robot_cam', quality=82):
                    if camera != 'robot_cam' or robot_id not in ports:
                        raise ValueError('own active robot camera only')
                    return self.hooks.capture(self.index, world, robot_id)
                world.render_jpeg = jpeg
                # search23 profile disables top recording in the frozen runner.
                def reject_top(*a, **kw):
                    raise RuntimeError('unexpected top render in warp2 beampair profile')
                world.render_team_jpeg = reject_top
            yield self.context
        while float(world.data.time) < target-1e-8:
            if world.data.eq_active.any():
                raise RuntimeError('WELD_ACTIVE')
            if target-float(world.data.time) < .1-1e-8:
                raise RuntimeError('frozen pair advance must use the existing 0.1 SIM second grid')
            self.hooks.record_state(self.index, round(float(world.data.time)*10), world)
            yield dict(kind='step', target=target)


def make_lane(adapter_source, teacher_source, plan, out, hooks, index, cap_s):
    bridge = Bridge(hooks, index)
    bridge.output = Path(out)
    def factory():
        path = Path(adapter_source)/'scripts/run_beampair1.py'
        spec = importlib.util.spec_from_file_location(f'_warp2_adapter_{index}', path)
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        namespace = adapter.__dict__.copy()
        namespace['__warp2_bridge__'] = bridge
        # The frozen adapter admits only the old CPU machine. This new caller
        # already verified real project/instance/machine metadata (including L4).
        # Keep truthful identity; do not rename L4 as the original n4 host.
        namespace['gcp2_identity'] = lambda identity: dict(hooks.host, provider='gcp',
            schema='ugrp.grasp_act.host.v1', cpu_count=len(os.sched_getaffinity(0)))
        function, audit = compile_function(path.read_text(), 'run', namespace)
        bridge.transforms.append(audit)
        return function(plan, Path(out)/'raw', Path(teacher_source), mode=adapter.MODE,
            candidate='baseline', cap_s=cap_s, rendezvous='peer_rendezvous_v2',
            approach_repair='beampair_approach_v2', failure_tail=True,
            wall_layer='beampair_wall_clear_v1')
    return Lane(factory, adapter_source), bridge
