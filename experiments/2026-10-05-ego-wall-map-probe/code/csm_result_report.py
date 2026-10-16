"""Post-replay artifacts/figures only. No prediction, sensors, physics or models.

Optional selected-frames DR map is a post-hoc evaluation diagnostic: keep the
on branch's frame selection but use its frozen off poses, to expose selection
versus pose effects. Never fed back to either controller or acceptance criteria.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import shutil
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import odom_grid_replay as base
from harness.self_odom_grid import OdomGrid, transform


def selected_dr(case, off, on):
    poses = {row['t']: row['pose'] for row in base.read_rows(case/'off/poses.jsonl')}
    grid = OdomGrid(on['robot'], settle_s=None)
    for obs in base.read_rows(case/'on/observations.jsonl'):
        pose = poses[obs['t']]
        grid.insert(transform([obs['camera']], pose)[0], [transform(s, pose) for s in obs['segments']])
    episode = Path(next(s['path'] for s in off['sources'] if s['path'].endswith('scene.xml'))).parent
    obstacles = json.loads((episode/'inputs/static_map.json').read_text())['obstacles']
    rects = np.array([list(o['center_m'])+list(o['half_extents_m']) for o in obstacles if o.get('kind') == 'wall'])
    points = transform(grid.occupied_points(), off['origin_eval_only'])
    result, _ = base.quality(points, rects, base.wall_samples(rects))
    result.update(scope='post-hoc eval-only; on-selected contacts at frozen off poses; not a third controller run')
    return result, rects


def figures(cases, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, axes = plt.subplots(2, 2, figsize=(10, 8), constrained_layout=True)
    for i, robot in enumerate(('r1', 'r2')):
        case, off, on, _, rects = cases['s912-'+robot]
        for j, (label, summary) in enumerate((('off', off), ('on', on))):
            ax = axes[i, j]
            cells = np.asarray(json.loads((case/label/'grid.json').read_text())['cells'])
            pts = (cells[cells[:, 2] > 0, :2]+.5)*.1
            pts = transform(pts, summary['origin_eval_only'])
            for x, y, hx, hy in rects:
                ax.add_patch(Rectangle((x-hx, y-hy), 2*hx, 2*hy, color='#858585', alpha=.35))
            ax.scatter(pts[:, 0], pts[:, 1], s=12, c='#ad392d', label='occupied')
            paths = base.read_rows(case/label/'poses.jsonl')
            xy = transform(np.array([r['pose'][:2] for r in paths]), summary['origin_eval_only'])
            ax.plot(xy[:, 0], xy[:, 1], color='#386cb0', lw=1, label='estimated path')
            q = summary['final']
            ax.set(title=f's912 {robot} {label}: P {q["precision_015"]:.1%}, R {q["wall_coverage"]:.1%}\n'
                         f'wall RMSE {q["wall_error_rmse_m"]:.3f} m', aspect='equal', xlabel='world x (m)', ylabel='y (m)')
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
    fig.suptitle('Private maps: start-pose GT alignment only; gray walls are evaluation-only')
    fig.savefig(out/'s912-off-on-maps.png', dpi=125)
    plt.close(fig)
    fig, axes = plt.subplots(3, 2, figsize=(10, 9), constrained_layout=True)
    for i, seed in enumerate(('s911', 's912', 's913')):
        for j, robot in enumerate(('r1', 'r2')):
            name = seed+'-'+robot
            case, off, on, _, _ = cases[name]
            ax = axes[i, j]
            for label, color in [('off', '#777777'), ('on', '#2677af')]:
                rows = base.read_rows(case/label/'path_errors.jsonl')
                ax.plot([r['t'] for r in rows], [r['xy_error_m'] for r in rows], color=color, label=label)
            events = base.read_rows(case/'on/corrections.jsonl')
            accepted = [r['t'] for r in events if r['status'] == 'accepted']
            ax.scatter(accepted, [0.]*len(accepted), marker='|', s=50, color='#c64a36', label='accepted CSM')
            ax.set(title=f'{name}: end {off["end_position_error_m"]:.3f} -> {on["end_position_error_m"]:.3f} m',
                   xlabel='recording time (s)', ylabel='XY error (m)', ylim=(-.05, 1.15))
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
    fig.suptitle('Saved-recording replay only: s911 development; s912/s913 confirmation replay')
    fig.savefig(out/'path-errors-off-on.png', dpi=125)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--development', default=str(ROOT/'outputs/self-map-csm-v1-development'))
    parser.add_argument('--confirmation', default=str(ROOT/'outputs/self-map-csm-v1-confirmation'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifests, cases, files = {}, {}, []
    for split, root in [('development', Path(args.development)), ('confirmation', Path(args.confirmation))]:
        manifests[split] = json.loads((root/'manifest.json').read_text())
        shutil.copyfile(root/'manifest.json', out/(split+'-source.json'))
        for case in sorted(root.glob('s*-r*')):
            name = case.name
            off, on = [json.loads((case/k/'summary.json').read_text()) for k in ('off', 'on')]
            selection, rects = selected_dr(case, off, on)
            cases[name] = (case, off, on, selection, rects)
            base.dump(out/(name+'-selection-diagnostic.json'), selection)
            for label in ('off', 'on'):
                for filename in ('summary.json', 'series.jsonl', 'path_errors.jsonl'):
                    src = case/label/filename
                    dst = out/(name+'-'+label+'-'+filename)
                    shutil.copyfile(src, dst)
                    files.append({'file': dst.name, 'source': str(src), 'sha256': base.sha(src), 'bytes': src.stat().st_size})
            for filename in ('corrections.jsonl', 'map_ledger.jsonl'):
                src = case/'on'/filename
                dst = out/(name+'-'+filename)
                shutil.copyfile(src, dst)
                files.append({'file': dst.name, 'source': str(src), 'sha256': base.sha(src), 'bytes': src.stat().st_size})
            for filename in ('comparison.json', 'off_golden.json'):
                src = case/filename
                dst = out/(name+'-'+filename)
                shutil.copyfile(src, dst)
                files.append({'file': dst.name, 'source': str(src), 'sha256': base.sha(src), 'bytes': src.stat().st_size})
    figures(cases, out)
    import scipy
    import matplotlib
    base.dump(out/'environment.json', {'python': sys.version, 'platform': platform.platform(), 'numpy': np.__version__,
                                      'scipy': scipy.__version__, 'matplotlib': matplotlib.__version__,
                                      'scope': 'offline replay and post-replay reporting; existing Mac environment'})
    for p in sorted(out.iterdir()):
        if p.name not in {f['file'] for f in files}:
            files.append({'file': p.name, 'sha256': base.sha(p), 'bytes': p.stat().st_size})
    # Full local outputs retain grid/covariance/poses in addition to Git subset.
    raw_files = [{'path': str(p), 'sha256': base.sha(p), 'bytes': p.stat().st_size}
                 for root in (Path(args.development), Path(args.confirmation)) for p in sorted(root.rglob('*')) if p.is_file()]
    base.dump(out/'manifest.json', {'replay_source_sha': manifests['development']['source_sha'],
                                  'report_script_sha256': base.sha(Path(__file__)), 'files': files, 'local_outputs': raw_files,
                                  'remote_scope': 'listed Git subset only; original videos and full outputs remain local',
                                  'criteria_commit': 'e44f12c9',
                                  'all_confirmation_success': all(json.loads((case/'comparison.json').read_text())['success']
                                                                  for name, (case, *_) in cases.items()
                                                                  if not name.startswith('s911'))})
    print('| 녹화 | 종료 XY off→on (m) | 경로 RMSE off→on (m) | P off→on | R off→on | 벽 RMSE off→on (m) |')
    for name, (case, off, on, selection, _) in cases.items():
        vals = [f'{off[k]:.3f}→{on[k]:.3f}' for k in ('end_position_error_m',)]
        vals += [f'{off["path_position_error"]["rmse_m"]:.3f}→{on["path_position_error"]["rmse_m"]:.3f}']
        for k in ('precision_015', 'wall_coverage'):
            vals.append(f'{off["final"][k]:.1%}→{on["final"][k]:.1%}')
        vals.append(f'{off["final"]["wall_error_rmse_m"]:.3f}→{on["final"]["wall_error_rmse_m"]:.3f}')
        print('| '+name+' | '+' | '.join(vals)+' |')
    print('Total Git artifact bytes:', sum(p.stat().st_size for p in out.iterdir()))


if __name__ == '__main__':
    main()
