"""Public, immutable long-beam role requests; no peer/world state is accepted.

The existing action/message schemas remain unchanged. A high-level caller can
select a complete assignment before dispatch, or explicitly submit its own
partner and role through pair_carry. Both robots must still submit locally.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

PROFILE = 'zone_pair_roles_v1'
ROBOTS = ('r1', 'r2', 'r3')
ROLES = ('end_neg', 'end_pos')


@dataclass(frozen=True)
class PairRoles:
    end_neg: str
    end_pos: str

    def __post_init__(self):
        if (self.end_neg not in ROBOTS or self.end_pos not in ROBOTS
                or self.end_neg == self.end_pos):
            raise ValueError('UNSUPPORTED_PAIR')

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, Mapping) or set(value) != set(ROLES):
            raise ValueError('BAD_PAIR_ROLE_ASSIGNMENT')
        return cls(value['end_neg'], value['end_pos'])

    @classmethod
    def from_request(cls, actor, partner, role):
        if role not in ROLES:
            raise ValueError('UNSUPPORTED_PAIR_ROLE')
        return cls(actor, partner) if role == 'end_neg' else cls(partner, actor)

    @property
    def participants(self):
        return (self.end_neg, self.end_pos)

    def mapping(self):
        return dict(zip(ROLES, self.participants))

    def role(self, actor):
        if actor not in self.participants:
            raise ValueError('UNSUPPORTED_PAIR')
        return ROLES[self.participants.index(actor)]

    def partner(self, actor):
        self.role(actor)
        return self.end_pos if actor == self.end_neg else self.end_neg

    def sign(self, actor):
        return 1. if self.role(actor) == 'end_neg' else -1.

    def sha256(self):
        raw = json.dumps(self.mapping(), sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(raw).hexdigest()


LEGACY_ROLES = PairRoles('r1', 'r2')


def requested_roles(actor, partner, role=None):
    """Only the old r1/r2 API may omit role; never guess an r3 assignment."""
    if role is None:
        if LEGACY_ROLES.partner(actor) != partner:
            raise ValueError('UNSUPPORTED_PAIR')
        return LEGACY_ROLES
    return PairRoles.from_request(actor, partner, role)
