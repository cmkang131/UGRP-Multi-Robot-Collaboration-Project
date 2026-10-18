"""Eval-only contact recorder for the cross-room flow (fix candidate).

Reads the MJWarp contact arrays after each batch step and records, per
control tick: the number of active contacts per world and, on a rising edge,
the contact geom pairs classified by body category (robot, wall, cargo,
peer, floor, other).  It never feeds a control input and never reads a world
pose; only contact counts/geom ids go to the eval-only record.

The implementation is defensive about the exact mujoco_warp array layout
(fields: ``nacon``, ``contact.geom``, ``contact.worldid``); if the layout is
not understood it reports ``layout_unknown`` instead of guessing.
"""
from __future__ import annotations

import numpy as np


def _np(value):
    if value is None:
        return None
    try:
        return np.asarray(value.numpy())
    except AttributeError:
        try:
            return np.asarray(value)
        except Exception:
            return None
    except Exception:
        return None


class ContactRecorder:
    def __init__(self, model, nworld, decimate=5):
        self.m = model
        self.nworld = nworld
        self.decimate = max(1, int(decimate))
        self._tick = 0
        self.prev_interest = 0
        self.events = []
        self.ticks_with_contact = 0
        self.ticks_checked = 0
        self.ticks_with_interest = 0
        self.layout = 'unknown'
        self.count_layout = 'unknown'
        self.errors = []
        # geom id -> category
        self.geom_category = {}
        for gid in range(model.ngeom):
            name = (model.geom(gid).name or '').lower()
            body = model.body(model.geom_bodyid[gid]).name or ''
            if any(s in name or s in body for s in ('wall',)):
                cat = 'wall'
            elif any(s in name or s in body for s in ('cargo_', 'team_', 'red_block',
                                                     'yellow_block', 'blue_block',
                                                     'warehouse_', 'beam')):
                cat = 'cargo'
            elif body.startswith('r1__'):
                cat = 'robot_r1'
            elif body.startswith(('r2__', 'r3__')):
                cat = 'peer'
            elif 'floor' in name or 'ground' in name:
                cat = 'floor'
            else:
                cat = 'other'
            self.geom_category[gid] = (cat, name, body)

    def _classify_pairs(self, geom_pairs, gcat=None):
        cats = set()
        for pair in geom_pairs:
            for gid in pair:
                gid = int(gid)
                if gid < 0:
                    continue
                cat, _, _ = self.geom_category.get(gid, ('other', '', ''))
                cats.add(cat)
        return sorted(cats)

    def update(self, wd, t):
        """Call after each control tick's physics launch.

        Global ``nacon`` is read every tick (cheap).  The contact geom pairs are
        read every ``decimate`` ticks (0.5 SIM s at 10 Hz) because the global
        count includes permanent wheel-floor contacts; an "interesting" contact
        is a pair that joins the r1 robot with a wall, cargo or peer geom.
        Events are rising edges of that interesting count and are eval-only.
        """
        nacon = _np(getattr(wd, 'nacon', None))
        if nacon is None:
            if not self.errors:
                self.errors.append('nacon_unavailable')
            return {'counts': None, 'global_nacon': None}
        raw = np.asarray(nacon).reshape(-1)
        global_nacon = int(raw[0]) if raw.size else 0
        if raw.size == self.nworld:
            counts = raw.astype(int).tolist()
            self.count_layout = 'per_world'
        elif raw.size == 1:
            counts = None
            self.count_layout = 'global_only'
        else:
            self.count_layout = 'size_%d' % raw.size
            counts = raw.astype(int).tolist()[:self.nworld]
        if global_nacon > 0:
            self.ticks_with_contact += 1
        self._tick += 1
        if self._tick % self.decimate == 0:
            self.ticks_checked += 1
            interest, pairs = self._interesting_pairs(wd)
            if interest > 0:
                self.ticks_with_interest += 1
            if interest > self.prev_interest and interest > 0:
                self.events.append(dict(
                    t=float(t), interesting=interest,
                    nacon=global_nacon, layout=self.layout,
                    pairs=pairs[:8],
                    categories=sorted({c for p in pairs for c in p[1]}),
                    blocked_object=','.join(sorted({c for p in pairs for c in p[1]
                                                    if c != 'robot_r1'})) or 'not_observed'))
            self.prev_interest = interest
        return dict(counts=counts, global_nacon=global_nacon,
                    ticks_with_interest=self.ticks_with_interest)

    def _interesting_pairs(self, wd):
        contact = getattr(wd, 'contact', None)
        if contact is None:
            return 0, []
        geom = _np(getattr(contact, 'geom', None))
        if geom is None:
            return 0, []
        try:
            g = np.asarray(geom)
            if g.ndim == 3 and g.shape[-1] == 2:
                flat = g.reshape(-1, 2)
                self.layout = 'world_first_pairs'
            elif g.ndim == 2 and g.shape[-1] == 2:
                flat = g
                self.layout = 'flat_pairs_with_worldid'
            else:
                self.errors.append('contact_geom_layout:%s' % (g.shape,))
                return 0, []
            pairs = []
            for pair in flat:
                cats = [self.geom_category.get(int(gid), ('other',))[0]
                        for gid in pair if int(gid) >= 0]
                if 'robot_r1' in cats and any(c in ('wall', 'cargo', 'peer')
                                              for c in cats):
                    pairs.append(([int(pair[0]), int(pair[1])], cats))
            return len(pairs), pairs
        except Exception as exc:  # noqa: BLE001 - eval only, report not crash
            self.errors.append(repr(exc))
            return 0, []

    def _classify_rising(self, wd, w):
        contact = getattr(wd, 'contact', None)
        if contact is None:
            return []
        geom = _np(getattr(contact, 'geom', None))
        if geom is None:
            return []
        try:
            g = np.asarray(geom)
            if g.ndim == 3 and g.shape[-1] == 2:
                pairs = g[w][:int(np.maximum(1, np.sum(g[w].any(axis=1))))]
                self.layout = 'world_first_pairs'
            elif g.ndim == 2 and g.shape[-1] == 2:
                worldid = _np(getattr(contact, 'worldid', None))
                if worldid is None:
                    return []
                wid = np.asarray(worldid).reshape(-1)
                pairs = g[wid == w]
                self.layout = 'flat_pairs_with_worldid'
            else:
                self.errors.append('contact_geom_layout:%s' % (g.shape,))
                return []
            return self._classify_pairs(pairs)
        except Exception as exc:  # noqa: BLE001 - eval only, report not crash
            self.errors.append(repr(exc))
            return []

    def summary(self):
        return dict(ticks_with_contact=self.ticks_with_contact,
                    ticks_checked=self.ticks_checked,
                    ticks_with_interest=self.ticks_with_interest,
                    events=self.events[-50:], layout=self.layout,
                    count_layout=self.count_layout,
                    decimate=self.decimate,
                    errors=self.errors[:5])
