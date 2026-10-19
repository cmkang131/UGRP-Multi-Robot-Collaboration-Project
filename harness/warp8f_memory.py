"""warp8f owner-side self-centric memory evidence for release relocalization.

The e2ewarp release adapter (``release_relocalization_memory_v1``) binds the
navigator snapshot in ``start`` and calls an injected owner after the own-RGB
lookaround.  This module is the owner boundary: it consults the navigator's
``ugrp.e2ewarp.selfnav.v1`` registration and returns an echo of the snapshot
the release attempt was bound to, together with the live destination landmark
of the bound kind.  It never reads map geometry, a global pose, GT or world
state.

Why the bound snapshot is echoed instead of the current one: the navigator
advances ``evidence_revision`` (and therefore ``memory_sha256``) on every own
frame, including the frames observed during the release lookaround.  Requiring
the current hash would make the release permanently fail-closed.  The owner
therefore checks the live memory for a usable destination landmark, echoes the
exact bound hash/revision that the release adapter validated at ``start``, and
reports the current revision/hash separately for audit.

Fail-closed codes (surfaced verbatim by the release adapter):

* ``owner_navigator_snapshot_missing`` - no navigator memory source/snapshot.
* ``owner_navigator_snapshot_unavailable`` - the source raised.
* ``owner_navigator_snapshot_invalid`` - snapshot violates the selfnav schema.
* ``owner_navigator_snapshot_stale`` - live revision is behind the bound one.
* ``owner_navigator_snapshot_hash_mismatch`` - same revision, different hash.
* ``owner_navigator_not_ready`` / ``_memory_unregistered`` /
  ``_destination_unregistered`` - the navigator cannot back the destination.
* ``owner_navigator_destination_mismatch`` - live destination kind differs.
* ``owner_navigator_landmark_missing`` / ``_mismatch`` /
  ``_from_future`` - the live destination landmark is not usable evidence.

No claim is made for a static map, global pose, truth or held-world read.
"""
from __future__ import annotations

import math

from harness.e2ewarp_selfnav import (OWNER as NAVIGATOR_OWNER,
                                     validate_memory_registration)

OWNER = 'warp8f'
SOURCE = 'navigator_memory_registration_v1'
LANDMARK_FIELDS = ('kind', 'range_m', 'bearing_deg', 'last_seen_s',
                   'uncertainty_m', 'range_measured')
#: Reason codes the release adapter may forward verbatim instead of collapsing
#: owner-side fail-closed evidence into ``owner_memory_registered_false``.
REASONS = (
    'owner_evidence_invalid',
    'owner_evidence_views_missing',
    'owner_evidence_views_invalid',
    'owner_bound_snapshot_invalid',
    'owner_bound_destination_invalid',
    'owner_navigator_snapshot_missing',
    'owner_navigator_snapshot_unavailable',
    'owner_navigator_snapshot_invalid',
    'owner_navigator_snapshot_stale',
    'owner_navigator_snapshot_hash_mismatch',
    'owner_navigator_not_ready',
    'owner_navigator_memory_unregistered',
    'owner_navigator_destination_unregistered',
    'owner_navigator_destination_mismatch',
    'owner_navigator_landmark_missing',
    'owner_navigator_landmark_mismatch',
    'owner_navigator_landmark_from_future',
)


def _digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in '0123456789abcdef' for c in value))


def _fail(reason, *, views=0):
    """Owner-side fail-closed report; no static-map or GT field is emitted."""
    return dict(owner=OWNER, relocalized=False, memory_registered=False,
                reason=reason, source=SOURCE, views=int(views),
                truth_inputs=0, held_world_reads=0)


class Warp8fMemoryOwner:
    """Owner callable for ``release_relocalization_memory_v1``.

    ``memory_source`` is the navigator's self-centric memory registration: a
    mapping, a zero-argument callable returning one (for example
    ``navigator.memory_registration``), or an object exposing a
    ``memory_registration()`` method.  It is consulted at owner-call time; the
    release adapter's bound snapshot remains the echo identity.
    """

    def __init__(self, memory_source=None):
        if memory_source is not None:
            getter = getattr(memory_source, 'memory_registration', None)
            if not (isinstance(memory_source, dict) or callable(memory_source)
                    or callable(getter)):
                raise ValueError('OWNER_MEMORY_SOURCE_REQUIRED')
        self.memory_source = memory_source

    def _snapshot(self):
        """Return ``(snapshot, error)``; never raise from the owner boundary."""
        source = self.memory_source
        if source is None:
            return None, 'absent'
        try:
            if isinstance(source, dict):
                return source, None
            if callable(source):
                return source(), None
            return source.memory_registration(), None
        except Exception as exc:  # owner failure is unknown, never a claim
            return None, type(exc).__name__

    def __call__(self, evidence):
        if not isinstance(evidence, dict):
            return _fail('owner_evidence_invalid')
        views = evidence.get('views')
        if not isinstance(views, (list, tuple)) or not views:
            return _fail('owner_evidence_views_missing')
        times = []
        for view in views:
            if not isinstance(view, dict):
                return _fail('owner_evidence_views_invalid', views=len(views))
            t = view.get('t')
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t):
                return _fail('owner_evidence_views_invalid', views=len(views))
            times.append(float(t))
        if evidence.get('navigator_owner') != NAVIGATOR_OWNER:
            return _fail('owner_bound_snapshot_invalid', views=len(views))
        digest = evidence.get('memory_sha256')
        if not _digest(digest):
            return _fail('owner_bound_snapshot_invalid', views=len(views))
        revision = evidence.get('navigator_evidence_revision')
        if type(revision) is not int or revision < 0:
            return _fail('owner_bound_snapshot_invalid', views=len(views))
        kind = evidence.get('destination_kind')
        if not isinstance(kind, str) or not kind.startswith('zone_'):
            return _fail('owner_bound_destination_invalid', views=len(views))
        snapshot, error = self._snapshot()
        if error == 'absent':
            return _fail('owner_navigator_snapshot_missing', views=len(views))
        if error is not None:
            return _fail('owner_navigator_snapshot_unavailable', views=len(views))
        if snapshot is None:
            return _fail('owner_navigator_snapshot_missing', views=len(views))
        try:
            validate_memory_registration(snapshot)
        except ValueError:
            return _fail('owner_navigator_snapshot_invalid', views=len(views))
        current_revision = snapshot['evidence_revision']
        if current_revision < revision:
            return _fail('owner_navigator_snapshot_stale', views=len(views))
        if current_revision == revision and snapshot['memory_sha256'] != digest:
            return _fail('owner_navigator_snapshot_hash_mismatch', views=len(views))
        if snapshot['ready'] is not True:
            return _fail('owner_navigator_not_ready', views=len(views))
        if snapshot['registered'] is not True:
            return _fail('owner_navigator_memory_unregistered', views=len(views))
        if snapshot['destination_registered'] is not True:
            return _fail('owner_navigator_destination_unregistered', views=len(views))
        if snapshot.get('destination_kind') != kind:
            return _fail('owner_navigator_destination_mismatch', views=len(views))
        landmark = snapshot.get('destination_landmark')
        if not isinstance(landmark, dict):
            return _fail('owner_navigator_landmark_missing', views=len(views))
        if landmark.get('kind') != kind:
            return _fail('owner_navigator_landmark_mismatch', views=len(views))
        last_seen = landmark.get('last_seen_s')
        if (isinstance(last_seen, bool) or not isinstance(last_seen, (int, float))
                or not math.isfinite(last_seen)):
            return _fail('owner_navigator_landmark_missing', views=len(views))
        if last_seen > max(times) + 1e-6:
            return _fail('owner_navigator_landmark_from_future', views=len(views))
        return dict(owner=OWNER, relocalized=True, memory_registered=True,
                    memory_sha256=digest,
                    navigator_evidence_revision=revision,
                    navigator_current_revision=int(current_revision),
                    navigator_current_memory_sha256=snapshot['memory_sha256'],
                    memory_landmark={key: landmark[key]
                                     for key in LANDMARK_FIELDS if key in landmark},
                    source=SOURCE, views=len(views),
                    truth_inputs=0, held_world_reads=0)


def owner_factory(memory_source=None):
    """Owner injection point: ``owner=warp8f_memory.owner_factory(navigator)``."""
    return Warp8fMemoryOwner(memory_source)
