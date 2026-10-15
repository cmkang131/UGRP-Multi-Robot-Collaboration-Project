"""Offline fixed-trace policy replay. No plant, renderer, remote or truth reads."""
import argparse
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
from harness.natural_floor_slam import compose, _motion_covariance
from harness.self_map_integration import SelfMapIntegration
from harness.self_pulse_odom import command_odometry
from harness.selfmap5_revision import revision_test, issued_distance, partial_poses
from harness.selfmap5_registration import MultiFrameEvidence, calibrated_covariance
from harness.selfmap4_geometry import observe, static_input
from harness.self_map_landmark_sensor import Sensor
from harness.own_map_amcl_vendor.landmarks import MapFeatures
from scripts.offline_self_map import rows, dump, digest


def analyze(raw, images):
    trace, trace_source = rows(raw/'trace.jsonl')
    bundle = json.loads((raw/'bundle.json').read_text())
    commands, commands_source = rows(raw/'robots/r3/commands.jsonl')
    frames, frames_source = rows(raw/'robots/r3/frames.jsonl')
    acc = object.__new__(SelfMapIntegration)
    acc.delta, acc.Q = np.zeros(3), np.zeros((3, 3))
    odom = command_odometry(commands[0]['t'], motion_model='s2_pulse_v122_rotL_v1')
    odom.step_callback = acc._motion
    ci = 0; previous = None; distance = 0.; anchor = -1
    revisions, history, segments = [], [], []
    for row in trace:
        t = row['t']
        while ci < len(commands) and commands[ci]['t'] < t-1e-8:
            odom.command(commands[ci]); ci += 1
        odom.advance(t)
        flow = row.get('plane_flow') or {}
        if flow.get('status') == 'measured':
            from harness.e2e_rgb_vo import fuse
            acc.delta, acc.Q, _, _ = fuse(acc.delta, acc.Q, flow['delta'], flow['covariance'])
        if previous is None:
            prior = np.array(row['pose']); predicted_cov = np.asarray(row['covariance'])
        else:
            prior = compose(previous['pose'], acc.delta)
            predicted_cov = _motion_covariance(previous['pose'], acc.delta,
                                               np.asarray(previous['covariance']), acc.Q)
        distance += issued_distance(acc.delta)
        if row['pose_source'] in ('visual_update', 'visual_relocalized'):
            measured = np.asarray(row['covariance'])
            if bundle['options'].get('bootstrap') == 'command_prior_v1' and row['visual_reason'] != 'selfmap4_static_lines':
                measured = measured-predicted_cov
            test = revision_test(prior, row['pose'], predicted_cov, measurement_covariance=measured)
            legacy = (np.linalg.norm(np.asarray(row['pose'])[:2]-prior[:2]) > .1 or
                      abs(test['innovation'][2]) > math.radians(5))
            revisions.append(dict(t=t, frame_id=row['frame_id'], legacy_fixed_gate=bool(legacy), **test))
            # Exercise the partial trajectory reconstruction even when v2 correctly
            # avoids quarantine. This is a forced numerical diagnostic, not a map commit.
            if legacy or test['required']:
                rev = dict(t=t, anchor_frame_id=anchor, prior=prior.tolist(), corrected=row['pose'],
                    distance=distance, endpoint_frame_id=row['frame_id'])
                poses, reason = partial_poses(history, rev)
                changed = [r['observation'].frame_id for r in history if r['observation'].frame_id > anchor]
                segments.append(dict(**rev, success=poses is not None, reason=reason,
                    corrected_frame_ids=changed, corrected_N=len(changed) if poses is not None else 0,
                    preserved_N=len(history)-len(changed), history_N=len(history),
                    raster_verified=False))
        if row['map_updated']:
            history.append(dict(observation=SimpleNamespace(frame_id=row['frame_id']),
                pose=np.asarray(row['pose']), source=row['pose_source'], distance_since_visual=distance))
        if row['pose_source'] in ('visual_update', 'visual_relocalized', 'bootstrap'):
            anchor = row['frame_id']; distance = 0.
        previous = row; acc.delta, acc.Q = np.zeros(3), np.zeros((3, 3))
    static, static_sha = static_input(); landmarks = MapFeatures(static)
    sensor = Sensor(landmarks.hues); evidence = MultiFrameEvidence()
    by_id = {r['frame_id']:r for r in trace}
    detections = []; sweep_active = False
    # Sweep membership comes from recorded executor stages, not invented frames.
    frame_by_id = {f['frame_id']:f for f in frames}
    for row in trace:
        active = row['stage'] == 'spin'
        if active and not sweep_active:
            evidence.begin(row['t'])
        if not active and sweep_active:
            evidence.end()
        sweep_active = active
        f = frame_by_id[row['frame_id']]; path = images/f['path']
        if not path.exists():
            continue
        if digest(path) != f['sha256']:
            raise ValueError('RGB_HASH_MISMATCH')
        servo = {int(k):v for k,v in f['commanded_servo'].items()}
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        obs = observe(rgb, servo, sensor)
        evidence.add(obs, row['pose'], row['t'])
        sr = row['static_registration']
        supported, detail = evidence.supported(landmarks.edges, sr['world_pose'], row['pose'],
                                               calibrated_covariance(sr['covariance']))
        detections.append(dict(frame_id=f['frame_id'], t=row['t'], path=str(path),
            sha256=f['sha256'], feature_count=len(obs['features']), supported=supported, **detail))
    return dict(schema='ugrp.selfmap5_offline.v1', base_sha='d8a7530a9f3f6f11d77d0ea7d06838db1486d296',
        sources=[trace_source, commands_source, frames_source], authored_static_sha256=static_sha,
        trace_N=len(trace), visual_N=len(revisions),
        legacy_rebuild_required_times=[r['t'] for r in revisions if r['legacy_fixed_gate']],
        v2_rebuild_required_times=[r['t'] for r in revisions if r['required']],
        revisions=revisions, forced_partial_pose_rebuilds=segments,
        S2=dict(rgb_available_N=len(detections), trace_N=len(trace), observations=detections,
            max_independent_axis_count=max((d['independent_axis_count'] for d in detections), default=0),
            full_sweep_evidence_complete=False, pf_rerun=False),
        limitations=['fixed recorded trajectory, not closed-loop success',
            'six locally retained RGB only; full segment ray raster and full multi-frame sweep unavailable',
            'PF bias cause and reinjection effectiveness unverified; covariance factor 6 is a conservative diagnostic setting',
            'forced partial rebuild counts corrected poses, not ORB refits or a verified occupancy map'],
        physics_calls=0, render_calls=0, model_calls=0, pool_with_previous_results=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw', type=Path, required=True)
    p.add_argument('--images', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); result = analyze(a.raw, a.images)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    dump(a.output, result)
    print(json.dumps({k:result[k] for k in ('trace_N', 'visual_N', 'legacy_rebuild_required_times', 'v2_rebuild_required_times')}))
    print(json.dumps(dict(partial=result['forced_partial_pose_rebuilds'], S2={k:v for k,v in result['S2'].items() if k!='observations'})))


if __name__ == '__main__':
    main()
