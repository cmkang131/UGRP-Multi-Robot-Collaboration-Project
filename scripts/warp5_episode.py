"""Isolated legacy controller lanes; scheduling adapters, no policy rewrite."""
from __future__ import annotations
import hashlib,importlib.util,json,sys,os
from pathlib import Path
from scripts.warp5_batch import transform_runner


def owned(name):return name.split('.')[0] in ('harness','sim','scripts','markerless_probe','height_free_wall','ego_wall_map','self_mask')


class Lane:
    """Each generator retains its own legacy module globals and monkeypatches."""
    def __init__(self,factory,source):
        self.factory,self.source=factory,str(source);self.modules={};self.generator=None;self.closed=False
    def invoke(self,method):
        parent={k:v for k,v in sys.modules.copy().items() if owned(k)};search=sys.path[:]
        try:
            for name in list(sys.modules):
                if owned(name):del sys.modules[name]
            sys.modules.update(self.modules);sys.path.insert(0,self.source)
            if self.generator is None:self.generator=self.factory()
            return getattr(self.generator,method)()
        finally:
            self.modules={k:v for k,v in sys.modules.copy().items() if owned(k)}
            for name in list(sys.modules):
                if owned(name):del sys.modules[name]
            sys.modules.update(parent);sys.path[:]=search
    def __next__(self):return self.invoke('__next__')
    def close(self):
        if self.generator is not None and not self.closed:
            try:self.invoke('close')
            finally:self.closed=True


class Bridge:
    def __init__(self,host):self.host=host;self.context=None;self.ast_audit=None
    def setup_carry(self,scope):
        w=scope['world'];rid=scope['rid']
        self.context=dict(kind='setup',world=w,ports={rid:scope['port']},port=scope['port'],
            rid=rid,gids=scope['gids'],finger_ids=scope['finger_ids'],origin=float(w.data.time))
        return self.context
    def setup_selfmap(self,backend):
        w=backend.world;m=w.model;rid=backend.bundle['task']['robot_id']
        ids=[i for i in range(m.ngeom) if (m.geom(i).name or '').startswith('cargo_box_') and m.geom_contype[i]]
        if not ids:raise ValueError('selfmap evaluation cargo geometry missing')
        fingers={m.geom(rid+'__'+s+'_finger').id:i for i,s in enumerate(('left','right'))}
        self.context=dict(kind='setup',world=w,ports=backend.ports,port=backend.ports[rid],rid=rid,
            gids=ids[:1],finger_ids=fingers,origin=float(w.data.time),backend=backend)
        return self.context
    def setup_e2e(self,backend):
        w=backend.world;m=w.model
        ids=[i for i in range(m.ngeom) if (m.geom(i).name or '').startswith('cargo_') and m.geom_contype[i]]
        fingers={m.geom('r1__'+s+'_finger').id:i for i,s in enumerate(('left','right'))}
        self.context=dict(kind='setup',world=w,ports=backend.ports,port=backend.ports['r1'],rid='r1',
            gids=ids[:1],finger_ids=fingers,origin=float(w.data.time),backend=backend)
        return self.context


def prepare_modules(host,active_robot='r1'):
    from harness.warp5_perception import install as perception_install
    perception_install()
    from harness.warp7_perception import install as warp7_perception_install
    warp7_perception_install()
    from sim import masterpi_drive_friction_v7 as factory
    from sim import reloc16_scene
    from scripts import grasp_act_host
    original=factory.build_world
    def build(scene,*a,**kw):
        kw['render']=False
        sleep=os.environ.get('UGRP_WARP7_NATIVE_SLEEP','off')
        if sleep not in ('off','on_v1'):raise ValueError('UNKNOWN_WARP7_NATIVE_SLEEP')
        if sleep=='on_v1':
            from scripts.warp_act_core import sleep_scene_xml
            transform,setup=scene.robot_transform,scene.setup
            scene.robot_transform=lambda xml,**options:sleep_scene_xml(transform(xml,**options),active_robot)
            def sleeping_setup(world):
                # Exact existing shared Transport.make_world sleep setup:
                # native wake sentinel, ordinary setup, then its .4s folded
                # quiet settle. No body is artificially fixed; contacts wake it.
                world.data.qfrc_applied[:]=-0.0;setup(world);world.data.qfrc_applied[:]=0.0
                for _ in range(round(.4/world.model.opt.timestep)):world._physics_step_for(world.robot(active_robot))
            scene.setup=sleeping_setup
        return original(scene,*a,**kw)
    factory.build_world=build
    # Validate model dressing as before; native GL texture-state calls are
    # inapplicable to the new renderer. No GL owner/thread is created.
    def configure(world,profile):
        if profile!=reloc16_scene.PROFILE:return None
        from sim.scene_contrast_v5 import verify_model
        return dict(scene=verify_model(world.model,profile),camera_quality=dict(renderer='MJWarp',
            native_GL_disabled=True,requested_quality='no_mip_v1',qualification='see separate paired88 audit'))
    reloc16_scene.configure_world=configure
    grasp_act_host.identity=lambda execution_host:dict(host)


def make_carry(source,plan,out,host,kwargs):
    bridge=Bridge(host)
    def factory():
        prepare_modules(host,plan['robot_id'])
        from scripts import run_solo_grasp_act_teacher as runner
        function,audit=transform_runner(Path(runner.__file__).read_text(),runner.__dict__,bridge,'carry')
        bridge.ast_audit=audit
        return function(plan,Path(out),execution_host='gcp2',**kwargs)
    return Lane(factory,source),bridge


def make_selfmap(source,bundle,out,host):
    bridge=Bridge(host)
    def factory():
        prepare_modules(host,bundle['task']['robot_id'])
        from scripts import run_self_map_diagnostic as runner
        from sim.own_map_closed_loop import PhysicsBackend
        function,audit=transform_runner(Path(runner.__file__).read_text(),runner.__dict__,bridge,'selfmap')
        bridge.ast_audit=audit
        return function(Path(out),bundle,PhysicsBackend)
    return Lane(factory,source),bridge
