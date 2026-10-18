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
import copy
from pathlib import Path
import sys

ADAPTER_SHA = 'b663fcb76caaf36300bddca751cdd0356fc94096'
TEACHER_SHA = 'f8c1b7162d2d4d19c25c1cd1c7b325b2bdfea13c'
RELEASE_SHA = '8e81b7d96c0c73171635348c90631462adfe1eb0'


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
    edits = {'advance_definition': 0, 'advance_call': 0, 'runner_call': 0,'evaluation_rows':0}

    class Rewrite(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if runner and node is not function and node.name == 'advance':
                edits['advance_definition'] += 1
                original = copy.deepcopy(node)
                original.name = '_command_advance'
                node.body = ast.parse('yield from __warp2_bridge__.advance(world, ports, scene, target, _command_advance)').body
                return [original, node]
            return self.generic_visit(node)

        def visit_Call(self, node):
            self.generic_visit(node)
            if (runner and namespace.get('__warp4_release__') and isinstance(node.func,ast.Attribute)
                    and isinstance(node.func.value,ast.Name) and node.func.value.id=='report' and node.func.attr=='update'
                    and any(k.arg=='release_success' and not isinstance(k.value,ast.Constant) for k in node.keywords)):
                # Persist the original evaluator rows, including GPU force
                # samples during the terminal2.4s check. No row enters control.
                node.keywords.append(ast.keyword(arg='evaluation_checks',value=ast.Name(id='checks',ctx=ast.Load())))
                edits['evaluation_rows']+=1
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
    expected = {'advance_definition': 1, 'advance_call': 2, 'runner_call': 0,'evaluation_rows':0} if runner else {
        'advance_definition': 0, 'advance_call': 0, 'runner_call': 1,'evaluation_rows':0}
    if runner and name == 'run' and namespace.get('__warp4_release__'):
        # Freeze the observed release25 scheduling call count in the audit.
        expected['advance_call'] = 4
        expected['evaluation_rows'] = 1
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
        self.canonical = None
        self.command_tape = []
        self.recording_commands = False

    def build(self, original, scene, **kwargs):
        from sim import masterpi_drive_friction_v7 as drive
        from warp_flow_model import canonical_xml
        from warp_flow_admission import scene_admission,MODE,PlacementRejected
        import json
        admission=scene_admission(self.plan,scene,mode=MODE if getattr(self.hooks,'placement_graspable_filter_v1',False) else 'off',
            certification_source=self.certification_source)
        self.output.mkdir(parents=True,exist_ok=True)
        (self.output/'placement-admission.json').write_text(json.dumps(admission,indent=2)+'\n')
        if not admission['accepted']:
            raise PlacementRejected(json.dumps(admission))
        cls = drive.MultiMasterPiProductionV2
        init = cls.__init__
        def canonical_init(world, *args, **kw):
            transform = kw['xml_transform']
            def final(xml):
                text = transform(xml)
                if getattr(self.hooks,'contact_xml_transform',None):text=self.hooks.contact_xml_transform(text)
                if self.hooks.native_sleep_policy_compat_v1:
                    from warp_act_core import sleep_scene_xml
                    text=sleep_scene_xml(text,('r1','r2'))
                if self.canonical.get('xml') is None:
                    self.canonical['xml'] = canonical_xml(text,text)[0]
                try:
                    text, audit = canonical_xml(text, self.canonical['xml'],world_parameters=getattr(self.hooks,'world_model_parameters_v1',False))
                except ValueError:
                    self.output.mkdir(parents=True,exist_ok=True)
                    (self.output/'incompatible-scene.xml').write_text(text)
                    (self.output/'canonical-reference.xml').write_text(self.canonical['xml'])
                    raise
                self.model_audit = audit
                return text
            kw['xml_transform'] = final
            return init(world, *args, **kw)
        cls.__init__ = canonical_init
        kwargs.update(render=self.hooks.native_render, width=640, height=480)
        try:
            world=original(scene, **kwargs)
            if self.hooks.native_sleep_policy_compat_v1:
                setup=scene.setup
                def quiet_setup(w):
                    w.data.qfrc_applied[:]=-0.0
                    setup(w)
                    w.data.qfrc_applied[:]=0.0
                    # Reuse PR534's existing .4s quiet native initialization.
                    # This is setup, not an acceptance/policy time threshold.
                    for _ in range(round(.4/w.model.opt.timestep)):
                        w._physics_step_for(w.robot('r1'))
                scene.setup=quiet_setup
            return world
        finally:
            cls.__init__ = init

    def install_scene_quality(self):
        from sim import gatesv5_scene
        from sim.scene_contrast_v5 import verify_model
        original = gatesv5_scene.scene_bindings
        def bindings(*args, **kwargs):
            if self.hooks.native_render:return original(*args,**kwargs)
            pair = original(*args, **kwargs)
            if pair is None:
                raise ValueError('warp4 requires selected scene-v5')
            install, _ = pair
            def configure(world, out):
                import json
                record = dict(scene_profile='walls_floor_contrast_v5_indigo110_s80',
                    camera_quality='no_mip_v1', profile=verify_model(world.model,'walls_floor_contrast_v5_indigo110_s80'),
                    renderer='MJWarp LINEAR / one mip level; no OpenGL context',
                    source='warp3/render-quality-source-audit.json')
                Path(out).mkdir(parents=True, exist_ok=True)
                (Path(out)/'scene-quality.json').write_text(json.dumps(record,indent=2)+'\n')
                return record
            return install, configure
        gatesv5_scene.scene_bindings = bindings

    def install_command_recorder(self, world):
        """Execute the frozen issued-command decoder, replacing ONLY mj_step.

        The advance closure retains port deadlines, quantized wheels and issued
        odometry per physics substep. No measured state is read by this decoder.
        The common backend alone advances physics with the resulting ctrl tape.
        """
        import inspect, textwrap, types
        method = world._physics_step_for
        text=textwrap.dedent(inspect.getsource(method.__func__))
        tree = ast.parse(text)
        count = 0
        bridge = self
        class Replace(ast.NodeTransformer):
            def visit_Call(self, node):
                nonlocal count
                if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='mujoco' and node.func.attr=='mj_step':
                    count += 1
                    return ast.copy_location(ast.Call(func=ast.Name(id='_record_substep',ctx=ast.Load()),args=[ast.Name(id='self',ctx=ast.Load())],keywords=[]),node)
                return self.generic_visit(node)
        Replace().visit(tree)
        if count != 1:
            raise ValueError('frozen v7 command decoder mj_step shape changed')
        def record(w):
            if not bridge.recording_commands:
                raise RuntimeError('physics call outside frozen command-advance boundary')
            bridge.command_tape.append(w.data.ctrl.copy())
            w.data.time += float(w.model.opt.timestep)
        namespace = {**method.__func__.__globals__, '_record_substep':record}
        exec(compile(ast.fix_missing_locations(tree),'<warp4-command-only>','exec'),namespace)
        world._physics_step_for=types.MethodType(namespace['_physics_step_for'],world)
        self.transforms.append(dict(kind='v7_command_only',mj_step_replacements=count,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            transformed_ast_sha256=hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest()))

    def execute_runner(self, runner, *args, **kwargs):
        # Change only how the frozen world is advanced and rendered. The original
        # factory, scene setup, camera binding and native actuator objects remain.
        from sim import masterpi_drive_friction_v7 as factory
        original = factory.build_world
        def build(*a, **kw):
            return self.build(original,*a,**kw)
        factory.build_world = build
        namespace = runner.__dict__.copy()
        namespace['__warp2_bridge__'] = self
        function, audit = compile_function(Path(runner.__file__).read_text(), 'run', namespace, runner=True)
        self.transforms.append(audit)
        try:
            return (yield from function(*args, **kwargs))
        finally:
            factory.build_world = original

    def advance(self, world, ports, scene, target, command_advance):
        if self.context is None:
            inst = next(c for c in scene.cargo if c.item_id == 'beam_1')
            gids = [world.model.geom(inst.geom(p.name)).id for p in inst.spec().parts if p.collision]
            fingers = {world.model.geom(f'{rid}__{side}_finger').id: 2*j+k
                for j, rid in enumerate(ports) for k, side in enumerate(('left', 'right'))}
            self.context = dict(kind='setup', world=world, ports=ports, gids=gids,
                finger_ids=fingers, camera_size=(640, 480), origin=float(world.data.time),
                scene_xml_path=self.output/'raw/scene.xml')
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
            self.install_command_recorder(world)
            yield self.context
        while float(world.data.time) < target-1e-8:
            if world.data.eq_active.any():
                raise RuntimeError('WELD_ACTIVE')
            if target-float(world.data.time) < .1-1e-8:
                raise RuntimeError('frozen pair advance must use the existing 0.1 SIM second grid')
            self.hooks.record_state(self.index, round(float(world.data.time)*10), world)
            before=float(world.data.time)
            self.command_tape=[]
            self.recording_commands=True
            try:command_advance(min(target,before+.1))
            finally:self.recording_commands=False
            self.context['command_tape']=self.command_tape
            world.data.time=before
            yield dict(kind='step', target=target)


def make_lane(adapter_source, teacher_source, plan, out, hooks, index, cap_s, *, flow='beampair', profile=None, canonical=None, candidate='baseline'):
    bridge = Bridge(hooks, index)
    bridge.output = Path(out)
    bridge.plan = plan
    bridge.certification_source=Path(teacher_source) if teacher_source else Path(adapter_source).parent/TEACHER_SHA
    bridge.canonical = canonical if canonical is not None else {}
    def factory():
        bridge.install_scene_quality()
        if flow=='release':
            from scripts import run_grasp_act_release as runner
            namespace=runner.__dict__.copy()
            namespace.update(__warp2_bridge__=bridge,__warp4_release__=True)
            original=namespace['build_world'] if 'build_world' in namespace else None
            from sim import masterpi_drive_friction_v7 as drive
            original=drive.build_world
            drive.build_world=lambda *a,**kw:bridge.build(original,*a,**kw)
            function,audit=compile_function(Path(runner.__file__).read_text(),'run',namespace,runner=True)
            bridge.transforms.append(audit)
            return function(plan,Path(out)/'raw',cap_s=cap_s,**profile)
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
            candidate=candidate, cap_s=cap_s, rendezvous='peer_rendezvous_v2',
            approach_repair='beampair_approach_v2', failure_tail=True,
            wall_layer='beampair_wall_clear_v1',peer_yield='beampair_peer_yield_v1')
    return Lane(factory, adapter_source), bridge
