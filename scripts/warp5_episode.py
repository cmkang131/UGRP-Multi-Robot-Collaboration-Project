"""Isolated legacy controller lanes; scheduling adapters, no policy rewrite."""
from __future__ import annotations
import hashlib,importlib.util,json,sys
from pathlib import Path
from scripts.warp5_batch import transform_runner


def owned(name):return name.split('.')[0] in ('harness','sim','scripts')


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


def prepare_modules(host):
    from sim import masterpi_drive_friction_v7 as factory
    from sim import reloc16_scene
    from scripts import grasp_act_host
    original=factory.build_world
    def build(*a,**kw):kw['render']=False;return original(*a,**kw)
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
        prepare_modules(host)
        from scripts import run_solo_grasp_act_teacher as runner
        function,audit=transform_runner(Path(runner.__file__).read_text(),runner.__dict__,bridge,'carry')
        bridge.ast_audit=audit
        return function(plan,Path(out),execution_host='gcp2',**kwargs)
    return Lane(factory,source),bridge


def make_selfmap(source,bundle,out,host):
    bridge=Bridge(host)
    def factory():
        prepare_modules(host)
        from scripts import run_self_map_diagnostic as runner
        from sim.own_map_closed_loop import PhysicsBackend
        function,audit=transform_runner(Path(runner.__file__).read_text(),runner.__dict__,bridge,'selfmap')
        bridge.ast_audit=audit
        return function(Path(out),bundle,PhysicsBackend)
    return Lane(factory,source),bridge
