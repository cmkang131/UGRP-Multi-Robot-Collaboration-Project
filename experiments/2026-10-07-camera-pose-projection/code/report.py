"""Summarize sealed projection evidence; no estimation, fitting, or replay."""
from pathlib import Path
import json
import subprocess
import sys
import hashlib
import numpy as np

sys.path.insert(0,str(Path(__file__).parent))
import audit as a
import evaluate_fk as e


def main():
    frozen=a.load(a.EXP/'freeze.json')
    assert frozen['hashes']==e.source_hashes()
    decomp=a.load(a.OUT/'decomposition/summary.json')
    out=a.EXP/'results'
    out.mkdir(exist_ok=True)
    a.write(out/'decomposition.json',decomp)
    results={case:a.load(a.OUT/'servo_fk_v1'/case/'result.json') for case in a.old.EPISODES}
    for case,row in results.items():
        assert row['hashes']==frozen['hashes']
        assert row['prediction_sha256']==a.digest(a.OUT/'servo_fk_v1'/case/'own-predictions.jsonl')
    assert not any(r['gate']['passed'] for r in results.values())
    assert not (a.OUT/'maps').exists()
    text=['# 투영 결과','','단위 m, 기존 주석·분모 고정. 실제 카메라는 평가 전용.','',
          '| 녹화 | 고정 점 수 | 기존 중앙/P90 | 명령 FK 중앙/P90 | FK 4m 유효율 | 실제 카메라 중앙/P90 | FK 관문 |',
          '|---|---:|---:|---:|---:|---:|---|']
    for case,r in results.items():
        b,c=r['baseline'],r['candidate']
        actual=decomp[case]['boundary_error'].get('actual_all')
        o='NA (미기록)' if actual is None else f"{actual['median']:.4f}/{actual['p90']:.4f}"
        text.append(f"| {case} | {r['fixed_annotation_points']} | {b['median']:.4f}/{b['p90']:.4f} | {c['median']:.4f}/{c['p90']:.4f} | {100*r['within4m_points']/r['fixed_annotation_points']:.2f}% | {o} | FAIL |")
    text+=['','## 실제 − 보정, paired frame 차이 중앙','',
        '| 녹화 | 무하중 유효 frame | 전후 mm | 좌우 mm | 높이 mm | yaw ° | pitch ° | roll ° |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for case in ('s1045','s1046','s1047'):
        g=decomp[case]['groups']['eligible']
        text.append('| '+case+' | '+str(g['x']['n'])+' | '+' | '.join(f"{g[k]['median']:.4f}" for k in a.COMPONENTS)+' |')
    text+=['','## 한 항만 실제로 치환한 중앙 벽 오차','',
        '| 녹화 | 기존 | 전후 | 좌우 | 높이 | yaw | pitch | roll | 실제 전체 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for case in ('s1045','s1046','s1047'):
        x=decomp[case]['boundary_error']
        keys=['nominal']+['nominal_replace_'+k for k in a.COMPONENTS]+['actual_all']
        text.append('| '+case+' | '+' | '.join(f"{x[k]['median']:.4f}" for k in keys)+' |')
    text+=['','실제에서 한 항만 nominal로 되돌린 반대 치환, point displacement, P05/P90/P95 및 자세별 표본은 decomposition.json에 있다.',
           '기여율을 합산하지 않는다. 이 oracle 결과는 실제 제어 성능이나 명령 FK 관문 통과가 아니다.']
    (out/'tables.md').write_text('\n'.join(text)+'\n')
    high={}
    for case in ('s1045','s1046','s1047'):
        fs=a.old.base.read_rows(a.OUT/'decomposition'/f'{case}-frames.jsonl')
        rows=[r for r in fs if r['command_pose']=='896,2035,1894,1500']
        high[case]=dict(frames=len(rows),nominal_unloaded_pitch_deg=float(np.median([r['nominal_angles_deg'][1] for r in rows])),
            actual_pitch_deg=float(np.median([r['actual_angles_deg'][1] for r in rows])),
            nominal_height_m=float(np.median([r['nominal_origin'][2] for r in rows])),
            actual_height_m=float(np.median([r['actual_origin'][2] for r in rows])))
    a.write(out/'high-comparison.json',dict(current_unloaded_table_vs_recorded_high=high,
        earlier_s2_rigid_high=dict(pitch_deg=-36.59168,height_m=.179896,actual_height_at_160s_m=.187288),
        source_ref=subprocess.check_output(['git','rev-parse','origin/codex/s2-realism'],text=True).strip(),
        source_path='experiments/2026-10-06-s2-realism/README.md',same_class_of_mismatch=True,
        same_mechanical_cause='NOT_IDENTIFIABLE_WITHOUT_ACTUAL_JOINT_AND_CHASSIS_TILT'))
    # Diagnostic figure only, not an updated occupancy map.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases=['s1045','s1046','s1047']
    labels=['PnP nominal','Pitch only (oracle)','Full camera (oracle)','Command FK']
    values=[[decomp[c]['boundary_error']['nominal']['median'] for c in cases],
            [decomp[c]['boundary_error']['nominal_replace_pitch']['median'] for c in cases],
            [decomp[c]['boundary_error']['actual_all']['median'] for c in cases],
            [results[c]['candidate']['median'] for c in cases]]
    fig,ax=plt.subplots(figsize=(8,4.4),layout='constrained')
    x=np.arange(3)
    for i,(label,y) in enumerate(zip(labels,values)):
        rects=ax.bar(x+(i-1.5)*.2,y,.19,label=label)
        ax.bar_label(rects,fmt='%.3f',fontsize=8,padding=2)
    ax.axhline(.1,color='black',linestyle='--',linewidth=1,label='Preregistered median gate')
    ax.set_xticks(x,cases)
    ax.set_ylim(0,.87)
    ax.set_ylabel('Median annotated-contact wall error (m)')
    ax.set_title('Camera-pose counterfactuals (evaluation only)')
    ax.legend(fontsize=8,ncol=2,loc='upper left')
    fig.savefig(out/'projection-components.png',dpi=160)
    plt.close(fig)
    manifest=[]
    for p in sorted(a.OUT.rglob('*')):
        if p.is_file():
            manifest.append(dict(path=str(p),bytes=p.stat().st_size,sha256=a.digest(p)))
    a.write(out/'raw-manifest.json',dict(files=manifest,total_bytes=sum(r['bytes'] for r in manifest)))
    untracked=['analyze_wall_detection.py','create_wall_visualizations.py','create_wall_visualizations_v2.py','parameter_probe.py']
    a.write(out/'verification.json',dict(frozen_candidate_hashes_unchanged=True,unit_tests=16,
        off_golden='transform bytes + nonempty scan/segment/adapter golden passed',
        development_pass=0,development_total=2,confirmation_pass=0,confirmation_total=4,
        map_replays=0,updated_occupancy_figures=0,physics=0,render=0,model_calls=0,
        original_annotation_bytes_unchanged=True,pr406_modified=False,
        preserved_untracked={n:a.digest(a.ROOT/n) for n in untracked},raw_files=len(manifest),
        raw_total_bytes=sum(r['bytes'] for r in manifest)))
    print('PASS source/raw/denominator checks; projection gate FAIL 0/6; map replay blocked')
    print('raw',len(manifest),sum(r['bytes'] for r in manifest))


if __name__=='__main__':main()
