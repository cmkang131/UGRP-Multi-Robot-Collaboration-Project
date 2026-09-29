"""Model-aware static team geometry; polygon operations reuse the frozen v2 module."""
from harness import zone_team_footprint as legacy
from sim.zone_model_conventions import convention, station_offset


class TeamFootprintV3(legacy.TeamFootprint):
    def __init__(self, scene_or_static, kind, roles, *, margin=legacy.TEAM_MARGIN_M):
        profile = convention(scene_or_static)
        if profile['robot_model'] != 'masterpi_v3':
            raise ValueError('v3 footprint requires a v3 scene')
        super().__init__(kind, roles, margin=margin)
        self.robot_model = profile['robot_model']
        self.stations = {role: station_offset(scene_or_static, kind, role) for role in self.roles}
        # V2 chassis rectangle contains the drawing's smaller v3 wheel envelope.
        # Extend its front by the arm mount too: conservative until physical QA.
        mount = profile['arm_mount_x_m']
        chassis = legacy.rect(legacy.CHASSIS_X_M[0] - margin, legacy.CHASSIS_X_M[1] + mount + margin,
                              legacy.CHASSIS_Y_M[0] - margin, legacy.CHASSIS_Y_M[1] + margin)
        arm = legacy.rect(0., profile['station_radius_m'] + .030 + margin,
                          -legacy.ARM_HALF_W_M - margin, legacy.ARM_HALF_W_M + margin)
        self.carrier_parts = {r: [legacy.transform(p, self.stations[r]) for p in (chassis, arm)]
                              for r in self.roles}
        self.parts = self.item_parts + [p for r in self.roles for p in self.carrier_parts[r]]
        self.hull = legacy.convex_hull([pt for p in self.parts for pt in p])

    def record(self):
        return {**super().record(), 'robot_model': self.robot_model,
                'envelope_status': 'conservative_static_not_physical_validation'}


def team_footprint(scene_or_static, kind, roles=None, *, margin=legacy.TEAM_MARGIN_M):
    if convention(scene_or_static)['robot_model'] == 'masterpi_v2':
        return legacy.team_footprint(kind, roles, margin=margin)
    if roles is None:
        roles = legacy.CATALOGUE[kind].formations[0] if kind in legacy.CATALOGUE else ('west',)
    return TeamFootprintV3(scene_or_static, kind, roles, margin=margin)
