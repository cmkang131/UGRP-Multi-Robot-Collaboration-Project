"""S3 physics owner. Only capture() is a robot input; truth is written separately."""
from __future__ import annotations

import base64
import copy
import io

from harness.zone_final_pair_binding import bind
from sim.solo_cyan_v106 import PhysicsBackend as SoloBackend
from sim.final_environment_checks import PhysicsBackend as BaseBackend
from scripts.run_final_environment_checks import write

ROBOTS = ('r1', 'r2', 'r3')


def make_scene(bundle, seed):
    from sim.zone_environment_scene_provider import scenario_scene
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    return wrap(install(scenario_scene(bundle['scenario_id'], seed), 'floor_light_v1'))


class PhysicsBackend(SoloBackend):
    def __init__(self, bundle, out, *, seed):
        # Same v3 world, three command-only ports, clock, contact and nearclip.
        bind(SoloBackend.__init__, make_scene=make_scene)(self, bundle, out, seed=seed)
        try:
            self.objects = copy.deepcopy(self.scene.config['setup_only']['objects'])
            for cargo in self.scene.cargo:
                self.objects[cargo.item_id] = {'kind': cargo.kind, 'body_name': 'cargo_'+cargo.item_id}
            # Same name/geometry join used by OwnCamTeamHost's referee.
            import mujoco
            m = self.world.model
            names = [mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, i) or '' for i in range(m.ngeom)]
            self._fingers = {r: ({i for i, n in enumerate(names) if n == r+'__left_finger'},
                                {i for i, n in enumerate(names) if n == r+'__right_finger'}) for r in ROBOTS}
            self._box_geom = {item: {i for i in range(m.ngeom)
                                     if int(m.geom_bodyid[i]) == int(m.body(o['body_name']).id)}
                              for item, o in self.objects.items()}
            if any(not gs for gs in self._box_geom.values()) or any(
                    not left or not right for left, right in self._fingers.values()):
                raise ValueError('S3 referee item/finger geometry missing')
        except Exception:
            self.close()
            raise

    def reset(self, cap):
        elapsed = super().reset(cap)
        from scripts.run_zone_study_integration import placements_match
        from sim.zone_scenario_scene import load_scenario
        self.spec = self.scene.spec
        placements_match(load_scenario(self.bundle['scenario_id']), self)
        return elapsed

    def issue(self, rid, action):
        if rid not in ROBOTS:
            raise ValueError('unknown S3 actuator owner')
        if action['kind'] == 'hold':
            self.ports[rid].hold(self.now)
            self._append(f'robots/{rid}/commands.jsonl', {'t': self.now, **action})
        else:
            BaseBackend.issue(self, rid, action)

    def capture(self):
        import numpy as np
        from PIL import Image
        frames = {}
        for rid in ROBOTS:
            obs = self.ports[rid].capture()
            jpeg = base64.b64decode(obs['image'], validate=True)
            rgb = np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB'))
            relative = f'robots/{rid}/rgb/{self.frame:05d}.jpg'
            path = self.out/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpeg)
            self._append(f'robots/{rid}/frames.jsonl', {**{k: v for k, v in obs.items() if k != 'image'},
                'path': relative, 'commanded_servo': self.commands[rid]})
            frames[rid] = (obs, rgb)
        self.frame += 1
        return frames

    def eval_sample(self):
        BaseBackend.eval_sample(self)  # contacts/weld audit only
        from scripts.run_zone_study_integration import StudyTeamHost
        truth = StudyTeamHost.referee_truth(self)
        self._append('eval_only/referee_truth.jsonl', {'t': self.now, 'items': truth})
        # No evaluation return value or live referee visible to the runtime.

    def evaluate(self, orders, static):
        """Replay only AFTER the control loop; delivery cannot trigger any action."""
        import json
        from harness.zone_study_referee import Referee
        from harness.zone_evidence_key import key_for
        run_id = f's3-v107-{self.bundle["source_sha"][:12]}-s{self.bundle["seed"]}'
        key = key_for({'run_id': run_id, 'trial_id': run_id, 'condition': 'no_comm',
                       'seed': self.bundle['seed'], 'attempt': 1})
        referee = Referee(orders, static, evidence_key=key)
        path = self.out/'eval_only/referee_truth.jsonl'
        if path.exists():
            # _append streams are line-buffered. Keep originals and replay all samples.
            with path.open() as stream:
                for line in stream:
                    row = json.loads(line)
                    referee.observe(row['t'], row['items'])
        result = referee.record()
        write(self.out/'eval_only/referee.json', result)
        return {'orders_complete': result['orders_complete'], 'orders': result['orders'],
                'samples': result['samples'], 'profile': result['profile'],
                'feedback_to_controller': False, 'source': 'post_run_truth_replay',
                'qualification': 'DEV simulator delivery only; not S2 graduation or real robot success'}
