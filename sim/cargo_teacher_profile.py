"""Per-cargo geometry for the two-robot demonstration teachers (beam, heavy crate).

The beam teachers (PR #484/#491) hard-code the beam: grasp bands at +-0.27 m,
landing ends at +-0.30 m, obstacle discs along 0.54 m. This table carries the same
quantities for other two-robot cargo so the existing teacher classes can be
reused. ``BEAM`` reproduces the old constants exactly (default everywhere).

Role mapping: the teacher classes keep their internal end names ``teal`` and
``blue``. For the heavy crate ``teal`` is the west lug (robot faces +x in the
crate frame, heading = crate yaw) and ``blue`` is the east lug (heading = crate
yaw + pi), i.e. the same sign convention as the beam. The student-facing role
tickets are ``west`` / ``east`` (harness/grasp_act_contract.KIND_ROLES).

Numbers (sim/zone_cargo.py, heavy_crate): body 140x100x60 mm (half .07/.05/.03),
two lugs 60x40x46 mm centred at x = +-0.09 (spanning 0.06..0.12), 0.900 kg total,
grasp point (+-0.10, 0, 0.024), landing half extents (.12, .05).
"""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CargoProfile:
    kind: str
    item_id: str
    roles: tuple                 # student role tickets for (teal, blue)
    band_geoms: tuple            # model geom names for (teal, blue) grasp markers
    band_center_m: float         # |marker centre| along the object axis
    grasp_m: float               # |grasp point| along the object axis (jaw centre)
    end_z_offset_m: float        # grasp-point z minus marker-centre z
    landing_end_m: float         # |outer landing end| along the axis
    scan_lateral_m: float        # floor scan offset beside the axis (clear of the body)
    discs: tuple                 # ((offset along axis, radius), ...) planning obstacles
    probe_xy: tuple              # marker top-face probe fractions of the half sizes
    landing_kind: str

    @property
    def band_to_grasp_m(self):
        return self.grasp_m-self.band_center_m

    @property
    def grasp_to_end_m(self):
        return self.landing_end_m-self.grasp_m

    @property
    def half_len_m(self):
        return self.landing_end_m

    def end_name(self, role):
        return ('teal', 'blue')[self.roles.index(role)]

    def role_of(self, end):
        return self.roles[('teal', 'blue').index(end)]


_FRACTIONS_X = (-.9, -.45, 0., .45, .9)
_FRACTIONS_Y = (-.9, 0., .9)

BEAM = CargoProfile(
    kind='long_beam', item_id='beam_1', roles=('teal', 'blue'),
    band_geoms=('cargo_beam_1__band_neg', 'cargo_beam_1__band_pos'),
    band_center_m=.27, grasp_m=.27, end_z_offset_m=-.0086,        # beam code: end z = band-centre z - .0086
    landing_end_m=.30, scan_lateral_m=.05,
    discs=tuple((d, .02) for d in (-.27, -.135, 0., .135, .27)),
    probe_xy=tuple((x, y) for x in _FRACTIONS_X for y in _FRACTIONS_Y), landing_kind='long_beam')

# Obstacle discs for the crate: body footprint (140x100 mm) and the two lugs. They
# must leave the base station (0.10 + 0.203 = 0.303 m from the centre) reachable at
# the unfolded planning radius 0.17 m: 0.303-0.07 = 0.233 >= 0.045+0.17 = 0.215.
CRATE = CargoProfile(
    kind='heavy_crate', item_id='crate_1', roles=('west', 'east'),
    band_geoms=('cargo_crate_1__lug_west', 'cargo_crate_1__lug_east'),
    band_center_m=.09, grasp_m=.10, end_z_offset_m=.024-.023,   # lug centre z = .023, grasp z = .024
    landing_end_m=.12, scan_lateral_m=.07,
    discs=((-.10, .02), (-.07, .045), (0., .055), (.07, .045), (.10, .02)),
    probe_xy=tuple((x, y) for x in _FRACTIONS_X for y in _FRACTIONS_Y), landing_kind='heavy_crate')

PROFILES = {'long_beam': BEAM, 'heavy_crate': CRATE}


def profile(kind):
    return PROFILES[kind]


def with_item(p, item_id):
    """The same profile for another instance id (e.g. crate_2)."""
    prefix_old, prefix_new = 'cargo_'+p.item_id+'__', 'cargo_'+item_id+'__'
    return CargoProfile(**{**p.__dict__, 'item_id': item_id,
                           'band_geoms': tuple(g.replace(prefix_old, prefix_new) for g in p.band_geoms)})


def axis_heading(p, end, yaw):
    """Heading the robot faces to take ``end`` (teal: along +axis, blue: reversed)."""
    return yaw+(math.pi if end == 'blue' else 0.)


def end_points(p, x, y, yaw, z_object=0.):
    """World grasp points {teal, blue} for an object pose (teacher/evaluation geometry)."""
    c, s = math.cos(yaw), math.sin(yaw)
    return {'teal': (x-p.grasp_m*c, y-p.grasp_m*s), 'blue': (x+p.grasp_m*c, y+p.grasp_m*s)}


def station_xy(p, end, x, y, yaw, station_m=.203):
    """Chassis station (x, y, heading) from which ``end`` is grasped."""
    g = end_points(p, x, y, yaw)[end]
    h = axis_heading(p, end, yaw)
    return g[0]-station_m*math.cos(h), g[1]-station_m*math.sin(h), h


def planning_discs(p, x, y, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return [(x+d*c, y+d*s, r) for d, r in p.discs]
