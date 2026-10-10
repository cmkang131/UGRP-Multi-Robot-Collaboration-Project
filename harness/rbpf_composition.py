"""Explicit insertion + selective weighting composition; defaults do nothing.

CSM rejection skips its weights/resampling, but retains motion-pose insertion.
Manhattan conditioning and graph switchable constraints remain separate owners.
Frozen comparison: experiments/2026-10-08-rbpf-turn-audit/README.md.
"""
from functools import partial
from types import MethodType
from harness.rbpf_rejection import _proposals
from harness.self_map_rbpf import improved_proposal

OPTION = 'insert_selective_v1'
SEARCH = 'correlative_20deg_v1'


def install(grid, *, rbpf_composition='off', rbpf_search='off'):
    if rbpf_composition == rbpf_search == 'off':
        return grid
    if (rbpf_composition != OPTION or rbpf_search not in ('off', SEARCH)
            or not hasattr(grid, '_selective_state')
            or grid.wall_confidence != 'inverse_sensor_v1'):
        raise ValueError('COMPOSITION_REQUIRES_SELECTIVE_INVERSE_SENSOR')
    if hasattr(grid, '_selective_proposals') or hasattr(grid, '_manhattan_axes'):
        raise ValueError('COMPOSITION_INSTALL_ONCE_BEFORE_MANHATTAN')
    grid._selective_proposals = _insert_all
    grid._composition_search = rbpf_search
    if rbpf_search == SEARCH:
        # Same RBPF objective, quadrature, importance weights, XY search.
        # Cartographer's fixed default angular extent; no truth-based selection.
        grid._selective_proposal = partial(improved_proposal, yaw_window_deg=20.)
    grid._composition_export_base = grid.export
    grid.export = MethodType(_export, grid)
    return grid


def _insert_all(self, points, camera, attempt):
    events, update, rejection = _proposals(self, points, camera, attempt)
    for event in events:
        event['inserted'] = True
        event['insertion_reason'] = 'motion_fallback' if rejection else event['reason']
    return events, update, rejection


def _export(self):
    out = self._composition_export_base()
    out.update(rbpf_composition=OPTION, rbpf_insertion='gmapping_range_v1',
               rbpf_search=self._composition_search,
               rejection_policy='insert_motion_samples_without_csm_weight_or_resampling')
    return out
