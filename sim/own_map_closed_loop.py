"""Existing egomap34 physics, with write-only sampled contact audit."""
from sim.active_wall_map import PhysicsBackend as Base


class PhysicsBackend(Base):
    def __init__(self, bundle, out, *, seed):
        if bundle['options'].get('render_profile') != 'floor_light_textured_v1':
            super().__init__(bundle, out, seed=seed)
            return
        # The existing backend builds an isolated scene, already light/nearclip
        # wrapped. Dress only that instance after its original XML transform.
        from sim import active_wall_map as host
        from sim.natural_scene_texture import apply, manifest, verify_model, MANIFEST_SHA256
        import xml.etree.ElementTree as ET
        import hashlib
        original = host.make_scene
        def textured(*args, **kwargs):
            base = {**args[0], 'options': {**args[0]['options'], 'render_profile':'floor_light_v1'}}
            scene = original(base, *args[1:], **kwargs)
            inner = scene.transform
            def transform(xml):
                before = inner(xml)
                after = ET.tostring(apply(ET.fromstring(before)), encoding='unicode')
                scene.manifest['natural_scene_texture'] = dict(name='floor_light_textured_v1',
                    manifest_sha256=MANIFEST_SHA256, source_commit='db0a6858f6387e9048d4a37e78bc8eefd2ead484',
                    before_sha256=hashlib.sha256(before.encode()).hexdigest(),
                    after_sha256=hashlib.sha256(after.encode()).hexdigest())
                return after
            scene.transform = transform
            return scene
        manifest()  # Verify pinned assets before building the plant.
        host.make_scene = textured
        try:
            super().__init__(bundle, out, seed=seed)
            self.texture_audit = verify_model(self.world.model)
        except Exception:
            self.close()
            raise
        finally:
            host.make_scene = original

    def eval_sample(self):
        import mujoco
        m,d=self.world.model,self.world.data
        pairs=[]
        for c in d.contact[:d.ncon]:
            names=[mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,int(i)) or '' for i in (c.geom1,c.geom2)]
            if not any(n.startswith('r3__') for n in names):continue
            kind='wall' if any('wall' in n for n in names) else 'robot' if any(n.startswith(('r1__','r2__')) for n in names) else None
            if kind:pairs.append(dict(kind=kind,geoms=names,distance=float(c.dist)))
        self._append('eval_only/contact-audit.jsonl',dict(t=self.now,pairs=pairs))
        super().eval_sample()  # retain original wall/tilt/nonfinite failure boundary
