"""Opt-in P02 host adapter; the registered OwnCamTeamHost bytes stay frozen."""
import copy
import json

from harness.zone_mixed_jobs import dispatch_refusal, validate_host_spec
from harness.zone_own_team_host import HOST_APIS, OwnCamTeamHost


class MixedOwnCamTeamHost(OwnCamTeamHost):
    """Validate mixed inventory, then attach the unchanged pair dispatcher.

    The base constructor initializes the world and solo executors. Pair setup
    happens here after that, because its legacy admission equates order/item
    IDs. No global monkeypatch or rewritten registration is needed.
    """

    def __init__(self, spec, student, *, root, study_layer, frames_dir=None, scene=None,
                 pose_factory=None):
        from sim.zone_cargo_contact import base_profile
        from sim.zone_mixed_inventory import MixedGeometryCargoZoneScene, check_scene_inventory

        validate_host_spec(spec)
        if frames_dir is None:
            raise ValueError('M2 requires frames_dir to preserve every own-camera input')
        if scene is None:
            scene = MixedGeometryCargoZoneScene.from_spec(spec, base_profile(spec['contact_profile']))
        check_scene_inventory(scene.config['setup_only']['objects'],
                              scene.config['cargo_set']['items'], spec['mixed_jobs'])
        solo_spec = copy.deepcopy(spec)
        solo_spec['pair_order_sheets'] = {}
        super().__init__(solo_spec, student, root=root, study_layer=study_layer, frames_dir=frames_dir,
                         scene=scene, pose_factory=pose_factory)
        self.spec = copy.deepcopy(spec)
        from scripts.run_m2_pair import CALIBRATION
        params = json.loads(CALIBRATION.read_text())['params']
        self.enable_pair_carry(spec['pair_order_sheets'], params, policy=spec['pair_policy'])

    def call(self, rid, api, *args):
        if api not in HOST_APIS:
            return super().call(rid, api, *args)
        slot = self.robots[rid]
        # Preserve base shutdown/dead-robot precedence and all accepted calls.
        if not self.closed and not slot.dead:
            refusal = dispatch_refusal(self.spec['mixed_jobs'], rid, api, args)
            if refusal:
                now = float(self.world.data.time)
                slot.executor.now = now
                ack = slot.executor.refuse(api, refusal)
                self._pair_safety(now)
                self.api_calls.append(ack)
                return ack
        return super().call(rid, api, *args)
