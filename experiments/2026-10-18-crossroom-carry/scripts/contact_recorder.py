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
    def __init__(self, model, nworld):
        self.m = model
        self.nworld = nworld
        self.prev = [0] * nworld
        self.events = []
        self.ticks_with_contact = 0
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
        """Call after each control tick's physics launch. Returns per-world ncon."""
        nacon = _np(getattr(wd, 'nacon', None))
        if nacon is None:
            if not self.errors:
                self.errors.append('nacon_unavailable')
            return None
        raw = np.asarray(nacon).reshape(-1)
        if raw.size == self.nworld:
            counts = raw.astype(int).tolist()
            self.count_layout = 'per_world'
        elif raw.size == 1:
            # A single global contact count: keep it as a total and do not
            # invent per-world attribution (eval-only reference).
            counts = [int(raw[0])] + [0] * (self.nworld - 1)
            self.count_layout = 'global_only'
        else:
            self.count_layout = 'size_%d' % raw.size
            counts = raw.astype(int).tolist()[:self.nworld]
            counts += [0] * (self.nworld - len(counts))
        if any(counts):
            self.ticks_with_contact += 1
        for w in range(self.nworld):
            if counts[w] > 0 and self.prev[w] == 0:
                cats = self._classify_rising(wd, w)
                self.events.append(dict(t=t, world=w, ncon=counts[w],
                                        categories=cats,
                                        blocked_object=('not_observed' if not cats
                                                        else ','.join(cats))))
        self.prev = counts
        return dict(counts=counts, ticks_with_contact=self.ticks_with_contact)

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
                    events=self.events[-50:], layout=self.layout,
                    count_layout=self.count_layout,
                    errors=self.errors[:5])
