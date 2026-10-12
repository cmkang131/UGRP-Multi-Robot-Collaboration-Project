"""Private Module F: read-only grid -> sourced wall claims for own LLM memory.

No map alignment, peers, live truth, transport, or model client. Confidence is
existing TSDF fusion support, never sigmoid(occupancy) or a calibrated probability.
"""
from __future__ import annotations
import math
import hashlib
import json
import numpy as np
from harness.self_odom_grid import OdomGrid
from harness.self_pose_graph import validate_rows
from harness.self_wall_validation import hit_cells
from harness.self_wall_evidence import build_evidence

OPTION = 'segments_confidence_v1'
FRAME = 'own start chassis: x forward, y left, metres'


def pose_std(covariance):
    if covariance is None:
        return None
    q = np.asarray(covariance, float)
    if (q.shape != (3, 3) or not np.isfinite(q).all() or
            not np.allclose(q, q.T) or np.linalg.eigvalsh(q).min() < -1e-9):
        raise ValueError('INVALID_EXPORT_POSE_COVARIANCE')
    return float(np.sqrt(max(0., np.linalg.eigvalsh(q[:2, :2]).max())))


def export_walls(grid, ledger, *, robot_id, wall_export='off', observations=None,
                 pose_covariance=None, now=None):
    """Off does not inspect inputs. On returns JSON-safe, own-frame claims only.

    Historical sources are endpoint hits near the summarized segment; they do
    not certify a true wall. Export leaves the grid and frontend RNG untouched.
    """
    if wall_export == 'off':
        return None
    if wall_export != OPTION:
        raise ValueError('UNKNOWN_WALL_EXPORT')
    if grid['robot_id'] != robot_id or grid['frame'] != FRAME:
        raise ValueError('EXPORT_OWN_FRAME_REQUIRED')
    validate_rows(ledger, robot_id)
    observations = observations or {}
    ids = [r['frame_id'] for r in ledger]
    if len(set(ids)) != len(ids):
        raise ValueError('DUPLICATE_EXPORT_SCAN')
    now = float(max((r['t'] for r in ledger), default=0.) if now is None else now)
    if not math.isfinite(now) or any(r['t'] > now for r in ledger):
        raise ValueError('INVALID_EXPORT_TIME')
    resolution = float(grid['resolution_m'])
    occupied = {tuple(c[:2]) for c in grid['cells'] if c[2] > 0}
    view = OdomGrid(robot_id, resolution_m=resolution, text_top_k=max(1, len(occupied)))
    view.cells = {tuple(c[:2]): c[2] for c in grid['cells']}
    lines = view.lines()  # Existing grid summary algorithm, no refit/tuning.
    revision = hashlib.sha256(json.dumps(grid['cells'], separators=(',', ':')).encode()).hexdigest()[:12]
    evidence = build_evidence(ledger, robot_id=robot_id, wall_evidence='tsdf_weight_v1',
                              resolution_m=resolution)
    support = {tuple(c['cell']): c for c in evidence['cells']}
    sources, cell_frames = {}, {}
    for row in ledger:
        fid = row['frame_id']
        meta = observations.get(fid, {})
        if meta.get('robot_id', robot_id) != robot_id:
            raise ValueError('EXPORT_PEER_SOURCE_FORBIDDEN')
        frame_sha = meta.get('frame_sha256')
        if frame_sha is not None and (len(frame_sha) != 64 or any(c not in '0123456789abcdef' for c in frame_sha)):
            raise ValueError('INVALID_EXPORT_FRAME_HASH')
        sources[fid] = dict(obs_id=meta.get('obs_id', f'{robot_id}-obs-{fid:06d}'),
            t_sim=float(row['t']), frame_id=fid, frame_sha256=frame_sha, source='own',
            observer_pose=dict(xyyaw=list(row['pose']), std_xy_m=pose_std(meta.get('pose_covariance')),
                source='own_rbpf_pose_ledger', uncertainty_scope='frontend marginal; not graph-smoothed covariance'))
        _, hits = hit_cells(row, resolution)
        for cell in hits & occupied:
            cell_frames.setdefault(cell, set()).add(fid)
    cells = sorted(occupied)
    points = (np.asarray(cells, float).reshape(-1, 2)+.5)*resolution
    claims = []
    for i, line in enumerate(lines):
        a, b = np.asarray(line['a']), np.asarray(line['b'])
        vector = b-a
        u = np.clip((points-a)@vector/(vector@vector), 0., 1.)
        near = np.linalg.norm(points-(a+u[:, None]*vector), axis=1) <= resolution/math.sqrt(2)+1e-9
        keys = [cells[k] for k in np.flatnonzero(near)]
        frames = sorted(set().union(*(cell_frames.get(k, set()) for k in keys)))
        refs = [sources[f] for f in frames]
        stats = [support[k] for k in keys if k in support]
        score = float(np.mean([s['support_score'] for s in stats])) if stats else None
        last = max(refs, key=lambda r: (r['t_sim'], r['frame_id'])) if refs else None
        stds = [s['observer_pose']['std_xy_m'] for s in refs if s['observer_pose']['std_xy_m'] is not None]
        claims.append(dict(obs_id=f'{robot_id}-wall-{revision}-{i+1:04d}',
            t_sim=None if last is None else last['t_sim'],
            frame_sha256=None if last is None else last['frame_sha256'],
            observer_pose=None if last is None else last['observer_pose'],
            entity=dict(kind='wall_segment', id=f'{robot_id}/wall/{revision}/{i+1:04d}'),
            claim=dict(state='observed_wall_candidate', endpoints_m=[line['a'], line['b']]),
            evidence=dict(detector='egomap34_frozen_contacts+odom_grid_hough_tls',
                score=score, semantics='TSDF support; NOT calibrated wall probability',
                grid_fit_cells=line['cells'], nearby_occupied_cells=len(keys),
                scan_count=len(frames), observation_ids=[r['obs_id'] for r in refs],
                observations=refs, first_t_sim=min((r['t_sim'] for r in refs), default=None),
                last_t_sim=None if last is None else last['t_sim'],
                max_observer_std_xy_m=max(stds, default=None),
                view_circular_variance=float(np.mean([s['view_circular_variance'] for s in stats])) if stats else None,
                association='historical endpoint-hit cells within half-cell diagonal of summary line'),
            confidence='unvalidated_support' if refs else 'unsupported', source='own',
            age_s=None if last is None else now-last['t_sim']))
    return dict(schema='ugrp.own_wall_memory.v1', option=OPTION, robot_id=robot_id,
        audience='own_llm_only', source='own', generated_t_sim=now, map_revision=revision,
        coordinate_frame=dict(id=f'{robot_id}/own_start', origin='own initial chassis pose',
            x='forward', y='left', yaw='counterclockwise positive', units=dict(position='m', angle='rad'),
            world_alignment=None, current_pose_xyyaw=list(grid['pose_xyyaw']),
            current_std_xy_m=pose_std(pose_covariance)),
        map_samples=dict(occupied_cells=len(occupied), observed_cells=len(grid['cells']),
            resolution_m=resolution, observed_area_m2=len(grid['cells'])*resolution**2,
            insertion_scans=len(ledger), exported_segments=len(claims)), items=claims)


def memory_text(export, *, top_k=6, max_bytes=1024):
    """ASCII bytes upper-bound byte-BPE tokens; budget covers this summary only."""
    if export is None:
        return ''
    if top_k < 1 or max_bytes < 256:
        raise ValueError('INVALID_EXPORT_TEXT_BUDGET')
    frame = export['coordinate_frame']
    out = (f"own_wall_memory {frame['id']} (m; x forward,y left,CCW+); "
           f"pose_std_xy={frame['current_std_xy_m']}; support!=wall_probability; ")
    ranked = sorted(export['items'], key=lambda x: (-(x['evidence']['score'] or 0.), x['obs_id']))
    for item in ranked[:top_k]:
        a, b = item['claim']['endpoints_m']; e = item['evidence']
        latest = e['observation_ids'][-1] if e['observation_ids'] else 'none'
        score = 'unknown' if e['score'] is None else f"{e['score']:.2f}"
        part = (f"{item['entity']['id']} ({a[0]:.2f},{a[1]:.2f})->({b[0]:.2f},{b[1]:.2f}) "
                f"support={score} scans={e['scan_count']} last={latest}@{item['t_sim']} "
                f"age={item['age_s']}s source=own; ")
        if len((out+part).encode('utf-8')) > max_bytes:
            break
        out += part
    return out.rstrip('; ')
