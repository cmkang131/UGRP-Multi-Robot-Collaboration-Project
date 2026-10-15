"""Opt-in, asymmetric approach reservation from the currently visible beam.

Silver (2005) motivates reserving another agent's destination before planning;
PIBT (2019) motivates breaking symmetric contention with an ordered priority.
This local geometric reservation is neither full algorithm and has no MAPF
completeness claim. No peer trajectory, messages or hidden pose are required.
"""
import math

MODE = 'beampair_peer_yield_v1'


def reserved_teal_stance(world, rid, end, folded, station):
    # Blue yields the teal destination throughout approach. The ordered end
    # labels already come from the authorized task, not a live peer state.
    # Only a CURRENT admitted own-camera band may supply beam geometry.
    if (end != 'blue' or world['beam'] is None
            or world['visibility'][rid]['visible_probes'] < 5):
        return None
    g = world['beam']['ends']['teal']
    a = world['beam']['pose'][2]
    # station is the pinned nominal grasp stance (STATION_M), not a new fit.
    # Match visible_route.constraints' unchanged peer exclusion exactly:
    # own radius .13 folded/.17 unfolded + peer .17 + folding compensation.
    radius = .13 if folded else .17
    return (g[0]-station*math.cos(a), g[1]-station*math.sin(a),
            .17+(.17-radius))


class PeerYieldMixin:
    def _constraints(self, world):
        cs = super()._constraints(world)
        if self.peer_yield == 'off' or self.phase in ('pick', 'complete'):
            return cs
        from sim.grasp_act_teacher import STATION_M
        disc = reserved_teal_stance(world, self.rid, self.end, self.folded_ready, STATION_M)
        if disc is None:
            return cs
        radius, discs, rects = cs
        # A fixed task-space reservation must survive dynamic peer TTL expiry.
        # It is an extra plain disc, never a removed/expired physical keepout.
        now = world['t']
        if not self.peer_yield_log or self.peer_yield_log[-1]['t'] != now:
            gap = math.dist(world['robots'][self.rid]['pose'][:2], disc[:2])-disc[2]-radius
            self.peer_yield_log.append(dict(t=now, event='reserved_teal_destination',
                reason_category='peer_destination_reservation', blocked_object='reserved:teal_stance',
                min_gap_m=gap, blocked=gap < 0., reserved_disc=list(disc),
                gap_scope='own visible band + known rigid beam + original peer exclusion; not measured peer pose'))
        return radius, [*discs, disc], rects

    def diagnostic(self):
        d = super().diagnostic()
        d.update(peer_yield=self.peer_yield, peer_yield_log=self.peer_yield_log)
        return d
