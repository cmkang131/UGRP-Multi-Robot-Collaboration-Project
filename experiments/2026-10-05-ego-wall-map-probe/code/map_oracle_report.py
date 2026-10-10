"""Verify and publish the six evaluation-only oracle results; no estimator runs."""
import argparse
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import map_error_oracle as e

CASES = [f's{s}-{r}' for s in (911, 912, 913) for r in ('r1','r2')]


def load(path):
    return json.loads(path.read_text())


def points(grid):
    cells = np.array(grid['cells'])
    return (cells[cells[:, 2] > 0, :2]+.5)*grid['resolution_m']


def verify(source):
    records = []
    for name in CASES:
        directory = source/name
        s = load(directory/'summary.json')
        earlier = e.base.ROOT/'outputs/self-map-oracle-diagnostic-v1-complete'/name
        prior = load(earlier/'summary.json')
        for c in e.CONDITIONS:
            assert s['conditions'][c]['attribution'] == prior['conditions'][c]['attribution']
            for filename in (f'{c}-gt-grid.json', f'{c}-false-cells.jsonl'):
                assert e.base.sha(directory/filename) == e.base.sha(earlier/filename)
            for scope in ('original', 'matched_gt_pose'):
                for metric in ('precision_015', 'wall_coverage', 'wall_error_rmse_m', 'occupied_cells'):
                    assert s['conditions'][c][scope][metric] == prior['conditions'][c][scope][metric]
        for f in s['sources']:
            assert e.base.sha(f['path']) == f['sha256'], f['path']
        samples = load(directory/'wall_samples.json')
        xy = np.array(samples['xy'])
        for k, n in s['visibility_counts'].items():
            assert sum(samples[k]) == n
        assert np.all(np.array(samples['contact_visible']) <= samples['visible'])
        assert np.all(np.array(samples['contact_near4']) <= samples['contact_visible'])
        assert np.all(np.array(samples['contact_admitted']) <= samples['contact_visible'])
        scene = Path(next(f['path'] for f in s['sources'] if f['path'].endswith('scene.xml')))
        walls = [w for w in load(scene.parent/'inputs/static_map.json')['obstacles'] if w.get('kind') == 'wall']
        rects = np.array([w['center_m']+w['half_extents_m'] for w in walls])
        for c, r in s['conditions'].items():
            grid = load(directory/f'{c}-gt-grid.json')
            q, cover = e.base.quality(e.transform(points(grid), s['origin_eval_only']), rects, xy)
            for key in q:
                assert q[key] == r['matched_gt_pose'][key]
            for key in s['visibility_counts']:
                assert float(cover[np.array(samples[key])].mean()) == r['matched_gt_pose']['recall_'+key]
            a = r['attribution']
            rows = e.base.read_rows(directory/f'{c}-false-cells.jsonl')
            assert len(rows) == a['false_cells']
            assert math.isclose(sum(a['cell_equivalents'].values()), a['false_cells'], abs_tol=1e-8)
            assert a['false_cells'] == round(r['original']['occupied_cells']*(1-r['original']['precision_015']))
            for row in rows:
                assert math.isclose(sum(row['shares'].values()), 1., abs_tol=1e-8)
                assert 0 <= row['behind_camera_share'] <= row['shares']['range_projection']+1e-10
            assert all(r['exact_original_grid_and_metrics'] for r in s['conditions'].values())
        # Independently verify every stored optical label against rigid camera
        # transforms at saved qpos (no camera update/dynamics/render pipeline).
        robot = name[-2:]
        geometry = e.SavedGeometry(scene)
        camera = geometry.model.camera(robot+'__robot_cam')
        body = camera.bodyid[0]
        quatrot = np.empty(9)
        geometry.mj.mju_quat2Mat(quatrot, camera.quat)
        fixed = quatrot.reshape(3, 3)@np.diag([1., -1., -1.])
        states = {round(r['t'], 6): r['qpos'] for r in e.base.read_rows(scene.parent/'eval_only/trajectory.jsonl')}
        max_origin, max_rot, count = 0., 0., 0
        for label in e.base.read_rows(scene.parent/f'eval_only/{robot}/camera_labels.jsonl'):
            geometry.at(states[round(label['t'], 6)])
            rb = geometry.data.xmat[body].reshape(3, 3)
            origin, rotation = e.camera_world(label)
            max_origin = max(max_origin, float(np.linalg.norm(geometry.data.xpos[body]+rb@camera.pos-origin)))
            max_rot = max(max_rot, float(np.max(abs(rb@fixed-rotation))))
            count += 1
        assert max_origin < 1e-9 and max_rot < 1e-9
        records.append({'case': name, 'source_hashes': True, 'all_four_original_maps_exact': True,
                        'all_four_gt_maps_rescored': True, 'false_cell_mass_conserved': True, 'representative_phase_maps_attribution_unchanged': True,
                        'camera_labels_checked': count, 'camera_origin_max_difference_m': max_origin,
                        'camera_rotation_max_element_difference': max_rot})
    return records


def tables(summaries):
    text = ['### 20.2 여섯 녹화의 원래 지도와 공통 GT 자세 지도', '',
            '각 칸은 **precision % / 전체 recall % / 가시 recall % / 벽 RMSE m**. GT는 off의 관측 원장과 같은 관측·가중치다.', '',
            '| 녹화 | off | v2 | prob | RBPF100 | GT 자세 (off 관측) |', '|---|---|---|---|---|---|']
    def fmt(q):
        return f'{q["precision_015"]*100:.1f} / {q["wall_coverage"]*100:.1f} / {q["recall_visible"]*100:.1f} / {q["wall_error_rmse_m"]:.3f}'
    for name, s in summaries.items():
        rows = s['conditions']
        text.append('| '+name+' | '+' | '.join([fmt(rows[c]['original']) for c in e.CONDITIONS]+[fmt(rows['off']['matched_gt_pose'])])+' |')
    text += ['', '관측 선택·가중치까지 고정한 **조건별 GT 자세** 결과(같은 단위):', '',
             '| 녹화 | off 관측 | v2 관측 | prob 관측 | RBPF100 최종 입자 관측 |', '|---|---|---|---|---|']
    for name,s in summaries.items():
        text.append('| '+name+' | '+' | '.join(fmt(s['conditions'][c]['matched_gt_pose']) for c in e.CONDITIONS)+' |')
    text += ['', '### 20.3 가시 분모 감사', '',
             '| 녹화 | 전체 표본 | 몸체 가시 | 접점 가시 | 접점 가시 ∩ 4 m | off 삽입 프레임의 접점 가시 | RBPF100 가시 recall 분자/분모 | GT(off) 가시 recall 분자/분모 |',
             '|---|---|---|---|---|---|---|---|']
    for name,s in summaries.items():
        v=s['visibility_counts']; n=v['visible']
        r=s['conditions']['rbpf100']['original']['covered_visible_count']
        g=s['conditions']['off']['matched_gt_pose']['covered_visible_count']
        text.append(f'| {name} | 349 | {n} | {v["contact_visible"]} | {v["contact_near4"]} | {v["contact_admitted"]} | {r}/{n} | {g}/{n} |')
    text += ['', '### 20.4 거짓 점유 셀의 운영적 원인 분해', '',
             '각 행은 **해당 조건·녹화의 최종 거짓 셀**을 분모로 한다. 단위 %. 혼합 띠는 (a)/(c)에 분할했으며 별도 열은 그 불확실한 기여량이다.', '',
             '| 녹화 | 조건 | 거짓 셀 | (a) 거리/투영 | (b) 자세 | (c) 비벽 | (d) 칸 경계 | 판별 불가 | 혼합 띠 기여 | 카메라 뒤 교점 기여(a의 일부) |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for name,s in summaries.items():
        for c in e.CONDITIONS:
            a=s['conditions'][c]['attribution']; n=a['false_cells']
            parts=' | '.join(f'{100*a["fractions"][k]:.1f}' for k in e.CATEGORIES)
            text.append(f'| {name} | {c} | {n} | {parts} | {100*a["mixed_patch_cell_equivalents"]/n:.1f} | {100*a["behind_camera_cell_equivalents"]/n:.1f} |')
    return '\n'.join(text)+'\n'


def figures(source, out, summaries):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    extent = [np.array([[-1.075,-3.175],[5.425,1.475]])]
    for name in CASES:
        for gpath in (e.base.ROOT/'outputs/self-map-prob-rbpf-v1-complete/rbpf100'/name/'grid.json', source/name/'rbpf100-gt-grid.json'):
            extent.append(e.transform(points(load(gpath)), summaries[name]['origin_eval_only']))
    bounds = np.vstack(extent)
    low, high = bounds.min(0)-.2, bounds.max(0)+.2
    fig, axes = plt.subplots(3, 4, figsize=(14, 10), constrained_layout=True)
    for i,seed in enumerate((911,912,913)):
        for j,robot in enumerate(('r1','r2')):
            name=f's{seed}-{robot}'
            s=summaries[name]
            scene=Path(next(f['path'] for f in s['sources'] if f['path'].endswith('scene.xml')))
            walls=[w for w in load(scene.parent/'inputs/static_map.json')['obstacles'] if w.get('kind')=='wall']
            ws=load(source/name/'wall_samples.json');xy=np.array(ws['xy']);visible=np.array(ws['visible'])
            saved=e.base.ROOT/'outputs/self-map-prob-rbpf-v1-complete/rbpf100'/name/'grid.json'
            for k,gpath in enumerate((saved,source/name/'rbpf100-gt-grid.json')):
                ax=axes[i,j*2+k]
                for w in walls:
                    x,y=w['center_m'];hx,hy=w['half_extents_m']
                    ax.add_patch(Rectangle((x-hx,y-hy),2*hx,2*hy,color='gray',alpha=.25))
                ax.scatter(xy[visible,0],xy[visible,1],s=9,c='#267650',label='ever visible')
                pts=e.transform(points(load(gpath)),s['origin_eval_only'])
                ax.scatter(pts[:,0],pts[:,1],s=5,c='#b94232',label='occupied')
                label='RBPF100' if k==0 else 'GT pose, same scans'
                q=s['conditions']['rbpf100']['original' if k==0 else 'matched_gt_pose']
                ax.set(title=f'{name} {label}\nP {q["precision_015"]:.1%}, Rvis {q["recall_visible"]:.1%}',aspect='equal',xlim=(low[0],high[0]),ylim=(low[1],high[1]))
                ax.grid(alpha=.2)
                ax.tick_params(labelsize=7)
                ax.legend(fontsize=6,loc='lower left')
    fig.suptitle('Evaluation only: same selected-particle scans, remove pose error (world metres)')
    fig.savefig(out/'rbpf100-gt-maps.png',dpi=115)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,4),layout='constrained')
    colors=['#d19332','#3979aa','#b94848','#799a64','#777777']
    left=np.zeros(6)
    for category,color in zip(e.CATEGORIES,colors):
        values=np.array([summaries[n]['conditions']['rbpf100']['attribution']['fractions'][category]*100 for n in CASES])
        ax.barh(CASES,values,left=left,label=category,color=color)
        left+=values
    ax.invert_yaxis()
    ax.set(xlim=(0,100),xlabel='Percent of final false occupied cells (surviving log-odds contribution)',title='RBPF100: operational attribution, not unique causal identification')
    ax.legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,-.15),fontsize=8)
    fig.savefig(out/'false-cell-attribution.png',dpi=130)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    verified=verify(args.source)
    args.output.mkdir(parents=True,exist_ok=False)
    summaries={n:load(args.source/n/'summary.json') for n in CASES}
    for name in CASES:
        dest=args.output/name
        dest.mkdir()
        for f in ('summary.json','wall_samples.json'):
            shutil.copyfile(args.source/name/f,dest/f)
        for c in e.CONDITIONS:
            shutil.copyfile(args.source/name/f'{c}-false-cells.jsonl',dest/f'{c}-false-cells.jsonl')
    (args.output/'tables.md').write_text(tables(summaries))
    e.base.dump(args.output/'verification.json',verified)
    figures(args.source,args.output,summaries)
    raw=[p for p in sorted(args.source.rglob('*')) if p.is_file()]
    failed=e.base.ROOT/'outputs/self-map-oracle-diagnostic-v1'
    raw+=[p for p in sorted(failed.rglob('*')) if p.is_file()]
    for old in ('self-map-oracle-diagnostic-v1-complete', 'self-map-oracle-representative-only-report'):
        raw += [p for p in sorted((e.base.ROOT/'outputs'/old).rglob('*')) if p.is_file()]
    raw += [e.base.ROOT/'outputs'/f'self-map-oracle-diagnostic-{v}.log' for v in ('v1','v1-complete','v2-complete')]
    committed=[p for p in sorted(args.output.rglob('*')) if p.is_file()]
    e.base.dump(args.output/'manifest.json',{'replay_source_sha':summaries[CASES[0]]['source_sha'],
        'local_only': [{'path':str(p.resolve()),'bytes':p.stat().st_size,'sha256':e.base.sha(p)} for p in raw],
        'git_artifacts':[{'path':str(p.relative_to(args.output)),'bytes':p.stat().st_size,'sha256':e.base.sha(p)} for p in committed]})
    print('Verified 24 original grids, 24 GT grids, attribution mass and',sum(v['camera_labels_checked'] for v in verified),'camera labels. Published',args.output)


if __name__=='__main__':
    main()
