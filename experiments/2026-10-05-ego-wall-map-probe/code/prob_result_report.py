"""Post-evaluation tables, figures and small Git artifacts (no predictor calls)."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import odom_grid_replay as base

CONDITIONS = ('off', 'v1', 'v2', 'prob', 'rbpf30', 'rbpf100')
CASES = [f's{s}-{r}' for s in (911, 912, 913) for r in ('r1', 'r2')]


def historical(name, condition):
    split = 'development' if name.startswith('s911') else 'confirmation'
    version = 'v1' if condition == 'v1' else 'v2'
    label = 'off' if condition == 'off' else 'on'
    return ROOT/f'outputs/self-map-csm-{version}-{split}'/name/label


def figures(paths, summaries, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, axes = plt.subplots(2, 4, figsize=(15, 7), constrained_layout=True)
    for row, robot in enumerate(('r1', 'r2')):
        name = 's912-'+robot
        ref = summaries[name, 'off']
        episode = Path(next(s['path'] for s in ref['sources'] if s['path'].endswith('scene.xml'))).parent
        walls = [o for o in json.loads((episode/'inputs/static_map.json').read_text())['obstacles'] if o.get('kind') == 'wall']
        for col, condition in enumerate(('v2', 'prob', 'rbpf30', 'rbpf100')):
            ax = axes[row, col]
            grid = json.loads((paths[name, condition]/'grid.json').read_text())
            cells = np.array(grid['cells'])
            pts = (cells[cells[:, 2] > 0, :2]+.5)*.1
            pts = base.transform(pts, ref['origin_eval_only'])
            for wall in walls:
                x, y = wall['center_m']
                hx, hy = wall['half_extents_m']
                ax.add_patch(Rectangle((x-hx, y-hy), 2*hx, 2*hy, color='#777777', alpha=.3))
            ax.scatter(pts[:, 0], pts[:, 1], s=7, c='#b54732')
            poses = base.read_rows(paths[name, condition]/'poses.jsonl')
            xy = base.transform(np.array([p['pose'][:2] for p in poses]), ref['origin_eval_only'])
            ax.plot(xy[:, 0], xy[:, 1], lw=.8, color='#286ca8')
            q = summaries[name, condition]['final']
            ax.set(title=f'{name} {condition}\nP={q["precision_015"]:.1%} R={q["wall_coverage"]:.1%}, RMSE={q["wall_error_rmse_m"]:.3f}m',
                   aspect='equal', xlabel='evaluation world x (m)', ylabel='y (m)')
            ax.grid(alpha=.2)
    fig.suptitle('Private maps, initial-pose GT alignment only (gray walls: evaluation only)')
    fig.savefig(out/'s912-probability-maps.png', dpi=115)
    plt.close(fig)
    fig, axes = plt.subplots(3, 2, figsize=(11, 9), constrained_layout=True)
    for ax, name in zip(axes.flat, CASES):
        for condition in ('off', 'v2', 'prob', 'rbpf30', 'rbpf100'):
            rows = base.read_rows(paths[name, condition]/'path_errors.jsonl')
            ax.plot([r['t'] for r in rows], [r['xy_error_m'] for r in rows], lw=1., label=condition)
        ax.set(title=name+(' development' if name.startswith('s911') else ' confirmation replay'), xlabel='recording time (s)', ylabel='XY error (m)')
        ax.legend(fontsize=7, ncol=3)
        ax.grid(alpha=.2)
    fig.savefig(out/'probability-path-errors.png', dpi=115)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    paths, summaries, comparisons = {}, {}, {}
    for name in CASES:
        for condition in CONDITIONS:
            source = historical(name, condition) if condition in ('off','v1','v2') else args.source/condition/name
            paths[name, condition] = source
            summaries[name, condition] = json.loads((source/'summary.json').read_text())
            comparison_path = source.parent/'comparison.json' if condition in ('v1','v2') else source/'comparison.json'
            if condition != 'off':
                comparisons[name, condition] = json.loads(comparison_path.read_text())
            if condition in ('off','v1','v2'):
                continue
            target = out/f'{condition}-{name}'
            target.mkdir()
            for filename in ('summary.json', 'comparison.json', 'off_golden.json', 'resources.json',
                             'prediction_hashes.json', 'series.jsonl', 'path_errors.jsonl', 'llm.txt'):
                shutil.copyfile(source/filename, target/filename)
            rows = base.read_rows(source/'corrections.jsonl')
            compact = []
            for e in rows:
                record = {k: v for k, v in e.items() if k != 'particle_events'}
                if 'particle_events' in e:
                    record['particle_reason_counts'] = dict(Counter(r['reason'] for r in e['particle_events']))
                compact.append(record)
            (target/'decisions.jsonl').write_text(''.join(json.dumps(e, allow_nan=False)+'\n' for e in compact))
    for file in ('development_fixed.json', 'development_execution.json', 'confirmation_execution.json', 'verification.json'):
        shutil.copyfile(args.source/file, out/file)
    figures(paths, summaries, out)
    tables = ['단위: 각 칸은 **종료 XY m / 경로 XY RMSE m / precision % / recall % / 벽 RMSE m**.', '',
              '| 녹화 | off | v1 | v2 | prob | RBPF30 | RBPF100 |', '|---|---|---|---|---|---|---|']
    for name in CASES:
        values = []
        for condition in CONDITIONS:
            s = summaries[name, condition]
            q = s['final']
            values.append(f'{s["end_position_error_m"]:.3f} / {s["path_position_error"]["rmse_m"]:.3f} / {100*q["precision_015"]:.1f} / {100*q["wall_coverage"]:.1f} / {q["wall_error_rmse_m"]:.3f}')
        tables.append('| '+name+' | '+' | '.join(values)+' |')
    tables += ['', '| 조건 | 개발 전체 기준 통과 | 확인 전체 기준 통과 | 확인 7개 개별 기준 통과 수(각 건) |', '|---|---|---|---|']
    for condition in CONDITIONS[1:]:
        dev = sum(comparisons[n, condition]['success'] for n in CASES[:2])
        conf = sum(comparisons[n, condition]['success'] for n in CASES[2:])
        checks = ', '.join(f'{n}: {sum(comparisons[n,condition]["checks"].values())}/7' for n in CASES[2:])
        tables.append(f'| {condition} | {dev}/2 | {conf}/4 | {checks} |')
    tables += ['', '시간은 prediction 구간, 메모리는 해당 프로세스의 prediction 종료까지 peak RSS다.', '',
               '| 녹화 | prob 초 / MiB | RBPF30 초 / MiB | RBPF100 초 / MiB |', '|---|---|---|---|']
    for name in CASES:
        values = [summaries[name, c]['resources'] for c in CONDITIONS[3:]]
        tables.append('| '+name+' | '+' | '.join(f'{v["prediction_wall_s"]:.2f} / {v["peak_rss_mib"]:.1f}' for v in values)+' |')
    tables += ['', '| 조건·녹화 | 선택 입자/단일지도 수락·거부·보류·bootstrap | 최종 삽입 scan | 재표본화 / 최소 N_eff | 종료 sqrt(trace(Σxy)/2) m |', '|---|---|---|---|---|']
    for condition in CONDITIONS[3:]:
        for name in CASES:
            s = summaries[name, condition]
            counts = s['correction_status_counts']
            count_text = '/'.join(str(counts.get(k,0)) for k in ('accepted','rejected','deferred','bootstrap'))
            cov = np.array(json.loads((paths[name, condition]/'grid.json').read_text())['covariance'])
            neff = f'{s["resamples"]} / {s["neff_min"]:.1f}' if condition != 'prob' else '—'
            tables.append(f'| {condition} {name} | {count_text} | {s["inserted_frames"]} | {neff} | {np.sqrt(np.trace(cov[:2,:2])/2):.3f} |')
    (out/'tables.md').write_text('\n'.join(tables)+'\n')
    raw = [{'path': str(p), 'sha256': base.sha(p), 'bytes': p.stat().st_size} for p in sorted(args.source.rglob('*')) if p.is_file()]
    archived = [{'file': str(p.relative_to(out)), 'sha256': base.sha(p), 'bytes': p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()]
    base.dump(out/'manifest.json', {'source_sha': summaries[CASES[0],'prob']['source_sha'], 'criteria_commit': '86b78790',
                                   'report_sha256': base.sha(Path(__file__)), 'files': archived, 'local_outputs': raw,
                                   'historical_baselines': [{'case': n, 'condition': c, 'path': str(paths[n,c]/'summary.json'),
                                                            'sha256': base.sha(paths[n,c]/'summary.json')}
                                                           for n in CASES for c in CONDITIONS[:3]],
                                   'backup_scope': 'Git subset only; full particle maps/traces and raw recordings remain local'})
    print('\n'.join(tables))
    print('archive_bytes', sum(x['bytes'] for x in archived), 'local_bytes', sum(x['bytes'] for x in raw))


if __name__ == '__main__':
    main()
