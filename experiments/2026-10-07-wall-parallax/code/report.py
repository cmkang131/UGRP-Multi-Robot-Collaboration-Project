"""Saved-log failure report; never invokes detector, LK, triangulation or world."""
from collections import Counter
import json
import subprocess
import numpy as np
import common as c
import replay as r


def main():
    assert r.hashes()==c.read(c.EXP/'freeze.json')['hashes']
    results=[]
    summaries=[]
    totals=Counter()
    for case in c.EPISODES:
        result=c.read(c.EXP/'results'/f'{case}.json')
        source=c.OUT/'parallax_v1'/case
        receipt=c.read(source/'receipt.json')
        assert c.sha(source/'predictions.jsonl')==result['predictions_sha256']==receipt['predictions_sha256']
        rows=c.old.base.read_rows(source/'predictions.jsonl')
        assert [x['frame_id'] for x in rows]==c.read(c.EXP/'cohort.json')['cases'][case]['eligible_frames']
        assert all(not x['candidate'] for x in rows)
        assert result['reports']['candidate']['annotated']['all']['recall']==0 and not result['passed']
        # v7 command camera baseline available in the fixed ten-view horizon.
        history=[]
        baselines=[]
        durations=[]
        for row in rows:
            if history:
                p=history[-1]
                same=(p['frame_id']+2==row['frame_id'] and row['t']-p['t']<=.5 and
                      p['origin']==row['origin'] and p['rotation']==row['rotation'])
                if not same:history=[]
            history=(history+[row])[-10:]
            if len(history)<3:continue
            def centre(v):return c.old.transform([v['origin'][:2]],v['pose'])[0]
            baselines.append(float(np.linalg.norm(centre(row)-centre(history[0]))))
            durations.append(row['t']-history[0]['t'])
        summaries.append(dict(case=case,command_window_baseline_m=r.stats(baselines),
            command_window_seconds=r.stats(durations),baseline_at_least_004m=sum(b>=.04 for b in baselines),
            windows=len(baselines),counts=result['counts']))
        totals.update(result['counts'])
        results.append(result)
        if case in c.old.EPISODES:
            original=c.read(c.ROOT/f'experiments/2026-10-07-wall-floor-boundary/results/off/{case}.json')['all_points']['all']
            current=result['reports']['baseline']['points']['all']
            assert current['n']==original['predicted']
            assert abs(current['precision']-original['metric_precision'])<1e-12
    c.dump(c.EXP/'results/diagnosis.json',dict(cases=summaries,total_event_counts=dict(totals),
        note='Events repeat the same track over time; command windows are available baselines, not actual tracked pairs'))
    table=['# 동일 eligible 프레임 비교','',
        '| 녹화 | eligible | 바닥 P | 바닥 R¹ | 바닥 중앙/P90/RMSE m | 시차 점 | 시차 P / R¹ | 시차 오차 | 주석 분모 |',
        '|---|---:|---:|---:|---|---:|---|---|---:|']
    for result in results:
        b=result['reports']['baseline']['points']['all']
        a=result['reports']['baseline']['annotated']['all']
        q=result['reports']['candidate']['annotated']['all']
        table.append(f"| {result['case']} | {result['frames']} | {b['precision']:.2%} | {a['recall']:.2%} | "
                     f"{b['median']:.3f}/{b['p90']:.3f}/{b['rmse']:.3f} | 0 | NA / 0% | NA | {q['positive']} |")
    table.extend(['','¹ R은 봉인된 주석6프레임의 가시 접점/96열 분모다. P는 모든 eligible 프레임의 metric point precision.',
                  '주석 frame precision·거리별 P/R은 각 case JSON에 별도 보존. 시차 무검출을 오차0 또는 precision100%로 바꾸지 않음.'])
    (c.EXP/'results/table.md').write_text('\n'.join(table)+'\n')
    manifest=[dict(path=str(p.relative_to(c.OUT)),bytes=p.stat().st_size,sha256=c.sha(p))
              for p in sorted(c.OUT.rglob('*')) if p.is_file()]
    c.dump(c.EXP/'results/raw-manifest.json',dict(root=str(c.OUT),files=manifest))
    c.dump(c.EXP/'results/verification.json',dict(frozen_hashes_unchanged=True,frozen_files=len(r.hashes()),
        recordings=len(results),eligible_frames=sum(q['frames'] for q in results),accepted_points=0,
        gates_passed=0,legacy_s1042_s1047_point_precision_exact=True,prediction_receipts_verified=8,
        annotation_frames=48,physics=0,model_calls=0,map_replays=0,
        raw_files=len(manifest),raw_bytes=sum(p['bytes'] for p in manifest)))
    plot(summaries)
    print(json.dumps(dict(events=dict(totals),baseline_windows=summaries,raw_files=len(manifest),
                          raw_bytes=sum(p['bytes'] for p in manifest)),indent=2))


def plot(rows):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    names=['zero_baseline','low_parallax','reprojection','behind_camera','lk_failure','outside_wall_roi','insufficient_views']
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    y=np.arange(len(rows))
    bottom=np.zeros(len(rows))
    for key in names:
        values=np.array([r['counts'].get(key,0) for r in rows])
        axes[0].barh(y,values,left=bottom,label=key)
        bottom+=values
    axes[0].set(yticks=y,yticklabels=[r['case'] for r in rows],xlabel='Track update / rejection events',
                title='No accepted wall points (all 8 recordings)')
    axes[0].legend(fontsize=7,loc='upper right')
    x=np.arange(len(rows))
    axes[1].bar(x,[r['command_window_baseline_m']['p90']*100 for r in rows],color='#517da3',label='P90')
    axes[1].scatter(x,[r['command_window_baseline_m']['median']*100 for r in rows],color='#222222',label='Median')
    axes[1].axhline(4,ls='--',color='#b54338',label='~1.15 deg at 2 m, transverse baseline')
    axes[1].set(xticks=x,xticklabels=[r['case'] for r in rows],ylabel='Command camera baseline (cm)',
                title='Available baseline in fixed 10-view window',ylim=(0,58))
    axes[1].tick_params(axis='x',rotation=45)
    axes[1].legend(fontsize=7)
    path=c.EXP/'figures/failure-diagnosis.png'
    path.parent.mkdir(exist_ok=True)
    fig.savefig(path,dpi=150)
    plt.close(fig)


if __name__=='__main__':main()
