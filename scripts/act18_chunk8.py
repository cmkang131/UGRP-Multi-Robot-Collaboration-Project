"""Default-off contract-chunk gate for the ACT18 takeover pilot.

The frozen deployment contract fixes one action horizon (``CHUNK=8``).  A
checkpoint trained with a different horizon, such as the matched act18 R100
(``chunk=100``), cannot be fed to :class:`harness.grasp_act_policy.ChunkExecutor`
without either redefining the executor horizon or slicing the first eight
actions out of every prediction.  Both choices change what the policy is
doing: R100 was evaluated with every-tick temporal ensembling over all 100
horizons, so dropping horizons 8..99 and re-querying every eight ticks is a
different controller, not a transport fix.

This module therefore *admits* only a checkpoint whose declared horizon is
already the contract horizon.  It deliberately does not slice a longer chunk.
The gate is default off, so importing/calling the helpers without
``enabled=True`` is a strict no-op and existing callers are unchanged.

The helpers live under ``scripts/`` rather than ``harness/`` because the
takeover pilot prepends a pinned actor source to ``sys.path``.  That source
contains its own ``harness`` package; keeping the gate outside it makes the
default-off import unambiguous.
"""
from __future__ import annotations

import numpy as np


def _contract():
    # Import at call time so the pilot's pinned actor source and the repo
    # checkout both resolve the contract that is actually in force.  The two
    # copies are hash-identical (SHA256 6bc58d6f...).
    from harness import grasp_act_contract as contract
    return contract


def require_contract_chunk(chunk, *, enabled=False):
    """Fail closed unless ``chunk`` equals the frozen contract horizon.

    Disabled is a strict no-op returning ``None``.  Enabled accepts only an
    ``int`` equal to ``grasp_act_contract.CHUNK`` (8); it never truncates a
    longer horizon.
    """
    if not enabled:
        return None
    contract = _contract()
    if type(chunk) is not int or chunk != contract.CHUNK:
        raise ValueError(
            f'checkpoint chunk {chunk!r} does not equal frozen contract chunk '
            f'{contract.CHUNK}; the pilot does not slice a longer ACT chunk '
            '(that changes policy semantics). Use the chunk=8 R8 checkpoint '
            'with --contract-chunk8.')
    return chunk


def pilot_checkpoint_chunk(meta, *, takeover_pilot=False, enabled=False):
    """Resolve the pilot checkpoint chunk under the default-off gate.

    Off returns ``meta['chunk']`` unchanged.  On requires the act18 adapter,
    the takeover-pilot lane and an exactly contract-sized horizon.
    """
    if not enabled:
        return meta.get('chunk')
    if not takeover_pilot:
        raise ValueError('--contract-chunk8 is takeover-pilot-only')
    if meta.get('schema') != 'ugrp.act18.adapter.v1':
        raise ValueError('--contract-chunk8 requires the act18 adapter schema')
    chunk = meta.get('chunk')
    require_contract_chunk(chunk, enabled=True)
    return chunk


def contract_chunk_rows(values, *, enabled=False):
    """Validate exactly one contract-sized action block.

    Disabled returns the caller's object unchanged (identity).  Enabled
    requires shape ``(CHUNK, ACTION_DIM)`` with finite values, so a 100-row
    R100 prediction is rejected rather than silently sliced to eight.
    """
    if not enabled:
        return values
    contract = _contract()
    rows = np.asarray(values, dtype=float)
    expected = (contract.CHUNK, contract.ACTION_DIM)
    if rows.shape != expected:
        raise ValueError(f'chunk rows {rows.shape} do not equal {expected}; '
                         'the pilot does not slice a longer ACT chunk')
    if not np.isfinite(rows).all():
        raise ValueError('nonfinite contract chunk')
    return rows


def contract_chunk_predict(predict, *, enabled=False):
    """Wrap a policy predict callable with the contract boundary.

    Disabled returns the exact original callable (no wrapper and no added
    validation).  Enabled returns a wrapper that admits only a single
    ``(CHUNK, ACTION_DIM)`` block; a chunk=8 callable produces byte-identical
    rows, while a chunk=100 callable fails before the executor sees it.
    """
    if not enabled:
        return predict

    def guarded(observation, jpegs):
        return contract_chunk_rows(predict(observation, jpegs),
                                   enabled=True).tolist()
    return guarded
