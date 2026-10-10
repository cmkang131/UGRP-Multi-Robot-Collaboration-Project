"""Post-prediction evaluation only; never changes detector, motion or texture."""
import json
import math
import xml.etree.ElementTree as ET
import numpy as np

import replay_texture as adapter

c, EXP = adapter.c, adapter.EXP
RAW = c.OUT.parent


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def stats(v):
    v = np.asarray(v)
    return dict(n=len(v), median=float(np.median(v)), p90=float(np.quantile(v, .9)), max=float(np.max(v))) if len(v) else None


def main():
    adapter.verify()
    assert all((c.OUT / 'parallax_v1' / case / 'receipt.json').is_file() for case in c.EPISODES)
    output, traces = {}, {}
    old_root = c.ROOT / 'experiments/2026-10-07-wall-parallax-strafe'
    old = c.read(old_root / 'results/diagnosis.json')['cases']
    for case, ep in c.EPISODES.items():
        pred = rows(c.OUT / 'parallax_v1' / case / 'predictions.jsonl')
        receipt = c.read(c.OUT / 'parallax_v1' / case / 'receipt.json')
        assert c.sha(c.OUT / 'parallax_v1' / case / 'predictions.jsonl') == receipt['predictions_sha256']
        truth = rows(ep / 'eval_only/trajectory.jsonl')
        xy = np.array([r['robot_xyz_m'][:2] for r in truth])
        yaw = np.array([r['robot_yaw_rad'] for r in truth])
        rotation = np.array([[math.cos(yaw[0]), -math.sin(yaw[0])], [math.sin(yaw[0]), math.cos(yaw[0])]])
        local = (xy - xy[0]) @ rotation
        times = np.array([r['t'] for r in truth])
        own = list(c.stream(case))
        dr = np.array([r[3] for r in own])
        ts = np.array([r[0]['sim_time'] for r in own])
        indices = [int(np.argmin(abs(times - t))) for t in ts]
        errors = np.linalg.norm(dr[:, :2] - local[indices], axis=1)
        candidates = [p for r in pred for p in r['candidate']]
        totals = receipt['counts']
        keys = ['low_parallax', 'zero_baseline', 'reprojection', 'behind_camera',
                'outside_wall_roi', 'lk_failure', 'insufficient_views', 'range']
        assert not set(totals) - set(keys) - {'accepted', 'unsettled', 'calibrated_unloaded', 'seeded', 'reset_tracks'}
        events = {k: totals.get(k, 0) for k in keys}
        n_events = sum(events.values()) + totals.get('accepted', 0)
        root = ET.fromstring((ep / 'scene.xml').read_text())
        visual = [dict(g.attrib) for g in root.iter('geom') if g.get('name', '').startswith('tape_v1_')]
        assert len(visual) == 24 and all(g['contype'] == g['conaffinity'] == '0' for g in visual)
        old_case = case.replace('tape-', 'strafe-')
        old_raw = RAW.parent / 'wall-parallax-strafe-v1' / (old_case + ('-host-retry1' if old_case.endswith('north') else ''))
        old_truth = rows(old_raw / 'eval_only/trajectory.jsonl')
        actual_span, dr_span = float(np.ptp(local[:, 1])), float(np.ptp(dr[:, 1]))
        result = c.read(EXP / 'results' / (case + '.json'))
        output[case] = dict(eligible_frames=receipt['frames'], counts=totals, event_count=n_events,
            event_fractions={k: v / n_events for k, v in events.items()},
            actual_xy_extent_m=np.ptp(local, axis=0).tolist(), dr_xy_extent_m=np.ptp(dr[:, :2], axis=0).tolist(),
            dr_over_actual_lateral=dr_span / actual_span,
            actual_path_m=float(np.linalg.norm(np.diff(xy, axis=0), axis=1).sum()),
            actual_yaw_span_deg=float(np.degrees(np.ptp(np.unwrap(yaw)))),
            dr_path_error_m=stats(errors), dr_end_error_m=float(errors[-1]),
            available_10view_dr_baseline_m=stats([np.linalg.norm(dr[i, :2] - dr[i - 9, :2]) for i in range(9, len(dr))]),
            available_10view_actual_baseline_m=stats([np.linalg.norm(local[indices[i]] - local[indices[i - 9]]) for i in range(9, len(dr))]),
            accepted_unique_tracks=len(set(p['track_id'] for p in candidates)),
            accepted_frame_ids=[r['frame_id'] for r in pred if r['candidate']],
            accepted_parallax_deg=stats([p['parallax_deg'] for p in candidates]),
            confidence=stats([p['confidence'] for p in candidates]),
            depth_sigma_m=result['depth_sigma_m'], seed_ratio_to_off=totals['seeded'] / old[old_case]['counts']['seeded'],
            visual_planes=len(visual), acquisition=c.read(ep / 'result.json'),
            commands_identical_to_off=c.sha(ep / 'robots/r3/commands.jsonl') == c.sha(old_raw / 'robots/r3/commands.jsonl'),
            actual_trajectory_max_difference_to_off_m=float(np.max(np.linalg.norm(xy - np.array([r['robot_xyz_m'][:2] for r in old_truth]), axis=1))),
            passed=result['passed'], evaluation_sources={str(p): c.sha(p) for p in
                [ep / 'eval_only/trajectory.jsonl', ep / 'eval_only/camera.jsonl', ep / 'scene.xml']})
        traces[case] = dict(t=times - times[0], local=local, ts=ts - times[0], dr=dr)
    passed = sum(r['passed'] for r in output.values())
    c.dump(EXP / 'results/diagnosis.json', dict(cases=output, passed=passed, texture_tuning=0,
        detector_tuning=0, mapping_replays=0, decision='STOP_GATE_FAILED' if passed < 2 else 'MAP_RECORDING_ADMITTED'))

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(10, 6), constrained_layout=True)
    for j, (case, trace) in enumerate(traces.items()):
        ax = axes[0, j]
        ax.plot(trace['t'], trace['local'][:, 1], color='black', label='actual lateral (evaluation only)')
        ax.plot(trace['ts'], trace['dr'][:, 1], color='#b14a36', label='frozen command DR')
        ax.set(title=case, xlabel='time after reset (s)', ylabel='lateral displacement (m)')
        ax.legend(fontsize=8)
        keys = ['seeded', 'accepted', 'low_parallax', 'zero_baseline', 'reprojection', 'outside_wall_roi', 'lk_failure']
        ax = axes[1, j]
        y = np.arange(len(keys))
        prior = old[case.replace('tape-', 'strafe-')]['counts']
        now = output[case]['counts']
        ax.barh(y - .18, [prior.get(k, 0) for k in keys], height=.36, color='#999999', label='texture off (egomap15)')
        ax.barh(y + .18, [now.get(k, 0) for k in keys], height=.36, color='#397498', label='tape_v1')
        ax.set(yticks=y, yticklabels=keys, xlabel='seeds / repeated track events (different units)')
        ax.legend(fontsize=8)
    fig.savefig(EXP / 'figures/texture-diagnosis.png', dpi=140)
    plt.close(fig)
    c.dump(EXP / 'results/raw-manifest.json', dict(root=str(RAW), files={str(p.relative_to(RAW)):
        dict(bytes=p.stat().st_size, sha256=c.sha(p)) for p in sorted(RAW.rglob('*')) if p.is_file()}))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
